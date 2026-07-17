# Contributing to Arkhe

Thanks for your interest. Ground rules first, because they are commitments,
not boilerplate.

## The commitments

- **Free forever.** Arkhe is Apache-2.0 and will never charge for anything.
  There is no commercial edition, no open core, and no plan to create one.
- **No CLA, ever.** Contributions are accepted under the inbound=outbound
  norm: you license your contribution under Apache-2.0, the same terms you
  received the project under. A Developer Certificate of Origin sign-off
  (`git commit -s`) is required so provenance stays clean.
- **Decisions in public.** Design decisions are recorded as ADRs in
  [docs/adr/](docs/adr/). If a change contradicts an accepted ADR, the pull
  request should include a superseding ADR, not a silent reversal.

## Current state

The project is in early development, pre-v0.1. The most useful contributions
right now are issues: holes in the spec sketch, prior art the README should
acknowledge, domains where the metamodel breaks. Code contributions will make
more sense once the golden-file fixtures and validator land, because the
fixtures define conformance.

## Practical notes

- The spec is the contract; the golden files are the spec. A behaviour change
  without a fixture change did not happen.
- Keep emitters thin. If an emitter needs real logic, the fix belongs in the
  tool-contract IR.
- Prose style for docs: plain sentences, no marketing language, no
  first-ever claims.
