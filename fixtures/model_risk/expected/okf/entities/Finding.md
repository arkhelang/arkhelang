---
description: A weakness identified during validation.
tags:
- model_risk
title: Finding
type: Arkhe Entity
---

# Finding

A weakness identified during validation.

## Keys

- `finding_id`

## Properties

| Property | Type | Values | Optional |
| --- | --- | --- | --- |
| `finding_id` | string |  | no |
| `severity` | enum | low, medium, high | no |
| `status` | state | open, remediated, waived | no |
| `raised_date` | date |  | no |

## Lifecycle

The `status` property is a lifecycle state with values: open, remediated, waived. Initial state: open.

## Traversals

- [raised_in](../links/raised_in.md) to [ValidationReview](ValidationReview.md) (one)

## Actions

Actions targeting this entity:

- [waive_finding](../actions/waive_finding.md)
