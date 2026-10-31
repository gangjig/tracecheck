"""Reports and the CLI exit-code contract: 0 pass, 1 rule failure,
2 unreadable input. The bundled demo must show exactly 4 pass / 2 fail."""

import json
from importlib import resources
from pathlib import Path

import pytest

from tracecheck.cli import main
from tracecheck.report import render_json, render_markdown
from tracecheck.rules import evaluate, load_rules
from tracecheck.trace import load_trace, trace_from_dicts


def _data(name):
    return Path(str(resources.files("tracecheck").joinpath(f"data/{name}")))


def test_bundled_demo_is_4_pass_2_fail():
    trace = load_trace(_data("sample_trace.jsonl"))
    rules = load_rules(_data("sample_rules.json"))
    results = evaluate(trace, rules)
    assert [r.ok for r in results] == [True, False, False, True, True, True]
    md = render_markdown(trace, results)
    assert "4/6 rules passed" in md
    assert "**FAIL**" in md
    data = json.loads(render_json(trace, results))
    assert data["metric"] == "tracecheck"
    assert data["passed"] == 4 and data["failed"] == 2 and data["ok"] is False


def _write(tmp_path, rows, rules):
    trace_path = tmp_path / "t.jsonl"
    trace_path.write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    rules_path = tmp_path / "r.json"
    rules_path.write_text(json.dumps(rules), encoding="utf-8")
    return trace_path, rules_path


def test_cli_check_exit_codes(tmp_path, capsys):
    passing = (
        [{"event": "call", "tool": "search", "args": {}}],
        [{"type": "min_calls", "tool": "search", "count": 1}],
    )
    trace_path, rules_path = _write(tmp_path, *passing)
    assert main(["check", str(trace_path), "--rules", str(rules_path)]) == 0
    capsys.readouterr()

    failing = (
        [{"event": "call", "tool": "shell", "args": {}}],
        [{"type": "forbidden", "tool": "shell"}],
    )
    trace_path, rules_path = _write(tmp_path, *failing)
    assert main(["check", str(trace_path), "--rules", str(rules_path)]) == 1
    capsys.readouterr()

    assert main(["check", str(tmp_path / "nope.jsonl"), "--rules", str(rules_path)]) == 2
    assert "error:" in capsys.readouterr().err


def test_cli_check_json_format(tmp_path, capsys):
    trace_path, rules_path = _write(
        tmp_path,
        [{"event": "final", "text": "done"}],
        [{"type": "requires", "tool": "final", "needs": "verify"}],
    )
    assert (
        main(
            ["check", str(trace_path), "--rules", str(rules_path), "--format", "json"]
        )
        == 1
    )
    data = json.loads(capsys.readouterr().out)
    assert data["failed"] == 1


def test_cli_demo_returns_0_and_shows_failures(capsys):
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "# Trace check" in out
    assert "4/6 rules passed" in out


def test_render_markdown_summary_line():
    trace = trace_from_dicts(
        [
            {"event": "call", "tool": "search", "args": {}},
            {"event": "final", "text": "done"},
        ]
    )
    results = evaluate(trace, load_rules(_data("sample_rules.json"))[:1])
    md = render_markdown(trace, results)
    assert "search × 1" in md
    assert "final event: yes" in md
