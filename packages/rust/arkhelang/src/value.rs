//! A small, self-contained YAML value model.
//!
//! Decoupled from the parser crate so the rest of the validator never depends
//! on `yaml-rust2` types directly. Mapping keys are always strings (every key
//! in an Arkhe module is a string); non-string keys are stringified on the way
//! in so a malformed document degrades rather than panics.
//!
//! Scalar typing (null / bool / int / real / string) is taken from the parser
//! rather than re-resolved here, which keeps YAML's core-schema rules
//! (a bare `0.1.0` is a string, a bare `2` is an integer) exactly as the
//! reference implementation sees them.

use yaml_rust2::Yaml;

/// A parsed YAML value. `Mapping` preserves declaration order, which several
/// semantic checks depend on (name-collision resolution walks members in the
/// order they were written).
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum Value {
    Null,
    Bool(bool),
    Int(i64),
    /// A YAML real, kept in its source string form so the value stays `Eq`/`Hash`.
    Real(String),
    String(String),
    Array(Vec<Value>),
    Mapping(Vec<(String, Value)>),
}

impl Value {
    pub fn as_str(&self) -> Option<&str> {
        match self {
            Value::String(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Value::Bool(b) => Some(*b),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&[Value]> {
        match self {
            Value::Array(a) => Some(a),
            _ => None,
        }
    }

    pub fn as_mapping(&self) -> Option<&[(String, Value)]> {
        match self {
            Value::Mapping(m) => Some(m),
            _ => None,
        }
    }

    pub fn is_mapping(&self) -> bool {
        matches!(self, Value::Mapping(_))
    }

    /// Look up a key in a mapping; `None` for non-mappings or absent keys.
    pub fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Value::Mapping(m) => m.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }

    pub fn contains_key(&self, key: &str) -> bool {
        self.get(key).is_some()
    }
}

/// Convert a `yaml-rust2` value into our model.
pub fn from_yaml(y: &Yaml) -> Value {
    match y {
        Yaml::Null => Value::Null,
        Yaml::Boolean(b) => Value::Bool(*b),
        Yaml::Integer(i) => Value::Int(*i),
        Yaml::Real(s) => Value::Real(s.clone()),
        Yaml::String(s) => Value::String(s.clone()),
        Yaml::Array(a) => Value::Array(a.iter().map(from_yaml).collect()),
        Yaml::Hash(h) => Value::Mapping(
            h.iter()
                .map(|(k, v)| (key_to_string(k), from_yaml(v)))
                .collect(),
        ),
        // Anchors/aliases are outside the v0.1 surface; treat as null rather
        // than panic. A real module never reaches these arms.
        Yaml::Alias(_) => Value::Null,
        Yaml::BadValue => Value::Null,
    }
}

fn key_to_string(y: &Yaml) -> String {
    match y {
        Yaml::String(s) => s.clone(),
        Yaml::Integer(i) => i.to_string(),
        Yaml::Boolean(b) => b.to_string(),
        Yaml::Real(s) => s.clone(),
        _ => String::new(),
    }
}
