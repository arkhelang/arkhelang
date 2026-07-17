# ADR 0003: The tool-contract IR is the centre; protocols are emitters

Date: 2026-07-17
Status: Accepted

## Context

The obvious 2026 design would compile the ontology directly to MCP tool
definitions. MCP is a wire protocol having a moment: its extensions framework
is still settling, and OpenAI function schemas, Google ADK tools, and future
protocols all want essentially the same information. Coupling the core to any
protocol makes protocol churn the project's problem.

## Decision

The compiler's primary output is a neutral intermediate representation, the
tool contract: one JSON document per action type carrying the resolved
guard (canonical CEL), authority binding, approval escalation, audit
obligation, effects declaration, and provenance (module set and content
hashes). Read contracts are generated per entity and link type. The IR is
part of the specification and lives in the golden files. Everything
downstream is an emitter, and emitters are serialization only: tens of lines
each. No protocol is load-bearing anywhere in the core.

## Consequences

- MCP is deliberately not mandatory. It arrives later as one thin emitter
  among several, when its extensions framework stabilises.
- The guard-refusal demo works as a plain function call against a generated
  native library, with no server and no wire protocol.
- If an emitter needs more than serialization, the IR is missing something,
  and the fix belongs in the IR, never in the emitter.
