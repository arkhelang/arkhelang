# Arkhe

**An ontology language for AI systems.**

Arkhe is a neutral, version-controlled language for declaring what exists in a
domain, how it connects, and what may be done to it, by whom, with what trace,
so that AI systems can be grounded in it, constrained by it, and audited
against it.

One file (or module set) in a git repo is the authoritative artifact.
Compilers emit projections for the systems that need them. The spec is a
contract, never a runtime.

## Why

Three failures fill agentic AI post-mortems: agents that behave differently on
identical inputs, models that assert things that do not exist, and systems
that cannot show an auditor why they did what they did. All three are failures
of meaning. Nothing machine-readable says what exists in the business, how it
connects, and what actions are allowed, by whom, with what trace.

Arkhe declares exactly that, in YAML a domain owner can read and object to:

```yaml
entities:
  FinancialModel:
    keys: [model_id]
    properties: [purpose, tier, owner_desk, last_validated]

actions:
  grant_production_use:
    target: FinancialModel
    guard: months_since(last_validated) <= 12
    authority: head_of_model_risk
    audit: mandatory
```

The entity register bounds what an agent may talk about. Guards pin what it
may do. Authority and audit produce the evidence. One artifact, three failure
modes addressed.

## How it works

```
YAML surface syntax -> canonical JSON model -> tool-contract IR -> emitters
```

The centre of the design is the tool-contract intermediate representation:
one JSON document per action carrying the resolved guard (CEL), authority
binding, approval escalation, audit obligation, and provenance hashes.
Everything downstream is an emitter, and emitters are deliberately thin:
serialization, not semantics. No protocol is load-bearing anywhere in the
core. MCP, OpenAI function schemas, and Google ADK tool definitions are
emitters, never inputs to the metamodel.

## Status

Early development. v0.1 ships exactly four things:

1. The specification (metamodel as JSON Schema, prose, golden-file fixtures)
2. A validator (`arkhe validate`)
3. The tool-contract IR (`arkhe contracts`)
4. One emitter: native library stubs with guard pre-checks and structured
   refusals

Cedar policies, JSON Schema models, and OKF knowledge bundles follow in v0.2+.
Design decisions are recorded as ADRs in [docs/adr/](docs/adr/).

## What Arkhe refuses to do

No execution or write-back. No data storage. No metric definitions. No
workflow or orchestration. No policy evaluation (emit to Cedar; let Cedar
evaluate). No inference. No protocol dependency in the core. The refusals are
the design.

## Prior art

This idea has neighbours, acknowledged plainly. Palantir's Foundry Ontology
is the conceptual prior art: object types, link types, and governed action
types in one system, locked to one platform. Open Ontology (ontology-db) is
an open neighbour building a Lisp-based agent-operations runtime in adjacent
territory. The World Avatar project demonstrated ontology-to-tool compilation
academically (arXiv 2602.03439). Arkhe's contribution is narrower than any of
them: a portable, domain-neutral file format for nouns and governed verbs
together, with thin compilers outward. No first-ever claims are made here.

## Relationship to GATE

Arkhe's author also authors [GATE](https://deterministicagents.ai), an open
framework for governed agent runtimes. Interoperability with GATE is a goal:
a GATE-style runtime is a natural consumer of Arkhe's tool contracts, guard
pre-checks, and audit obligations, and a natural producer of the attestations
that Arkhe's declared effects invite. Exclusivity is not a goal. Arkhe stays
runtime-neutral; GATE gets no privileged hooks in the spec, and anything a
GATE runtime can consume, any other runtime can consume the same way. The
shared authorship is stated here so readers can weigh it.

## Name

Arkhe is from ἀρχή (arkhē): both *first principle* and *rule, authority*. One
word for the source of what is true and the source of who may act, which is
the whole metamodel. The org and package name is **arkhelang** (one word, the
golang pattern); the binary is `arkhe`.

Reserved namespaces: [PyPI](https://pypi.org/project/arkhelang/),
[npm](https://www.npmjs.com/package/arkhelang),
[crates.io arkhelang](https://crates.io/crates/arkhelang) and
[arkhe](https://crates.io/crates/arkhe).

## License

Apache-2.0. Free forever. This project will never charge for anything, and
there is no CLA and never will be; contributions are accepted under the
inbound=outbound norm with DCO sign-off. See [CONTRIBUTING.md](CONTRIBUTING.md).
