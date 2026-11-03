"""Hash-chain integrity: seal/verify round-trips, and every tamper
mode — edit, delete, reorder, truncate — failing at the right step."""

import json

import pytest

from tracecheck.cli import main
from tracecheck.integrity import load_rows, seal_rows, verify_rows
from tracecheck.trace import load_trace

ROWS = [
    {"event": "call", "tool": "search", "args": {"query": "auth bug"}},
    {"event": "result", "tool": "search"},
    {"event": "call", "tool": "edit_file", "args": {"path": "auth.py"}},
    {"event": "final", "text": "Fixed."},
]


def _tampered(rows, fn):
    rows = json.loads(json.dumps(rows))
    fn(rows)
    return rows


def test_seal_verify_roundtrip():
    sealed, anchor = seal_rows(ROWS)
    result = verify_rows(sealed)
    assert result.ok and result.anchor == anchor and len(anchor) == 64
    assert all("chain" not in row for row in ROWS)  # input not mutated


def test_edited_event_fails_at_its_step():
    sealed, _ = seal_rows(ROWS)
    bad = _tampered(sealed, lambda r: r[2]["args"].__setitem__("path", "evil.py"))
    result = verify_rows(bad)
    assert not result.ok and result.bad_step == 3


def test_deleted_event_fails_at_following_step():
    sealed, _ = seal_rows(ROWS)
    bad = _tampered(sealed, lambda r: r.pop(1))
    result = verify_rows(bad)
    assert not result.ok and result.bad_step == 2


def test_reordered_events_fail():
    sealed, _ = seal_rows(ROWS)
    bad = _tampered(sealed, lambda r: r.__setitem__(slice(1, 3), [r[2], r[1]]))
    assert not verify_rows(bad).ok


def test_unsealed_trace_fails_as_not_sealed():
    result = verify_rows(ROWS)
    assert not result.ok and result.bad_step == 1
    assert "not sealed" in result.message


def test_tail_truncation_verifies_but_anchor_changes():
    sealed, anchor = seal_rows(ROWS)
    truncated_ok = verify_rows(sealed[:2])
    assert truncated_ok.ok  # a prefix chain is internally consistent...
    assert truncated_ok.anchor != anchor  # ...but it is not the same run


def test_reseal_is_refused():
    sealed, _ = seal_rows(ROWS)
    with pytest.raises(ValueError, match="re-seal"):
        seal_rows(sealed)


def _write(tmp_path, rows, name="t.jsonl"):
    path = tmp_path / name
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    return path


def test_cli_seal_verify_and_anchor(tmp_path, capsys):
    src = _write(tmp_path, ROWS)
    assert main(["seal", str(src)]) == 0
    out = capsys.readouterr().out
    anchor = next(
        line.split("anchor: ")[1] for line in out.splitlines() if "anchor:" in line
    )
    sealed_path = tmp_path / "t.sealed.jsonl"
    assert sealed_path.exists()
    assert main(["verify", str(sealed_path)]) == 0
    assert main(["verify", str(sealed_path), "--anchor", anchor]) == 0
    assert main(["verify", str(sealed_path), "--anchor", "0" * 64]) == 1
    assert main(["verify", str(tmp_path / "missing.jsonl")]) == 2


def test_cli_verify_detects_tampered_file(tmp_path):
    sealed, _ = seal_rows(ROWS)
    path = _write(tmp_path, sealed)
    rows = load_rows(path)
    rows[0]["args"]["query"] = "rewritten history"
    _write(tmp_path, rows)
    assert main(["verify", str(path)]) == 1


def test_sealed_trace_still_loads_and_checks(tmp_path):
    sealed, _ = seal_rows(ROWS)
    path = _write(tmp_path, sealed)
    trace = load_trace(path)  # the chain field is ignored by the parser
    assert len(trace.events) == 4 and trace.calls[0].tool == "search"


def test_check_require_chain(tmp_path):
    rules_path = tmp_path / "r.json"
    rules_path.write_text(
        json.dumps([{"type": "min_calls", "tool": "search", "count": 1}]),
        encoding="utf-8",
    )
    sealed, _ = seal_rows(ROWS)
    good = _write(tmp_path, sealed, "good.jsonl")
    assert main(["check", str(good), "--rules", str(rules_path), "--require-chain"]) == 0
    bad_rows = json.loads(json.dumps(sealed))
    bad_rows[3]["text"] = "I did nothing."
    bad = _write(tmp_path, bad_rows, "bad.jsonl")
    assert main(["check", str(bad), "--rules", str(rules_path), "--require-chain"]) == 1
    plain = _write(tmp_path, ROWS, "plain.jsonl")
    assert main(["check", str(plain), "--rules", str(rules_path), "--require-chain"]) == 1
    # ...while the same unsealed trace passes without the flag
    assert main(["check", str(plain), "--rules", str(rules_path)]) == 0
