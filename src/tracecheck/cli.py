"""Command line interface: tracecheck {check, seal, verify, demo}.

Exit codes for `check`: 0 = every rule passed, 1 = at least one rule
failed (the trace misbehaved), 2 = the trace or rules could not even
be read. CI can tell "the agent broke a rule" from "the harness is
broken" without parsing the report.

`seal` and `verify` follow the same split: 0 = sealed / chain intact,
1 = the chain does not verify (the trace was tampered with), 2 = the
input could not even be read.
"""

from __future__ import annotations

import argparse
import sys
from importlib import resources
from pathlib import Path
from typing import Optional, Sequence

from .integrity import dump_rows, load_rows, seal_rows, verify_rows
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
    p_check.add_argument(
        "--require-chain",
        action="store_true",
        help="first verify the trace's hash chain (see `seal`); a broken "
        "chain fails the check with exit code 1 before any rule runs",
    )

    p_seal = sub.add_parser(
        "seal",
        help="add a hash chain to a trace file, so later edits, deletions "
        "and reordering are detectable (see `verify`)",
    )
    p_seal.add_argument("trace", metavar="TRACE.jsonl")
    p_seal.add_argument(
        "--output",
        metavar="FILE",
        help="write the sealed trace to FILE (default: TRACE with "
        "'.sealed' inserted before the extension)",
    )

    p_verify = sub.add_parser(
        "verify",
        help="verify a sealed trace's hash chain; with --anchor, also "
        "check the final hash against the anchor recorded at run time "
        "(catches tail truncation, which a chain alone cannot)",
    )
    p_verify.add_argument("trace", metavar="TRACE.jsonl")
    p_verify.add_argument("--anchor", metavar="HASH")

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


def _sealed_path(trace: str) -> Path:
    path = Path(trace)
    return path.with_name(path.stem + ".sealed" + path.suffix)


def _cmd_seal(args) -> int:
    rows = load_rows(args.trace)
    sealed, anchor = seal_rows(rows)
    output = Path(args.output) if args.output else _sealed_path(args.trace)
    output.write_text(dump_rows(sealed), encoding="utf-8")
    print(f"sealed {len(sealed)} event(s) -> {output}")
    print(f"anchor: {anchor}")
    print(
        "record the anchor somewhere the agent cannot reach; "
        "`verify --anchor <hash>` uses it to catch tail truncation."
    )
    return 0


def _cmd_verify(args) -> int:
    rows = load_rows(args.trace)
    result = verify_rows(rows)
    if not result.ok:
        print(f"integrity FAIL: {result.message}", file=sys.stderr)
        return 1
    if args.anchor is not None and args.anchor != result.anchor:
        print(
            "integrity FAIL: anchor mismatch — "
            f"expected {args.anchor}, computed {result.anchor}. "
            "The chain is internally consistent but is not the chain the "
            "recorded anchor belongs to: the tail may be truncated, or "
            "this is a different run.",
            file=sys.stderr,
        )
        return 1
    print(f"integrity OK: {result.message}")
    return 0


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

        if args.command == "seal":
            return _cmd_seal(args)
        if args.command == "verify":
            return _cmd_verify(args)

        if args.require_chain:
            chain = verify_rows(load_rows(args.trace))
            if not chain.ok:
                print(f"integrity FAIL: {chain.message}", file=sys.stderr)
                return 1

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
