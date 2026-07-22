---
description: Tier-1 production models declare a primary data feed.
tags:
- model_risk
title: tier1_production_has_primary_feed
type: Arkhe Invariant
---

# tier1_production_has_primary_feed

Tier-1 production models declare a primary data feed.

## Scope

[FinancialModel](../entities/FinancialModel.md)

## Constraint

This constraint must hold for every FinancialModel:

```text
!(entity.tier == 1 && entity.status == "production") || entity.consumes.exists(c, c.criticality == "primary")
```
