//! YAML loading: a value tree, source positions, and duplicate-key rejection.
//!
//! Two passes over the same text:
//!
//! 1. The high-level `YamlLoader` produces the value tree. This is the stable,
//!    well-exercised path and it drives structural and semantic conformance;
//!    it also resolves scalar types correctly (YAML core schema), which a
//!    hand-rolled event reconstruction would risk getting wrong.
//! 2. A marked event pass builds a path -> (line, column) index and detects
//!    duplicate mapping keys. The high-level loader silently keeps the last of
//!    a duplicated key, so duplicate detection has to run at the event level.
//!
//! The reference implementation (`validate.py`) treats a duplicate key as a
//! `yaml` finding via a strict loader, and attaches source positions from a
//! separate `yaml.compose` walk. This module mirrors both.
//!
//! Verify items (author was compiling-blind; see BUILD_NOTES.md):
//!   - `yaml_rust2::parser::{Parser, Event, MarkedEventReceiver}` names/paths.
//!   - `Event` variant shapes (`Scalar`, `MappingStart`, `SequenceStart` carry
//!     extra anchor/tag fields that are matched with `..` here).
//!   - `yaml_rust2::scanner::Marker` accessors `line()` (1-based) and `col()`
//!     (0-based); the +1 on the column matches the reference's `column + 1`.
//!   - `Parser::new(chars)` and `Parser::load(&mut recv, multi)` signatures.

use std::collections::{HashMap, HashSet};

use yaml_rust2::parser::{Event, MarkedEventReceiver, Parser};
use yaml_rust2::scanner::Marker;
use yaml_rust2::YamlLoader;

use crate::finding::Finding;
use crate::value::{from_yaml, Value};

/// Path -> 1-based (line, column). Keys are the document path split into
/// segments (sequence indices are their decimal strings), matching the
/// reference's tuple-keyed index.
pub type Positions = HashMap<Vec<String>, (usize, usize)>;

/// A loaded module, or a single `yaml` finding if it could not be loaded.
pub enum LoadOutcome {
    Loaded { value: Value, positions: Positions },
    Finding(Finding),
}

/// Load YAML text into a value tree plus a source-position index, rejecting
/// duplicate keys as a `yaml` finding.
pub fn load(text: &str) -> LoadOutcome {
    // Pass 2 first: a duplicate key is a load failure in the reference, so it
    // must win over anything the value tree might yield.
    let (dup, positions) = scan(text);
    if let Some(finding) = dup {
        return LoadOutcome::Finding(finding);
    }

    // Pass 1: the value tree (and syntax errors).
    let docs = match YamlLoader::load_from_str(text) {
        Ok(docs) => docs,
        Err(err) => {
            return LoadOutcome::Finding(Finding::yaml_file(format!(
                "not parseable as YAML: {err}"
            )))
        }
    };

    let value = match docs.first() {
        Some(y) => from_yaml(y),
        // An empty document is not a mapping; mirror the reference message.
        None => {
            return LoadOutcome::Finding(Finding::yaml_file("document is not a mapping"))
        }
    };

    LoadOutcome::Loaded { value, positions }
}

/// Attach the closest known source position to each finding, walking the path
/// upward until a prefix is found. Mirrors `_locate` in the reference.
pub fn attach_positions(findings: &mut [Finding], positions: &Positions) {
    if positions.is_empty() {
        return;
    }
    for f in findings.iter_mut() {
        if f.path == "(root)" || f.path == "(file)" {
            if let Some(&(line, col)) = positions.get(&Vec::<String>::new()) {
                f.line = Some(line);
                f.column = Some(col);
            }
            continue;
        }
        let mut segs: Vec<String> = f.path.split('/').map(str::to_string).collect();
        while !segs.is_empty() && !positions.contains_key(&segs) {
            segs.pop();
        }
        if let Some(&(line, col)) = positions.get(&segs) {
            f.line = Some(line);
            f.column = Some(col);
        }
    }
}

// --- marked event pass ------------------------------------------------------

enum Frame {
    Map { expect_key: bool, seen: HashSet<String> },
    Seq { idx: usize },
}

struct Scan {
    stack: Vec<Frame>,
    path: Vec<String>,
    positions: Positions,
    dup: Option<(String, usize)>,
    // A merge key (`<<`) and its 1-based (line, column), if one was seen.
    merge: Option<(usize, usize)>,
}

impl Scan {
    fn new() -> Self {
        Scan {
            stack: Vec::new(),
            path: Vec::new(),
            positions: HashMap::new(),
            dup: None,
            merge: None,
        }
    }

    /// Record the position of a node that is beginning. A mapping value's
    /// position was already recorded against its key (the reference lets the
    /// key mark win); a sequence item takes the item's own mark; the root
    /// takes the document mark.
    fn begin_node(&mut self, line: usize, col: usize) {
        match self.stack.last_mut() {
            None => {
                self.positions.entry(Vec::new()).or_insert((line, col));
            }
            Some(Frame::Seq { idx }) => {
                let i = *idx;
                self.path.push(i.to_string());
                self.positions.insert(self.path.clone(), (line, col));
            }
            Some(Frame::Map { .. }) => {
                // Map value: key already pushed and positioned. Nothing to do.
            }
        }
    }

    /// Close a value/item once it has fully arrived, restoring the path.
    fn end_node(&mut self) {
        match self.stack.last_mut() {
            None => {}
            Some(Frame::Seq { idx }) => {
                self.path.pop();
                *idx += 1;
            }
            Some(Frame::Map { expect_key, .. }) => {
                self.path.pop();
                *expect_key = true;
            }
        }
    }
}

impl MarkedEventReceiver for Scan {
    fn on_event(&mut self, ev: Event, mark: Marker) {
        let line = mark.line();
        let col = mark.col() + 1;
        match ev {
            Event::MappingStart(..) => {
                self.begin_node(line, col);
                self.stack.push(Frame::Map {
                    expect_key: true,
                    seen: HashSet::new(),
                });
            }
            Event::MappingEnd => {
                self.stack.pop();
                self.end_node();
            }
            Event::SequenceStart(..) => {
                self.begin_node(line, col);
                self.stack.push(Frame::Seq { idx: 0 });
            }
            Event::SequenceEnd => {
                self.stack.pop();
                self.end_node();
            }
            Event::Scalar(text, ..) => {
                let is_key = matches!(
                    self.stack.last(),
                    Some(Frame::Map { expect_key: true, .. })
                );
                if is_key {
                    // A merge key is not part of the Arkhe YAML surface (D2). The
                    // low-level parser reports `<<` as a plain scalar key; catch
                    // it here, mirroring the reference's document-level finding.
                    if text == "<<" && self.merge.is_none() {
                        self.merge = Some((line, col));
                    }
                    if let Some(Frame::Map { expect_key, seen }) = self.stack.last_mut() {
                        if !seen.insert(text.clone()) && self.dup.is_none() {
                            self.dup = Some((text.clone(), line));
                        }
                        *expect_key = false;
                    }
                    self.path.push(text);
                    self.positions.insert(self.path.clone(), (line, col));
                } else {
                    self.begin_node(line, col);
                    self.end_node();
                }
            }
            _ => {}
        }
    }
}

fn scan(text: &str) -> (Option<Finding>, Positions) {
    let mut scan = Scan::new();
    let mut parser = Parser::new(text.chars());
    if parser.load(&mut scan, false).is_err() {
        // A syntax error is reported by the high-level pass instead; here we
        // simply have no positions and no duplicate to report.
        return (None, HashMap::new());
    }
    // A merge key is a distinct, clearly-worded finding (D2); it wins over the
    // duplicate-key message when both are present. Both are load failures.
    if let Some((line, col)) = scan.merge {
        let mut finding =
            Finding::yaml_file("merge keys (<<) are not part of the Arkhe YAML surface");
        finding.line = Some(line);
        finding.column = Some(col);
        return (Some(finding), scan.positions);
    }
    let dup = scan.dup.map(|(key, line)| {
        Finding::yaml_file(format!("not parseable as YAML: duplicate key '{key}' at line {line}"))
    });
    (dup, scan.positions)
}
