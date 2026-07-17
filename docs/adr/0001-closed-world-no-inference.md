# ADR 0001: Closed-world semantics, no inference in the core

Date: 2026-07-17
Status: Accepted

## Context

Ontology languages descend from two traditions. The description-logic
tradition (OWL) uses open-world semantics and reasoning: an unstated fact is
unknown, and tooling infers what must be true. The validation tradition
(SHACL, JSON Schema, database constraints) uses closed-world semantics: an
unstated fact is false, and tooling checks rather than infers. Arkhe's
consumers are AI systems that need a decidable answer to "may this action
happen right now, against this object, by this actor."

## Decision

Arkhe is closed-world with a unique-name assumption. An unstated fact is
false; two names are two things. Validation is constraint checking, not
reasoning. The v0.1 metamodel permits single-inheritance interfaces for
entity types and nothing else that would require a reasoner. Every language
capability must be implementable in a straightforward validator.

## Consequences

- Guards and invariants are decidable and cheap to evaluate.
- Arkhe cannot express subsumption hierarchies, property chains, or
  equivalence axioms. Domains that need them should use OWL, or wait for a
  separate, explicitly named conformance level that adds richer semantics
  without complicating the core.
- An RDF/OWL export remains on the roadmap for interoperability; export is
  lossy in the inference direction by design.
