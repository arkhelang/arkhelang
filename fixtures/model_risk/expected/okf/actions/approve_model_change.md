---
description: Approve a proposed change. Tier-1 models escalate to the head of model risk for second approval.
tags:
- model_risk
title: approve_model_change
type: Arkhe Action
---

# approve_model_change

Approve a proposed change. Tier-1 models escalate to the head of model risk for second approval.

## Target

[ModelChange](../entities/ModelChange.md)

## Guard

This action is permitted only when the following condition holds:

```text
target.status == "proposed" && target.applies_to.status != "retired"
```

## Authority

Role: [model_risk_officer](../roles/model_risk_officer.md)

## Approval

A second approval from [head_of_model_risk](../roles/head_of_model_risk.md) is required when:

```text
target.applies_to.tier == 1
```

## Audit

mandatory

## Effects

| Path | Value |
| --- | --- |
| `target.status` | approved |

## Write surface

- [ModelChange](../entities/ModelChange.md)
