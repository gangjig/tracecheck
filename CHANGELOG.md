# Changelog

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
