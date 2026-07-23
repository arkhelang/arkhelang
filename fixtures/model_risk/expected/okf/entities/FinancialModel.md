---
description: A quantitative model used for pricing, risk, capital, or financial crime detection. The unit of governance in this module.
tags:
- model_risk
title: FinancialModel
type: Arkhe Entity
---

# FinancialModel

A quantitative model used for pricing, risk, capital, or financial crime detection. The unit of governance in this module.

## Keys

- `model_id`

## Properties

| Property | Type | Values | Optional |
| --- | --- | --- | --- |
| `model_id` | string |  | no |
| `name` | string |  | no |
| `purpose` | enum | pricing, risk, capital, aml | no |
| `tier` | enum | 1, 2, 3 | no |
| `status` | state | draft, in_validation, validated, production, retired | no |
| `commissioned_date` | date |  | no |
| `last_validated` | date |  | yes |

## Lifecycle

The `status` property is a lifecycle state with values: draft, in_validation, validated, production, retired. Initial state: draft.

## Traversals

- [changes](../links/applies_to.md) to [ModelChange](ModelChange.md) (many)
- [consumes](../links/consumes.md) to [MarketDataFeed](MarketDataFeed.md) (many)
- [owned_by](../links/owned_by.md) to [TradingDesk](TradingDesk.md) (one)
- [reviewed_by](../links/assesses.md) to [ValidationReview](ValidationReview.md) (many)

## Actions

Actions targeting this entity:

- [grant_production_use](../actions/grant_production_use.md)
- [reclassify_model](../actions/reclassify_model.md)
- [retire_model](../actions/retire_model.md)
- [submit_for_validation](../actions/submit_for_validation.md)
