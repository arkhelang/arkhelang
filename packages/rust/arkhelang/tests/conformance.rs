//! Conformance: the golden files are the spec.
//!
//! Three layers:
//!   1. Every module under `fixtures/invalid/` must fail structural validation
//!      at the path its manifest records (`error_at`), with code `struct`.
//!   2. The two valid modules (model_risk fixture one, okf_edge catalogue)
//!      must produce zero findings.
//!   3. A battery of small modules, each carrying exactly one semantic fault,
//!      pins every ported non-guard semantic pass to its code and path. Their
//!      expected outputs were taken from the Python reference.
//!
//! Guard-dependent conformance is deliberately out of scope for this cut. The
//! reference's SEMANTIC/GUARD probe suite includes CEL guard cases
//! (guard-unknown-name, guard-syntax, guard-traversal-depth, guard-macro-*,
//! guard-index, guard-unknown-function). This port analyses no guards, so
//! those cases are not asserted here; `guard_expressions_are_not_analysed`
//! locks the current behaviour and points at BUILD_NOTES.md.

use std::path::PathBuf;

use arkhelang::{validate_file, validate_text, ValidationResult};

fn repo_root() -> PathBuf {
    // CARGO_MANIFEST_DIR = <repo>/packages/rust/arkhelang
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
}

fn codes(r: &ValidationResult) -> Vec<String> {
    r.findings.iter().map(|f| f.code.clone()).collect()
}

fn has(r: &ValidationResult, code: &str, path: &str) -> bool {
    r.findings.iter().any(|f| f.code == code && f.path == path)
}

// --- 1. invalid fixtures, driven by the manifest ---------------------------

#[test]
fn invalid_fixtures_fail_at_the_manifest_path() {
    let invalid = repo_root().join("fixtures").join("invalid");
    let manifest = std::fs::read_to_string(invalid.join("manifest.yaml"))
        .expect("read manifest.yaml");
    let docs = yaml_rust2::YamlLoader::load_from_str(&manifest).expect("parse manifest");
    let cases = docs[0]["cases"].as_vec().expect("cases list");

    let mut checked = 0;
    for case in cases {
        let file = case["file"].as_str().expect("case file");
        let error_at = case["error_at"].as_str().expect("case error_at");
        // Most cases are structural; a case may name a different finding code
        // (the merge-key case is a document-level `yaml` finding). Default is
        // `struct`, matching the reference's manifest walk.
        let code = case["code"].as_str().unwrap_or("struct");
        let result = validate_file(invalid.join(file)).expect("read fixture");

        assert!(
            !result.ok(),
            "{file} must fail validation, got none"
        );
        assert!(
            has(&result, code, error_at),
            "{file}: expected a {code} finding at '{error_at}', got {:?}",
            result
                .findings
                .iter()
                .map(|f| (f.code.as_str(), f.path.as_str()))
                .collect::<Vec<_>>()
        );
        checked += 1;
    }
    assert_eq!(checked, 17, "manifest case count changed");
}

// --- 2. valid modules -------------------------------------------------------

#[test]
fn model_risk_fixture_one_is_valid() {
    let path = repo_root()
        .join("fixtures")
        .join("model_risk")
        .join("model-risk.arkhe.yaml");
    let result = validate_file(path).expect("read model-risk");
    assert!(result.ok(), "expected no findings, got {:?}", result.findings);
}

#[test]
fn okf_edge_catalogue_is_valid() {
    let path = repo_root()
        .join("packages")
        .join("python")
        .join("tests")
        .join("fixtures")
        .join("okf_edge")
        .join("catalogue.arkhe.yaml");
    let result = validate_file(path).expect("read catalogue");
    assert!(result.ok(), "expected no findings, got {:?}", result.findings);
}

// --- 3. semantic battery ----------------------------------------------------

const BASE: &str = r#"
module: m
version: 0.1.0
arkhe: "0.1"
roles:
  op: {}
entities:
  Thing:
    keys: [thing_id]
    properties:
      thing_id: { type: string }
      status:
        type: state
        values: [draft, done]
        initial: draft
actions:
  finish:
    target: Thing
    guard: target.status == "draft"
    authority: op
    audit: standard
    effects:
      - target.status: done
"#;

#[test]
fn base_module_is_valid() {
    assert!(validate_text(BASE).ok());
}

#[test]
fn semantic_key_ref() {
    let m = BASE.replace("keys: [thing_id]", "keys: [nope]");
    assert!(has(&validate_text(&m), "key-ref", "entities/Thing/keys"));
}

#[test]
fn semantic_key_type_optional() {
    let m = BASE.replace(
        "thing_id: { type: string }",
        "thing_id: { type: string, optional: true }",
    );
    assert!(has(&validate_text(&m), "key-type", "entities/Thing/keys"));
}

#[test]
fn semantic_key_type_state() {
    let m = BASE.replace("keys: [thing_id]", "keys: [status]");
    assert!(has(&validate_text(&m), "key-type", "entities/Thing/keys"));
}

#[test]
fn semantic_state_initial() {
    let m = BASE.replace("initial: draft", "initial: zzz");
    assert!(has(
        &validate_text(&m),
        "state-initial",
        "entities/Thing/properties/status"
    ));
}

#[test]
fn semantic_link_ref() {
    let m = format!(
        "{BASE}\nlinks:\n  owned:\n    from: Thing\n    to: Ghost\n    cardinality: many_to_one\n"
    );
    assert!(has(&validate_text(&m), "link-ref", "links/owned/to"));
}

#[test]
fn semantic_name_collision() {
    let m = format!(
        "{BASE}\nlinks:\n  assess:\n    from: Thing\n    to: Thing\n    reverse: status\n    cardinality: many_to_one\n"
    );
    assert!(has(&validate_text(&m), "name-collision", "entities/Thing"));
}

#[test]
fn semantic_action_ref() {
    let m = BASE.replace("authority: op", "authority: nobody");
    assert!(has(
        &validate_text(&m),
        "action-ref",
        "actions/finish/authority"
    ));
}

#[test]
fn semantic_effect_path() {
    let m = BASE.replace("- target.status: done", "- target.ghost: x");
    assert!(has(
        &validate_text(&m),
        "effect-path",
        "actions/finish/effects/target.ghost"
    ));
}

#[test]
fn semantic_effect_value() {
    let m = BASE.replace("- target.status: done", "- target.status: zombie");
    assert!(has(
        &validate_text(&m),
        "effect-value",
        "actions/finish/effects/target.status"
    ));
}

#[test]
fn semantic_effect_duplicate() {
    let m = BASE.replace(
        "- target.status: done",
        "- target.status: done\n      - target.status: draft",
    );
    assert!(has(
        &validate_text(&m),
        "effect-duplicate",
        "actions/finish/effects/target.status"
    ));
}

#[test]
fn semantic_effect_cardinality() {
    let m = r#"
module: m
version: 0.1.0
arkhe: "0.1"
roles:
  op: {}
entities:
  Thing:
    keys: [thing_id]
    properties:
      thing_id: { type: string }
      status:
        type: state
        values: [draft, done]
        initial: draft
  Other:
    keys: [other_id]
    properties:
      other_id: { type: string }
      foo: { type: string }
links:
  owns:
    from: Thing
    to: Other
    reverse: owner
    cardinality: one_to_many
actions:
  finish:
    target: Thing
    guard: target.status == "draft"
    authority: op
    audit: standard
    effects:
      - target.status: done
      - target.owns.foo: bar
"#;
    assert!(has(
        &validate_text(m),
        "effect-cardinality",
        "actions/finish/effects/target.owns.foo"
    ));
}

#[test]
fn semantic_effect_value_optional_param() {
    let m = BASE.replace(
        "    effects:\n      - target.status: done",
        "    parameters:\n      sev: { type: enum, values: [draft], optional: true }\n    effects:\n      - target.status: params.sev",
    );
    assert!(has(
        &validate_text(&m),
        "effect-value",
        "actions/finish/effects/target.status"
    ));
}

fn with_entity_synonyms(syns: &str) -> String {
    BASE.replace(
        "  Thing:\n    keys: [thing_id]",
        &format!(
            "  Thing:\n    annotations:\n      synonyms: \"{syns}\"\n    keys: [thing_id]"
        ),
    )
}

#[test]
fn semantic_synonym_duplicate() {
    let m = with_entity_synonyms("a, a");
    assert!(has(&validate_text(&m), "synonym-duplicate", "entities/Thing"));
}

#[test]
fn semantic_synonym_collision() {
    let m = with_entity_synonyms("Thing");
    assert!(has(&validate_text(&m), "synonym-collision", "entities/Thing"));
}

#[test]
fn semantic_synonym_empty() {
    let m = with_entity_synonyms("a,,");
    assert!(has(&validate_text(&m), "synonym-empty", "entities/Thing"));
}

#[test]
fn semantic_synonym_collision_case_folds_onto_entity_name() {
    // Names stay case-sensitive, but a lowercase synonym that case-folds onto a
    // declared entity name in scope is a collision (it would ground onto that
    // name under any case-insensitive matcher). Here "widget" case-folds onto
    // the entity type "Widget".
    let m = r#"
module: m
version: 0.1.0
arkhe: "0.1"
roles:
  op: {}
entities:
  Thing:
    annotations:
      synonyms: "widget"
    keys: [thing_id]
    properties:
      thing_id: { type: string }
  Widget:
    keys: [widget_id]
    properties:
      widget_id: { type: string }
actions:
  finish:
    target: Thing
    guard: target.thing_id != ""
    authority: op
    audit: standard
    effects:
      - target.thing_id: x
"#;
    assert!(has(&validate_text(m), "synonym-collision", "entities/Thing"));
}

#[test]
fn semantic_link_property_collision() {
    // A link property may not collide with a property of the far entity it
    // merges into (ADR 0006). Here `shared` is declared on both the link and
    // the to-entity `Other`.
    let m = r#"
module: m
version: 0.1.0
arkhe: "0.1"
roles:
  op: {}
entities:
  Thing:
    keys: [thing_id]
    properties:
      thing_id: { type: string }
  Other:
    keys: [other_id]
    properties:
      other_id: { type: string }
      shared: { type: string }
links:
  rel:
    from: Thing
    to: Other
    cardinality: many_to_one
    properties:
      shared: { type: string }
actions:
  finish:
    target: Thing
    guard: target.thing_id != ""
    authority: op
    audit: standard
    effects:
      - target.thing_id: x
"#;
    assert!(has(
        &validate_text(m),
        "name-collision",
        "links/rel/properties/shared"
    ));
}

#[test]
fn semantic_enum_subset_into_state_is_accepted() {
    // Positive acceptance: an enum parameter whose values are a subset of the
    // state destination's declared values may drive the effect.
    let m = r#"
module: m
version: 0.1.0
arkhe: "0.1"
roles:
  op: {}
entities:
  Thing:
    keys: [thing_id]
    properties:
      thing_id: { type: string }
      status:
        type: state
        values: [draft, done]
        initial: draft
actions:
  finish:
    target: Thing
    parameters:
      st: { type: enum, values: [done] }
    guard: target.status == "draft"
    authority: op
    audit: standard
    effects:
      - target.status: params.st
"#;
    assert!(validate_text(m).ok(), "expected valid, got {:?}", validate_text(m).findings);
}

#[test]
fn semantic_effect_value_bool_into_int_enum() {
    // Strict effect-value typing (ADR 0009, D3): a boolean literal is not an
    // integer enum member, so `true` written into a [1, 2, 3] enum is rejected.
    // The Value model keeps Bool and Int distinct, so equality never conflates
    // them.
    let m = r#"
module: m
version: 0.1.0
arkhe: "0.1"
roles:
  op: {}
entities:
  Thing:
    keys: [thing_id]
    properties:
      thing_id: { type: string }
      tier:
        type: enum
        values: [1, 2, 3]
actions:
  set_tier:
    target: Thing
    guard: target.tier == 1
    authority: op
    audit: standard
    effects:
      - target.tier: true
"#;
    assert!(has(
        &validate_text(m),
        "effect-value",
        "actions/set_tier/effects/target.tier"
    ));
}

// --- loader behaviour -------------------------------------------------------

#[test]
fn duplicate_yaml_keys_are_rejected() {
    // Joined line by line: a backslash string continuation would strip the
    // indentation that makes the second A a duplicate inside entities.
    let doc = [
        "module: m",
        "version: 0.1.0",
        "arkhe: '0.1'",
        "entities:",
        "  A:",
        "    keys: [x]",
        "    properties:",
        "      x: {type: string}",
        "  A:",
        "    keys: [y]",
        "    properties:",
        "      y: {type: string}",
        "",
    ]
    .join("\n");
    let result = validate_text(&doc);
    assert!(!result.ok());
    assert_eq!(result.findings[0].code, "yaml");
}

#[test]
fn merge_keys_are_rejected() {
    // A merge key (`<<`) is a document-level `yaml` finding (ADR 0009, D2);
    // plain anchors and aliases stay allowed.
    let doc = "module: m\nversion: 0.1.0\narkhe: '0.1'\n\
_shared: &base\n  type: string\n\
entities:\n  A:\n    keys: [x]\n    properties:\n      x:\n        <<: *base\n";
    let result = validate_text(doc);
    assert!(!result.ok());
    assert_eq!(result.findings[0].code, "yaml");
    assert!(
        result.findings[0].message.contains("merge keys (<<)"),
        "expected the merge-key message, got {:?}",
        result.findings[0]
    );
}

#[test]
fn struct_findings_carry_source_locations() {
    let path = repo_root()
        .join("fixtures")
        .join("invalid")
        .join("state_without_initial.arkhe.yaml");
    let result = validate_file(path).expect("read fixture");
    let finding = result.findings.first().expect("a finding");
    assert!(
        finding.line.is_some() && finding.column.is_some(),
        "expected a source position on {:?}",
        finding
    );
}

// --- guard gate -------------------------------------------------------------

#[test]
fn guard_expressions_are_not_analysed() {
    // A guard referencing an unknown name would raise guard-unknown-name in the
    // reference. This port does not analyse CEL, so it emits no guard finding.
    // See BUILD_NOTES.md, "Guard stub milestone". Update this test when CEL
    // conformance lands.
    let m = BASE.replace(r#"guard: target.status == "draft""#, "guard: target.ghost == 1");
    let result = validate_text(&m);
    assert!(
        !codes(&result).iter().any(|c| c.starts_with("guard-")),
        "no guard-* finding is expected yet, got {:?}",
        result.findings
    );
    assert!(result.ok(), "the module is otherwise valid, got {:?}", result.findings);
}
