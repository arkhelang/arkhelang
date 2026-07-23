---
description: 'Reclassify a model''s purpose and materiality tier outside of production. Writes two enum destinations: purpose (string-valued) and tier (integer-valued).'
tags:
- model_risk
title: reclassify_model
type: Arkhe Action
---

# reclassify_model

Reclassify a model's purpose and materiality tier outside of production. Writes two enum destinations: purpose (string-valued) and tier (integer-valued).

## Target

[FinancialModel](../entities/FinancialModel.md)

## Guard

This action is permitted only when the following condition holds:

```text
target.status != "production" && target.status != "retired"
```

## Authority

Role: [head_of_model_risk](../roles/head_of_model_risk.md)

## Audit

mandatory

## Effects

| Path | Value |
| --- | --- |
| `target.purpose` | risk |
| `target.tier` | 2 |

## Write surface

- [FinancialModel](../entities/FinancialModel.md)
