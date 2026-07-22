---
description: Put a model into independent validation. Allowed from draft (initial validation) or production (periodic revalidation).
tags:
- model_risk
title: submit_for_validation
type: Arkhe Action
---

# submit_for_validation

Put a model into independent validation. Allowed from draft (initial validation) or production (periodic revalidation).

## Target

[FinancialModel](../entities/FinancialModel.md)

## Guard

This action is permitted only when the following condition holds:

```text
target.status == "draft" || target.status == "production"
```

## Authority

Role: [model_owner](../roles/model_owner.md)

## Audit

standard

## Effects

| Path | Value |
| --- | --- |
| `target.status` | in_validation |

## Write surface

- [FinancialModel](../entities/FinancialModel.md)
