# Arkhe for GRC Professionals

Arkhe is an open-source ontology language for AI systems, released under Apache-2.0 and free to use without restriction. It is written and maintained by Andrew Stevens. This guide is for people who own controls rather than write code: governance, risk, and compliance officers, second-line staff, and auditors who need to understand what Arkhe declares, what it enforces, and where its scope ends.

The short version: Arkhe lets a domain owner write down, in one YAML file, what entities exist in a business process, how they relate, and what actions can be taken on them, including who is allowed to take each action and what has to happen before an AI agent (or any other caller) is permitted to do it. A compiler turns that file into a machine-checkable contract and into generated code where every function checks the contract before it runs. If a call would violate a guard condition, the generated code refuses and says which clause failed. This is not a claim about what an AI agent will do; it is a claim about what the code it calls will let it do.

## Controls as data

In most AI deployments, the rules that govern an action live in a prompt, a policy document, or a reviewer's head. Arkhe's position is that governed actions belong in a declared, versioned artifact that a compiler reads, not in instructions a model is asked to follow.

Take a concrete example from Arkhe's model risk management fixture, a worked domain module covering the lifecycle of financial models under a regime such as SR 11-7 or SS1/23. One of its actions is `waive_finding`:

```yaml
waive_finding:
  annotations:
    description: >
      Waive a finding with justification. High-severity findings cannot
      be waived; they must be remediated.
  target: Finding
  parameters:
    justification: { type: string }
  guard: target.status == "open" && target.severity != "high"
  authority: model_risk_officer
  audit: mandatory
  effects:
    - target.status: waived
```

The guard is a CEL (Common Expression Language) boolean expression: `target.status == "open" && target.severity != "high"`. Read plainly, this says a finding can only be waived while it is open, and never if its severity is high. That is the control. It is not a comment or a policy reference; it is the condition the compiled function evaluates before it does anything.

The demo module includes a finding with `severity="high"` and an officer with the right role attempting to waive it anyway:

```
== attempt to waive the high finding
REFUSED
  failed_clause: target.severity != "high"
  explanation:   guard clause evaluated to false
```

The refusal names the exact clause that failed. Nobody has to argue about intent, and no amount of prompting the calling agent changes the outcome, because the check runs in the generated function, not in the model's reasoning. This is the structural claim Arkhe makes: a guard is enforced at the point of execution in whatever code the compiler produced, so it cannot be argued around by a differently phrased request. That claim depends on callers actually going through the generated function rather than mutating state directly, which is a deployment discipline, not something the file can force on its own.

## Approval escalation as a declaration

Four-eyes requirements are also written into the action, not layered on afterwards. The `approve_model_change` action reads:

```yaml
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

A model risk officer normally has authority to approve a change. The `approval` block adds a condition: when the change applies to a tier-1 model, a second approval from the head of model risk is required. The compiled contract for this action carries that escalation as structured data:

```json
"approval": {
  "when": "target.applies_to.tier == 1",
  "authority": {
    "role": "model_risk.head_of_model_risk",
    "claims": { "groups": "mrm/head" }
  }
}
```

For an action with no escalation, such as `grant_production_use`, the same field is simply `"approval": null` in the compiled contract, so the presence or absence of a second approval is visible by inspecting the contract rather than by reading a runbook and hoping it matches what the code does.

## Audit by construction

Every action declares an `audit` level: `none`, `standard`, or `mandatory`. This is a schema-level enum, so an action cannot be governed by an ad hoc audit convention that varies module to module. In the fixture, the actions that change control-relevant state (`approve_model_change`, `grant_production_use`, `waive_finding`, `retire_model`) are all marked `audit: mandatory`; routine lifecycle moves such as `submit_for_validation` are `audit: standard`.

Each contract also carries an `event` name derived from the module, action, and a version tag, for example `model_risk.grant_production_use.v1`. When an allowed call succeeds, the generated code writes an audit event using that name. Running the fixture's demo scenario end to end (an intern refused on authority, the head of model risk refused on the open finding, the finding remediated, then the promotion allowed) produces this line on the record:

```json
{"event": "model_risk.grant_production_use.v1", "target": "irs-pricer", "actor": "maria", "params": {}, "effects": [{"entity": "FinancialModel", "key": "irs-pricer", "property": "status", "value": "production"}]}
```

That is a real audit event from running the demo, not an illustration. It names the event type, the target entity and key, the actor, the parameters supplied, and the effect that was applied. As an auditor, this is the shape you should expect to see logged for any mandatory-audit action: who did what, to which record, under which contract, with what result. What Arkhe does not do is decide where that event goes, retain it, or attach a retention policy; the emitted event is the evidence unit, and downstream storage and retrieval is a decision for whoever operates the system consuming it.

## Reading an action without being an engineer

You do not need to read CEL fluently to review one of these actions, though it helps to be able to sound one out. Take `grant_production_use`:

```yaml
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
```

Walking it as a control owner would:

- **What does it act on?** `target: FinancialModel`. This action changes a financial model's record.
- **What has to be true first?** The `guard`. Read left to right: the model's status must already be `validated`; the last validation must be no more than 12 months old; and for every review linked to this model, every finding raised in that review must be either not-open or low severity. The `annotations.description` above the guard is a human-readable restatement of the same condition, and it is worth checking the two agree, since the description is prose written for you and the guard is the version that actually runs.
- **Who is allowed to invoke it?** `authority: head_of_model_risk`, matched against the caller's claims (here, membership in the `mrm/head` group).
- **What happens if it succeeds?** `effects`: the model's status moves to `production`. That is the entire effect of the action; nothing else changes.
- **Is it logged?** `audit: mandatory`, so a `grant_production_use` event fires with the actor, target, and effect on success.

If any of those five things reads wrong to you as the process owner, that is the point at which you raise it, before the module is compiled and shipped, because after that point the behaviour is what the guard says, not what anyone intended it to say.

## Evidence and provenance

Every compiled contract carries a `provenance` block:

```json
"provenance": {
  "module": "model_risk",
  "module_version": "0.1.0",
  "arkhe_version": "0.1",
  "source_hash": "sha256:a2c44dc6929212db1e2ad0d916b3461a24c164bc2e5b3c2259cbf23d4ac8e72d"
}
```

The `source_hash` is computed over a canonical form of the module (per ADR 0007 in the Arkhe repository): the schema-validated document, with CEL expressions folded to consistent whitespace, serialised as JSON with sorted keys. Reformatting the YAML file, reordering keys, or changing comment style does not change the hash; changing any actual declaration does. Two contracts sharing a `source_hash` were compiled from the same governed logic, and a contract's hash not matching the module you have on file is a signal to ask what changed and when. This gives you a change-control anchor: when someone tells you the guard on `waive_finding` was tightened last quarter, the module's version history and the hash on the contract in production should agree with that story.

## Model risk management, walked as a whole

The fixture module governs the full lifecycle: a model starts in `draft`, goes to `in_validation` via `submit_for_validation`, moves to `validated` once `record_validation_outcome` records an approved review, reaches `production` via `grant_production_use`, and can later be moved back into `in_validation` for periodic revalidation or into `retired` via `retire_model`. Findings raised during validation are tracked separately and can be `waived` (except at high severity, as shown above) or remediated. Changes to a model go through `approve_model_change`, with tier-1 models requiring the extra sign-off already described.

The module also declares invariants that hold independent of any single action, for example that no model may sit in `production` with a validation older than 12 months, and that a model marked `validated` must have at least one review with an `approved` or `approved_with_conditions` outcome. These are checks over the state of the world rather than over a single call, and the validator confirms the module is internally consistent (no dangling references, no contradictory state machines) before any contract is compiled.

## Other places the same pattern applies

The model risk fixture is the only module Arkhe ships as a worked example today. The pattern it demonstrates, entities plus governed actions plus guards plus authority plus audit, is domain-neutral, and the same shape maps onto other GRC processes without requiring anything new from the language:

- **Access recertification.** Entities for users, entitlements, and systems; an action such as `revoke_access` guarded on the entitlement being flagged in the current recertification cycle, with authority resting on the resource owner and audit set to mandatory.
- **Incident response actions.** Entities for incidents and remediation steps; an action such as `close_incident` guarded on all linked remediation items being resolved, with escalation to a security lead for high-severity incidents, mirroring the tier-1 escalation shown above.
- **Financial approvals.** Entities for payment requests and approval thresholds; an action such as `approve_payment` guarded on amount thresholds, with an `approval` block escalating above a defined limit, structurally the same shape as `approve_model_change`.

These are sketches of how the existing primitives would be composed for those domains, not modules that exist in the Arkhe repository today. Nobody should read this section as a claim that access recertification or incident response tooling ships now; it does not.

## What Arkhe does not do

Arkhe is a specification and a compiler, not a runtime and not a product you deploy in front of a system to enforce policy live. Being specific about v0.1 scope, as stated in the project's own documentation:

- No execution or write-back. Arkhe does not run your business process; it compiles contracts and, in v0.1, generated library stubs that other code calls.
- No data storage. Arkhe holds no record of your actual models, incidents, or entitlements; the fixture's `World` object in the demo is an in-memory test harness, not a system of record.
- No workflow or orchestration engine. Sequencing across multiple actions, retries, and human task routing are not Arkhe's concern.
- No policy evaluation engine of its own. The stated design intent is to emit to policy engines such as Cedar and let them evaluate; that emitter is planned for v0.2 and later, not shipped in v0.1.
- No protocol dependency in the core. MCP, OpenAI function schemas, and similar are treated as emitters consuming the IR, not as something the metamodel depends on.

v0.1 ships four things only: the specification (JSON Schema plus prose plus golden fixtures), a validator, the tool-contract IR, and one emitter that produces native Python library stubs with guard pre-checks and structured refusals. If someone tells you Arkhe enforces a control in a live production system today, ask which emitter is running and what calls it, because Arkhe itself compiles the contract; something else has to call the generated function for the guard to run.

## A short CLI reference

You will likely never run these commands yourself, but knowing what to ask an engineer for is useful, particularly for capturing evidence.

```
arkhe validate model-risk.arkhe.yaml
```

Validates a module against the schema and semantic rules (dangling references, state machine consistency, CEL guard syntax). Human-readable table output:

```
arkhe 0.1.0.dev1 validate

  module                                     findings  status
  fixtures/model_risk/model-risk.arkhe.yaml         0  valid

  1 module: 1 valid, 0 invalid
```

```
arkhe validate model-risk.arkhe.yaml --json
```

The same check with machine-readable output, useful if you want a validation result captured as evidence rather than a screenshot of a terminal:

```
{
  "fixtures/model_risk/model-risk.arkhe.yaml": {
    "ok": true,
    "findings": []
  }
}
```

Exit code 0 means the module is valid; exit code 1 means it is invalid and findings are printed; exit code 2 is a usage error. If you are asking for evidence that a module passed validation before it was compiled into contracts, this is the command and the exit code to ask for.

```
arkhe contracts model-risk.arkhe.yaml --out CONTRACTS_DIR
```

Validates the module, then writes one JSON contract per action (and a read contract per entity) into a directory. This is the artifact this guide has been quoting from throughout; ask for it directly if you want to read the guard, authority, approval, and audit fields for a specific action yourself.

```
arkhe emit model-risk.arkhe.yaml --target lib --out FILE
```

Generates the Python library stub whose functions enforce the contracts, `lib` being the only target in v0.1. This is what an engineer runs to produce the code that other systems call; it is one step removed from what you as a reviewer need, but knowing it exists explains where the enforcement in your audit log actually comes from.

## Links

- https://arkhelang.org
- https://github.com/arkhelang/arkhelang
