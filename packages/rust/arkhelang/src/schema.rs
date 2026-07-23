//! Structural validation: the arkhe-0.1 JSON Schema, hand-rolled.
//!
//! The reference runs the module through a `Draft202012Validator` against
//! `schema/arkhe-0.1.schema.json`. Rather than pull a JSON Schema engine, the
//! rules are transcribed directly here as code. The trade-off: this validator
//! implements exactly the arkhe-0.1 metamodel and nothing more, so it is not a
//! general JSON Schema engine, but it is small, dependency-free, and its
//! findings carry the same `struct` code and the same document paths the
//! reference produces (verified against every fixture in `fixtures/invalid`).
//!
//! Finding messages are written to read clearly; they are close to but not a
//! byte-for-byte copy of the underlying `jsonschema` wording, and conformance
//! keys on the finding code and path, not the message text (see BUILD_NOTES).

use crate::finding::Finding;
use crate::value::Value;

const TOP_KEYS: &[&str] = &[
    "module",
    "version",
    "arkhe",
    "annotations",
    "imports",
    "roles",
    "entities",
    "links",
    "actions",
    "invariants",
];
const SCALAR_TYPES: &[&str] = &[
    "string", "int", "number", "bool", "date", "datetime", "document",
];
const CARDINALITIES: &[&str] = &["one_to_one", "many_to_one", "one_to_many", "many_to_many"];
const AUDIT_LEVELS: &[&str] = &["none", "standard", "mandatory"];

const NAME_PATTERN: &str = "^[a-z][a-z0-9_]*$";
const TYPE_PATTERN: &str = "^[A-Z][A-Za-z0-9]*$";
const VERSION_PATTERN: &str = r"^[0-9]+\.[0-9]+\.[0-9]+$";
const EFFECT_PATTERN: &str = r"^target(\.[a-z][a-z0-9_]*){1,2}$";

/// Validate a document against the arkhe-0.1 structure. Returns `struct`
/// findings; an empty list means the module is structurally sound.
pub fn validate(doc: &Value) -> Vec<Finding> {
    let mut f = Vec::new();
    let root = match doc.as_mapping() {
        Some(_) => doc,
        None => return f, // caller has already produced a `yaml` finding
    };

    require(root, &["module", "version", "arkhe", "entities"], "(root)", &mut f);
    unknown_fields(root, TOP_KEYS, "(root)", &mut f);

    if let Some(v) = root.get("module") {
        check_pattern(v, NAME_PATTERN, is_member_name, "module", &mut f);
    }
    if let Some(v) = root.get("version") {
        check_pattern(v, VERSION_PATTERN, is_version, "version", &mut f);
    }
    if let Some(v) = root.get("arkhe") {
        if v.as_str() != Some("0.1") {
            let got = scalar_repr(v);
            f.push(Finding::new(
                "struct",
                "arkhe",
                format!("this validator implements Arkhe spec '0.1'; the module declares '{got}'"),
            ));
        }
    }
    if let Some(v) = root.get("annotations") {
        check_annotations(v, "annotations", &mut f);
    }
    if let Some(v) = root.get("imports") {
        check_imports(v, "imports", &mut f);
    }
    if let Some(v) = root.get("roles") {
        check_roles(v, "roles", &mut f);
    }
    if let Some(v) = root.get("entities") {
        check_entities(v, "entities", &mut f);
    }
    if let Some(v) = root.get("links") {
        check_links(v, "links", &mut f);
    }
    if let Some(v) = root.get("actions") {
        check_actions(v, "actions", &mut f);
    }
    if let Some(v) = root.get("invariants") {
        check_invariants(v, "invariants", &mut f);
    }

    f.sort_by(|a, b| a.path.cmp(&b.path));
    f
}

// --- containers -------------------------------------------------------------

fn check_annotations(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(map) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    for (k, val) in map {
        if val.as_str().is_none() {
            f.push(Finding::new(
                "struct",
                &format!("{path}/{k}"),
                "annotation values must be strings",
            ));
        }
    }
}

fn check_imports(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(items) = v.as_array() else {
        f.push(type_error(path, "an array"));
        return;
    };
    for (i, item) in items.iter().enumerate() {
        let ip = format!("{path}/{i}");
        let Some(_) = item.as_mapping() else {
            f.push(type_error(&ip, "an object"));
            continue;
        };
        require(item, &["module", "version"], &ip, f);
        unknown_fields(item, &["module", "version"], &ip, f);
        if let Some(m) = item.get("module") {
            check_pattern(m, NAME_PATTERN, is_member_name, &format!("{ip}/module"), f);
        }
        if let Some(ver) = item.get("version") {
            check_pattern(ver, VERSION_PATTERN, is_version, &format!("{ip}/version"), f);
        }
    }
}

fn check_roles(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(map) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    for (name, role) in map {
        property_name(name, NAME_PATTERN, is_member_name, path, f);
        let rp = format!("{path}/{name}");
        let Some(_) = role.as_mapping() else {
            f.push(type_error(&rp, "an object"));
            continue;
        };
        unknown_fields(role, &["annotations", "claims"], &rp, f);
        if let Some(an) = role.get("annotations") {
            check_annotations(an, &format!("{rp}/annotations"), f);
        }
        if let Some(claims) = role.get("claims") {
            check_string_map(claims, &format!("{rp}/claims"), f);
        }
    }
}

fn check_entities(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(map) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    if map.is_empty() {
        f.push(Finding::new("struct", path, "at least one entity is required"));
    }
    for (name, ent) in map {
        property_name(name, TYPE_PATTERN, is_type_name, path, f);
        check_entity(ent, &format!("{path}/{name}"), f);
    }
}

fn check_entity(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(_) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    require(v, &["keys", "properties"], path, f);
    unknown_fields(v, &["annotations", "keys", "properties"], path, f);
    if let Some(an) = v.get("annotations") {
        check_annotations(an, &format!("{path}/annotations"), f);
    }
    if let Some(keys) = v.get("keys") {
        check_keys(keys, &format!("{path}/keys"), f);
    }
    if let Some(props) = v.get("properties") {
        check_properties(props, &format!("{path}/properties"), f, false);
    }
}

fn check_keys(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(items) = v.as_array() else {
        f.push(type_error(path, "an array"));
        return;
    };
    if items.is_empty() {
        f.push(Finding::new("struct", path, "at least one key component is required"));
    }
    // Per-item pattern/type violations report at the item index (matching the
    // reference's jsonschema `absolute_path`); uniqueItems reports at the array.
    for (i, item) in items.iter().enumerate() {
        let ip = format!("{path}/{i}");
        match item.as_str() {
            Some(s) if is_member_name(s) => {}
            Some(s) => f.push(Finding::new(
                "struct",
                &ip,
                format!("'{s}' does not match '{NAME_PATTERN}'"),
            )),
            None => f.push(Finding::new("struct", &ip, "key components must be strings")),
        }
    }
    if !unique_scalars(items) {
        f.push(Finding::new("struct", path, "key components must be unique"));
    }
}

fn check_properties(v: &Value, path: &str, f: &mut Vec<Finding>, data_only: bool) {
    let Some(map) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    if !data_only && map.is_empty() {
        f.push(Finding::new("struct", path, "at least one property is required"));
    }
    for (name, prop) in map {
        property_name(name, NAME_PATTERN, is_member_name, path, f);
        check_property(prop, &format!("{path}/{name}"), f, data_only);
    }
}

fn check_property(v: &Value, path: &str, f: &mut Vec<Finding>, data_only: bool) {
    let Some(_) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    require(v, &["type"], path, f);
    unknown_fields(v, &["type", "values", "initial", "optional", "annotations"], path, f);

    let ty = v.get("type").and_then(Value::as_str);
    if let Some(t) = ty {
        let known = SCALAR_TYPES.contains(&t) || t == "enum" || t == "state";
        if !known {
            f.push(Finding::new(
                "struct",
                &format!("{path}/type"),
                format!("'{t}' is not a known property type"),
            ));
        }
    }

    if let Some(values) = v.get("values") {
        check_values(values, &format!("{path}/values"), f);
    }
    if let Some(opt) = v.get("optional") {
        if opt.as_bool().is_none() {
            f.push(Finding::new("struct", &format!("{path}/optional"), "must be a boolean"));
        }
    }
    if let Some(an) = v.get("annotations") {
        check_annotations(an, &format!("{path}/annotations"), f);
    }

    let has_values = v.contains_key("values");
    let has_initial = v.contains_key("initial");
    match ty {
        Some("enum") => {
            if !has_values {
                f.push(Finding::new("struct", path, "missing required field 'values'"));
            }
            if has_initial {
                f.push(Finding::new(
                    "struct",
                    path,
                    "'initial' is not allowed on an enum property; it belongs to state",
                ));
            }
        }
        Some("state") => {
            if data_only {
                f.push(Finding::new(
                    "struct",
                    path,
                    "lifecycle state is entity-only; this location may not declare it",
                ));
            }
            if !has_values {
                f.push(Finding::new("struct", path, "missing required field 'values'"));
            }
            if !has_initial {
                f.push(Finding::new("struct", path, "missing required field 'initial'"));
            }
        }
        _ => {
            if has_values {
                f.push(Finding::new(
                    "struct",
                    path,
                    "'values' is only allowed on enum and state properties",
                ));
            }
            if has_initial {
                f.push(Finding::new(
                    "struct",
                    path,
                    "'initial' is only allowed on state properties",
                ));
            }
        }
    }
}

fn check_values(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(items) = v.as_array() else {
        f.push(type_error(path, "an array"));
        return;
    };
    if items.is_empty() {
        f.push(Finding::new("struct", path, "at least one value is required"));
    }
    // Per-item type violations report at the item index (matching the
    // reference's jsonschema `absolute_path`); uniqueItems reports at the array.
    for (i, item) in items.iter().enumerate() {
        if !matches!(item, Value::String(_) | Value::Int(_)) {
            f.push(Finding::new(
                "struct",
                &format!("{path}/{i}"),
                "enum and state values must be strings or integers",
            ));
        }
    }
    if !unique_scalars(items) {
        f.push(Finding::new("struct", path, "values must be unique"));
    }
}

fn check_links(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(map) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    for (name, link) in map {
        property_name(name, NAME_PATTERN, is_member_name, path, f);
        check_link(link, &format!("{path}/{name}"), f);
    }
}

fn check_link(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(_) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    require(v, &["from", "to", "cardinality"], path, f);
    unknown_fields(
        v,
        &["annotations", "from", "to", "reverse", "cardinality", "properties"],
        path,
        f,
    );
    if let Some(an) = v.get("annotations") {
        check_annotations(an, &format!("{path}/annotations"), f);
    }
    if let Some(from) = v.get("from") {
        check_pattern(from, TYPE_PATTERN, is_type_name, &format!("{path}/from"), f);
    }
    if let Some(to) = v.get("to") {
        check_pattern(to, TYPE_PATTERN, is_type_name, &format!("{path}/to"), f);
    }
    if let Some(rev) = v.get("reverse") {
        check_pattern(rev, NAME_PATTERN, is_member_name, &format!("{path}/reverse"), f);
    }
    if let Some(card) = v.get("cardinality") {
        check_enum(card, CARDINALITIES, &format!("{path}/cardinality"), f);
    }
    if let Some(props) = v.get("properties") {
        check_properties(props, &format!("{path}/properties"), f, true);
    }
}

fn check_actions(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(map) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    if map.is_empty() {
        f.push(Finding::new("struct", path, "at least one action is required"));
    }
    for (name, act) in map {
        property_name(name, NAME_PATTERN, is_member_name, path, f);
        check_action(act, &format!("{path}/{name}"), f);
    }
}

fn check_action(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(_) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    require(v, &["target", "guard", "authority", "audit", "effects"], path, f);
    unknown_fields(
        v,
        &[
            "annotations",
            "target",
            "parameters",
            "guard",
            "authority",
            "approval",
            "audit",
            "effects",
        ],
        path,
        f,
    );
    if let Some(an) = v.get("annotations") {
        check_annotations(an, &format!("{path}/annotations"), f);
    }
    if let Some(target) = v.get("target") {
        check_pattern(target, TYPE_PATTERN, is_type_name, &format!("{path}/target"), f);
    }
    if let Some(auth) = v.get("authority") {
        check_pattern(auth, NAME_PATTERN, is_member_name, &format!("{path}/authority"), f);
    }
    if let Some(guard) = v.get("guard") {
        check_cel(guard, &format!("{path}/guard"), f);
    }
    if let Some(audit) = v.get("audit") {
        check_enum(audit, AUDIT_LEVELS, &format!("{path}/audit"), f);
    }
    if let Some(params) = v.get("parameters") {
        check_properties(params, &format!("{path}/parameters"), f, true);
    }
    if let Some(approval) = v.get("approval") {
        check_approval(approval, &format!("{path}/approval"), f);
    }
    if let Some(effects) = v.get("effects") {
        check_effects(effects, &format!("{path}/effects"), f);
    }
}

fn check_approval(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(_) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    require(v, &["when", "authority"], path, f);
    unknown_fields(v, &["when", "authority"], path, f);
    if let Some(when) = v.get("when") {
        check_cel(when, &format!("{path}/when"), f);
    }
    if let Some(auth) = v.get("authority") {
        check_pattern(auth, NAME_PATTERN, is_member_name, &format!("{path}/authority"), f);
    }
}

fn check_effects(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(items) = v.as_array() else {
        f.push(type_error(path, "an array"));
        return;
    };
    if items.is_empty() {
        f.push(Finding::new("struct", path, "at least one effect is required"));
    }
    for (i, item) in items.iter().enumerate() {
        check_effect(item, &format!("{path}/{i}"), f);
    }
}

fn check_effect(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(map) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    if map.len() != 1 {
        f.push(Finding::new("struct", path, "an effect is exactly one assignment"));
    }
    for (key, val) in map {
        if !is_effect_path(key) {
            f.push(Finding::new(
                "struct",
                path,
                format!("'{key}' does not match '{EFFECT_PATTERN}'"),
            ));
        }
        let ok_value = matches!(
            val,
            Value::String(_) | Value::Int(_) | Value::Real(_) | Value::Bool(_)
        );
        if !ok_value {
            // A wrong-typed effect value reports at the assigned key, matching
            // the reference's jsonschema `absolute_path` (.../effects/N/<key>).
            f.push(Finding::new(
                "struct",
                &format!("{path}/{key}"),
                "an effect value must be a literal or a params./target. reference",
            ));
        }
    }
}

fn check_invariants(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(map) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    for (name, inv) in map {
        property_name(name, NAME_PATTERN, is_member_name, path, f);
        check_invariant(inv, &format!("{path}/{name}"), f);
    }
}

fn check_invariant(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(_) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    require(v, &["over", "check"], path, f);
    unknown_fields(v, &["annotations", "over", "check"], path, f);
    if let Some(an) = v.get("annotations") {
        check_annotations(an, &format!("{path}/annotations"), f);
    }
    if let Some(over) = v.get("over") {
        check_pattern(over, TYPE_PATTERN, is_type_name, &format!("{path}/over"), f);
    }
    if let Some(check) = v.get("check") {
        check_cel(check, &format!("{path}/check"), f);
    }
}

// --- leaf helpers -----------------------------------------------------------

fn require(obj: &Value, fields: &[&str], path: &str, f: &mut Vec<Finding>) {
    let missing: Vec<&str> = fields.iter().copied().filter(|k| !obj.contains_key(k)).collect();
    if !missing.is_empty() {
        let names = missing
            .iter()
            .map(|m| format!("'{m}'"))
            .collect::<Vec<_>>()
            .join(", ");
        f.push(Finding::new("struct", path, format!("missing required field {names}")));
    }
}

fn unknown_fields(obj: &Value, allowed: &[&str], path: &str, f: &mut Vec<Finding>) {
    if let Some(map) = obj.as_mapping() {
        let unknown: Vec<&str> = map
            .iter()
            .map(|(k, _)| k.as_str())
            .filter(|k| !allowed.contains(k))
            .collect();
        if !unknown.is_empty() {
            let names = unknown
                .iter()
                .map(|u| format!("'{u}'"))
                .collect::<Vec<_>>()
                .join(", ");
            f.push(Finding::new("struct", path, format!("unknown field {names}")));
        }
    }
}

fn property_name(
    name: &str,
    pattern: &str,
    ok: fn(&str) -> bool,
    container_path: &str,
    f: &mut Vec<Finding>,
) {
    if !ok(name) {
        f.push(Finding::new(
            "struct",
            container_path,
            format!("'{name}' does not match '{pattern}'"),
        ));
    }
}

fn check_pattern(v: &Value, pattern: &str, ok: fn(&str) -> bool, path: &str, f: &mut Vec<Finding>) {
    match v.as_str() {
        Some(s) if ok(s) => {}
        Some(s) => f.push(Finding::new(
            "struct",
            path,
            format!("'{s}' does not match '{pattern}'"),
        )),
        None => f.push(type_error(path, "a string")),
    }
}

fn check_enum(v: &Value, allowed: &[&str], path: &str, f: &mut Vec<Finding>) {
    match v.as_str() {
        Some(s) if allowed.contains(&s) => {}
        _ => {
            let got = scalar_repr(v);
            f.push(Finding::new(
                "struct",
                path,
                format!("'{got}' is not one of: {}", allowed.join(", ")),
            ));
        }
    }
}

fn check_cel(v: &Value, path: &str, f: &mut Vec<Finding>) {
    match v.as_str() {
        Some(s) if !s.is_empty() => {}
        Some(_) => f.push(Finding::new("struct", path, "expression must not be empty")),
        None => f.push(type_error(path, "a string")),
    }
}

fn check_string_map(v: &Value, path: &str, f: &mut Vec<Finding>) {
    let Some(map) = v.as_mapping() else {
        f.push(type_error(path, "an object"));
        return;
    };
    for (k, val) in map {
        if val.as_str().is_none() {
            f.push(Finding::new(
                "struct",
                &format!("{path}/{k}"),
                "values must be strings",
            ));
        }
    }
}

fn type_error(path: &str, expected: &str) -> Finding {
    Finding::new("struct", path, format!("expected {expected}"))
}

fn scalar_repr(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Int(i) => i.to_string(),
        Value::Real(s) => s.clone(),
        Value::Bool(b) => b.to_string(),
        Value::Null => "null".to_string(),
        _ => "<non-scalar>".to_string(),
    }
}

fn unique_scalars(items: &[Value]) -> bool {
    for i in 0..items.len() {
        for j in (i + 1)..items.len() {
            if items[i] == items[j] {
                return false;
            }
        }
    }
    true
}

// --- pattern predicates -----------------------------------------------------

fn is_member_name(s: &str) -> bool {
    let mut chars = s.chars();
    match chars.next() {
        Some(c) if c.is_ascii_lowercase() => {}
        _ => return false,
    }
    chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

fn is_type_name(s: &str) -> bool {
    let mut chars = s.chars();
    match chars.next() {
        Some(c) if c.is_ascii_uppercase() => {}
        _ => return false,
    }
    chars.all(|c| c.is_ascii_alphanumeric())
}

fn is_version(s: &str) -> bool {
    let parts: Vec<&str> = s.split('.').collect();
    parts.len() == 3 && parts.iter().all(|p| !p.is_empty() && p.chars().all(|c| c.is_ascii_digit()))
}

fn is_effect_path(s: &str) -> bool {
    let mut parts = s.split('.');
    if parts.next() != Some("target") {
        return false;
    }
    let hops: Vec<&str> = parts.collect();
    (1..=2).contains(&hops.len()) && hops.iter().all(|h| is_member_name(h))
}
