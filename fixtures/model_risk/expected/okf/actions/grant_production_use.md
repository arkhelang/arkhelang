---
description: Promote a validated model to production. Requires a current validation and no open findings above low severity anywhere in the model's review history.
tags:
- model_risk
title: grant_production_use
type: Arkhe Action
---

# grant_production_use

Promote a validated model to production. Requires a current validation and no open findings above low severity anywhere in the model's review history.

## Target

[FinancialModel](../entities/FinancialModel.md)

## Guard

This action is permitted only when the following condition holds:

```text
target.status == "validated" && months_since(target.last_validated) <= 12 && target.reviewed_by.all(r, r.findings.all(f, f.status != "open" || f.severity == "low"))
```

## Authority

Role: [head_of_model_risk](../roles/head_of_model_risk.md)

## Audit

mandatory

## Effects

| Path | Value |
| --- | --- |
| `target.status` | production |

## Write surface

- [FinancialModel](../entities/FinancialModel.md)
