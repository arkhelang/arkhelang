---
description: An external data feed a model consumes.
tags:
- model_risk
title: MarketDataFeed
type: Arkhe Entity
---

# MarketDataFeed

An external data feed a model consumes.

## Keys

- `feed_id`

## Properties

| Property | Type | Values | Optional |
| --- | --- | --- | --- |
| `feed_id` | string |  | no |
| `provider` | string |  | no |
| `asset_class` | string |  | no |
| `snapshot_frequency` | string |  | no |

## Traversals

- [consumed_by](../links/consumes.md) to [FinancialModel](FinancialModel.md) (many)
