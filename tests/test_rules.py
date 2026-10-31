"""Every rule type, passing and failing, with step-precise messages."""

import pytest

from tracecheck.rules import Rule, evaluate
from tracecheck.trace import trace_from_dicts


def call(tool, args=None):
    return {"event": "call", "tool": tool, "args": args or {}}


def result(tool):
    return {"event": "result", "tool": tool}


def final(text="done"):
    return {"event": "final", "text": text}


def check(rows, rule_dict):
    (outcome,) = evaluate(trace_from_dicts(rows), [Rule.from_dict(rule_dict)])
    return outcome


def test_order_pass_fail_vacuous():
    rows = [call("search"), result("search"), call("edit_file")]
    assert check(rows, {"type": "order", "before": "search", "after": "edit_file"}).ok
    outcome = check(
        [call("edit_file"), call("search")],
        {"type": "order", "before": "search", "after": "edit_file"},
    )
    assert not outcome.ok
    assert "step 1" in outcome.message
    assert check(
        [call("search")],
        {"type": "order", "before": "search", "after": "edit_file"},
    ).ok  # after never called


def test_requires_tool_and_final():
    rows = [call("verify"), call("submit"), final()]
    assert check(rows, {"type": "requires", "tool": "submit", "needs": "verify"}).ok
    outcome = check(
        [call("submit")], {"type": "requires", "tool": "submit", "needs": "verify"}
    )
    assert not outcome.ok
    # final variant: finishing requires a prior verify call.
    outcome = check(
        [call("edit_file"), final()],
        {"type": "requires", "tool": "final", "needs": "verify"},
    )
    assert not outcome.ok
    assert "step 2" in outcome.message
    assert check(
        [call("verify"), final()],
        {"type": "requires", "tool": "final", "needs": "verify"},
    ).ok
    # No final event at all: vacuous pass.
    assert check(
        [call("edit_file")],
        {"type": "requires", "tool": "final", "needs": "verify"},
    ).ok


def test_forbidden_plain_and_args_match():
    rows = [call("shell", {"command": "ls"})]
    assert not check(rows, {"type": "forbidden", "tool": "shell"}).ok
    # args_match narrows the ban to matching calls only.
    ban_rm = {"type": "forbidden", "tool": "shell", "args_match": {"command": "rm\\s"}}
    assert check(rows, ban_rm).ok
    outcome = check([call("shell", {"command": "rm -rf /"})], ban_rm)
    assert not outcome.ok
    assert "step 1" in outcome.message


def test_max_and_min_calls_boundaries():
    rows = [call("search"), call("search")]
    assert check(rows, {"type": "max_calls", "tool": "search", "count": 2}).ok
    assert not check(rows, {"type": "max_calls", "tool": "search", "count": 1}).ok
    assert check(rows, {"type": "min_calls", "tool": "search", "count": 2}).ok
    assert not check(rows, {"type": "min_calls", "tool": "search", "count": 3}).ok


def test_no_repeat_identical_args_only():
    repeated = [call("edit_file", {"a": 1}), result("edit_file"), call("edit_file", {"a": 1})]
    outcome = check(repeated, {"type": "no_repeat"})
    assert not outcome.ok
    assert "step 3" in outcome.message and "step 1" in outcome.message
    changed = [call("edit_file", {"a": 1}), call("edit_file", {"a": 2})]
    assert check(changed, {"type": "no_repeat"}).ok
    # A repeat of a different tool is ignored when a tool filter is set.
    mixed = [call("search", {"q": "x"}), call("edit_file", {"a": 1}), call("search", {"q": "x"})]
    assert not check(mixed, {"type": "no_repeat"}).ok
    assert check(mixed, {"type": "no_repeat", "tool": "edit_file"}).ok
    # Not back-to-back for the same tool after a different-args call.
    spaced = [
        call("search", {"q": "x"}),
        call("search", {"q": "y"}),
        call("search", {"q": "x"}),
    ]
    assert check(spaced, {"type": "no_repeat"}).ok


def test_max_events():
    rows = [call("search"), result("search"), final()]
    assert check(rows, {"type": "max_events", "count": 3}).ok
    assert not check(rows, {"type": "max_events", "count": 2}).ok


def test_rule_validation():
    with pytest.raises(ValueError, match="unknown rule type"):
        Rule.from_dict({"type": "vibes"})
    with pytest.raises(ValueError, match="missing 'after'"):
        Rule.from_dict({"type": "order", "before": "search"})
    with pytest.raises(ValueError, match="non-negative integer"):
        Rule.from_dict({"type": "max_calls", "tool": "search", "count": -1})
    with pytest.raises(ValueError, match="invalid regex"):
        Rule.from_dict(
            {"type": "forbidden", "tool": "shell", "args_match": {"c": "([bad"}}
        )
