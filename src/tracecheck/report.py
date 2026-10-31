"""Render a check run as Markdown or JSON."""

from __future__ import annotations

import json

from .rules import Result
from .trace import Trace


def report_to_dict(trace: Trace, results: list[Result]) -> dict:
    passed = sum(1 for r in results if r.ok)
    return {
        "metric": "tracecheck",
        "trace": trace.summary(),
        "rules": [r.to_dict() for r in results],
        "passed": passed,
        "failed": len(results) - passed,
        "ok": passed == len(results),
    }


def render_json(trace: Trace, results: list[Result]) -> str:
    return json.dumps(report_to_dict(trace, results), indent=2) + "\n"


def render_markdown(trace: Trace, results: list[Result]) -> str:
    summary = trace.summary()
    tools = (
        ", ".join(
            f"{name} × {count}"
            for name, count in sorted(summary["tools"].items())
        )
        or "(none)"
    )
    passed = sum(1 for r in results if r.ok)
    lines = [
        "# Trace check",
        "",
        f"Trace: {summary['events']} events, {summary['tool_calls']} tool "
        f"calls ({tools}); final event: "
        f"{'yes' if summary['has_final'] else 'no'}.",
        "",
        "| # | Rule | Result | Detail |",
        "|---:|---|---|---|",
    ]
    for index, result in enumerate(results, start=1):
        status = "PASS" if result.ok else "**FAIL**"
        lines.append(
            f"| {index} | {result.rule.describe()} | {status} | "
            f"{result.message} |"
        )
    lines += [
        "",
        f"**{passed}/{len(results)} rules passed.**",
        "",
    ]
    return "\n".join(lines)
