# ADR 0006: Link properties in traversals

Date: 2026-07-17
Status: Accepted

## Context

Fixture one's tier-1 invariant requires "the model declares a primary data
feed", where `criticality: primary` is a property of the `consumes` link, not
of either endpoint. Under ADR 0005 alone, a variable bound through a
traversal saw only the far entity's properties, making rules about the
relationship itself inexpressible. Link properties exist precisely because
some facts belong to neither endpoint; rules about those facts are half the
reason links are first-class.

## Decision

A variable bound through a link traversal in a guard or invariant sees both
the far entity's properties and the traversed link's own properties. In
`entity.consumes.exists(c, c.criticality == "primary")`, `c` carries
MarketDataFeed's properties and the `consumes` link's `criticality`.

Two consequences are normative. Link properties are terminal: they are
scalar reads, and no further traversal continues through them. And a link
property name may not collide with a property name of an entity reachable
through that link's traversals; the collision is a validation error on the
link declaration, because an ambiguous name would silently shadow one side.

## Consequences

- The primary-feed class of rule is expressible, and fixture one exercises
  it.
- The validator checks link-property collisions against the far entity for
  each declared traversal direction.
- Emitters binding evaluation contexts must merge link properties into the
  bound object; the tool contract's traversal declarations carry the link
  name so runtimes know which properties to merge.
