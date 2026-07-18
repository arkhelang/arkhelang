# ADR 0007: Canonical form and the provenance hash

Date: 2026-07-17
Status: Accepted

## Context

Every contract carries a provenance hash tying it to the module that
produced it, and every implementation (Python now, Rust and Go planned) must
reproduce the same hash for the same module. Hashing the raw parser output
is not portable: YAML 1.1 parsers coerce scalars (unquoted `yes` to a
boolean, zero-padded numbers to octal) where YAML 1.2 parsers do not, and
formatting choices in block scalars leak into guard strings.

## Decision

The provenance hash is computed over the module's canonical form, defined
as follows. Start from the schema-validated document; schema validation is
what makes this portable, because coerced scalars fail type checks (a
boolean where a string is required, a boolean in an enum value list), so a
document that validates parses to the same values under any conforming
parser. Then fold every CEL expression (guards, approval conditions,
invariant checks) to single-space whitespace. Serialize as JSON with
lexicographically sorted keys, no insignificant whitespace, UTF-8 encoding,
and no ASCII escaping of non-ASCII characters. The hash is the SHA-256 of
those bytes, recorded as `sha256:<hex>`.

Conforming implementations in any language must reproduce this byte
sequence. The canonical form is defined on the validated document, never on
parser-native structures.

## Consequences

- Reformatting a module (indentation, key order, block-scalar style) does
  not change its hash; changing any declaration does.
- Ports get a precise conformance target, testable from the golden files.
- Documents that only parse "correctly" by the grace of YAML 1.1 quirks are
  rejected by the schema rather than hashed differently across languages.
