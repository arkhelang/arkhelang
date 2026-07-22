---
description: Each model is owned by exactly one desk.
tags:
- model_risk
title: owned_by
type: Arkhe Link
---

# owned_by

Each model is owned by exactly one desk.

## Endpoints

- From: [FinancialModel](../entities/FinancialModel.md)
- To: [TradingDesk](../entities/TradingDesk.md)

## Cardinality

many_to_one

## Reverse

`models` traverses from [TradingDesk](../entities/TradingDesk.md) back to [FinancialModel](../entities/FinancialModel.md).

## Properties

| Property | Type | Values | Optional |
| --- | --- | --- | --- |
| `since_date` | date |  | no |
