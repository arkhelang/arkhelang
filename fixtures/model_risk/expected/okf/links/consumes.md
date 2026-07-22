---
description: Models consume market data feeds.
tags:
- model_risk
title: consumes
type: Arkhe Link
---

# consumes

Models consume market data feeds.

## Endpoints

- From: [FinancialModel](../entities/FinancialModel.md)
- To: [MarketDataFeed](../entities/MarketDataFeed.md)

## Cardinality

many_to_many

## Reverse

`consumed_by` traverses from [MarketDataFeed](../entities/MarketDataFeed.md) back to [FinancialModel](../entities/FinancialModel.md).

## Properties

| Property | Type | Values | Optional |
| --- | --- | --- | --- |
| `criticality` | enum | primary, fallback | no |
