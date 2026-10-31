"""tracecheck: deterministic assertions over agent traces."""

from .report import render_json, render_markdown, report_to_dict
from .rules import Result, Rule, evaluate, load_rules
from .trace import Event, Trace, load_trace, trace_from_dicts

__version__ = "0.1.0"

__all__ = [
    "Event",
    "Result",
    "Rule",
    "Trace",
    "evaluate",
    "load_rules",
    "load_trace",
    "render_json",
    "render_markdown",
    "report_to_dict",
    "trace_from_dicts",
    "__version__",
]
