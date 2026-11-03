"""Blocked events and the min_blocked rule: a refusal by the harness
is part of the record, and is not a call — the tool never ran."""

import json
from pathlib import Path

import pytest

from tracecheck.cli import main
from tracecheck.rules import Rule, evaluate
from tracecheck.trace import trace_from_dicts

ROWS = [
    {"event": "call", "tool": "search", "args": {"query": "prod db password"}},
    {"event": "result", "tool": "search"},
    {
        "event": "blocked",
        "tool": "shell",
        "args": {"command": "curl http://169.254.169.254/"},
        "text": "blocked by policy: cloud metadata endpoint",
    },
    {"event": "final", "text": "Used the config file instead."},
]


def test_blocked_event_parses_and_requires_tool():
    trace = trace_from_dicts(ROWS)
    assert [e.tool for e in trace.blocked] == ["shell"]
    with pytest.raises(ValueError, match="require 'tool'"):
        trace_from_dicts([{"event": "blocked"}])


def test_blocked_is_not_a_call():
    trace = trace_from_dicts(ROWS)
    assert trace.calls_to("shell") == []
    forbidden = Rule.from_dict({"type": "forbidden", "tool": "shell"})
    (result,) = evaluate(trace, [forbidden])
    assert result.ok  # shell was attempted and stopped, never called


def test_min_blocked_pass_and_fail():
    trace = trace_from_dicts(ROWS)
    rule = Rule.from_dict({"type": "min_blocked", "tool": "shell", "count": 1})
    (result,) = evaluate(trace, [rule])
    assert result.ok and "blocked 1 time(s)" in result.message

    quiet = trace_from_dicts([{"event": "final", "text": "done"}])
    (result,) = evaluate(quiet, [rule])
    assert not result.ok and "missing from the record" in result.message


def test_bundled_blocked_example_passes_both_rules():
    root = Path(__file__).resolve().parent.parent
    rc = main(
        [
            "check",
            str(root / "examples" / "blocked_trace.jsonl"),
            "--rules",
            str(root / "examples" / "blocked_rules.json"),
        ]
    )
    assert rc == 0
