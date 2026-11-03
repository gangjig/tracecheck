"""Hash-chain integrity for trace files: tamper evidence, not trust.

A trace is only worth checking if it is the trace the run actually
left behind. If whatever produced the file can also edit it, a rule
report proves nothing: a denied call can be re-labelled as a success,
or deleted outright, and every rule still passes.

`seal` appends a `chain` field to every event:

    chain[n] = sha256(chain[n-1] + canonical(event[n] without chain))

with a fixed genesis string as chain[0]'s predecessor. Editing any
event, deleting one, or reordering two breaks every hash from that
point on, and `verify` names the first step where the chain stops
adding up. The canonical form is JSON with sorted keys and compact
separators, so whitespace and key order in the file do not matter —
only content does.

What a chain does *not* prove: completeness at the tail. Chopping
the last events off leaves a shorter chain that still verifies, so
the final hash — the *anchor* — has to be recorded somewhere the
agent cannot reach (the harness's own log, a CI artifact, a second
system) at the end of the run. `verify --anchor <hash>` compares
against that record: prefix integrity from the chain, completeness
from the anchor.

This module is deliberately only the checkable half of the NIST /
NSA / CISA guidance on agent incident readiness (Oct 2026): traces
appended in real time by the harness, stored where the monitored
agent cannot rewrite them, denials included. tracecheck cannot
store anything for you — it can verify that what you were handed
is what was sealed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, Path]

GENESIS = "tracecheck:genesis:v1"
CHAIN_FIELD = "chain"


def canonical(row: dict) -> str:
    """The stable string a row's hash commits to (chain field excluded)."""
    content = {key: value for key, value in row.items() if key != CHAIN_FIELD}
    return json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _next_hash(previous: str, row: dict) -> str:
    return hashlib.sha256((previous + canonical(row)).encode("utf-8")).hexdigest()


def load_rows(path: PathLike) -> list[dict]:
    """Read a trace file as raw event dicts (no field normalization).

    Integrity has to cover the event exactly as written, so unlike
    `load_trace` this keeps every field, including `chain` itself.
    """
    rows: list[dict] = []
    with Path(path).open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            if not isinstance(data, dict):
                raise ValueError(f"{path}:{lineno}: event must be a JSON object")
            rows.append(data)
    if not rows:
        raise ValueError(f"{path}: trace is empty")
    return rows


def dump_rows(rows: list[dict]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def seal_rows(rows: list[dict]) -> tuple[list[dict], str]:
    """Return (sealed copy of rows, anchor). Input rows are not mutated."""
    sealed: list[dict] = []
    previous = GENESIS
    for index, row in enumerate(rows, start=1):
        if CHAIN_FIELD in row:
            raise ValueError(
                f"event {index}: already carries a {CHAIN_FIELD!r} field; "
                "refusing to re-seal a sealed trace"
            )
        digest = _next_hash(previous, row)
        sealed.append({**row, CHAIN_FIELD: digest})
        previous = digest
    return sealed, previous


@dataclass(frozen=True)
class ChainResult:
    ok: bool
    events: int
    anchor: Optional[str]
    bad_step: Optional[int]
    message: str


def verify_rows(rows: list[dict]) -> ChainResult:
    """Recompute the chain and compare, step by step.

    A row whose stored hash disagrees with the recomputed one, or
    that has no hash at all, fails at its own step: that is the first
    point where the file stops being the file that was sealed.
    """
    previous = GENESIS
    for index, row in enumerate(rows, start=1):
        claimed = row.get(CHAIN_FIELD)
        if claimed is None:
            return ChainResult(
                False,
                len(rows),
                None,
                index,
                f"step {index} has no {CHAIN_FIELD!r} field — the trace is not sealed",
            )
        digest = _next_hash(previous, row)
        if digest != claimed:
            return ChainResult(
                False,
                len(rows),
                None,
                index,
                f"step {index}: chain hash mismatch — this event was altered, "
                "or an earlier event was removed or reordered",
            )
        previous = digest
    return ChainResult(
        True,
        len(rows),
        previous,
        None,
        f"chain intact over {len(rows)} event(s); anchor {previous}",
    )
