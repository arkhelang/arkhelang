# Documentation style

House style for all Arkhe documentation: README, ADRs, spec prose, site copy,
release notes. Checked before anything merges.

## Hard rules

- No em dashes (U+2014) or en dashes used as em dashes. Use commas, colons,
  or periods.
- Banned words: "honest", "honestly", "quietly", "blast radius".
- No "It's not X, it's Y" constructions or negative parallelisms.
- No marketing language, no superlatives, no first-ever claims.
- Prior art is acknowledged plainly and by name.

## Register

- Hedge observations, sharpen opinions. Factual claims get "often", "most",
  "usually" rather than "every" and "always". Design positions are stated
  bluntly.
- Plain verbs over staged imagery. No metaphors that dramatize the everyday.
- Avoid forcing arguments into three-item lists. Avoid aphoristic closers on
  every paragraph. Leave small imperfections in; over-polished symmetry reads
  as machine output.

## Precision

- Name products and protocols canonically on first reference, as the upstream
  project spells them.
- Distinguish the language or spec from its deployment artifact when a
  project has both (Cedar the language vs. cedar-agent the daemon).
- For every integration described, say whether it is turn-key upstream or a
  custom build. Readers evaluating adoption need to know what they must
  build.
- Verify version and date claims against the upstream source before they
  merge; spec-adjacent claims go stale fast.

## Refrains

Some lines are canonical and recur across documents in fixed form. Keep them
exact; drift is a bug:

- "The spec is a contract, never a runtime."
- "The refusals are the design."
- "The golden files are the spec."

Changes to a refrain require an ADR, since the refrains carry design meaning.
