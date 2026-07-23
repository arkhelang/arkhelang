# ADR 0009: YAML surface and strict typing

Date: 2026-07-23
Status: Accepted

## Context

The Rust port (ADR 0008, item 4) is a second conforming implementation, and
building it surfaced three behaviours the spec never pinned down. Each is a
place where the Python reference and the Rust port could diverge while both
believed they were correct, so each needs a ruling rather than an accident of
whichever YAML library each language reached for.

1. Scalar typing. The reference loads modules with PyYAML, whose default
   resolver follows YAML 1.1: a bare `yes`, `no`, `on`, or `off` becomes a
   boolean. `yaml-rust2` follows the YAML 1.2 core schema, where those are
   strings. The two implementations disagreed on what a document means.
2. Merge keys. PyYAML raised an incidental construction error on `<<`;
   `yaml-rust2` treated `<<` as an ordinary key. Neither behaviour was chosen.
3. Effect-value typing. Python treats `True == 1` and `1.0 == 1` as equal, and
   `bool` is a subclass of `int`, so enum and state membership checks accepted a
   boolean or a float where an integer value was declared. Rust's value model
   keeps the variants distinct, so it did not.

## Decision

**D1. Scalar typing follows YAML 1.2 core.** Only `true` and `false` (in their
three capitalisations) are booleans. `yes`, `no`, `on`, `off`, `y`, and `n` are
strings. This is the Norway problem: a country-code list containing `NO` should
not silently become a list containing `false`. The reference stops applying the
YAML 1.1 bool resolver; the port already resolved this way, so it is unchanged.

**D2. Merge keys (`<<`) are not part of the Arkhe YAML surface.** Both loaders
detect a merge key and emit a clear document-level `yaml` finding, "merge keys
(<<) are not part of the Arkhe YAML surface", with line and column when
available, in the same shape as the duplicate-key finding. Plain anchors and
aliases remain allowed; they are ordinary reuse and do not change a document's
meaning the way a merge does. The motive is determinism: a module's canonical
form (ADR 0007) is defined on the validated document, and merge resolution is
one more place two parsers could produce different trees.

**D3. Effect-value typing is strict.** For enum and state membership and for the
subset checks on effect sources, a value equals a declared value only when their
types match exactly. A boolean is never an integer; `1.0` is never `1`. The
reference adopts type-aware comparison guarding against `bool`'s `int`
subclassing; the port was already strict by construction.

The throughline is that there should be one spec, not two accidents of two YAML
libraries. Where the port and the reference disagreed, the ruling picks the
behaviour that is portable and deterministic, and both implementations move to
it.

## Consequences

- The reference changes behaviour before 1.0: `yes`/`no`/`on`/`off` now load as
  strings, and a module that relied on their coercion to booleans will fail the
  boolean type check instead. This is a deliberate pre-1.0 correction, not a
  breaking change to a released contract.
- Three conformance additions land in `fixtures/`: `yaml_11_boolean`
  (`optional: yes` is a string, so a `struct` boolean finding) and `merge_key`
  (a `yaml` finding) join the invalid manifest, and a strict-typing effect case
  (a boolean literal into an integer enum) joins both suites' semantic battery.
- The manifest gains an optional `code` field so a case can name a non-`struct`
  finding; both harnesses read it, defaulting to `struct`.
- A planned deep dive maps this surface to the portable canonical form of
  ADR 0007.
