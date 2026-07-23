//! Semantic validation: every non-guard pass from `validate.py::_semantic`.
//!
//! Ported passes: key-ref/key-type, state-initial, link-ref, link-property
//! and traversal name-collision, action-ref, effect-* (path/value/cardinality/
//! duplicate), synonym-* (with the neighbourhood scoping and case-fold rule),
//! and invariant-ref.
//!
//! Not ported: CEL guard analysis (`guards.py`). Guard and approval-`when`
//! expressions and invariant `check` expressions are left unchecked; the
//! validator emits no `guard-*` findings. See BUILD_NOTES.md for the CEL
//! milestone. Everything a guard check would flag is out of scope here, so a
//! module with a broken guard still validates in this port.

use std::collections::HashSet;

use crate::finding::Finding;
use crate::model::{Action, Entity, Link, Module, Property};
use crate::value::Value;

pub fn validate(m: &Module) -> Vec<Finding> {
    let mut f = Vec::new();

    // Keys reference declared, non-optional, non-state properties.
    for e in m.entities.values() {
        for key in &e.keys {
            let where_ = format!("entities/{}/keys", e.name);
            match e.properties.get(key) {
                None => f.push(Finding::new(
                    "key-ref",
                    &where_,
                    format!("key '{key}' is not a declared property"),
                )),
                Some(prop) if prop.is_state() => f.push(Finding::new(
                    "key-type",
                    &where_,
                    format!("key '{key}' may not be a state property"),
                )),
                Some(prop) if prop.optional => f.push(Finding::new(
                    "key-type",
                    &where_,
                    format!("key '{key}' may not be optional"),
                )),
                Some(_) => {}
            }
        }
    }

    // State initial values are members of the declared value set.
    for e in m.entities.values() {
        for p in e.properties.values() {
            if p.is_state() {
                let in_values = match (&p.initial, &p.values) {
                    (Some(init), Some(values)) => values.contains(init),
                    _ => false,
                };
                if !in_values {
                    let init = p.initial.as_ref().map(value_repr).unwrap_or_default();
                    f.push(Finding::new(
                        "state-initial",
                        &format!("entities/{}/properties/{}", e.name, p.name),
                        format!("initial '{init}' is not among declared values"),
                    ));
                }
            }
        }
    }

    // Link endpoints exist.
    for l in m.links.values() {
        for (end, label) in [(&l.from_entity, "from"), (&l.to_entity, "to")] {
            if !m.entities.contains_key(end) {
                f.push(Finding::new(
                    "link-ref",
                    &format!("links/{}/{}", l.name, label),
                    format!("'{end}' is not a declared entity"),
                ));
            }
        }
    }

    // Link properties may not collide with far-entity properties (ADR 0006).
    for l in m.links.values() {
        for far in far_ends(l) {
            let Some(far_entity) = m.entities.get(&far) else {
                continue;
            };
            for pname in l.properties.keys() {
                if far_entity.properties.contains_key(pname) {
                    f.push(Finding::new(
                        "name-collision",
                        &format!("links/{}/properties/{}", l.name, pname),
                        format!("link property '{pname}' collides with a property of {far}"),
                    ));
                }
            }
        }
    }

    // Traversal names do not collide with properties or each other per entity.
    for e in m.entities.values() {
        let mut seen: Vec<(String, String)> = Vec::new();
        for p in e.properties.values() {
            seen.push((p.name.clone(), "property".to_string()));
        }
        for l in m.links.values() {
            let mut names: Vec<(String, String)> = Vec::new();
            if l.from_entity == e.name {
                names.push((l.name.clone(), format!("link '{}'", l.name)));
            }
            if let Some(rev) = &l.reverse {
                if l.to_entity == e.name {
                    names.push((rev.clone(), format!("reverse of link '{}'", l.name)));
                }
            }
            for (name, what) in names {
                if let Some((_, prior)) = seen.iter().find(|(n, _)| *n == name) {
                    f.push(Finding::new(
                        "name-collision",
                        &format!("entities/{}", e.name),
                        format!("'{name}' ({what}) collides with {prior} on {}", e.name),
                    ));
                }
                seen.push((name, what));
            }
        }
    }

    // Actions: references, effects. Guards are not analysed (see module docs).
    for a in m.actions.values() {
        let where_ = format!("actions/{}", a.name);
        let Some(target) = m.entities.get(&a.target) else {
            f.push(Finding::new(
                "action-ref",
                &format!("{where_}/target"),
                format!("'{}' is not a declared entity", a.target),
            ));
            continue;
        };
        if !m.roles.contains(&a.authority) {
            f.push(Finding::new(
                "action-ref",
                &format!("{where_}/authority"),
                format!("'{}' is not a declared role", a.authority),
            ));
        }
        if let Some(approval) = &a.approval {
            if !m.roles.contains(&approval.authority) {
                f.push(Finding::new(
                    "action-ref",
                    &format!("{where_}/approval/authority"),
                    format!("'{}' is not a declared role", approval.authority),
                ));
            }
        }

        let mut seen_paths: HashSet<String> = HashSet::new();
        for (path, value) in &a.effects {
            if !seen_paths.insert(path.clone()) {
                f.push(Finding::new(
                    "effect-duplicate",
                    &format!("{where_}/effects/{path}"),
                    "the same path is assigned more than once",
                ));
            }
            f.extend(effect(m, a, target, path, value));
        }
    }

    f.extend(synonyms(m));

    // Invariants: endpoint exists. The `check` expression is not analysed.
    for inv in m.invariants.values() {
        let where_ = format!("invariants/{}", inv.name);
        if !m.entities.contains_key(&inv.over) {
            f.push(Finding::new(
                "invariant-ref",
                &format!("{where_}/over"),
                format!("'{}' is not a declared entity", inv.over),
            ));
        }
    }

    f
}

fn far_ends(l: &Link) -> Vec<String> {
    let mut ends = vec![l.to_entity.clone()];
    if l.reverse.is_some() {
        ends.push(l.from_entity.clone());
    }
    ends
}

/// Whether traversing `traversal_name` follows the link toward one object.
fn to_one(link: &Link, traversal_name: &str) -> bool {
    let forward = traversal_name == link.name;
    match link.cardinality.as_str() {
        "one_to_one" => true,
        "many_to_one" => forward,
        "one_to_many" => !forward,
        _ => false, // many_to_many
    }
}

fn effect(m: &Module, a: &Action, target: &Entity, path: &str, value: &Value) -> Vec<Finding> {
    let mut f = Vec::new();
    let where_ = format!("actions/{}/effects/{}", a.name, path);
    let segs: Vec<&str> = path.split('.').skip(1).collect(); // drop 'target'

    let prop: &Property;
    if segs.len() == 1 {
        match target.properties.get(segs[0]) {
            Some(p) => prop = p,
            None => {
                f.push(Finding::new(
                    "effect-path",
                    &where_,
                    format!("'{}' is not a property of {}", segs[0], target.name),
                ));
                return f;
            }
        }
    } else {
        // Two segments: one hop then property (the schema bounds the length).
        let info = m.traversal_info(&target.name);
        let hop = info.iter().find(|(name, _, _)| name == segs[0]);
        let Some((_, far, link)) = hop else {
            f.push(Finding::new(
                "effect-path",
                &where_,
                format!("'{}' is not a traversal from {}", segs[0], target.name),
            ));
            return f;
        };
        if !to_one(link, segs[0]) {
            f.push(Finding::new(
                "effect-cardinality",
                &where_,
                format!(
                    "'{}' traverses toward many {far} objects; an effect must address exactly one",
                    segs[0]
                ),
            ));
            return f;
        }
        match m.entities.get(far).and_then(|e| e.properties.get(segs[1])) {
            Some(p) => prop = p,
            None => {
                f.push(Finding::new(
                    "effect-path",
                    &where_,
                    format!("'{}' is not a property of {far}", segs[1]),
                ));
                return f;
            }
        }
    }

    let closed = prop.ty == "enum" || prop.ty == "state";

    match value {
        Value::String(s) if s.starts_with("params.") => {
            let pname = &s["params.".len()..];
            match a.parameters.get(pname) {
                None => f.push(Finding::new(
                    "effect-value",
                    &where_,
                    format!("'{s}' is not a declared parameter"),
                )),
                Some(param) if param.optional => f.push(Finding::new(
                    "effect-value",
                    &where_,
                    format!(
                        "optional parameter '{pname}' may not drive an effect; the write would be undefined when it is omitted"
                    ),
                )),
                Some(param) if closed => {
                    let ok = param.ty == "enum" && subset(&param.values, &prop.values);
                    if !ok {
                        f.push(Finding::new(
                            "effect-value",
                            &where_,
                            format!(
                                "parameter '{pname}' may carry values outside '{}''s declared value set",
                                prop.name
                            ),
                        ));
                    }
                }
                Some(_) => {}
            }
        }
        Value::String(s) if s.starts_with("target.") => {
            let refs: Vec<&str> = s.split('.').skip(1).collect();
            let src = if refs.len() == 1 {
                target.properties.get(refs[0])
            } else {
                None
            };
            match src {
                None => f.push(Finding::new(
                    "effect-value",
                    &where_,
                    format!("'{s}' does not reference a property of {}", target.name),
                )),
                Some(src) if closed => {
                    let src_closed = src.ty == "enum" || src.ty == "state";
                    if !src_closed || !subset(&src.values, &prop.values) {
                        f.push(Finding::new(
                            "effect-value",
                            &where_,
                            format!(
                                "'{s}' may carry values outside '{}''s declared value set",
                                prop.name
                            ),
                        ));
                    }
                }
                Some(_) => {}
            }
        }
        _ => {
            if closed {
                let in_values = prop.values.as_ref().map(|vs| vs.contains(value)).unwrap_or(false);
                if !in_values {
                    f.push(Finding::new(
                        "effect-value",
                        &where_,
                        format!(
                            "'{}' is not among declared values of '{}'",
                            value_repr(value),
                            prop.name
                        ),
                    ));
                }
            }
        }
    }
    f
}

fn subset(inner: &Option<Vec<Value>>, outer: &Option<Vec<Value>>) -> bool {
    let inner = inner.as_deref().unwrap_or(&[]);
    let outer = outer.as_deref().unwrap_or(&[]);
    inner.iter().all(|v| outer.contains(v))
}

fn value_repr(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Int(i) => i.to_string(),
        Value::Real(s) => s.clone(),
        Value::Bool(b) => b.to_string(),
        Value::Null => "null".to_string(),
        _ => String::new(),
    }
}

// --- synonyms ---------------------------------------------------------------

/// One declaration's synonym block: (declaration name, its labels, finding path).
struct Decl {
    name: String,
    synonyms: Vec<String>,
    where_: String,
}

/// Check one synonym namespace. Mirrors `_synonym_group`.
fn synonym_group(names: &HashSet<String>, decls: &[Decl]) -> Vec<Finding> {
    let mut f = Vec::new();
    let names_cf: Vec<(String, String)> =
        names.iter().map(|n| (n.to_lowercase(), n.clone())).collect();
    let mut claimed: Vec<(String, String)> = Vec::new(); // synonym -> owning declaration

    for decl in decls {
        let mut seen_here: HashSet<String> = HashSet::new();
        for s in &decl.synonyms {
            if s.is_empty() {
                f.push(Finding::new(
                    "synonym-empty",
                    &decl.where_,
                    "a synonym is empty; list non-empty, comma-separated labels",
                ));
                continue;
            }
            if !seen_here.insert(s.clone()) {
                f.push(Finding::new(
                    "synonym-duplicate",
                    &decl.where_,
                    format!("synonym '{s}' is listed more than once"),
                ));
                continue;
            }
            if names.contains(s) {
                f.push(Finding::new(
                    "synonym-collision",
                    &decl.where_,
                    format!("synonym '{s}' collides with a declared name in scope"),
                ));
            } else if let Some((_, declared)) =
                names_cf.iter().find(|(cf, _)| *cf == s.to_lowercase())
            {
                f.push(Finding::new(
                    "synonym-collision",
                    &decl.where_,
                    format!("synonym '{s}' case-folds onto declared name '{declared}' in scope"),
                ));
            } else if let Some((_, owner)) = claimed.iter().find(|(syn, _)| syn == s) {
                if owner != &decl.name {
                    f.push(Finding::new(
                        "synonym-collision",
                        &decl.where_,
                        format!("synonym '{s}' is already a synonym of '{owner}'"),
                    ));
                }
            } else {
                claimed.push((s.clone(), decl.name.clone()));
            }
        }
    }
    f
}

/// Reserved `synonyms` annotations, checked per namespace. Mirrors `_synonyms`,
/// including the just-landed neighbourhood scoping and case-fold rule.
fn synonyms(m: &Module) -> Vec<Finding> {
    let mut f = Vec::new();

    // Entity type names: module-wide scope.
    let entity_names: HashSet<String> = m.entities.keys().map(str::to_string).collect();
    let entity_decls: Vec<Decl> = m
        .entities
        .values()
        .map(|e| Decl {
            name: e.name.clone(),
            synonyms: e.synonyms.clone(),
            where_: format!("entities/{}", e.name),
        })
        .collect();
    f.extend(synonym_group(&entity_names, &entity_decls));

    // Action names: module-wide scope.
    let action_names: HashSet<String> = m.actions.keys().map(str::to_string).collect();
    let action_decls: Vec<Decl> = m
        .actions
        .values()
        .map(|a| Decl {
            name: a.name.clone(),
            synonyms: a.synonyms.clone(),
            where_: format!("actions/{}", a.name),
        })
        .collect();
    f.extend(synonym_group(&action_names, &action_decls));

    // Per-entity neighbourhood: properties and co-visible traversal names.
    for e in m.entities.values() {
        let mut names: HashSet<String> = e.properties.keys().map(str::to_string).collect();
        let mut decls: Vec<Decl> = e
            .properties
            .values()
            .map(|p| Decl {
                name: p.name.clone(),
                synonyms: p.synonyms.clone(),
                where_: format!("entities/{}/properties/{}", e.name, p.name),
            })
            .collect();
        for l in m.links.values() {
            if l.from_entity == e.name {
                names.insert(l.name.clone());
                decls.push(Decl {
                    name: l.name.clone(),
                    synonyms: l.synonyms.clone(),
                    where_: format!("links/{}", l.name),
                });
            }
            if let Some(rev) = &l.reverse {
                if l.to_entity == e.name {
                    names.insert(rev.clone());
                    decls.push(Decl {
                        name: rev.clone(),
                        synonyms: l.synonyms.clone(),
                        where_: format!("links/{}", l.name),
                    });
                }
            }
        }
        f.extend(synonym_group(&names, &decls));
    }

    // Link property synonyms: own names plus far-entity property names.
    for l in m.links.values() {
        let mut names: HashSet<String> = l.properties.keys().map(str::to_string).collect();
        for far in far_ends(l) {
            if let Some(far_entity) = m.entities.get(&far) {
                for pname in far_entity.properties.keys() {
                    names.insert(pname.to_string());
                }
            }
        }
        let decls: Vec<Decl> = l
            .properties
            .values()
            .map(|p| Decl {
                name: p.name.clone(),
                synonyms: p.synonyms.clone(),
                where_: format!("links/{}/properties/{}", l.name, p.name),
            })
            .collect();
        f.extend(synonym_group(&names, &decls));
    }

    // Action parameters: one scope each.
    for a in m.actions.values() {
        let names: HashSet<String> = a.parameters.keys().map(str::to_string).collect();
        let decls: Vec<Decl> = a
            .parameters
            .values()
            .map(|p| Decl {
                name: p.name.clone(),
                synonyms: p.synonyms.clone(),
                where_: format!("actions/{}/parameters/{}", a.name, p.name),
            })
            .collect();
        f.extend(synonym_group(&names, &decls));
    }

    // A link's synonyms are checked from both endpoints, so an intrinsic fault
    // can surface twice; collapse identical findings.
    let mut deduped: Vec<Finding> = Vec::new();
    let mut seen: HashSet<(String, String, String)> = HashSet::new();
    for finding in f {
        let key = (finding.code.clone(), finding.path.clone(), finding.message.clone());
        if seen.insert(key) {
            deduped.push(finding);
        }
    }
    deduped
}
