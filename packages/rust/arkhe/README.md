# arkhe (Rust CLI)

**An ontology language for AI systems.** Early development.

The command-line interface for the Arkhe validator Rust port.

```
arkhe validate <module.arkhe.yaml | dir> [--json]
```

Exit codes match the Python CLI: `0` valid, `1` invalid, `2` usage error or
unreadable input.

The `contracts` and `emit` subcommands are not part of this first cut (the
emitters are not ported yet). See `../BUILD_NOTES.md`.

- Project: https://github.com/arkhelang
- License: Apache-2.0
