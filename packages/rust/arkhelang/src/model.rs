//! In-memory model of an Arkhe module, built from a validated value tree.
//!
//! Mirrors `model.py`. Assumes the document already passed structural
//! validation, so required fields are present and well-typed; accessors fall
//! back to sensible defaults rather than panic if that assumption is broken.
//!
//! Maps preserve declaration order (`Vec` of pairs), which the name-collision
//! and synonym passes depend on.

use crate::value::Value;

/// An ordered string-keyed map, preserving declaration order.
#[derive(Debug, Clone, Default)]
pub struct Omap<V> {
    entries: Vec<(String, V)>,
}

impl<V> Omap<V> {
    pub fn new() -> Self {
        Omap { entries: Vec::new() }
    }

    pub fn insert(&mut self, key: String, value: V) {
        self.entries.push((key, value));
    }

    pub fn get(&self, key: &str) -> Option<&V> {
        self.entries.iter().find(|(k, _)| k == key).map(|(_, v)| v)
    }

    pub fn contains_key(&self, key: &str) -> bool {
        self.entries.iter().any(|(k, _)| k == key)
    }

    pub fn keys(&self) -> impl Iterator<Item = &str> {
        self.entries.iter().map(|(k, _)| k.as_str())
    }

    pub fn values(&self) -> impl Iterator<Item = &V> {
        self.entries.iter().map(|(_, v)| v)
    }
}

#[derive(Debug, Clone)]
pub struct Property {
    pub name: String,
    pub ty: String,
    pub values: Option<Vec<Value>>,
    pub initial: Option<Value>,
    pub optional: bool,
    pub synonyms: Vec<String>,
}

impl Property {
    pub fn is_state(&self) -> bool {
        self.ty == "state"
    }
}

#[derive(Debug, Clone)]
pub struct Entity {
    pub name: String,
    pub keys: Vec<String>,
    pub properties: Omap<Property>,
    pub synonyms: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct Link {
    pub name: String,
    pub from_entity: String,
    pub to_entity: String,
    pub cardinality: String,
    pub reverse: Option<String>,
    pub properties: Omap<Property>,
    pub synonyms: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct Approval {
    pub when: String,
    pub authority: String,
}

#[derive(Debug, Clone)]
pub struct Action {
    pub name: String,
    pub target: String,
    pub guard: String,
    pub authority: String,
    pub audit: String,
    pub effects: Vec<(String, Value)>,
    pub parameters: Omap<Property>,
    pub approval: Option<Approval>,
    pub synonyms: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct Invariant {
    pub name: String,
    pub over: String,
    pub check: String,
}

#[derive(Debug, Clone)]
pub struct Module {
    pub name: String,
    pub version: String,
    pub arkhe: String,
    pub roles: Vec<String>,
    pub entities: Omap<Entity>,
    pub links: Omap<Link>,
    pub actions: Omap<Action>,
    pub invariants: Omap<Invariant>,
}

impl Module {
    /// Map of traversal name -> (far entity name, link name), from this entity.
    /// Forward link names traverse from `from_entity`; declared reverse names
    /// traverse from `to_entity`.
    pub fn traversal_info<'a>(&'a self, entity_name: &str) -> Vec<(String, String, &'a Link)> {
        let mut out = Vec::new();
        for link in self.links.values() {
            if link.from_entity == entity_name {
                out.push((link.name.clone(), link.to_entity.clone(), link));
            }
            if let Some(rev) = &link.reverse {
                if link.to_entity == entity_name {
                    out.push((rev.clone(), link.from_entity.clone(), link));
                }
            }
        }
        out
    }
}

/// Parse a `synonyms` annotation into its list of labels, keeping empty labels
/// so the validator can flag them. Mirrors `parse_synonyms`.
pub fn parse_synonyms(raw: Option<&str>) -> Vec<String> {
    match raw {
        None => Vec::new(),
        Some(s) if s.is_empty() => Vec::new(),
        Some(s) => s.split(',').map(|label| label.trim().to_string()).collect(),
    }
}

fn node_synonyms(node: &Value) -> Vec<String> {
    let raw = node
        .get("annotations")
        .and_then(|a| a.get("synonyms"))
        .and_then(Value::as_str);
    parse_synonyms(raw)
}

fn build_properties(raw: Option<&Value>) -> Omap<Property> {
    let mut props = Omap::new();
    if let Some(Value::Mapping(entries)) = raw {
        for (name, p) in entries {
            props.insert(
                name.clone(),
                Property {
                    name: name.clone(),
                    ty: p.get("type").and_then(Value::as_str).unwrap_or("").to_string(),
                    values: p.get("values").and_then(Value::as_array).map(|a| a.to_vec()),
                    initial: p.get("initial").cloned(),
                    optional: p.get("optional").and_then(Value::as_bool).unwrap_or(false),
                    synonyms: node_synonyms(p),
                },
            );
        }
    }
    props
}

fn as_string_list(v: Option<&Value>) -> Vec<String> {
    v.and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|x| x.as_str().map(str::to_string)).collect())
        .unwrap_or_default()
}

/// Build a module from a structurally valid document.
pub fn build(doc: &Value) -> Module {
    let mut entities = Omap::new();
    if let Some(Value::Mapping(list)) = doc.get("entities") {
        for (name, e) in list {
            entities.insert(
                name.clone(),
                Entity {
                    name: name.clone(),
                    keys: as_string_list(e.get("keys")),
                    properties: build_properties(e.get("properties")),
                    synonyms: node_synonyms(e),
                },
            );
        }
    }

    let mut links = Omap::new();
    if let Some(Value::Mapping(list)) = doc.get("links") {
        for (name, l) in list {
            links.insert(
                name.clone(),
                Link {
                    name: name.clone(),
                    from_entity: l.get("from").and_then(Value::as_str).unwrap_or("").to_string(),
                    to_entity: l.get("to").and_then(Value::as_str).unwrap_or("").to_string(),
                    cardinality: l
                        .get("cardinality")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string(),
                    reverse: l.get("reverse").and_then(Value::as_str).map(str::to_string),
                    properties: build_properties(l.get("properties")),
                    synonyms: node_synonyms(l),
                },
            );
        }
    }

    let mut actions = Omap::new();
    if let Some(Value::Mapping(list)) = doc.get("actions") {
        for (name, a) in list {
            let mut effects = Vec::new();
            if let Some(Value::Array(items)) = a.get("effects") {
                for eff in items {
                    if let Value::Mapping(pairs) = eff {
                        if let Some((path, value)) = pairs.first() {
                            effects.push((path.clone(), value.clone()));
                        }
                    }
                }
            }
            let approval = a.get("approval").map(|ap| Approval {
                when: ap.get("when").and_then(Value::as_str).unwrap_or("").to_string(),
                authority: ap.get("authority").and_then(Value::as_str).unwrap_or("").to_string(),
            });
            actions.insert(
                name.clone(),
                Action {
                    name: name.clone(),
                    target: a.get("target").and_then(Value::as_str).unwrap_or("").to_string(),
                    guard: a.get("guard").and_then(Value::as_str).unwrap_or("").to_string(),
                    authority: a
                        .get("authority")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string(),
                    audit: a.get("audit").and_then(Value::as_str).unwrap_or("").to_string(),
                    effects,
                    parameters: build_properties(a.get("parameters")),
                    approval,
                    synonyms: node_synonyms(a),
                },
            );
        }
    }

    let mut invariants = Omap::new();
    if let Some(Value::Mapping(list)) = doc.get("invariants") {
        for (name, i) in list {
            invariants.insert(
                name.clone(),
                Invariant {
                    name: name.clone(),
                    over: i.get("over").and_then(Value::as_str).unwrap_or("").to_string(),
                    check: i.get("check").and_then(Value::as_str).unwrap_or("").to_string(),
                },
            );
        }
    }

    let roles = match doc.get("roles") {
        Some(Value::Mapping(list)) => list.iter().map(|(k, _)| k.clone()).collect(),
        _ => Vec::new(),
    };

    Module {
        name: doc.get("module").and_then(Value::as_str).unwrap_or("").to_string(),
        version: doc.get("version").and_then(Value::as_str).unwrap_or("").to_string(),
        arkhe: doc.get("arkhe").and_then(Value::as_str).unwrap_or("").to_string(),
        roles,
        entities,
        links,
        actions,
        invariants,
    }
}
