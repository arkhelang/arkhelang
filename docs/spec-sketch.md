# Arkhe: Design Sketch (v0.1)

This document is the working design for Arkhe v0.1. It precedes the formal
specification; where the two disagree once the spec exists, the spec wins.

Naming: **Arkhe** is the language, from ἀρχή, both "first principle" and
"rule, authority", which is the metamodel in one word. **arkhelang** is the
org and package name (one word, the golang pattern). **`arkhe`** is the
binary; **`akl`** may ship as an alias (one package, two console scripts).

## Purpose

**The ontology language for AI systems.** A neutral, version-controlled language for declaring what exists in a domain, how it connects, and what may be done to it, by whom, with what trace, so that AI systems can be grounded in it, constrained by it, and audited against it. One file (or module set) in a git repo is the authoritative artifact. Compilers emit projections for the systems that need them. The spec is a contract, never a runtime.

The positioning is deliberate and asymmetric: the *language* is domain-neutral (guards, authorities, and link types have nothing AI-specific in them, and welding AI concepts into a metamodel is the classic layering mistake), but the *purpose, emitters, and story* are AI-first. Agents are the first consumer that makes ontologies economically necessary rather than architecturally virtuous. Every compilation target exists to answer one of three questions for an AI system: what may it assert (grounding), what may it do (determinism), and how is either proven (evidence).

A second purpose falls out of the first: the ontology is the bridge between structured and unstructured data. Grounding an LLM is the act of binding unstructured text to structured referents; the OKF emitter works that seam from the structured side, and evidence references (open questions, below) work it from the unstructured side.

The differentiator against the July 2026 landscape: OSI/Ossie, LinkML, and every open semantic layer stop at nouns; Cedar, OpenFGA, and Microsoft's Agent Control Specification start at permissions and controls with no domain model; Palantir has both, locked to Foundry. One open near-neighbour exists, "Open Ontology" (ontology-db, 2026 research preview): a Lisp DSL with entities, relationships, actions, and Datalog constraints, bundled into a full agent-operations runtime. Arkhe's remaining distinct ground: reviewable YAML a domain owner can object to, CEL guards with an explicit authority role per action, thin emitters (Cedar, JSON Schema, OKF) instead of a runtime, and spec-never-runtime scope. Prior art is acknowledged plainly in the README: Palantir conceptually, Open Ontology as a neighbour, the World Avatar OWL-to-MCP paper mechanically. No "first ever" claims.

## Stance

- **Closed-world, unique-name assumption.** An unstated fact is false; two names are two things. Validation is constraint checking, not reasoning. Business operations need an answer to "may this happen right now", and closed-world semantics is the only footing that question makes sense on.
- **No inference in v0.1.** Single-inheritance interfaces for entity types, nothing else. Every capability the language ships must be implementable in a straightforward validator; anything that requires a reasoner is out. If richer semantics ever arrive, they arrive as a separate, clearly-named conformance level rather than complexity in the core.
- **Modules, imports, annotations.** Imports with well-defined merge semantics and semver ranges. Annotations on every declaration, because generated descriptions (docs, tool descriptions) come from them. A role is both an authority reference and a declarable entity.
- **Surface syntax YAML, canonical model JSON, metamodel published as JSON Schema.** Diff-able, reviewable by a domain owner, machine-checkable. An RDF/OWL export target is on the deferred list for interop with existing semantic-web tooling.

## Metamodel

Five declaration kinds:

1. **Entity types.** Keys (composite allowed), properties (typed, enums inline, optional units), derived properties (expression over own properties only, v0.1), lifecycle states optional.
2. **Link types.** First-class, named, directed, with cardinality and their own properties (the association-class move; LinkML's class-ranged slots are too weak here, Foundry's link types are the model to beat).
3. **Action types.** The differentiator. Fields: `target` (entity or link type), `parameters` (typed), `guard` (expression over target state, parameters, and actor attributes), `authority` (role reference), `approval` (optional second-authority escalation with threshold expression), `audit` (none | standard | mandatory), `effects` (declared postconditions on target state; declared, not executed).
4. **Roles/authorities.** Declared, not inferred; may bind to external identity claims (OIDC claim patterns) at compile time.
5. **Invariants.** Cross-entity constraints checked at validation time (CEL expressions over the instance graph).

Modules import modules; a compiled artifact records the full resolved module set and content hashes, so every emitted tool or policy is traceable to a git commit.

## Guard expression language

**CEL (Common Expression Language).** Non-Turing-complete, formally specified, battle-tested in Kubernetes and Envoy, implementations in Go/Java/C++/Rust. A defined CEL subset compiles cleanly to Cedar `when` clauses; anything outside the subset fails compilation with a named reason rather than degrading silently. Writing our own expression language is the classic way projects like this drown.

## The tool-contract IR (the centre of the design)

The compiler's primary output is a neutral intermediate representation, the **tool contract**: one JSON document per action type carrying the resolved action name, parameter schema, guard (CEL, canonical form), authority binding, approval escalation, audit obligation, effects declaration, and provenance (module set + content hashes). Read contracts (get-by-key, traverse-link per entity and link type) are generated alongside. Descriptions are generated from annotations, so an agent's view of the world is exactly the ontology's.

The IR is part of the spec and lives in the golden files. Everything downstream of it is an emitter, and emitters are deliberately boring: serialization, not semantics. No protocol is load-bearing anywhere in the core. The guard-refusal demo works as a plain function call against the generated native library, with no server and no wire protocol involved.

## Compilation pipeline

YAML surface syntax → canonical JSON model → tool-contract IR → emitters.

**v0.1 ships exactly four things, deliberately (see ADR 0004):**

1. The **spec** (metamodel JSON Schema + prose + golden files).
2. The **validator** (`arkhe validate`).
3. The **tool-contract IR** (`arkhe contracts`).
4. **One emitter: native library stubs** in one language, typed functions per action with guard pre-checks and structured refusals. This is the demo target; the guard-refusal demo is the release announcement.

**Next, in order (v0.2+):**

- **Cedar schema + policies.** Entities/actions to Cedar schema; guards+authority+approval to policies. We do not evaluate policy, ever; Cedar does.
- **JSON Schema / Pydantic models.** For pipeline and application code.
- **OKF bundle (Open Knowledge Format).** The knowledge projection for LLM consumption: one concept file per entity, link, and action type; frontmatter from annotations; property tables in the body; markdown links mirroring link types; guards rendered readably with rationale. Always generated, never hand-edited; regenerates on every ontology change; OKF's visualizer doubles as the docs site. Division of labour: the IR is what an agent may do, the OKF bundle is what an agent should know, one ontology behind both. (OKF is v0.1, June 2026, Google-published; markdown-plus-frontmatter, so the downside if it stalls is a good docs generator.)

Protocol emitters, explicitly thin and explicitly later: MCP tool manifest (deferred until the MCP extensions framework settles; the July 2026 release candidate is still moving), OpenAI function schemas, Google ADK tool definitions. Each should be tens of lines off the IR; if an emitter needs more, the IR is missing something and the fix belongs there.

Deferred beyond that, in rough order: OSI semantic-model projection (nouns only, their spec), SQL DDL, OWL/RDF export (open source should be open and interoperable; this keeps a bridge to existing semantic-web tooling), OpenFGA model.

## Refusals (scope fence for v0.1)

No execution or write-back. No data storage. No metric/measure definitions (compose with OSI; do not compete). No workflow or orchestration. No policy evaluation. No inference. No protocol dependency in the core: MCP and its siblings are emitters, never inputs to the metamodel. Each refusal is a sentence in the README, because the refusals are the design.

## Conformance and testing

A golden-file test suite is the spec: example ontologies with expected canonical JSON, tool-contract IR, and emitter outputs for every target. Fixture one is a financial-services model-risk domain; fixture two is a mining maintenance domain (the second domain is what stops the metamodel overfitting to the first). The flagship module, developed once the language stabilises, is an **AI-estate ontology written in Arkhe**: models, agents, tools, datasets, evaluations, guardrails, incidents, approvals, with governed actions like "promote model to production" guarded on eval results and open findings. The first thing the ontology language for AI describes is AI itself, and its OKF projection is documentation an auditor can walk. (Adjacent fragments exist: CycloneDX ML profile, SPDX AI profile, MLCommons Croissant for datasets, model cards. The module composes with them as evidence references rather than competing.) The validator CLI (`arkhe validate`, `arkhe contracts`, `arkhe emit --target=lib` in v0.1; `cedar|jsonschema|okf` and protocol targets join `emit` as they land; `akl` installs as an alias of `arkhe`) is the reference implementation. Property-based tests on the CEL-to-Cedar translation, since that seam is where correctness bugs will live.

## Open questions (the fun ones)

- Actions targeting **links** (approve a `consumes` relationship?), probably yes, syntax cost is low.
- **Temporal validity** on links and properties (as-of semantics), v0.2 at the earliest, but the metamodel should not preclude it.
- **Effects**: declared postconditions invite verification (did the tool actually do that?). Is a runtime attestation contract in scope for the spec, or a separate document that governed runtimes implement? Leaning: separate document. Interoperability with GATE (same author) is a goal here and exclusivity is not: the attestation contract, if it exists, is runtime-neutral, and GATE gets no privileged hooks. See the README's "Relationship to GATE".
- **LinkML relationship**: embed Arkhe actions as a LinkML extension and inherit their ecosystem, or standalone spec with a LinkML import path? Standalone-with-import keeps the actions semantics unpolluted; worth one prototype each way.
- **Audit sink contract**: `audit: mandatory` must mean something testable. Minimum: compiled tools emit a structured event schema; where it goes is the runtime's problem.
- **Evidence references (the structured/unstructured bridge)**: a property type `document` carrying a URI plus content hash, so an entity can bind to the unstructured artifact behind it (a ValidationReview to its PDF report, a dataset to its Croissant record, a model to its card). Likely v0.1: the type and hash semantics only; retrieval, chunking, and indexing are explicitly a consumer concern. This is what makes the ontology the join point between the structured graph and the document corpus.
