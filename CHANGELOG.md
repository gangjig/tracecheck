# Changelog

## 0.2.0 — 2026-11-03

Trace integrity and denial records, motivated by the NIST / NSA /
CISA joint guidance *Key Practices for Incident Readiness and
Response in Super Intelligence Training and Evaluation* (Oct 2026):
monitoring must live where the monitored agent cannot alter it, and
blocked tool calls belong in the evidence too.

- **Hash-chain sealing** (`tracecheck seal` / `verify`): every event
  gains a `chain` field committing to the previous event's hash, so
  edits, deletions and reordering are detectable at the exact step.
  `verify --anchor <hash>` additionally catches tail truncation
  against an anchor recorded out of band. `check --require-chain`
  refuses to run rules on a trace whose chain does not verify.
  Re-sealing a sealed trace is refused.
- **`blocked` event type**: a tool call the harness refused before
  it ran (guardrail/policy), with the reason in `text`. Blocked
  events are not calls and count toward no call rule.
- **`min_blocked` rule**: asserts at least N blocked events for a
  tool are on record — separating "the agent never tried" from
  "tried, blocked, and logged". See `examples/` for the pair
  (`forbidden` + `min_blocked`) in action.
- Tests: 15 → 30.

## 0.1.0 — 2026-10-31

- **Initial release: deterministic assertions over agent traces.**
  Traces are JSONL event logs (`call` / `result` / `message` /
  `final`, steps numbered by line) with strict, line-cited
  validation. Rules are a JSON list of seven types — `order`,
  `requires` (including `"tool": "final"` for finish-line
  requirements), `forbidden` (with optional per-argument regex
  narrowing), `max_calls`, `min_calls`, `no_repeat` (the identical
  back-to-back call, the agent-loop signature), and `max_events` —
  each with documented vacuous-pass semantics and failure messages
  that name the exact step. Reports render as Markdown or JSON with
  a trace summary. The `check` subcommand exits 0 / 1 / 2 for
  pass / rule failure / unreadable input, so CI can tell a
  misbehaving agent from a broken harness; `demo` checks a bundled
  coding-agent trace that repeats an edit and finishes without
  verifying (4 of 6 rules pass). Standard library only.
