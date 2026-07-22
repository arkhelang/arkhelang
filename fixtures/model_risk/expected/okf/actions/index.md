---
tags:
- model_risk
title: Actions
type: Arkhe Index
---

# Actions

Actions declared in the model_risk module.

- [approve_model_change](approve_model_change.md): Approve a proposed change. Tier-1 models escalate to the head of model risk for second approval.
- [grant_production_use](grant_production_use.md): Promote a validated model to production. Requires a current validation and no open findings above low severity anywhere in the model's review history.
- [record_validation_outcome](record_validation_outcome.md): Record the outcome of a completed review.
- [retire_model](retire_model.md): Retire a production model.
- [submit_for_validation](submit_for_validation.md): Put a model into independent validation. Allowed from draft (initial validation) or production (periodic revalidation).
- [waive_finding](waive_finding.md): Waive a finding with justification. High-severity findings cannot be waived; they must be remediated.
