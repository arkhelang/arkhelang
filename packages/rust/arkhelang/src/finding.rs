//! Findings and results.
//!
//! The JSON shape mirrors the Python reference (`validate.py`): a `Finding`
//! serialises to `{code, path, message, line, column}` in that field order,
//! with `line`/`column` null when unknown; a `Result` serialises to
//! `{ok, findings}`. `to_json` matches `json.dumps(..., indent=2)` layout.

use serde::Serialize;

/// One validator finding. `code` is stable (`struct`, `key-ref`, ...); `path`
/// is a document path with `/` separators; `line`/`column` are 1-based source
/// positions when the loader could supply them.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Finding {
    pub code: String,
    pub path: String,
    pub message: String,
    pub line: Option<usize>,
    pub column: Option<usize>,
}

impl Finding {
    pub fn new(code: &str, path: &str, message: impl Into<String>) -> Self {
        Finding {
            code: code.to_string(),
            path: path.to_string(),
            message: message.into(),
            line: None,
            column: None,
        }
    }

    /// A `yaml` finding anchored at the whole file, used for parse failures,
    /// non-UTF-8 input, duplicate keys, and non-mapping documents.
    pub fn yaml_file(message: impl Into<String>) -> Self {
        Finding::new("yaml", "(file)", message)
    }
}

/// The outcome of validating one module.
#[derive(Debug, Clone)]
pub struct ValidationResult {
    pub findings: Vec<Finding>,
}

impl ValidationResult {
    pub fn new(findings: Vec<Finding>) -> Self {
        ValidationResult { findings }
    }

    pub fn ok(&self) -> bool {
        self.findings.is_empty()
    }

    /// Serialise to the reference `{ok, findings}` JSON, two-space indented.
    pub fn to_json(&self) -> String {
        #[derive(Serialize)]
        struct Out<'a> {
            ok: bool,
            findings: &'a [Finding],
        }
        let out = Out {
            ok: self.ok(),
            findings: &self.findings,
        };
        // `serde_json` never fails to serialise this shape; fall back to an
        // empty object rather than unwrapping in library code.
        serde_json::to_string_pretty(&out).unwrap_or_else(|_| "{}".to_string())
    }
}
