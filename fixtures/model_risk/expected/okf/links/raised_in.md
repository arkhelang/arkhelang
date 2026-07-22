---
description: A finding is raised in exactly one review.
tags:
- model_risk
title: raised_in
type: Arkhe Link
---

# raised_in

A finding is raised in exactly one review.

## Endpoints

- From: [Finding](../entities/Finding.md)
- To: [ValidationReview](../entities/ValidationReview.md)

## Cardinality

many_to_one

## Reverse

`findings` traverses from [ValidationReview](../entities/ValidationReview.md) back to [Finding](../entities/Finding.md).
