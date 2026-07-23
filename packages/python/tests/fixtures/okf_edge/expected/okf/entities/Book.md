---
description: A catalogued book. A café favourite among readers.
tags:
- catalogue
title: Book
type: Arkhe Entity
---

# Book

A catalogued book. A café favourite among readers.

Also known as: volume, tome.

## Keys

- `book_id`

## Properties

| Property | Type | Values | Optional |
| --- | --- | --- | --- |
| `book_id` | string |  | no |
| `title` | string |  | no |
| `status` | state | draft, published | no |

## Lifecycle

The `status` property is a lifecycle state with values: draft, published. Initial state: draft.

## Traversals

- [sequel_of](../links/sequel_of.md) to [Book](Book.md) (one)
- [written_by](../links/written_by.md) to [Author](Author.md) (one)

## Actions

Actions targeting this entity:

- [publish_book](../actions/publish_book.md)
