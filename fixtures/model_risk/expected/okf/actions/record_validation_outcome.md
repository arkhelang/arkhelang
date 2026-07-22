---
description: Record the outcome of a completed review.
tags:
- model_risk
title: record_validation_outcome
type: Arkhe Action
---

# record_validation_outcome

Record the outcome of a completed review.

## Target

[ValidationReview](../entities/ValidationReview.md)

## Guard

This action is permitted only when the following condition holds:

```text
target.outcome == "in_progress"
```

## Authority

Role: [model_validator](../roles/model_validator.md)

## Audit

standard

## Parameters

| Parameter | Type | Values | Optional |
| --- | --- | --- | --- |
| `outcome` | enum | approved, approved_with_conditions, rejected | no |

## Effects

| Path | Value |
| --- | --- |
| `target.outcome` | params.outcome |
| `target.assesses.last_validated` | target.review_date |
| `target.assesses.status` | validated |

## Write surface

- [FinancialModel](../entities/FinancialModel.md)
- [ValidationReview](../entities/ValidationReview.md)
