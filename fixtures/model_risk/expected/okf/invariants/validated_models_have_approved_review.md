---
description: A model marked validated has at least one approved review.
tags:
- model_risk
title: validated_models_have_approved_review
type: Arkhe Invariant
---

# validated_models_have_approved_review

A model marked validated has at least one approved review.

## Scope

[FinancialModel](../entities/FinancialModel.md)

## Constraint

This constraint must hold for every FinancialModel:

```text
entity.status != "validated" || entity.reviewed_by.exists(r, r.outcome == "approved" || r.outcome == "approved_with_conditions")
```
