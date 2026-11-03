"""tracecheck: deterministic assertions over agent traces."""

from .integrity import ChainResult, load_rows, seal_rows, verify_rows
from .report import render_json, render_markdown, report_to_dict
from .rules import Result, Rule, evaluate, load_rules
from .trace import Event, Trace, load_trace, trace_from_dicts

__version__ = "0.2.0"

__all__ = [
    "ChainResult",
    "Event",
    "Result",
    "Rule",
    "Trace",
    "evaluate",
    "load_rows",
    "load_rules",
    "load_trace",
    "render_json",
    "render_markdown",
    "report_to_dict",
    "seal_rows",
    "trace_from_dicts",
    "verify_rows",
    "__version__",
]
