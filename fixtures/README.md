# Fixtures

The golden files are the spec. Each fixture is a hand-written Arkhe module
together with the outputs the toolchain must produce for it: canonical JSON,
tool contracts, and emitter artifacts. The validator and compiler are written
to make these pass; a behaviour change without a fixture change did not
happen.

| Fixture | Domain | Exercises |
| --- | --- | --- |
| [model_risk](model_risk/) | Financial-services model risk management | Lifecycle states, link properties, conditional approval escalation, multi-hop guards, stdlib functions, invariants |

Fixture two (a mining maintenance domain) follows once the metamodel
decisions surfaced by fixture one are settled; a second domain is what stops
the metamodel overfitting to the first.
