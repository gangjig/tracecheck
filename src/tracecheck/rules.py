"""Rules over a trace, and their deterministic evaluation.

A rules file is a JSON list of rule objects. Every rule is checked
mechanically against the trace — no model, no sampling — so a rule
that passes today passes tomorrow, and a failure names the exact
step where the trace went wrong.

Rule types (all operate on `call` events unless noted):

* `order`      {"before": "search", "after": "edit_file"}
  The first `after` call must be preceded by a `before` call.
  Vacuously true if `after` is never called.
* `requires`   {"tool": "submit", "needs": "verify"}
  The first `tool` call must be preceded by a `needs` call.
  `"tool": "final"` targets the final event instead: finishing
  requires a prior `needs` call.
* `forbidden`  {"tool": "shell", "args_match": {"command": "rm\\s"}}
  The tool must never be called; with `args_match`, only calls whose
  args match every key → regex (searched, on the string form of the
  value) are forbidden.
* `max_calls`  {"tool": "search", "count": 5}
* `min_calls`  {"tool": "run_tests", "count": 1}
* `no_repeat`  {"tool": "search"}   ("tool" optional)
  No two calls to the same tool with identical args, back to back
  among that tool's calls — the signature of an agent loop re-issuing
  a call that already failed to move it forward.
* `max_events` {"count": 50}
  The whole trace (all event types) stays within a step budget.
* `min_blocked` {"tool": "shell", "count": 1}
  At least `count` `blocked` events for the tool: the harness's
  refusals are on record. This is the rule that separates "the agent
  never tried" from "the agent tried, was stopped, and the stop was
  logged" — without it, a trace with no blocked events is ambiguous
  between a well-behaved agent and a harness that doesn't record
  denials at all.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

from .trace import Trace

PathLike = Union[str, Path]

RULE_TYPES = (
    "order",
    "requires",
    "forbidden",
    "max_calls",
    "min_calls",
    "no_repeat",
    "max_events",
    "min_blocked",
)


@dataclass(frozen=True)
class Rule:
    type: str
    raw: dict

    @classmethod
    def from_dict(cls, data: dict, where: str = "rule") -> "Rule":
        if not isinstance(data, dict):
            raise ValueError(f"{where}: rule must be a JSON object")
        rule_type = data.get("type")
        if rule_type not in RULE_TYPES:
            raise ValueError(
                f"{where}: unknown rule type {rule_type!r} "
                f"(expected one of {RULE_TYPES})"
            )

        def need(name: str) -> None:
            if name not in data:
                raise ValueError(
                    f"{where}: {rule_type} rule is missing {name!r}"
                )

        if rule_type == "order":
            need("before")
            need("after")
        elif rule_type == "requires":
            need("tool")
            need("needs")
        elif rule_type in ("forbidden", "no_repeat"):
            if rule_type == "forbidden":
                need("tool")
            if "args_match" in data:
                if not isinstance(data["args_match"], dict):
                    raise ValueError(f"{where}: 'args_match' must be an object")
                for key, pattern in data["args_match"].items():
                    try:
                        re.compile(str(pattern))
                    except re.error as exc:
                        raise ValueError(
                            f"{where}: invalid regex for arg {key!r}: {exc}"
                        ) from exc
        elif rule_type in ("max_calls", "min_calls", "min_blocked"):
            need("tool")
            need("count")
            if not isinstance(data["count"], int) or data["count"] < 0:
                raise ValueError(f"{where}: 'count' must be a non-negative integer")
        elif rule_type == "max_events":
            need("count")
            if not isinstance(data["count"], int) or data["count"] < 0:
                raise ValueError(f"{where}: 'count' must be a non-negative integer")
        return cls(type=rule_type, raw=dict(data))

    def describe(self) -> str:
        raw = self.raw
        if self.type == "order":
            return f"{raw['before']} must be called before {raw['after']}"
        if self.type == "requires":
            target = "finishing" if raw["tool"] == "final" else f"calling {raw['tool']}"
            return f"{target} requires a prior {raw['needs']} call"
        if self.type == "forbidden":
            if "args_match" in raw:
                return f"{raw['tool']} must not be called with args matching {raw['args_match']}"
            return f"{raw['tool']} must never be called"
        if self.type == "max_calls":
            return f"{raw['tool']} at most {raw['count']} call(s)"
        if self.type == "min_calls":
            return f"{raw['tool']} at least {raw['count']} call(s)"
        if self.type == "min_blocked":
            return f"{raw['tool']} blocked at least {raw['count']} time(s), on record"
        if self.type == "no_repeat":
            tool = raw.get("tool")
            return f"no repeated identical {tool} call" if tool else "no repeated identical call (any tool)"
        return f"trace at most {raw['count']} event(s)"


@dataclass(frozen=True)
class Result:
    rule: Rule
    ok: bool
    message: str

    def to_dict(self) -> dict:
        return {
            "rule": self.rule.raw,
            "description": self.rule.describe(),
            "ok": self.ok,
            "message": self.message,
        }


def load_rules(path: PathLike) -> list[Rule]:
    with Path(path).open(encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, list) or not data:
        raise ValueError(f"{path}: rules file must be a non-empty JSON list")
    return [
        Rule.from_dict(item, where=f"{path} rule {index + 1}")
        for index, item in enumerate(data)
    ]


def _first_step(trace: Trace, tool: str) -> Optional[int]:
    calls = trace.calls_to(tool)
    return calls[0].step if calls else None


def _check_order(trace: Trace, rule: Rule) -> Result:
    before, after = rule.raw["before"], rule.raw["after"]
    after_step = _first_step(trace, after)
    if after_step is None:
        return Result(rule, True, f"{after} was never called")
    before_step = _first_step(trace, before)
    if before_step is not None and before_step < after_step:
        return Result(
            rule, True, f"{before} at step {before_step} precedes {after} at step {after_step}"
        )
    return Result(
        rule,
        False,
        f"{after} first called at step {after_step} with no prior {before} call",
    )


def _check_requires(trace: Trace, rule: Rule) -> Result:
    tool, needs = rule.raw["tool"], rule.raw["needs"]
    if tool == "final":
        target = trace.final_event
        target_step = target.step if target else None
        target_name = "the final event"
    else:
        target_step = _first_step(trace, tool)
        target_name = f"the first {tool} call"
    if target_step is None:
        return Result(rule, True, f"{tool} never occurs, so the requirement is vacuous")
    needs_step = _first_step(trace, needs)
    if needs_step is not None and needs_step < target_step:
        return Result(
            rule, True, f"{needs} at step {needs_step} precedes {target_name} at step {target_step}"
        )
    return Result(
        rule,
        False,
        f"{target_name} is at step {target_step} with no prior {needs} call",
    )


def _args_match(args: dict, patterns: dict) -> bool:
    for key, pattern in patterns.items():
        if key not in args:
            return False
        if not re.search(str(pattern), str(args[key])):
            return False
    return True


def _check_forbidden(trace: Trace, rule: Rule) -> Result:
    tool = rule.raw["tool"]
    patterns = rule.raw.get("args_match")
    for call in trace.calls_to(tool):
        if patterns is None or _args_match(call.args, patterns):
            detail = f"{tool} called at step {call.step}"
            if patterns is not None:
                detail += f" with forbidden args {call.args}"
            return Result(rule, False, detail)
    return Result(rule, True, f"no forbidden {tool} call")


def _check_max_calls(trace: Trace, rule: Rule) -> Result:
    tool, count = rule.raw["tool"], rule.raw["count"]
    actual = len(trace.calls_to(tool))
    if actual <= count:
        return Result(rule, True, f"{tool} called {actual} time(s), limit {count}")
    return Result(rule, False, f"{tool} called {actual} time(s), limit {count}")


def _check_min_calls(trace: Trace, rule: Rule) -> Result:
    tool, count = rule.raw["tool"], rule.raw["count"]
    actual = len(trace.calls_to(tool))
    if actual >= count:
        return Result(rule, True, f"{tool} called {actual} time(s), minimum {count}")
    return Result(rule, False, f"{tool} called {actual} time(s), minimum {count}")


def _check_no_repeat(trace: Trace, rule: Rule) -> Result:
    only_tool = rule.raw.get("tool")
    last_seen: dict[str, tuple[dict, int]] = {}
    for call in trace.calls:
        if only_tool is not None and call.tool != only_tool:
            continue
        previous = last_seen.get(str(call.tool))
        if previous is not None and previous[0] == call.args:
            return Result(
                rule,
                False,
                f"{call.tool} call at step {call.step} repeats the identical "
                f"call from step {previous[1]} (args {call.args})",
            )
        last_seen[str(call.tool)] = (call.args, call.step)
    return Result(rule, True, "no identical back-to-back repeat")


def _check_max_events(trace: Trace, rule: Rule) -> Result:
    count = rule.raw["count"]
    actual = len(trace.events)
    if actual <= count:
        return Result(rule, True, f"{actual} event(s), limit {count}")
    return Result(rule, False, f"{actual} event(s), limit {count}")


def _check_min_blocked(trace: Trace, rule: Rule) -> Result:
    tool, count = rule.raw["tool"], rule.raw["count"]
    actual = len(trace.blocked_to(tool))
    if actual >= count:
        return Result(rule, True, f"{tool} blocked {actual} time(s), minimum {count}")
    return Result(
        rule,
        False,
        f"{tool} blocked {actual} time(s), minimum {count} — denials are "
        "missing from the record, or the harness does not log them",
    )


_CHECKERS: dict[str, Callable[[Trace, Rule], Result]] = {
    "order": _check_order,
    "requires": _check_requires,
    "forbidden": _check_forbidden,
    "max_calls": _check_max_calls,
    "min_calls": _check_min_calls,
    "no_repeat": _check_no_repeat,
    "max_events": _check_max_events,
    "min_blocked": _check_min_blocked,
}


def evaluate(trace: Trace, rules: list[Rule]) -> list[Result]:
    return [_CHECKERS[rule.type](trace, rule) for rule in rules]
