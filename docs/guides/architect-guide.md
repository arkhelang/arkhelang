# Arkhe for Architects

Arkhe is an open-source ontology language for AI systems, licensed Apache-2.0, written by Andrew Stevens. The idea is narrow on purpose: one versioned YAML module declares what exists in a domain, how it connects, and what governed actions may be taken against it, by whom, with what trace. A compiler turns that module into a canonical JSON model, then into a tool-contract intermediate representation (IR), then into artifacts that other systems consume. The specification is a contract. It is never a runtime.

This guide is written for the person who has to decide where Arkhe fits in an estate: what it replaces, what it feeds, what it deliberately refuses to do, and where the actual risk in adopting it sits. It draws on the design sketch, the accepted ADRs, and the fixture contracts and reference runtime that ship in v0.1, so the claims here are traceable to what the project has actually built rather than what it aspires to.

## Where Arkhe sits in a reference architecture

The mental model is a compiler, not a service. The ontology repository is the source of truth; everything else is a projection generated from it in CI.

```
model.arkhe.yaml (git, domain-owner reviewable)
        |
        v
  arkhe validate        <- CI gate; findings as file:line:col: [code] path: message
        |
        v
canonical JSON model     (schema-validated, SHA-256 provenance hash, ADR 0007)
        |
        v
  arkhe contracts   -->  tool-contract IR: one *.contract.json per action + per read
        |
        +--> arkhe emit --target=lib --> generated library (typed functions,
        |                                 guard pre-checks, structured refusals)
        |
        +--> (v0.2+, deferred) Cedar policies
        +--> (v0.2+, deferred) JSON Schema / Pydantic models
        +--> (v0.2+, deferred) OKF knowledge bundle
        +--> (later, deferred) MCP / OpenAI function / Google ADK tool manifests
```

And the deployment topology around it:

```
git repo (module + ADRs)
    |  PR: domain owner reads the YAML diff
    v
CI pipeline
    - arkhe validate     (blocks merge on any finding)
    - arkhe contracts     (IR, stamped with module content hash)
    - arkhe emit --target=lib
    |
    +--> published library package --> your agent runtime / application code
    |                                    (calls generated functions; guard
    |                                     pre-checks run before any effect)
    |
    +--> IR artifacts (*.contract.json) --> policy engine, once Cedar emitter ships
    |                                    --> semantic/docs layer, once OKF ships
    |                                    --> protocol emitters, once MCP settles
    |
    +--> audit events, emitted by whatever consumes the contract --> your SIEM
```

Two things are worth noting about this topology. First, nothing in the core has a network address. The IR is a file, not an endpoint, so the compiler never becomes a service you have to keep up. Second, every arrow leaving the IR box is an emitter, and the project's own framing is that emitters are "serialization, not semantics" -- if one needs to do more than serialize, that is treated as evidence the IR itself is incomplete, and the fix goes there.

## The three questions

The design sketch frames every compilation target as an answer to one of three questions an AI system needs answered. It is a useful lens for mapping constructs to concerns when you are deciding what a module needs to declare.

| Question | Answered by | What it looks like in the IR |
|---|---|---|
| What may the system assert (grounding)? | Entity types, keys, properties, link types | The `target.entity`, `properties`, and `traversals` blocks in a read contract |
| What may it do (determinism)? | Action types: guard (CEL), authority, approval escalation | `guard.expression`, `guard.context.traversals`, `authority.claims`, `approval` |
| How is either proven (evidence)? | Audit obligation, declared effects, write surface, provenance hash | `audit.level`/`audit.event`, `effects`, `write_surface`, `provenance.source_hash` |

Grounding bounds the vocabulary an agent can use to talk about the domain. Determinism bounds what it can do to that domain, and under what conditions. Evidence is what lets you or an auditor reconstruct, after the fact, that the first two held. A module that only declares entities gives you grounding without governance; the point of the action-type construct is that it is the same file doing both.

## Design decisions as trade-offs

Every one of these is a place where the project chose a narrower capability in exchange for a property it judged more valuable for the AI-consumption use case. It is worth naming what you give up in each case, since discovering a gap only after building against a module for months is a bad way to find out.

**Closed-world, no inference (ADR 0001).** Arkhe assumes an unstated fact is false and two differently-named things are two things. Validation is constraint checking, not reasoning. Set against OWL and the description-logic tradition, this means Arkhe cannot express subsumption hierarchies, property chains, or equivalence axioms -- if your domain genuinely needs "everything that is-a Vehicle is also a taxable Asset" inferred rather than declared, Arkhe is not built for that, and the ADR says so plainly rather than promising a future reasoner. What it buys back is decidability: a guard evaluates to true or false in constant, predictable cost, which matters when the caller is an agent deciding in real time whether it may act.

**CEL, not a bespoke DSL (ADR 0002).** Guards are Common Expression Language, the same non-Turing-complete expression language Kubernetes and Envoy use for policy-shaped checks, with implementations in Go, Java, C++, and Rust. The project treats "invent a better guard syntax" as permanently out of scope. This is a bet that borrowed maturity beats bespoke expressiveness, and it pays off specifically because CEL has a defined subset that compiles to Cedar `when` clauses -- the ADR calls the CEL-to-Cedar translation the highest-risk correctness seam in the compiler, which is why it is the one seam called out for property-based testing.

**The two-hop traversal bound and link properties (ADR 0005, ADR 0006).** A guard can traverse a declared link at most two hops, and aggregation over what it finds uses CEL's native `all`/`exists`/`filter`/`size` macros rather than a bespoke aggregation syntax. The fixture guard for granting production use of a financial model is a working example of the bound in practice:

```
target.status == "validated"
  && months_since(target.last_validated) <= 12
  && target.reviewed_by.all(r, r.findings.all(f, f.status != "open" || f.severity == "low"))
```

That is two traversals (`target.reviewed_by`, then `r.findings`) each carrying `many: true`, evaluated against the whole collection, not "the most recent review" -- ordering over collections is explicitly deferred to v0.2 (ADR 0005), so any rule needing "latest" has to be rewritten as a quantification for now. A traversed link also carries its own properties into the bound object, not just the far entity's -- the model-risk fixture's tier-1 invariant needs "the model declares a primary data feed," a fact that lives on the `consumes` link's `criticality` property, not on either endpoint (ADR 0006).

**Runtime-neutrality: why MCP is not load-bearing (ADR 0003).** The obvious 2026 design would compile straight to MCP tool definitions. Arkhe deliberately does not: MCP, OpenAI function schemas, and ADK tool definitions are all emitters off the same IR, none of them mandatory, none of them inputs to the metamodel. The consequence you can verify directly: the reference runtime's guard-refusal demo runs as a plain Python function call against a generated library, with no server and no wire protocol anywhere in the path. The cost is that you do not get a ready-made MCP manifest in v0.1; the project's stated reasoning is that coupling the core to a protocol still settling its own extensions framework would make protocol churn the project's problem rather than the emitter's.

**The canonical hash as a conformance target (ADR 0007).** Every contract carries `provenance.source_hash`, a SHA-256 computed over the module's canonical form: schema-validated document, CEL expressions folded to single-space whitespace, JSON serialized with sorted keys and no insignificant whitespace. This exists because YAML 1.1 and 1.2 parsers disagree on scalar coercion, and a hash computed over raw parser output would not be portable across implementations. The Python reference implementation exists now; Rust and Go ports are planned, and the hash is what lets you prove, mechanically, that a Go compiler and a Python compiler produced the same contract from the same module.

## Integration patterns

**Consuming contracts from your own runtime.** The contract is designed to be complete: a runtime should need nothing outside the JSON document plus its own instance data to decide and act. Reading `grant_production_use.contract.json`, a consuming runtime needs to provide bindings for `target` (the entity plus its declared traversals, depth-bounded and with link properties merged in), evaluate the guard, check `authority.claims` against the actor, check `approval` if present, apply `effects` within the declared `write_surface`, and emit `audit` if the level is not `none`. The Python reference runtime (`arkhelang.runtime`) does exactly this, and its docstring is explicit that it is "not a production runtime; it is the executable meaning of a contract" -- useful as a readable spec of the execution semantics, not as something to run in production. Its `execute()` function is worth reading end to end: it checks every effect path before applying any of them, so a refusal partway through can never leave a partial write behind, and refusals name the first failing guard clause by splitting on top-level `&&` (never `||`, since CEL precedence would make that split unsound) so an operator gets a legible reason rather than a boolean.

**Identity claims binding to your IdP groups.** `authority.claims` in the compiled contract is a small map, in the fixture `{"groups": "mrm/head"}`, checked against an actor object's own `claims`. The role declaration in the source module is what binds to your identity provider -- OIDC claim patterns are resolved at compile time -- so at runtime the check is a plain claims comparison, not a call out to your IdP. Approval escalation follows the same shape, with a second, distinct authority and an explicit four-eyes check that the approver is not the same actor.

**Audit events into your SIEM.** `audit.level` (`none`, `standard`, or `mandatory`) and a versioned `audit.event` name (`model_risk.grant_production_use.v1`) are the only obligations the contract states. What a runtime does with that event, and where it sends it, is left to the runtime. The spec-sketch calls this out as an open question rather than a settled answer: the minimum bar is that compiled tools emit a structured event schema, and the sink is a deployment decision, not a spec decision.

**What a GATE-class runtime adds.** Arkhe's author also authors GATE, a separate open framework for governed agent runtimes, and the README states the relationship directly: a GATE-style runtime is a natural consumer of Arkhe's contracts and a natural producer of attestations for the effects Arkhe only declares, but Arkhe grants it no privileged hooks in the spec. Anything a GATE runtime can do with a contract, any other runtime can do the same way. Whether attestation of effects becomes part of the Arkhe specification or a separate document that governed runtimes implement is explicitly unresolved; the design sketch leans toward keeping it a separate document.

## Governing the ontology itself

The module lives in git and the project treats the review discipline around it as part of the design, not an afterthought. Every accepted decision about the language is a numbered ADR (seven so far, covering closed-world semantics, the choice of CEL, the IR-as-centre decision, v0.1 scope, guard and effect semantics, link properties in traversals, and the canonical hash), each with context, decision, and consequences stated separately, so a reviewer can trace why a rule exists rather than just what it is.

The golden-file suite is described as the specification, not a test of it: example modules with expected canonical JSON, IR, and emitter output for every target. Two fixture domains ship deliberately -- financial-services model risk and mining maintenance -- specifically so the metamodel is checked against a second domain before anyone concludes it generalises from one. For a language that expects multiple implementations over time, the canonical hash gives a conformance target that does not depend on trusting a prose description: a port either reproduces the same bytes from the same module, or it does not.

## Adoption path

Start with one domain and one module. The fixture pattern in the repository is the template: a single `.arkhe.yaml` file per domain, entities and links first, then the governed actions that matter, validated in CI before anything downstream depends on it. Put `arkhe validate` in your pipeline as a gate -- it prints findings as `file:line:col: [code] path: message` for humans, or `--json` for tooling -- before you generate contracts from anything.

Defer everything past the four things v0.1 actually ships: the spec, the validator, the contracts generator, and one library emitter. Cedar policy generation, JSON Schema/Pydantic models, the OKF knowledge bundle, and every protocol emitter (MCP, OpenAI, ADK) are v0.2-and-later by explicit decision (ADR 0004), not by oversight. If your integration plan depends on one of those today, that dependency is premature; plan the pilot around the library emitter and your own runtime instead.

## Prior art

The project names its neighbours rather than claiming to be first. Palantir's Foundry Ontology is the conceptual prior art -- object types, link types, and governed action types in one system -- with the acknowledged difference that Foundry locks the model to its own platform. Open Ontology (ontology-db) is described as an open neighbour, a Lisp-based DSL with entities, relationships, actions, and Datalog constraints bundled into a full agent-operations runtime, which is a different design choice from shipping a portable spec with thin emitters. The World Avatar project is credited with demonstrating ontology-to-tool compilation academically. No first-ever claims are made anywhere in the project's own framing, and it is worth taking that at face value when you are weighing what is genuinely new here against what is a narrower, more portable take on an existing idea.

## Limits, plainly

v0.1 is a language and a compiler. It is not execution infrastructure beyond the reference runtime, and that runtime says of itself that it is not meant for production. Guard expressions may call exactly three stdlib functions (`months_since`, `days_since`, `today`); anything else requires a superseding ADR. There is no ordering concept yet, so "the latest review" cannot be expressed as a guard until v0.2 adds one. Effects can reach the action's target or at most one hop across a declared link, nothing further. Cedar policy compilation, JSON Schema/Pydantic model generation, the OKF documentation bundle, and every protocol emitter are deferred, not partially built. If your architecture needs any of those today, the reasonable approach is to treat Arkhe as a language and IR you can start writing against now, with the emitters your integration needs arriving on a roadmap worth tracking rather than assuming.

---

More: [arkhelang.org](https://arkhelang.org) - [github.com/arkhelang/arkhelang](https://github.com/arkhelang/arkhelang)
