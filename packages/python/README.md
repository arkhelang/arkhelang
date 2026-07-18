# arkhelang (Python)

The Python reference implementation of Arkhe, an ontology language for AI
systems. See the repository root for the language itself.

Currently provides the v0.1 validator:

    pip install arkhelang
    arkhe validate path/to/module.arkhe.yaml

Validation is two layers: structural (the published JSON Schema) and
semantic (name resolution, lifecycle-state rules, effect reach and
cardinality, CEL guard analysis with the two-hop traversal bound). Exit
codes: 0 valid, 1 invalid, 2 unreadable input. `--json` emits findings as
machine-readable output. `akl` is installed as an alias of `arkhe`.

The conformance fixtures in the repository's `fixtures/` directory are the
specification of this tool's behaviour; `pytest` runs them.
