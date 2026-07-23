# Changelog

All notable changes to Arkhe are documented here. The format follows
Keep a Changelog; versions follow semantic versioning. The golden files in
`fixtures/` are the specification; a behaviour change without a fixture
change did not happen.

## [0.2.0] - Unreleased

Additive language and IR work from ADR 0008. The metamodel schema is
unchanged; contracts gain fields that known-field readers ignore, so v0.1
consumers keep working.

### OKF emitter (ADR 0008 item 1)

- `arkhe emit --target=okf <file>`: an Open Knowledge Format bundle (Google,
  OKF v0.1), one markdown concept file per entity, link, action, role, and
  invariant, plus per-section and root `index.md` pages for progressive
  disclosure. Prose comes only from module annotations and the generated
  contracts; the emitter adds structural scaffolding, never domain text.
  Output is deterministic (the optional `timestamp` field is omitted by
  design), and every name that becomes a path segment is re-checked, so a
  malformed or reserved (`index`) name is refused rather than escaping into a
  path. A manifest lets a re-emit prune only what it previously wrote. Golden
  bundles for the model_risk fixture and an okf_edge edge-case fixture are the
  spec. Shipped in acc432e.

### Synonyms annotations (ADR 0008 item 2)

- A reserved `synonyms` annotation, a comma-separated list of alternate
  labels, on entities, links, actions, properties (including enum and state
  properties), and action parameters. The validator parses and checks each
  list: labels are trimmed and non-empty, unique within their declaration,
  and free of name clashes within their scope. Scopes mirror the base
  validator's own, not one flat module namespace: entity-type and action
  names are module-wide; a property or link (traversal) synonym is checked
  against the entity neighbourhood it shares at runtime (own properties plus
  the co-visible forward and reverse traversal names), a link's synonyms from
  both its endpoints; a link-property synonym is checked against the
  far-entity properties it merges into (ADR 0006). Names stay case-sensitive,
  but a synonym that case-folds onto a declared name is a collision. A label
  cannot itself contain a comma, which is the list separator. New finding
  codes `synonym-empty`, `synonym-duplicate`, and `synonym-collision`.
- Contracts carry the parsed list as structured data: `synonyms` on action
  and read contracts, on parameter and property declarations, and on read
  traversals for links. Tool descriptions stay prose; synonyms are data.
- Emitters surface them: pylib docstrings gain an "Also known as" line for
  entity, action, and read declarations, and parameter docs gain an
  "aka: ..." tail; OKF entity, link, and action files gain an "Also known
  as" line after the description, and property and parameter tables gain a
  Synonyms column when any row declares one. The okf_edge catalogue fixture
  declares synonyms across every kind; its golden bundle is updated
  accordingly.

### Resolved types on effects (ADR 0008 item 3)

- Each effect entry in an action contract now inlines the destination
  property's resolved type: `type` always, plus `values` for enum and state
  destinations. A contract consumer reads the write's destination type
  directly, without re-resolving the effect path against the target's read
  contract; the first consumers are the emitters and ports still to come.
  The model_risk fixture gains a `reclassify_model` action that writes both a
  string-valued and an integer-valued enum destination, so enum (non-state)
  coverage is a committed golden. Every action contract golden and the golden
  emitted library are regenerated with the new field.

### YAML surface and strict typing (ADR 0009)

The Rust port surfaced three behaviours the spec had left to whichever YAML
library each implementation used. ADR 0009 rules on all three, and the
reference loader changes to match; these are deliberate pre-1.0 corrections.

- **YAML 1.2 core scalar typing.** The strict loader no longer applies the
  YAML 1.1 bool resolver: a bare `yes`, `no`, `on`, `off`, `y`, or `n` loads as
  a string, and only `true`/`false` (in their three capitalisations) are
  booleans. A module that relied on the old coercion (for example `optional:
  yes`) now fails the boolean type check. This is the Norway problem: a bare
  `no` is a string.
- **Merge keys (`<<`) are refused.** Both loaders emit a document-level `yaml`
  finding, "merge keys (<<) are not part of the Arkhe YAML surface", with line
  and column, rather than a construction traceback. Plain anchors and aliases
  remain allowed.
- **Strict effect-value typing.** Enum and state membership and the subset
  checks compare with type-aware equality: a boolean is never an integer, and
  `1.0` is never `1`. Guards against Python's `bool`-is-`int` subclassing.
- Conformance grows: `fixtures/invalid/yaml_11_boolean` and
  `fixtures/invalid/merge_key` join the manifest (which gains an optional
  `code` field so a case can name a non-`struct` finding), and a strict-typing
  effect case joins the semantic battery in both the Python and Rust suites.

## [0.1.0] - 2026-07-18

The first release. Arkhe v0.1 is the language, its conformance suite, and a
working toolchain: exactly the four deliverables scoped in ADR 0004.

### The language (spec 0.1)

- Modules in YAML declaring entities (scalar, enum, and lifecycle `state`
  properties with declared initial values), first-class links (cardinality,
  optional `reverse` traversal names, link properties), actions (CEL guard,
  authority role with identity claims, conditional approval escalation,
  audit level, one-hop effects), and invariants.
- Closed-world semantics, no inference. Guards traverse links to a bound
  depth of two hops; traversal-bound variables see far-entity properties
  and the traversed link's own properties. The stdlib is exactly
  `months_since`, `days_since`, `today`.
- State-typed properties change only through action effects. Optional
  parameters may not drive effects. High-consequence rules are structural:
  what the ontology does not permit, no caller can do.
- The metamodel is published as JSON Schema
  (`schema/arkhe-0.1.schema.json`); design decisions are public as
  ADRs 0001 through 0007, including the canonical form and portable
  provenance hash (ADR 0007).

### The toolchain (arkhelang 0.1.0)

- `arkhe validate <file|directory>`: structural and semantic validation
  with compiler-style `file:line:col` findings, source-line carets, ANSI
  colour (NO_COLOR respected), per-directory results tables, `--json`.
- `arkhe contracts <file> [--out DIR]`: the tool-contract IR, one JSON
  document per action and a read contract per entity, carrying guards with
  their evaluation context (traversals, cardinality, stdlib), authority
  claims, approval, audit events, effects, the machine-readable write
  surface, structured refusal shapes, and provenance hashes.
- `arkhe emit --target=lib <file> [--out FILE]`: a generated Python library
  whose functions enforce their contracts, refusing with the failing guard
  clause named. Generated source is escaped and compile-checked.
- `arkhelang.runtime`: the reference in-memory execution semantics
  (neighbourhood materialization, whole-expression guard decisions with
  conjunct labelling, four-eyes approval, no partial effect writes, audit
  logging).
- Conformance suite: fixture one (financial-services model risk), fifteen
  invalid-module fixtures with a manifest, golden contracts for every
  action and entity, a golden emitted library, and adversarial regression
  tests. 84 tests.

### Documentation

- Guides for GRC professionals, data engineers, and architects under
  `docs/guides/`.
- The guard-refusal demo (`examples/guard_refusal_demo.py`).

### Known boundaries

- Single-module tooling: `imports` are schema-valid but not yet resolved
  by the toolchain.
- Guard analysis checks names, traversals, and calls, not operator typing.
- Deferred to v0.2+ by ADR: stdlib expansion, ordering semantics, resolved
  types on effects, Cedar and OKF and protocol emitters, OWL/RDF export.

[0.1.0]: https://github.com/arkhelang/arkhelang/releases/tag/v0.1.0
