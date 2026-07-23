//! Arkhe: an ontology language for AI systems.
//!
//! This crate is the Rust port of the Arkhe validator (ADR 0008, item 4). It
//! loads an `.arkhe.yaml` module, validates it structurally against the
//! arkhe-0.1 metamodel, then runs the semantic passes, and reports findings.
//! Conformance is defined by the frozen v0.1 golden fixtures.
//!
//! Not yet ported: CEL guard analysis. Guard, approval-`when`, and invariant
//! `check` expressions are left unchecked, so no `guard-*` finding is ever
//! emitted. See BUILD_NOTES.md for the CEL milestone and the list of
//! guard-dependent conformance cases this affects.
//!
//! ```no_run
//! let result = arkhelang::validate_file("model-risk.arkhe.yaml")?;
//! if result.ok() {
//!     println!("valid");
//! }
//! # Ok::<(), arkhelang::Error>(())
//! ```

mod loader;
mod schema;
mod semantic;

pub mod finding;
pub mod model;
pub mod value;

pub use finding::{Finding, ValidationResult};
pub use value::Value;

use std::path::Path;

/// The version of this crate.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Errors that stop validation before it can produce findings. Only genuine
/// I/O failures land here; malformed YAML, bad encodings, and every structural
/// or semantic problem are reported as findings instead.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("cannot read {path}: {source}")]
    Io {
        path: String,
        #[source]
        source: std::io::Error,
    },
}

/// Validate a module file. Returns an [`Error`] only if the file cannot be
/// read; everything else is a [`ValidationResult`] carrying findings.
pub fn validate_file(path: impl AsRef<Path>) -> Result<ValidationResult, Error> {
    let path = path.as_ref();
    let bytes = std::fs::read(path).map_err(|source| Error::Io {
        path: path.display().to_string(),
        source,
    })?;

    let text = match String::from_utf8(bytes) {
        Ok(text) => text,
        Err(err) => {
            return Ok(ValidationResult::new(vec![Finding::yaml_file(format!(
                "not readable as UTF-8 text: {err}"
            ))]))
        }
    };

    Ok(validate_text(&text))
}

/// Validate module text (already read and UTF-8 decoded).
pub fn validate_text(text: &str) -> ValidationResult {
    let (value, positions) = match loader::load(text) {
        loader::LoadOutcome::Loaded { value, positions } => (value, positions),
        loader::LoadOutcome::Finding(finding) => {
            return ValidationResult::new(vec![finding]);
        }
    };

    if !value.is_mapping() {
        return ValidationResult::new(vec![Finding::yaml_file("document is not a mapping")]);
    }

    let mut result = validate_value(&value);
    loader::attach_positions(&mut result.findings, &positions);
    result
}

/// Validate an already-parsed document value: structure first, then semantics.
/// Semantic checks need a well-formed document, so they run only when the
/// structural pass is clean (mirrors the reference).
pub fn validate_value(doc: &Value) -> ValidationResult {
    let struct_findings = schema::validate(doc);
    if !struct_findings.is_empty() {
        return ValidationResult::new(struct_findings);
    }
    let module = model::build(doc);
    ValidationResult::new(semantic::validate(&module))
}
