---
description: No model may sit in production with a stale validation.
tags:
- model_risk
title: production_models_are_current
type: Arkhe Invariant
---

# production_models_are_current

No model may sit in production with a stale validation.

## Scope

[FinancialModel](../entities/FinancialModel.md)

## Constraint

This constraint must hold for every FinancialModel:

```text
entity.status != "production" || months_since(entity.last_validated) <= 12
```
