---
description: Waive a finding with justification. High-severity findings cannot be waived; they must be remediated.
tags:
- model_risk
title: waive_finding
type: Arkhe Action
---

# waive_finding

Waive a finding with justification. High-severity findings cannot be waived; they must be remediated.

## Target

[Finding](../entities/Finding.md)

## Guard

This action is permitted only when the following condition holds:

```text
target.status == "open" && target.severity != "high"
```

## Authority

Role: [model_risk_officer](../roles/model_risk_officer.md)

## Audit

mandatory

## Parameters

| Parameter | Type | Values | Optional |
| --- | --- | --- | --- |
| `justification` | string |  | no |

## Effects

| Path | Value |
| --- | --- |
| `target.status` | waived |

## Write surface

- [Finding](../entities/Finding.md)
