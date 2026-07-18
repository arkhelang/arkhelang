# Changelog

All notable changes to Arkhe are documented here. The format follows
Keep a Changelog; versions follow semantic versioning. The golden files in
`fixtures/` are the specification; a behaviour change without a fixture
change did not happen.

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
