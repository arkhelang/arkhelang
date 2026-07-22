---
description: A front-office desk that owns and uses models.
tags:
- model_risk
title: TradingDesk
type: Arkhe Entity
---

# TradingDesk

A front-office desk that owns and uses models.

## Keys

- `desk_id`

## Properties

| Property | Type | Values | Optional |
| --- | --- | --- | --- |
| `desk_id` | string |  | no |
| `name` | string |  | no |
| `business_line` | string |  | no |

## Traversals

- [models](../links/owned_by.md) to [FinancialModel](FinancialModel.md) (many)
