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
optional `args`), `message`, and `final`. This is the least common
denominator of agent logging — any harness that can log what it did
can emit it, and tracecheck never needs to know which framework
produced the run.

## Rules

A rules file is a JSON list. Seven rule types cover the failure
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

Semantics are documented per rule in the module and are strict about
vacuous cases: `order` passes if the `after` tool is never called,
and `requires` passes if its target never occurs — a rule constrains
what happens *when* the agent acts, and `min_calls` is the tool for
forcing an action to happen at all.

## Recreate this project from a prompt

> Write a small Python command-line tool, standard library only, that
> checks recorded agent execution traces against deterministic rules,
> with no LLM judge. A trace is a JSONL file of events in execution
> order (tool calls and their results, messages, and a final event),
> validated strictly with errors that cite the offending line; rules are
> declared in a JSON file and cover ordering and prerequisites between
> calls, forbidden tools optionally narrowed by argument patterns, per-
> tool call-count limits, back-to-back identical repeats, and whole-
> trace event budgets. Checking is a pure evaluation that returns a pass
> or fail per rule with messages citing exact step numbers, rendered as
> a Markdown or JSON report with a trace summary, under a clear exit-
> code contract for CI. Include a demo with a bundled trace and rule set
> where a coding agent repeats an identical edit and finishes without
> verifying, so the failures are visible in the report.

## Limitations

- **Trace-level, not semantic.** tracecheck verifies the *shape* of
  behavior — order, counts, repetition, budgets. Whether the edit at
  step 5 was the *right* edit is a question for evals and judges;
  this tool exists so those expensive judgments are spent on runs
  that at least behaved structurally.
- **The trace must be honest.** Garbage-in applies: if the harness
  doesn't log a call, no rule can see it. Emit traces from the tool
  dispatch layer, not from the model's self-report.
- **Exact args equality for `no_repeat`.** A loop that mutates one
  character per retry evades it; pair it with `max_calls` for a hard
  ceiling.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e . pytest
python -m pytest        # 15 tests, fully offline
```

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Gang Ji.
