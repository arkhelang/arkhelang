# arkhelang (Rust)

**An ontology language for AI systems.** Early development.

The Rust port of the Arkhe validator (ADR 0008, item 4). It loads an
`.arkhe.yaml` module, checks it against the arkhe-0.1 metamodel structurally,
runs the semantic passes, and reports findings. Conformance is defined by the
frozen v0.1 golden fixtures.

```rust
let result = arkhelang::validate_file("model-risk.arkhe.yaml")?;
if result.ok() {
    println!("valid");
} else {
    println!("{}", result.to_json());
}
# Ok::<(), arkhelang::Error>(())
```

CEL guard analysis is not yet ported; the validator emits no `guard-*`
findings. See `../BUILD_NOTES.md` for scope, crate choices, and the CEL
milestone.

- Project: https://github.com/arkhelang
- License: Apache-2.0

The name comes from ἀρχή (arkhē): both *first principle* and *rule, authority*.
