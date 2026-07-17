# ADR 0002: CEL is the guard expression language

Date: 2026-07-17
Status: Accepted

## Context

Action guards need an expression language over target state, action
parameters, and actor attributes. The options were: invent a DSL, adopt
Datalog-style rules, or adopt an existing expression language. Guards must be
non-Turing-complete, statically checkable, readable in review by a domain
owner, and compilable to policy engines.

## Decision

Guards are written in CEL (Common Expression Language). A defined CEL subset
compiles to Cedar `when` clauses; expressions outside the subset fail
compilation with a named reason rather than degrading silently.

## Consequences

- Arkhe inherits CEL's spec, tooling, and implementations (Go, Java, C++,
  Rust) instead of maintaining its own expression semantics. Kubernetes and
  Envoy have already normalised CEL for exactly this kind of gate.
- The CEL-to-Cedar translation is the highest-risk correctness seam in the
  compiler and carries property-based tests for that reason.
- Inventing a "better" guard syntax is out of scope permanently. If CEL
  cannot express a guard, the guard is redesigned or the subset is extended
  by ADR.
