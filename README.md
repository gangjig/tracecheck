# tracecheck

**Unit tests for agent behavior: deterministic assertions over the
trace your agent actually left behind.**

How do you regression-test an agent? Not its final answer alone —
the *path*: did it search before editing, verify before finishing,
stay inside its step budget, never touch the shell? LLM judges can
opine on those questions, but they sample, they cost, and they
disagree with themselves. `tracecheck` treats them as what they are:
mechanical properties of an event log. You write rules in JSON, it
checks a JSONL trace, and every failure names the exact step where
the run went wrong. Same trace + same rules = same verdict, forever.

## Quickstart

```bash
pip install -e .
tracecheck demo
```

```
| # | Rule | Result | Detail |
|---:|---|---|---|
| 1 | search must be called before edit_file | PASS | search at step 1 precedes edit_file at step 5 |
| 2 | finishing requires a prior verify call | **FAIL** | the final event is at step 11 with no prior verify call |
| 3 | no repeated identical call (any tool) | **FAIL** | edit_file call at step 7 repeats the identical call from step 5 |
...
**4/6 rules passed.**
```

Against your own traces:

```bash
tracecheck check run.jsonl --rules rules.json
echo $?   # 0 = all rules pass, 1 = a rule failed, 2 = input unreadable
```

The exit-code split is deliberate: CI can distinguish "the agent
broke a rule" (1) from "the harness produced garbage" (2) without
parsing the report. `--format json` emits the same verdicts as
structured data.

## Traces

One event per JSONL line, in execution order; steps are line numbers:

```json
{"event": "call", "tool": "search", "args": {"query": "auth bug"}}
{"event": "result", "tool": "search"}
{"event": "call", "tool": "edit_file", "args": {"path": "auth.py"}}
{"event": "final", "text": "Fixed."}
```

Event types are `call` and `result` (both carry `tool`; calls carry
optional `args`), `blocked`, `message`, and `final`. A `blocked`
event records a call the harness *refused* — a guardrail or policy
stopped it before it ran. It is not a call and counts toward no call
rule; it exists so "the agent tried and was stopped" is
distinguishable from "the agent never tried". This is the least
common denominator of agent logging — any harness that can log what
it did can emit it, and tracecheck never needs to know which
framework produced the run.

## Rules

A rules file is a JSON list. Eight rule types cover the failure
modes that actually recur in agent runs:

| Rule | Example | Catches |
|---|---|---|
| `order` | `{"before": "search", "after": "edit_file"}` | acting before looking |
| `requires` | `{"tool": "final", "needs": "verify"}` | finishing without checking (`"tool": "final"` targets the final event) |
| `forbidden` | `{"tool": "shell", "args_match": {"command": "rm\\s"}}` | dangerous tools, or dangerous argument patterns via per-arg regexes |
| `max_calls` | `{"tool": "search", "count": 5}` | runaway tool use |
| `min_calls` | `{"tool": "run_tests", "count": 1}` | skipped verification steps |
| `no_repeat` | `{"tool": "edit_file"}` (tool optional) | the loop signature: the identical call issued again right after itself |
| `max_events` | `{"count": 50}` | whole-trace step budgets |
| `min_blocked` | `{"tool": "shell", "count": 1}` | denials missing from the record — separates "never tried" from "tried, blocked, and logged" |

Semantics are documented per rule in the module and are strict about
vacuous cases: `order` passes if the `after` tool is never called,
and `requires` passes if its target never occurs — a rule constrains
what happens *when* the agent acts, and `min_calls` is the tool for
forcing an action to happen at all.

## Trace integrity: hash chains

Rules are only as good as the trace they run on. If whatever wrote
the file can also edit it, a denied call can be re-labelled a
success — or deleted — and every rule still passes. `seal` and
`verify` add tamper evidence:

```bash
tracecheck seal run.jsonl            # writes run.sealed.jsonl, prints an anchor hash
tracecheck verify run.sealed.jsonl --anchor <hash>
tracecheck check run.sealed.jsonl --rules rules.json --require-chain
```

Sealing appends a `chain` field to every event:
`chain[n] = sha256(chain[n-1] + canonical(event[n]))`. Editing an
event, deleting one, or reordering two breaks the chain at exactly
that step, and `verify` names it (exit 1; `check --require-chain`
fails the same way before any rule runs). Two honest limits:

- **A chain proves the prefix, not the tail.** Chopping the last
  events off leaves a shorter chain that still verifies — that is
  what the anchor is for. Record the anchor somewhere the agent
  cannot reach at the end of the run; `--anchor` then catches
  truncation too.
- **Sealing is not storage.** The harness should append events in
  real time and keep the file (and the anchor) outside the
  monitored agent's reach; tracecheck verifies what you hand it, it
  cannot store anything for you. This is the checkable half of the
  NIST / NSA / CISA guidance on incident readiness for autonomous
  agents (Oct 2026), which also asks for exactly the `blocked`
  records above: monitoring the agent cannot alter, denials
  included.

## Recreate this project from a prompt

> Build a Python CLI called `tracecheck` that checks agent execution
> traces against deterministic rules — no LLM judge. A trace is a
> JSONL file with one event per line in execution order (steps are
> 1-based line numbers); event types are call/result (with a tool
> name, calls with an optional args object), message, and final, with
> strict validation errors that cite the line. A rules file is a JSON
> list supporting seven rule types: order (first after-call must be
> preceded by a before-call), requires (first call to a tool — or the
> final event when the tool is "final" — must be preceded by a needs
> call), forbidden (a tool never called, optionally narrowed by
> per-argument regex matching), max_calls and min_calls per tool,
> no_repeat (no two back-to-back calls to the same tool with
> identical args), and max_events for whole-trace budgets; document
> the vacuous-pass semantics. Evaluation is a pure function from
> trace + rules to per-rule pass/fail results whose messages cite
> exact step numbers. Render Markdown and JSON reports with a trace
> summary (event count, per-tool call counts, whether a final event
> exists). The CLI has a check subcommand with exit codes 0 (all
> pass), 1 (a rule failed) and 2 (unreadable input), plus a demo
> subcommand that bundles a sample trace and rules where a coding
> agent repeats an identical edit and finishes without verifying, so
> exactly 2 of 6 rules fail. Standard library only, with a pytest
> suite covering trace validation, every rule type passing and
> failing, report rendering, and the exit-code contract. Then
> extend it: add a fifth event type, blocked, for tool calls the
> harness refused before they ran (requires tool, optional args and
> a reason in text; never counted as a call), plus a min_blocked
> rule asserting at least N blocked events for a tool are on record.
> Add tamper evidence for trace files: a seal subcommand that
> appends a sha256 hash chain (each event's hash commits to the
> previous hash plus the canonical JSON of the event — sorted keys,
> compact separators), a verify subcommand that recomputes the
> chain and names the first broken step, an --anchor option that
> compares the final hash against one recorded out of band to catch
> tail truncation, a check --require-chain flag that fails before
> rules run, and re-sealing refused — all under the same 0/1/2
> exit-code contract, with tests for edit, deletion, reordering and
> truncation tamper modes.

## Limitations

- **Trace-level, not semantic.** tracecheck verifies the *shape* of
  behavior — order, counts, repetition, budgets. Whether the edit at
  step 5 was the *right* edit is a question for evals and judges;
  this tool exists so those expensive judgments are spent on runs
  that at least behaved structurally.
- **The trace must be honest.** Garbage-in applies: if the harness
  doesn't log a call, no rule can see it. Emit traces from the tool
  dispatch layer, not from the model's self-report. Hash-chain
  sealing (above) covers the other half of honesty: a trace that
  was complete when written but edited afterwards.
- **Exact args equality for `no_repeat`.** A loop that mutates one
  character per retry evades it; pair it with `max_calls` for a hard
  ceiling.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e . pytest
python -m pytest        # 30 tests, fully offline
```

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Gang Ji.
