"""Command line interface: tracecheck {check, demo}.

Exit codes for `check`: 0 = every rule passed, 1 = at least one rule
failed (the trace misbehaved), 2 = the trace or rules could not even
be read. CI can tell "the agent broke a rule" from "the harness is
broken" without parsing the report.
"""

from __future__ import annotations

import argparse
import sys
from importlib import resources
from pathlib import Path
from typing import Optional, Sequence

from .report import render_json, render_markdown
from .rules import evaluate, load_rules
from .trace import Trace, load_trace


def _data_path(name: str) -> Path:
    return Path(str(resources.files("tracecheck").joinpath(f"data/{name}")))


def _print_or_write(text: str, output: Optional[str]) -> None:
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def _render(trace: Trace, results, fmt: str) -> str:
    if fmt == "json":
        return render_json(trace, results)
    return render_markdown(trace, results)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracecheck",
        description="Deterministic assertions over agent traces: "
        "unit tests for agent behavior, no LLM judge.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="check a trace file against a rules file")
    p_check.add_argument("trace", metavar="TRACE.jsonl")
    p_check.add_argument("--rules", required=True, metavar="RULES.json")
    p_check.add_argument(
        "--format", choices=("md", "json"), default="md",
        help="output format (default: md)",
    )
    p_check.add_argument(
        "--output", metavar="FILE", help="write to FILE instead of stdout"
    )

    p_demo = sub.add_parser(
        "demo",
        help="check the bundled sample trace: a coding agent that "
        "repeats itself and finishes without verifying (2 rules fail)",
    )
    p_demo.add_argument(
        "--format", choices=("md", "json"), default="md",
        help="output format (default: md)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            trace = load_trace(_data_path("sample_trace.jsonl"))
            rules = load_rules(_data_path("sample_rules.json"))
            results = evaluate(trace, rules)
            _print_or_write(_render(trace, results, args.format), None)
            return 0  # a demo of failures is still a successful demo

        trace = load_trace(args.trace)
        rules = load_rules(args.rules)
        results = evaluate(trace, rules)
        _print_or_write(_render(trace, results, args.format), args.output)
        return 0 if all(r.ok for r in results) else 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
