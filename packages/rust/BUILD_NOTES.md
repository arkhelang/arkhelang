# Rust port build notes

Engineering notes for the Arkhe validator Rust port (ADR 0008, item 4). The
port was written compiling-blind: the authoring environment had no `cargo`, so
every external-API assumption is recorded here for verification on a machine
that can build. Andrew compiles locally; nothing here has been run through
`rustc`.

## What this is

A Rust implementation of the VALIDATOR only: YAML load, structural (schema)
validation, and the non-guard semantic passes. Conformance is defined by the
frozen v0.1 golden fixtures. It is deliberately small; the emitters
(`contracts`, `emit`) are not ported.

Layout (a Cargo workspace, mirroring `packages/python` and `packages/npm`):

```
packages/rust/
  Cargo.toml            workspace (members: arkhelang, arkhe)
  BUILD_NOTES.md        this file
  arkhelang/            library crate (reserved name)
    src/lib.rs          public API: validate_file, validate_text, validate_value
    src/value.rs        internal YAML value model
    src/loader.rs       YAML load, duplicate-key rejection, source positions
    src/schema.rs       arkhe-0.1 structural rules, hand-rolled
    src/model.rs        in-memory module model (port of model.py)
    src/semantic.rs     non-guard semantic passes (port of validate.py)
    src/finding.rs      Finding / ValidationResult and their JSON shape
    tests/conformance.rs
  arkhe/                CLI crate (reserved name)
    src/main.rs         arkhe validate <path> [--json]
```

Note: the repository already carries name-reservation placeholder crates at
`crates/arkhe` and `crates/arkhelang` (version `0.0.1`). This port is the real
implementation at `packages/rust/*` (version `0.1.0`). Two crates share each
name across the two locations, which is fine for building but would collide at
publish time; resolving that (retire the placeholders, or move this port into
`crates/`) is a packaging decision for Andrew, not done here.

## Crate choices

- **yaml-rust2** for YAML. Chosen over `serde_yaml`, which is archived and
  deprecated upstream (last release `0.9.34+deprecated`). Two further reasons:
  yaml-rust2 is pure Rust (no libyaml C build step), and its marked event API
  exposes source line/column, which the reference attaches to every finding.
  `serde_yaml` exposes positions only on parse errors, not per node.
  - **VERIFY**: crate version. Pinned `0.10`; confirm this resolves and that
    the API below matches. If the latest is newer/older, adjust.
- **serde + serde_json** for the findings JSON. `ValidationResult::to_json`
  derives `Serialize` and uses `to_string_pretty` (two-space indent), matching
  `json.dumps(..., indent=2)` layout. One known difference from the Python
  reference: Python's `json.dumps` defaults to `ensure_ascii=True` and escapes
  non-ASCII as `\uXXXX`; `serde_json` emits UTF-8 directly. All finding
  messages the fixtures produce are ASCII, so this does not bite the golden
  cases, but a module with non-ASCII text in a message would differ byte-wise.
- **thiserror** for the one error type (`Error::Io`), per the requested style.
- No `jsonschema` crate: the arkhe-0.1 schema is transcribed into `schema.rs`
  by hand. Trade-off: `schema.rs` is not a general JSON Schema engine, it
  implements exactly the arkhe-0.1 metamodel. It is small and dependency-free,
  and its finding paths were verified equal to the reference's `jsonschema`
  `absolute_path` output for all 15 invalid fixtures (see coverage table).
- No arg-parsing crate: the CLI hand-parses its tiny surface.

Standard rustfmt defaults, edition 2021, no `unwrap`/`expect` in library code
(only in `tests/`). No per-file licence headers (repo convention: the existing
crates set `license = "Apache-2.0"` in Cargo.toml and carry a LICENSE file, but
no source headers). A per-crate LICENSE file was not copied in to avoid
duplicating the 200-line text; add one before publishing if desired.

## Unverified API assumptions (yaml-rust2)

All in `src/loader.rs` unless noted. If the build fails, start here.

- Re-exports: `yaml_rust2::Yaml`, `yaml_rust2::YamlLoader` (used in
  `value.rs`, `loader.rs`, and the test). `YamlLoader::load_from_str(&str) ->
  Result<Vec<Yaml>, ScanError>`.
- `Yaml` variants matched in `value.rs`: `Null`, `Boolean(bool)`,
  `Integer(i64)`, `Real(String)`, `String(String)`, `Array(Vec<Yaml>)`,
  `Hash(LinkedHashMap<Yaml, Yaml>)`, `Alias(usize)`, `BadValue`. The `Hash`
  iterator is assumed insertion-ordered (LinkedHashMap); order matters for the
  name-collision and synonym passes.
- Marked event parsing:
  - `yaml_rust2::parser::{Parser, Event, MarkedEventReceiver}`.
  - `yaml_rust2::scanner::Marker`.
  - `Parser::new(text.chars())` where the argument is `Iterator<Item = char>`.
  - `Parser::load(&mut recv, multi: bool) -> Result<(), ScanError>`, dispatching
    to `MarkedEventReceiver::on_event(&mut self, ev: Event, mark: Marker)`.
  - `Event` variants used: `MappingStart(..)`, `MappingEnd`,
    `SequenceStart(..)`, `SequenceEnd`, `Scalar(String, ..)`. The `(..)` rest
    patterns absorb the anchor-id / tag / style fields whose count varies
    across versions, so arity changes should not break these arms.
  - `Marker::line() -> usize` assumed **1-based**; `Marker::col() -> usize`
    assumed **0-based** (the code adds 1, matching the reference's
    `column + 1`). If line turns out 0-based, findings will be off by one line;
    conformance does not assert positions (see below), but the CLI display and
    `struct_findings_carry_source_locations` test would be affected.
- If the marked pass cannot run (parser error), `loader::scan` returns empty
  positions and no duplicate; the value tree still comes from the high-level
  `YamlLoader`, so structural and semantic conformance is unaffected. The
  duplicate-key check and line/column are the only things that depend on the
  marked pass.

## ADR 0009 alignment (YAML surface and strict typing)

Three spec decisions were ratified after the port's first cut. Their effect on
the Rust side:

- **D1 (YAML 1.2 core scalar typing).** No Rust change. `yaml-rust2` already
  resolves scalars under the YAML core schema: a bare `yes`/`no`/`on`/`off` is a
  string, only `true`/`false` (and capitalised forms) are booleans. Confirmed
  against `value.rs`, which takes the parser's scalar type verbatim rather than
  re-resolving. The reference (PyYAML) had to strip its YAML 1.1 bool resolver
  to match; the port was already correct. The `yaml_11_boolean` fixture
  (`optional: yes`) yields the same `struct` "must be a boolean" finding here as
  in the reference.
- **D2 (merge keys forbidden).** Rust change, in `loader.rs`. The marked event
  pass now flags a `<<` mapping key and emits the document-level `yaml` finding
  "merge keys (<<) are not part of the Arkhe YAML surface", with the key's
  line/column, wording aligned with the reference. It short-circuits the value
  tree exactly as a duplicate key does, and takes priority over the duplicate
  message if both appear. Plain anchors and aliases stay allowed (they were
  already: `value.rs` maps `Yaml::Alias` through, and the event pass ignores
  alias events).
- **D3 (strict effect-value typing).** No Rust change. The `Value` enum keeps
  `Bool`, `Int`, and `Real` as distinct variants (`Real` is held as its source
  string), so derived `PartialEq` never conflates `true` with `1` or `1.0` with
  `1`. Enum/state membership (`Vec::contains`) and the subset check are variant
  aware by construction. The reference had to adopt type-aware comparison to
  match Python's `bool`-is-`int` and `1.0 == 1` semantics; the port was already
  strict. `semantic_effect_value_bool_into_int_enum` pins this.

### schema.rs path granularity (reviewer fix)

The hand-rolled schema now matches the reference's jsonschema `absolute_path` at
finer granularity, verified by running the reference over crafted inputs:

- a wrong-typed effect value reports at `.../effects/N/<key>` (the assigned key
  is appended), not at `.../effects/N`;
- a per-item pattern or type violation inside a `keys` array reports at
  `.../keys/N` (the index is appended); the `uniqueItems` violation still
  reports at `.../keys`;
- a per-item type violation inside a `values` array reports at `.../values/N`;
  its `uniqueItems` violation still reports at `.../values`.

## Accepted divergences from the reference

These are deliberate; conformance keys on finding code and path (membership,
not order), so none of them breaks a golden case. They are not bugs to fix.

- **Missing required fields.** jsonschema emits one finding per missing required
  field (N findings for N missing). `schema.rs::require` emits a single finding
  listing all missing fields. No fixture exercises multiple simultaneous
  missing fields, and the path is identical.
- **Finding order for array indices.** `schema.rs` sorts findings by
  `path.cmp` (lexicographic string order), so `.../keys/10` sorts before
  `.../keys/2`. jsonschema orders by `absolute_path`, whose indices are integers
  and sort numerically. Order differs only when a single array has ten-plus
  faulty items; the set of (code, path) pairs is the same.
- **Double finding on a non-string `arkhe`.** For an `arkhe` field that is not a
  string (e.g. a number), jsonschema emits both a `type` and a `const` finding;
  `schema.rs` emits one const-style finding at `arkhe`. The `wrong_spec_version`
  fixture uses a string mismatch, where both agree on a single finding.

## Guard stub milestone (the port's next step)

CEL guard analysis (`guards.py`) is **not ported**. Guard, approval-`when`,
and invariant-`check` expressions are left unanalysed and the validator emits
no `guard-*` finding. This is gated by the `guards` cargo feature, which is a
placeholder: enabling it changes nothing yet.

Consequence for the two valid fixtures: the reference compiles and type-walks
their guards and confirms they are well-formed; this port only confirms the
guard strings are present and non-empty (a structural check). It cannot yet
catch a guard that is structurally present but semantically broken.

Next milestone is CEL conformance. Candidate crates, to be evaluated by Andrew
(availability, API surface, and current maintenance state are **not asserted
here** and must be checked at build time):

- `cel-interpreter` (the cel-rust project).
- `clarkmcc/cel-rust`.

Whichever is chosen, the port needs a parse tree walk equivalent to
`guards.py`: member-path resolution against the module, the two-hop traversal
bound (ADR 0005), link-property visibility (ADR 0006), the closed stdlib
(`months_since`, `days_since`, `today`) plus the allowed CEL built-ins and
macros, and the macro-base collection check. The finding codes to reproduce
are `guard-syntax`, `guard-unknown-name`, `guard-unknown-function`,
`guard-traversal-depth`, `guard-index`, `guard-macro-arity`, `guard-macro-base`.

## Conformance coverage

### Invalid fixtures (structural, fully covered)

17 fixtures. 15 are single structural failures; the reference produces exactly
one finding for each, at the path recorded in `fixtures/invalid/manifest.yaml`
(`error_at`). A manifest case may carry an optional `code` field (default
`struct`); the `merge_key` case sets `code: yaml` because it is a
document-level load finding rather than a schema finding. Both harnesses read
`code` and assert a finding with that code at `error_at`; the count assertion
is 17. Paths were confirmed against the reference by running its validator over
each fixture.

| fixture | code | error_at | rule |
| --- | --- | --- | --- |
| state_without_initial | struct | entities/Widget/properties/status | state requires `initial` |
| action_without_guard | struct | actions/activate | action requires `guard` |
| bad_audit_level | struct | actions/activate/audit | audit enum |
| bad_cardinality | struct | links/near/cardinality | cardinality enum |
| lowercase_entity_name | struct | entities | type-name pattern (propertyNames) |
| effect_beyond_one_hop | struct | actions/activate/effects/0 | effect path pattern |
| effect_off_target | struct | actions/activate/effects/0 | effect path pattern |
| wrong_spec_version | struct | arkhe | `arkhe` const 0.1 |
| values_on_scalar_type | struct | entities/Widget/properties/widget_id | values only on enum/state |
| initial_on_plain_enum | struct | entities/Widget/properties/kind | initial only on state |
| state_typed_parameter | struct | actions/activate/parameters/st | state is entity-only |
| state_typed_link_property | struct | links/near/properties/phase | state is entity-only |
| duplicate_enum_values | struct | entities/Widget/properties/kind/values | values unique |
| duplicate_keys | struct | entities/Widget/keys | key components unique |
| unpinned_import_version | struct | imports/0/version | version pattern |
| yaml_11_boolean | struct | entities/Widget/properties/note/optional | `optional: yes` is a string under YAML 1.2 core, not a boolean (ADR 0009 D1) |
| merge_key | yaml | (file) | merge keys (`<<`) are refused at load (ADR 0009 D2) |

`struct` finding **messages** are written to read clearly and are close to,
but not a byte-for-byte copy of, the underlying `jsonschema` wording. The
conformance test keys on finding **code and path**, not message text, matching
how the reference's own `test_invalid_fixtures_are_rejected` asserts (it checks
only that validation fails; the manifest documents the path).

### Valid modules (zero findings)

- `fixtures/model_risk/model-risk.arkhe.yaml` (fixture one).
- `packages/python/tests/fixtures/okf_edge/catalogue.arkhe.yaml`.

Both are asserted to yield zero findings. Because guards are not analysed, the
zero-findings result does not depend on any guard-gated behaviour; there is no
`#[ignore]` in the suite. Confirmed with the reference (guards disabled) that
both modules produce zero non-guard findings.

### Semantic passes (covered by inline modules)

Each ported non-guard pass is pinned by a small module carrying exactly one
fault; expected code and path were taken from the reference:

key-ref, key-type (optional and state), state-initial, link-ref,
name-collision, action-ref, effect-path, effect-value, effect-duplicate,
effect-cardinality, effect-value (optional parameter), synonym-duplicate,
synonym-collision, synonym-empty. The synonym neighbourhood scoping (per-entity
properties plus co-visible traversals, link-property vs far-entity) is
implemented in `semantic.rs::synonyms` following `_synonyms`.

Added cases (this cut), each with its expected code and path taken from the
reference:

- `semantic_synonym_collision_case_folds_onto_entity_name`: a lowercase synonym
  that case-folds onto a declared entity name is a collision. The earlier note
  claimed the existing `semantic_synonym_collision` test exercised the case-fold
  rule "via the entity-name scope"; it did not (it uses an exact-name clash), so
  this dedicated test now covers the `casefold()` branch of `synonym_group`.
- `semantic_link_property_collision`: a link property that collides with a
  far-entity property (ADR 0006), pinning `name-collision` at
  `links/rel/properties/shared`.
- `semantic_enum_subset_into_state_is_accepted`: positive acceptance, an enum
  parameter whose values are a subset of the state destination's values may
  drive the effect (the module is valid).
- `semantic_effect_value_bool_into_int_enum`: strict effect-value typing
  (ADR 0009 D3), a boolean literal is not an integer enum member.

### Guard cases (gated, not asserted)

Not covered, pending the CEL milestone: guard-syntax, guard-unknown-name
(and its bare-function and bracket variants), guard-unknown-function,
guard-traversal-depth, guard-index, guard-macro-arity, guard-macro-base. The
test `guard_expressions_are_not_analysed` locks the current no-op behaviour so
it is visible and fails loudly when CEL support is added.

### Line/column

The manifest asserts no line/column expectations, and neither does the
conformance harness beyond `struct_findings_carry_source_locations` (which only
checks that a position is present). The reference's own line numbers come from
a `yaml.compose` walk; this port reproduces them from yaml-rust2 markers. If
the marker base (line 1-based, col 0-based) assumption is wrong, positions
shift but no golden-case assertion on a specific line/column fails, because
there are none.

## Commands Andrew runs

From `packages/rust`:

```
cargo build
cargo test
cargo test -p arkhelang --test conformance
```

Expected conformance test names (all in `arkhelang`,
`tests/conformance.rs`):

- `invalid_fixtures_fail_at_the_manifest_path` (17 cases)
- `model_risk_fixture_one_is_valid`
- `okf_edge_catalogue_is_valid`
- `base_module_is_valid`
- `semantic_key_ref`, `semantic_key_type_optional`, `semantic_key_type_state`,
  `semantic_state_initial`, `semantic_link_ref`, `semantic_name_collision`,
  `semantic_action_ref`, `semantic_effect_path`, `semantic_effect_value`,
  `semantic_effect_duplicate`, `semantic_effect_cardinality`,
  `semantic_effect_value_optional_param`, `semantic_synonym_duplicate`,
  `semantic_synonym_collision`, `semantic_synonym_empty`
- `semantic_synonym_collision_case_folds_onto_entity_name`,
  `semantic_link_property_collision`, `semantic_enum_subset_into_state_is_accepted`,
  `semantic_effect_value_bool_into_int_enum`
- `duplicate_yaml_keys_are_rejected`
- `merge_keys_are_rejected`
- `struct_findings_carry_source_locations`
- `guard_expressions_are_not_analysed`

Try the CLI:

```
cargo run -p arkhe -- validate ../../fixtures/model_risk/model-risk.arkhe.yaml
cargo run -p arkhe -- validate ../../fixtures/invalid/bad_audit_level.arkhe.yaml --json
echo "exit code: $?"    # 0 for the valid module, 1 for the invalid one
```

## Things to check first if the build fails

1. yaml-rust2 version and the API assumptions above (loader.rs).
2. `Marker::line()`/`col()` base and accessor names.
3. `Event` variant names and the `Parser::load` signature.
4. `thiserror` version (pinned `1`).
