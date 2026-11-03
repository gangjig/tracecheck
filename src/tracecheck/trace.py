"""Agent traces: the event log a harness leaves behind.

A trace is JSONL, one event per line, in execution order. Steps are
numbered from 1 by line, so every rule message can point at an exact
line in the file:

    {"event": "call",    "tool": "search", "args": {"query": "auth bug"}}
    {"event": "result",  "tool": "search"}
    {"event": "blocked", "tool": "shell", "args": {"command": "curl ..."}}
    {"event": "message", "text": "Found it in auth.py."}
    {"event": "call",    "tool": "edit_file", "args": {"path": "auth.py"}}
    {"event": "final",   "text": "Fixed."}

Event types:

* `call`    -- the agent invoked a tool (requires `tool`; `args` an
               optional object).
* `result`  -- a tool returned (requires `tool`).
* `blocked` -- the harness refused a tool call — a guardrail or
               policy stopped it before it ran (requires `tool`;
               `args` an optional object; `text` can carry the
               reason). A blocked call is *not* a call: it never
               executed, so it counts toward no `call` rule. It
               exists so that "the agent tried and was stopped" is
               distinguishable from "the agent never tried" — the
               difference an incident review lives on.
* `message` -- the agent said something (`text` optional).
* `final`   -- the agent finished (at most the semantics you give it;
               rules can require things *before* the final event).

The format is deliberately the least common denominator: any harness
that can log what it did can emit it, and `tracecheck` never needs to
know which framework produced the run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, Path]

EVENT_TYPES = ("call", "result", "blocked", "message", "final")


@dataclass(frozen=True)
class Event:
    step: int
    event: str
    tool: Optional[str] = None
    args: dict = field(default_factory=dict)
    text: str = ""

    @classmethod
    def from_dict(cls, data: dict, step: int, where: str) -> "Event":
        if not isinstance(data, dict):
            raise ValueError(f"{where}: event must be a JSON object")
        event = data.get("event")
        if event not in EVENT_TYPES:
            raise ValueError(
                f"{where}: 'event' must be one of {EVENT_TYPES}, "
                f"got {event!r}"
            )
        tool = data.get("tool")
        if event in ("call", "result", "blocked") and not tool:
            raise ValueError(f"{where}: {event!r} events require 'tool'")
        args = data.get("args", {})
        if not isinstance(args, dict):
            raise ValueError(f"{where}: 'args' must be an object")
        return cls(
            step=step,
            event=event,
            tool=str(tool) if tool is not None else None,
            args=args,
            text=str(data.get("text", "")),
        )


@dataclass(frozen=True)
class Trace:
    events: tuple[Event, ...]

    @property
    def calls(self) -> list[Event]:
        return [e for e in self.events if e.event == "call"]

    def calls_to(self, tool: str) -> list[Event]:
        return [e for e in self.calls if e.tool == tool]

    @property
    def blocked(self) -> list[Event]:
        return [e for e in self.events if e.event == "blocked"]

    def blocked_to(self, tool: str) -> list[Event]:
        return [e for e in self.blocked if e.tool == tool]

    @property
    def final_event(self) -> Optional[Event]:
        for event in self.events:
            if event.event == "final":
                return event
        return None

    def summary(self) -> dict:
        tools: dict[str, int] = {}
        for call in self.calls:
            tools[str(call.tool)] = tools.get(str(call.tool), 0) + 1
        return {
            "events": len(self.events),
            "tool_calls": len(self.calls),
            "tools": tools,
            "has_final": self.final_event is not None,
        }


def load_trace(path: PathLike) -> Trace:
    events: list[Event] = []
    with Path(path).open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            events.append(Event.from_dict(data, len(events) + 1, f"{path}:{lineno}"))
    if not events:
        raise ValueError(f"{path}: trace is empty")
    return Trace(events=tuple(events))


def trace_from_dicts(rows: list[dict]) -> Trace:
    """Build a trace from in-memory event dicts (used by tests/tools)."""
    return Trace(
        events=tuple(
            Event.from_dict(row, index + 1, f"event {index + 1}")
            for index, row in enumerate(rows)
        )
    )
