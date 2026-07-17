# ADR 0005: Guard and effect semantics

Date: 2026-07-17
Status: Accepted

## Context

Writing fixture one (the model-risk module) surfaced five semantic questions
the design sketch left open: how guards traverse links, what functions guard
expressions may call, how lifecycle state differs from a plain enum, how far
effects may reach, and whether guards can express ordering over collections.
The metamodel schema and validator cannot be written until these are fixed.

## Decisions

**Link traversal in guards.** Declared links bind into the CEL evaluation
context as lists. The link name traverses in the declared direction; a link
may declare an optional `reverse:` name for traversal from the target side
(for example `assesses` from review to model, `reviewed_by` from model to
reviews). Traversal depth in a single guard is bounded at two hops.
Aggregation uses CEL's native macros (`all`, `exists`, `filter`, `size`);
there is no bespoke aggregation syntax.

**Standard library.** Guard expressions may call a closed set of Arkhe
functions beyond core CEL. In v0.1 the set is exactly: `months_since(date)`,
`days_since(date)`, and `today()`. Every compiled contract declares which
stdlib functions its guard uses. Additions require a superseding ADR;
a broader stdlib is on the v0.2 roadmap.

**Lifecycle state.** `type: state` is first-class and distinct from `enum`:
a state property declares an `initial` value, and only action effects may
change a state-typed property. The validator rejects any other write path.
This is what makes lifecycles governable rather than merely documented.

**Effect reach and the write surface.** An effect may modify the action's
target, or reach at most one hop across a declared link (as
`record_validation_outcome` sets the assessed model's `last_validated`).
Every compiled contract lists its full write surface: every entity type the
action may modify. The write surface is contract data, not documentation,
because auditors and policy engines need it machine-readable.

**Ordering.** Deferred to v0.2. v0.1 guards quantify over whole collections;
"the latest review" is not expressible until the metamodel gains an ordering
concept, and that concept should not be rushed into the core.

## Consequences

- Fixture one is revised to use `reverse:` link names in guards and
  invariants, and its expected contracts declare traversals, stdlib usage,
  and write surfaces.
- The evaluation context a runtime must provide is now fully specified by
  the contract: target, bounded traversals, declared stdlib.
- Rules needing "most recent" semantics must be rewritten as
  quantifications, or wait for v0.2.
