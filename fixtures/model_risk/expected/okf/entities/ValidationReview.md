---
description: An independent validation exercise against one model.
tags:
- model_risk
title: ValidationReview
type: Arkhe Entity
---

# ValidationReview

An independent validation exercise against one model.

## Keys

- `review_id`

## Properties

| Property | Type | Values | Optional |
| --- | --- | --- | --- |
| `review_id` | string |  | no |
| `scope` | enum | full, targeted | no |
| `outcome` | state | in_progress, approved, approved_with_conditions, rejected | no |
| `review_date` | date |  | no |

## Lifecycle

The `outcome` property is a lifecycle state with values: in_progress, approved, approved_with_conditions, rejected. Initial state: in_progress.

## Traversals

- [assesses](../links/assesses.md) to [FinancialModel](FinancialModel.md) (one)
- [findings](../links/raised_in.md) to [Finding](Finding.md) (many)

## Actions

Actions targeting this entity:

- [record_validation_outcome](../actions/record_validation_outcome.md)
