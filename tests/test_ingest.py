"""Ingestion tests: drive the real Node.js edge and assert routing.

Skipped automatically if Node is not on PATH.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "ingest" / "server.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not installed"
)


def _run_batch(events, workdir: Path):
    firehose = workdir / "firehose.jsonl"
    firehose.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    # server.js writes to <repo>/data/landing|quarantine; run in an isolated copy.
    (workdir / "data" / "landing").mkdir(parents=True)
    (workdir / "data" / "quarantine").mkdir(parents=True)
    shutil.copytree(ROOT / "ingest", workdir / "ingest")
    proc = subprocess.run(
        ["node", str(workdir / "ingest" / "server.js"), "--batch", str(firehose)],
        capture_output=True, text=True, cwd=workdir,
    )
    assert proc.returncode == 0, proc.stderr
    landing = list((workdir / "data" / "landing").glob("*.jsonl"))
    quarantine = list((workdir / "data" / "quarantine").glob("*.jsonl"))
    return landing, quarantine


def test_valid_event_accepted(tmp_path):
    good = {
        "event_id": "e1", "event_type": "wager", "player_id": "P1",
        "timestamp": "2026-07-25T00:00:00+00:00",
        "session_id": "S1", "game_id": "slots_x", "amount": 5.0,
    }
    landing, quarantine = _run_batch([good], tmp_path)
    assert landing and not quarantine


def test_missing_field_quarantined(tmp_path):
    bad = {  # missing amount + timestamp
        "event_id": "e2", "event_type": "wager", "player_id": "P1",
        "session_id": "S1", "game_id": "slots_x",
    }
    landing, quarantine = _run_batch([bad], tmp_path)
    assert quarantine and not landing
    reject = json.loads((quarantine[0]).read_text().splitlines()[0])
    assert any("amount" in e for e in reject["errors"])


def test_negative_amount_quarantined(tmp_path):
    bad = {
        "event_id": "e3", "event_type": "deposit", "player_id": "P1",
        "timestamp": "2026-07-25T00:00:00+00:00",
        "payment_instrument": "CARD-1", "amount": -10.0,
    }
    _, quarantine = _run_batch([bad], tmp_path)
    assert quarantine