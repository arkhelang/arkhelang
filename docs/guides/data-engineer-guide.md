# Arkhe for Data Engineers

You already know schema-as-code. If you have written a dbt model with a `schema.yml` describing columns and tests, or a LinkML model describing classes and slots, Arkhe will feel familiar for about half a page, and then it will diverge. dbt and LinkML describe shape: what a table or record looks like, and maybe what constraints it must satisfy. Arkhe describes shape plus verbs: alongside the entities, it declares the links between them as first-class objects, and it declares the actions that may change them, gated by a guard expression, bound to an authority, and required to leave an audit trail.

Arkhe is an open-source ontology language for AI systems (Apache-2.0, written by Andrew Stevens). One version-controlled YAML file is the authoritative model. A toolchain validates it, compiles it to a neutral intermediate representation (the "tool contract"), and emits a generated library that enforces the contract in code. This guide walks the anatomy of a real module, the closed-world rules that catch people out, the full CLI surface with captured output, the error catalogue, and the shape of the IR, using excerpts from the project's own model-risk fixture throughout. Nothing here is invented; every sample is taken from the fixture module or the generated artefacts that ship alongside it.

## Why a data engineer should care

If you build pipelines that feed an agent, or pipelines an agent is allowed to trigger, you have almost certainly hand-rolled the equivalent of Arkhe already: a table of allowed state transitions, a permissions check scattered across a few services, an audit log that someone bolted on after the first incident. Arkhe asks you to write that down once, in a form a domain owner can read and object to, and then generates the enforcement code and the machine-readable contract that an agent's tool layer can consume. The ontology is not a runtime. It is closer to a schema migration file that also happens to define your RBAC and your write paths.

## The full anatomy of a module

The example throughout is `model-risk.arkhe.yaml`, a financial-services model risk management module. It governs the lifecycle of quantitative models: ownership, validation, findings, change control, and promotion to production.

### Module header

```yaml
module: model_risk
version: 0.1.0
arkhe: "0.1"
annotations:
  title: Model Risk Management
  description: >
    Governance of financial models across their lifecycle: ownership,
    validation, findings, change control, and production use. Guards encode
    the control logic a model risk function enforces; regimes such as
    SR 11-7 or SS1/23 are context, not dependencies.
```

`module` is the namespace (lowercase, snake_case). `version` is the module's own semver. `arkhe` pins the spec version the file is written against, currently `"0.1"`, and the validator refuses to process a file pinned to a version it does not implement. `annotations` are free-form key-value strings attached to almost every declaration; they are not decoration, they are the source for generated docs and tool descriptions downstream, so treat them as load-bearing text, not comments.

### Roles

```yaml
roles:
  model_owner:
    annotations:
      description: First-line owner of a model, accountable for its use.
    claims:
      groups: "mrm/model-owners"
  head_of_model_risk:
    annotations:
      description: Accountable executive for model risk.
    claims:
      groups: "mrm/head"
```

Roles are declared, not inferred, and `claims` are identity-claim patterns the role binds to at compile time (an OIDC group claim, here). An action's `authority` field references a role by name.

### Entities

```yaml
entities:
  FinancialModel:
    annotations:
      description: >
        A quantitative model used for pricing, risk, capital, or financial
        crime detection. The unit of governance in this module.
    keys: [model_id]
    properties:
      model_id: { type: string }
      name: { type: string }
      purpose:
        type: enum
        values: [pricing, risk, capital, aml]
      tier:
        type: enum
        values: [1, 2, 3]
        annotations:
          description: Materiality tier; 1 is highest.
      status:
        type: state
        values: [draft, in_validation, validated, production, retired]
        initial: draft
      commissioned_date: { type: date }
      last_validated: { type: date, optional: true }
```

The scalar property types are `string`, `int`, `number`, `bool`, `date`, `datetime`, and `document`. `document` is a forward-looking type: a URI plus content hash binding an entity to an unstructured artefact (a review's PDF, a model card), still narrow in v0.1 (type and hash semantics only, retrieval is a consumer concern).

Beyond the scalars there are two structured property kinds. `enum` is a closed value set with no ordering semantics of its own. `state` is a distinct kind: it also carries a closed value set, but it additionally declares an `initial` value and, as covered below, it can only be written by an action's declared effects, never by ordinary assignment. `keys` names the properties (composite allowed) that identify an instance.

### Links

```yaml
links:
  owned_by:
    annotations:
      description: Each model is owned by exactly one desk.
    from: FinancialModel
    to: TradingDesk
    reverse: models
    cardinality: many_to_one
    properties:
      since_date: { type: date }

  consumes:
    annotations:
      description: Models consume market data feeds.
    from: FinancialModel
    to: MarketDataFeed
    reverse: consumed_by
    cardinality: many_to_many
    properties:
      criticality:
        type: enum
        values: [primary, fallback]
```

This is where Arkhe stops looking like dbt or LinkML. A link is a first-class named object, directed (`from` / `to`), typed by `cardinality` (`one_to_one`, `many_to_one`, `one_to_many`, `many_to_many`), and it can carry its own properties, the association-class move dbt relationships and LinkML class-ranged slots do not give you. `owned_by` reads `FinancialModel.owned_by` toward `TradingDesk` and, thanks to `reverse: models`, also `TradingDesk.models` back toward every model that desk owns. Traversal names, not the underlying link, are what a guard or invariant uses.

### Actions

```yaml
actions:
  grant_production_use:
    annotations:
      description: >
        Promote a validated model to production. Requires a current
        validation and no open findings above low severity anywhere in the
        model's review history.
    target: FinancialModel
    guard: >
      target.status == "validated"
      && months_since(target.last_validated) <= 12
      && target.reviewed_by.all(r,
           r.findings.all(f,
             f.status != "open" || f.severity == "low"))
    authority: head_of_model_risk
    audit: mandatory
    effects:
      - target.status: production

  approve_model_change:
    annotations:
      description: >
        Approve a proposed change. Tier-1 models escalate to the head of
        model risk for second approval.
    target: ModelChange
    guard: target.status == "proposed" && target.applies_to.status != "retired"
    authority: model_risk_officer
    approval:
      when: target.applies_to.tier == 1
      authority: head_of_model_risk
    audit: mandatory
    effects:
      - target.status: approved
```

This is the differentiator. Every action declares: `target` (the entity or link type it acts on), optional `parameters` (typed, same property grammar as entity properties), `guard` (a CEL boolean expression over the target, parameters, and traversals), `authority` (which role may invoke it), an optional `approval` block (a second-authority escalation gated by its own `when` condition), `audit` (`none`, `standard`, or `mandatory`), and `effects` (declared postconditions on state, not executed code). `grant_production_use` shows a guard traversing two hops and calling the stdlib function `months_since`; `approve_model_change` shows escalation, where tier-1 model changes additionally require the head of model risk's sign-off.

### Invariants

```yaml
invariants:
  tier1_production_has_primary_feed:
    annotations:
      description: Tier-1 production models declare a primary data feed.
    over: FinancialModel
    check: >
      !(entity.tier == 1 && entity.status == "production")
      || entity.consumes.exists(c, c.criticality == "primary")
```

Invariants are cross-entity constraints checked at validation time, expressed the same way as guards but rooted at `entity` rather than `target`. `check` here reads the `criticality` property directly off the `consumes` link, an example of link-property traversal (more below).

## The closed-world rules that will surprise you

Arkhe is deliberately closed-world (ADR 0001): an unstated fact is false, two names are two things, and every rule the language ships must be checkable by a straightforward validator rather than a reasoner. That stance produces several rules that read as strict the first time you hit them.

**State properties are only writable via effects.** A `type: state` property is not just an enum with an `initial` value bolted on. It is the only property kind the validator lets you write through a declared action effect; there is no "just set the field" path, structurally or semantically. If you want a status field a pipeline can update directly outside an action, model it as a plain enum, not a state, and accept that the language then gives you no lifecycle governance over it.

**Keys must be required, non-state, declared properties.** The validator rejects a key that references an undeclared property (`key-ref`), a state-typed property (`key-type`), or an optional property (`key-type`). You cannot key an entity on something that might be null or that only changes via an action's effect.

**Guard traversal is bounded at two hops.** `grant_production_use`'s guard walks `target.reviewed_by` (hop one, model to review) then `r.findings` (hop two, review to finding). A third hop trips `guard-traversal-depth`. This is a hard ceiling, not a soft warning, and it is one reason "give me the latest anything" rules do not fit v0.1: there is no ordering concept yet (deferred to v0.2 per ADR 0005), so "most recent review" has to be rewritten as a quantification over the whole collection or dropped.

**The stdlib is exactly three functions.** `months_since(date)`, `days_since(date)`, and `today()`. That is the entire Arkhe-specific surface beyond core CEL (plus a small allow-list of CEL built-ins: `size`, `has`, `int`, `string`, `bool`, `double`, and the macros `all`, `exists`, `exists_one`, `filter`, `map`). Calling anything else in a guard trips `guard-unknown-function`. Extending the stdlib requires a superseding ADR; do not expect to reach for arbitrary date math.

**Optional parameters cannot drive an effect.** If an action parameter is `optional: true`, using it as an effect value (`target.status: params.foo`) is a validation error, because the write would be undefined when the caller omits the parameter. Effects need a value that is always present: a literal, a required parameter, or a same-hop target property.

**Effects reach at most one hop.** `record_validation_outcome` sets `target.assesses.last_validated` and `target.assesses.status`, one hop across the `assesses` link from `ValidationReview` to `FinancialModel`. A two-segment effect path beyond that (`target.a.b.c`) fails structural validation before semantic checks even run. Every contract's write surface (every entity type an action may modify) is generated data, not documentation, precisely so a policy engine or an auditor does not have to re-derive it from the guard.

**Reverse names and collision rules.** A link's `reverse:` name is what lets you traverse from the target side (`assesses` goes review-to-model; `reviewed_by` goes model-to-review). Two collision rules are enforced: a link property cannot share a name with a property of the entity reached through the traversal (`name-collision` on the link declaration, because it would silently shadow one side), and a link or reverse-link traversal name cannot collide with a plain property name on the entity it attaches to.

## Complete CLI reference

Three subcommands: `validate`, `contracts`, `emit`. Both `arkhe` and the alias `akl` install the same binary. Everything below is captured from a live run against the fixture, `PYTHONPATH=src python -m arkhelang.cli`, run from `packages/python`.

### `arkhe validate`

```
usage: arkhe validate [-h] [--json] path

positional arguments:
  path        A .arkhe.yaml module, or a directory to scan recursively

options:
  -h, --help  show this help message and exit
  --json      Machine-readable output
```

A single valid file:

```
$ arkhe validate model-risk.arkhe.yaml
arkhe 0.1.0.dev1 validate

  module                                  findings  status
  model-risk.arkhe.yaml                          0  valid

  1 module: 1 valid, 0 invalid
```

Exit code 0. Point `validate` at a directory instead of a file and it scans recursively for `*.arkhe.yaml` and reports one row per module, which is the shape you want for a CI job that validates an entire modules directory in one pass. Here it is run against the project's own catalogue of deliberately invalid fixtures:

```
$ arkhe validate fixtures/invalid/
arkhe 0.1.0.dev1 validate

  fixtures/invalid/action_without_guard.arkhe.yaml:21:3: [struct] actions/activate: missing required field 'guard'
     21 |   activate:
            ^
  fixtures/invalid/bad_audit_level.arkhe.yaml:25:5: [struct] actions/activate/audit: 'sometimes' is not one of: none, standard, mandatory
     25 |     audit: sometimes
              ^
  fixtures/invalid/state_without_initial.arkhe.yaml:14:7: [struct] entities/Widget/properties/status: missing required field 'initial'
     14 |       status:
                ^
  fixtures/invalid/wrong_spec_version.arkhe.yaml:4:1: [struct] arkhe: this validator implements Arkhe spec '0.1'; the module declares '0.9'
      4 | arkhe: '0.9'
          ^

  module                                                findings  status
  fixtures/invalid/action_without_guard.arkhe.yaml             1  INVALID
  fixtures/invalid/bad_audit_level.arkhe.yaml                  1  INVALID
  fixtures/invalid/state_without_initial.arkhe.yaml            1  INVALID
  fixtures/invalid/wrong_spec_version.arkhe.yaml               1  INVALID

  15 modules: 0 valid, 15 invalid
```

(Trimmed to four rows for space; all fifteen fixtures fail with exactly one finding each, which is itself part of the fixture's contract: a validator that lets any of them pass is nonconformant.) Exit code 1. Each finding prints as `path:line:col: [code] json-path: message`, followed by the offending source line and a caret under the exact column, which is what makes this usable from an editor's problem matcher or a pre-commit hook without piping through anything else.

`--json` gives the same information machine-readably, one entry per file:

```
$ arkhe validate fixtures/invalid/state_without_initial.arkhe.yaml --json
{
  "fixtures/invalid/state_without_initial.arkhe.yaml": {
    "ok": false,
    "findings": [
      {
        "code": "struct",
        "path": "entities/Widget/properties/status",
        "message": "missing required field 'initial'",
        "line": 14,
        "column": 7
      }
    ]
  }
}
```

Exit code 2 is reserved for usage errors and unreadable input (a path that does not exist, a directory with no `.arkhe.yaml` files), distinct from exit code 1 for a module that parses but fails validation.

### `arkhe contracts`

```
usage: arkhe contracts [-h] [--out DIR] file

Validate the module, then emit one JSON contract per action and a read
contract per entity.

  --out DIR   Write one <name>.contract.json per contract into DIR
              (default: print a single JSON object to stdout)
```

Without `--out`, it prints one JSON object keyed by contract name to stdout, which is convenient for piping into `jq` but awkward to diff. With `--out`, it writes one file per contract and prunes anything stale:

```
$ arkhe contracts model-risk.arkhe.yaml --out expected/
12 contracts written to expected/
```

The fixture yields twelve: six read contracts (one `<Entity>.get.contract.json` per entity type) and six action contracts (one per declared action). Re-running against a directory that already contains an unrelated leftover `.contract.json` file deletes it as part of the write, confirmed by dropping an extra file into the output directory and re-running: it disappears. That pruning is what makes `--out` safe to point at a committed `expected/` directory that also serves as your CI golden-file target, instead of accumulating orphaned contracts from renamed or deleted actions.

`contracts` refuses to run against an invalid module; it validates first and, on failure, prints findings to stderr and exits 1 rather than emitting a partial or stale IR.

### `arkhe emit`

```
usage: arkhe emit [-h] [--target {lib}] [--out FILE] file

Validate, generate contracts, then emit for a target. v0.1 target: lib (a
Python module of guarded functions).

  --target {lib}  Emitter target (default: lib)
  --out FILE      Output path (default: <module>_lib.py beside stdout)
```

`lib` is the only target in v0.1. It generates a self-contained Python module: the compiled contracts embedded as JSON, the resolved module document embedded alongside them, and one typed function per action:

```python
def grant_production_use(world, model_id, *, actor, approver=None):
    "Promote a validated model to production. Requires a current validation and no open findings above low severity anywhere in the model's review history."
    params = {}
    return execute(_CONTRACTS["model_risk.grant_production_use"], world, model_id,
                   actor=actor, params=params, approver=approver)


def waive_finding(world, finding_id, justification, *, actor, approver=None):
    'Waive a finding with justification. High-severity findings cannot be waived; they must be remediated.\n\njustification: string'
    params = {"justification": justification}
    params = {k: v for k, v in params.items() if v is not None}
    return execute(_CONTRACTS["model_risk.waive_finding"], world, finding_id,
                   actor=actor, params=params, approver=approver)
```

`{caption="Listing 1. Generated action functions in the emitted Python library, from model-risk.arkhe.yaml"}`

Every emitted function funnels through a shared `execute()` in `arkhelang.runtime`, which checks authority claims, evaluates the guard, walks the approval escalation if one is declared, applies the effects, and emits an audit event, refusing with a structured reason (`refused`, `action`, `failed_clause`, `explanation`) if any check fails. `emit` also refuses to run against an invalid module, same as `contracts`. This is the guard-refusal demo the project leads with: calling `grant_production_use` against a model that has not been validated in the last twelve months gets a plain function-call refusal, no server, no wire protocol.

## The error catalogue

Findings carry a stable `code`, a JSON-path-style `path`, and a human `message`. Verified directly against `validate.py` and `guards.py` in `packages/python/src/arkhelang/`:

| Code | Meaning |
|---|---|
| `yaml` | The file does not parse as YAML, including duplicate mapping keys, which Arkhe's loader rejects rather than silently merges |
| `struct` | The document does not match the v0.1 JSON Schema: missing required fields, wrong enum values, pattern mismatches on names |
| `key-ref` | An entity key references a property that is not declared |
| `key-type` | A key references a state-typed or optional property, neither of which is allowed |
| `state-initial` | A state property's `initial` value is not among its own declared `values` |
| `link-ref` | A link's `from` or `to` references an entity type that is not declared |
| `name-collision` | A link property collides with a far-entity property, or a link/reverse traversal name collides with an existing property or traversal name on an entity |
| `action-ref` | An action's `target`, `authority`, or approval `authority` references something not declared |
| `effect-path` | An effect's path segment is not a property of the target, or not a valid traversal from it |
| `effect-cardinality` | An effect traverses toward a many-valued collection; effects must address exactly one object |
| `effect-value` | An effect's value is not among a closed property's declared values, references an undeclared parameter, or references an optional parameter (which cannot drive a write) |
| `effect-duplicate` | The same effect path is assigned more than once in one action |
| `invariant-ref` | An invariant's `over` references an entity type that is not declared (present in source; not called out in the CLI's summarised help text, which only lists `effect-*` and `guard-*` as groups) |
| `guard-syntax` | The guard expression does not parse as CEL at all |
| `guard-unknown-name` | A guard references a variable, path segment, or parameter that is not bound in scope |
| `guard-unknown-function` | A guard calls a function or method outside the stdlib and the small CEL built-in allow-list |
| `guard-traversal-depth` | A guard traversal exceeds the two-hop bound (ADR 0005) |
| `guard-index` | A guard uses bracket access with a non-literal index, which is not analysable in v0.1 |
| `guard-macro-base` | A CEL macro (`all`, `exists`, `filter`, `map`, `exists_one`) is applied to something that is not a collection |
| `guard-macro-arity` | A macro is called with other than exactly two arguments (`.macro(var, expr)`) |

Note that the CLI's own `--help` text summarises the effect and guard families as `effect-*` and `guard-*` rather than listing every code; the table above expands both families and adds `invariant-ref`, which the help text omits, against the actual implementation.

## The IR: what a contract contains

`arkhe contracts` is the point of the whole exercise: the tool-contract IR is the specification's centre (ADR 0003), and everything downstream, including the `lib` emitter, is deliberately thin serialisation over it. Walking `grant_production_use.contract.json` field by field:

```json
{
  "arkhe_contract": "0.1",
  "kind": "action",
  "name": "model_risk.grant_production_use",
  "description": "Promote a validated model to production. ...",
  "target": {
    "entity": "model_risk.FinancialModel",
    "keys": ["model_id"]
  },
  "parameters": {},
  "guard": {
    "language": "cel",
    "expression": "target.status == \"validated\" && months_since(target.last_validated) <= 12 && target.reviewed_by.all(r, r.findings.all(f, f.status != \"open\" || f.severity == \"low\"))",
    "context": {
      "target": "model_risk.FinancialModel",
      "traversals": [
        { "path": "target.reviewed_by", "link": "model_risk.assesses", "direction": "reverse", "to": "model_risk.ValidationReview", "many": true },
        { "path": "r.findings", "link": "model_risk.raised_in", "direction": "reverse", "to": "model_risk.Finding", "many": true }
      ],
      "stdlib": ["months_since"]
    }
  },
  "authority": { "role": "model_risk.head_of_model_risk", "claims": { "groups": "mrm/head" } },
  "approval": null,
  "audit": { "level": "mandatory", "event": "model_risk.grant_production_use.v1" },
  "effects": [ { "path": "target.status", "value": "production" } ],
  "write_surface": ["model_risk.FinancialModel"],
  "refusal": {
    "shape": { "refused": true, "action": "model_risk.grant_production_use", "failed_clause": "string", "explanation": "string" }
  },
  "provenance": {
    "module": "model_risk",
    "module_version": "0.1.0",
    "arkhe_version": "0.1",
    "source_hash": "sha256:a2c44dc6929212db1e2ad0d916b3461a24c164bc2e5b3c2259cbf23d4ac8e72d"
  }
}
```

`{caption="Listing 2. grant_production_use.contract.json in full"}`

Names are namespaced by module (`model_risk.grant_production_use`), which is what lets multiple modules coexist in one deployment without collision. `guard.context.traversals` is the fully resolved evaluation context: it names every hop the guard walks, its direction, its cardinality, and the far entity, which is what a runtime needs to bind the CEL environment without re-parsing the expression itself. `guard.context.stdlib` lists exactly which Arkhe functions the guard uses (`months_since` here), so a compiling emitter knows what it needs to provide. `write_surface` is the full list of entity types the action may touch, generated from the effects, not hand-maintained; `record_validation_outcome`'s write surface, for comparison, lists both `ValidationReview` and `FinancialModel` because its effects reach one hop into the model it assesses. `refusal.shape` is a fixed schema every generated function's refusal object conforms to, useful for an agent framework that wants to pattern-match on refusals uniformly across every action in every module. `provenance.source_hash` is the payload that makes goldens work.

### Determinism and the canonical hash

Every contract's `source_hash` is a SHA-256 over the module's canonical form (ADR 0007), not over the raw file bytes. Canonical form is defined precisely so the hash is reproducible across parsers and languages: start from the schema-validated document (which is what makes coerced YAML scalars a non-issue, since a document with a stray unquoted `yes` fails type checking before it ever reaches the hash), fold every CEL expression to single-space whitespace, then serialise as JSON with lexicographically sorted keys, no insignificant whitespace, UTF-8, and no ASCII-escaping. Reformatting the YAML (indentation, key order, block-scalar style) never changes the hash; changing a declaration always does. All twelve fixture contracts share `sha256:a2c44dc6929212db1e2ad0d916b3461a24c164bc2e5b3c2259cbf23d4ac8e72d`, confirming they all derive from the same source module.

That is the property that makes CI goldens meaningful. Commit the `expected/` contracts directory alongside the module. In CI:

```
arkhe validate model-risk.arkhe.yaml
arkhe contracts model-risk.arkhe.yaml --out /tmp/contracts
diff -r /tmp/contracts expected/
```

A diff that only touches `source_hash` values across every file signals someone changed the module without regenerating goldens. A diff that touches a guard's `context.traversals` or a `write_surface` array without a corresponding, reviewed change to the guard expression is worth stopping the pipeline for; that is exactly the kind of silent capability drift a generated write surface exists to catch.

## v0.1 boundaries, stated plainly

- **Single-module only, in practice.** The schema accepts an `imports` block (module name plus an exact version pin; a range like `>=0.1` is rejected, `unpinned_import_version` is one of the fifteen catalogued failures), but the semantic model builder in `model.py` does not read or merge imports at all. A module with an `imports` block that passes structural validation still resolves as if the import were not there for every semantic check. Treat imports today as declared-but-not-yet-wired: reserve the field, do not build a multi-module pipeline on top of it expecting resolution.
- **No inference.** Closed-world by design (ADR 0001). No subsumption, no property chains, no entailment. What is not declared is false, and the validator checks rather than reasons.
- **No ordering.** "The latest review" is not expressible; guards and invariants quantify over whole collections, and an ordering concept is explicitly deferred to v0.2 (ADR 0005).
- **Guard traversal bounded at two hops**, described above, is a permanent v0.1 ceiling, not a temporary limitation of the current guard analyser.
- **One emitter.** `lib` (Python) is the only `emit --target`. Cedar policy compilation, JSON Schema/Pydantic models, and an OKF (Open Knowledge Format) bundle for LLM-facing documentation are all sketched in the design document as v0.2+ targets, not present in the CLI today. The CEL guard language itself is chosen partly because a defined subset compiles cleanly to Cedar `when` clauses once that emitter lands, but no such compilation exists yet.
- **No policy evaluation, no runtime, no data storage, no workflow orchestration.** The spec is explicit that Arkhe never evaluates policy itself; Cedar or an equivalent engine does that once the emitter exists. The generated `lib` module runs guard checks in-process for the demo, but Arkhe's contract is the artefact, not a service.

## Where to go next

The reference implementation is the golden-file suite itself: a hand-written module, its expected canonical contracts, and a catalogue of fifteen deliberately invalid modules the validator must reject. If you are evaluating Arkhe for a pipeline, start there rather than from the schema, because the fixture is normative and the schema is a piece of it.

https://arkhelang.org
https://github.com/arkhelang/arkhelang
