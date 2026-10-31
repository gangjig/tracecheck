"""Trace loading and validation."""

import json

import pytest

from tracecheck.trace import load_trace, trace_from_dicts

GOOD = [
    {"event": "call", "tool": "search", "args": {"query": "x"}},
    {"event": "result", "tool": "search"},
    {"event": "final", "text": "done"},
]


def test_trace_from_dicts_steps_and_summary():
    trace = trace_from_dicts(GOOD)
    assert [e.step for e in trace.events] == [1, 2, 3]
    summary = trace.summary()
    assert summary["events"] == 3
    assert summary["tool_calls"] == 1
    assert summary["tools"] == {"search": 1}
    assert summary["has_final"] is True


def test_load_trace_roundtrip(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in GOOD), encoding="utf-8"
    )
    trace = load_trace(path)
    assert trace.calls_to("search")[0].args == {"query": "x"}
    assert trace.final_event.text == "done"


def test_load_trace_validation(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text('{"event": "teleport"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="must be one of"):
        load_trace(path)
    path.write_text('{"event": "call"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="require 'tool'"):
        load_trace(path)
    path.write_text('{"event": "message", "args": [1]}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="'args' must be an object"):
        load_trace(path)
    path.write_text("{bad\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_trace(path)
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="trace is empty"):
        load_trace(path)
