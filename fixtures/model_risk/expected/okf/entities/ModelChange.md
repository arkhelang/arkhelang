---
description: A proposed change to a model under change control.
tags:
- model_risk
title: ModelChange
type: Arkhe Entity
---

# ModelChange

A proposed change to a model under change control.

## Keys

- `change_id`

## Properties

| Property | Type | Values | Optional |
| --- | --- | --- | --- |
| `change_id` | string |  | no |
| `category` | enum | recalibration, methodology, data_source | no |
| `status` | state | proposed, approved, deployed, rejected | no |
| `submitted_date` | date |  | no |

## Lifecycle

The `status` property is a lifecycle state with values: proposed, approved, deployed, rejected. Initial state: proposed.

## Traversals

- [applies_to](../links/applies_to.md) to [FinancialModel](FinancialModel.md) (one)

## Actions

Actions targeting this entity:

- [approve_model_change](../actions/approve_model_change.md)
