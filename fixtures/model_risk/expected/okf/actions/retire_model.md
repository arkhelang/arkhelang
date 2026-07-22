---
description: Retire a production model.
tags:
- model_risk
title: retire_model
type: Arkhe Action
---

# retire_model

Retire a production model.

## Target

[FinancialModel](../entities/FinancialModel.md)

## Guard

This action is permitted only when the following condition holds:

```text
target.status == "production"
```

## Authority

Role: [head_of_model_risk](../roles/head_of_model_risk.md)

## Audit

mandatory

## Parameters

| Parameter | Type | Values | Optional |
| --- | --- | --- | --- |
| `reason` | string |  | no |

## Effects

| Path | Value |
| --- | --- |
| `target.status` | retired |

## Write surface

- [FinancialModel](../entities/FinancialModel.md)
