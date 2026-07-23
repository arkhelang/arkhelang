---
description: Publish a draft book.
tags:
- catalogue
title: publish_book
type: Arkhe Action
---

# publish_book

Publish a draft book.

Also known as: release, go live.

## Target

[Book](../entities/Book.md)

## Guard

This action is permitted only when the following condition holds:

```text
target.status == "draft"
```

## Authority

Role: [librarian](../roles/librarian.md)

## Audit

standard

## Parameters

| Parameter | Type | Values | Optional | Synonyms |
| --- | --- | --- | --- | --- |
| `note` | string |  | yes | comment, remark |

## Effects

| Path | Value |
| --- | --- |
| `target.status` | published |

## Write surface

- [Book](../entities/Book.md)
