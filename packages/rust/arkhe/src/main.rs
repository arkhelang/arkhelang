//! The `arkhe` command-line interface (Rust port).
//!
//! v0.1 surface implemented here: `arkhe validate <path> [--json]`.
//! Exit codes match the Python CLI contract: 0 valid, 1 invalid, 2 usage or
//! unreadable input.
//!
//! `contracts` and `emit` are out of scope for the port's first cut (the
//! emitters are not ported); invoking them prints a short notice and exits 2.

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use arkhelang::{validate_file, Error, ValidationResult, VERSION};

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match run(&args) {
        Ok(code) => code,
        Err(message) => {
            eprintln!("arkhe: {message}");
            ExitCode::from(2)
        }
    }
}

fn run(args: &[String]) -> Result<ExitCode, String> {
    if args.is_empty() {
        print_help();
        return Ok(ExitCode::from(0));
    }
    if args.iter().any(|a| a == "-V" || a == "--version") {
        println!("arkhe {VERSION}");
        return Ok(ExitCode::from(0));
    }

    match args[0].as_str() {
        "validate" => cmd_validate(&args[1..]),
        "contracts" | "emit" => {
            Err(format!("'{}' is not available in the Rust port yet", args[0]))
        }
        other => Err(format!("unknown command '{other}'")),
    }
}

fn cmd_validate(args: &[String]) -> Result<ExitCode, String> {
    let mut json = false;
    let mut target: Option<String> = None;
    for arg in args {
        match arg.as_str() {
            "--json" => json = true,
            _ if arg.starts_with('-') => return Err(format!("unknown option '{arg}'")),
            _ => {
                if target.is_some() {
                    return Err("validate takes a single path".to_string());
                }
                target = Some(arg.clone());
            }
        }
    }
    let target = target.ok_or_else(|| "validate needs a path".to_string())?;
    let path = Path::new(&target);

    let files = if path.is_dir() {
        let mut found = Vec::new();
        collect_modules(path, &mut found);
        found.sort();
        if found.is_empty() {
            return Err(format!("no .arkhe.yaml modules under {}", path.display()));
        }
        found
    } else {
        vec![path.to_path_buf()]
    };

    println!("arkhe {VERSION} validate");
    println!();

    let mut results: Vec<(PathBuf, ValidationResult)> = Vec::new();
    for file in files {
        match validate_file(&file) {
            Ok(result) => results.push((file, result)),
            Err(Error::Io { path, source }) => {
                return Err(format!("cannot read {path}: {source}"));
            }
        }
    }

    if json {
        print_json(&results);
        let all_ok = results.iter().all(|(_, r)| r.ok());
        return Ok(ExitCode::from(if all_ok { 0 } else { 1 }));
    }

    for (file, result) in &results {
        if !result.ok() {
            print_findings(file, result);
        }
    }
    if results.iter().any(|(_, r)| !r.ok()) {
        println!();
    }

    let width = results
        .iter()
        .map(|(p, _)| p.display().to_string().len())
        .max()
        .unwrap_or(6)
        .max("module".len());
    println!("  {:<width$}  findings  status", "module", width = width);
    for (file, result) in &results {
        let n = result.findings.len();
        let status = if result.ok() { "valid" } else { "INVALID" };
        println!(
            "  {:<width$}  {:>8}  {}",
            file.display().to_string(),
            n,
            status,
            width = width
        );
    }
    let valid = results.iter().filter(|(_, r)| r.ok()).count();
    let invalid = results.len() - valid;
    println!();
    let plural = if results.len() == 1 { "" } else { "s" };
    println!(
        "  {} module{}: {} valid, {} invalid",
        results.len(),
        plural,
        valid,
        invalid
    );
    Ok(ExitCode::from(if invalid == 0 { 0 } else { 1 }))
}

fn collect_modules(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_modules(&path, out);
        } else if path.to_string_lossy().ends_with(".arkhe.yaml") {
            out.push(path);
        }
    }
}

fn print_findings(file: &Path, result: &ValidationResult) {
    for f in &result.findings {
        let where_ = match (f.line, f.column) {
            (Some(line), Some(col)) => format!("{}:{}:{}", file.display(), line, col),
            _ => file.display().to_string(),
        };
        println!("  {}: [{}] {}: {}", where_, f.code, f.path, f.message);
    }
}

fn print_json(results: &[(PathBuf, ValidationResult)]) {
    // Mirrors the reference CLI: an object keyed by path string, each value the
    // module's `{ok, findings}` result. Built by hand to keep the per-path
    // wrapper without another serialisation type.
    let mut out = String::from("{\n");
    for (i, (file, result)) in results.iter().enumerate() {
        let key = json_string(&file.display().to_string());
        let body = indent(&result.to_json(), 2);
        out.push_str(&format!("  {key}: {body}"));
        if i + 1 < results.len() {
            out.push(',');
        }
        out.push('\n');
    }
    out.push('}');
    println!("{out}");
}

fn indent(s: &str, spaces: usize) -> String {
    let pad = " ".repeat(spaces);
    let mut lines = s.lines();
    let mut out = String::new();
    if let Some(first) = lines.next() {
        out.push_str(first);
    }
    for line in lines {
        out.push('\n');
        out.push_str(&pad);
        out.push_str(line);
    }
    out
}

fn json_string(s: &str) -> String {
    let mut out = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\t' => out.push_str("\\t"),
            '\r' => out.push_str("\\r"),
            _ => out.push(c),
        }
    }
    out.push('"');
    out
}

fn print_help() {
    println!("arkhe {VERSION}: an ontology language for AI systems.");
    println!();
    println!("usage:");
    println!("  arkhe validate <module.arkhe.yaml | dir> [--json]");
    println!();
    println!("exit codes:");
    println!("  0  the module is valid");
    println!("  1  the module is invalid (findings printed)");
    println!("  2  usage error or unreadable input");
    println!();
    println!("finding codes:");
    println!("  yaml               the file is not parseable YAML (duplicate keys included)");
    println!("  struct             structural: the module does not match the v0.1 schema");
    println!("  key-ref, key-type  entity keys must be declared, required, non-state properties");
    println!("  state-initial      a state's initial value must be among its declared values");
    println!("  link-ref           link endpoints must be declared entities");
    println!("  name-collision     traversal and property names must not collide");
    println!("  action-ref         action targets and authorities must be declared");
    println!("  effect-*           effect path, value, cardinality, and duplicate rules");
    println!("  synonym-*          synonyms are non-empty, unique, and free of name clashes");
    println!();
    println!("note: CEL guard checks (guard-*) are not yet implemented in this port.");
}
