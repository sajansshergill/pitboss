"""Graph loader tests: referral parsing and graceful skip without Neo4j."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from graph import load_graph  # noqa: E402


def test_load_referrals_reads_csv(tmp_path):
    f = tmp_path / "referrals.csv"
    f.write_text("referrer,referee\nP1,P2\nP2,P3\n")
    pairs = load_graph._load_referrals(f)
    assert pairs == [("P1", "P2"), ("P2", "P3")]


def test_load_referrals_missing_file(tmp_path):
    assert load_graph._load_referrals(tmp_path / "nope.csv") == []


def test_graph_load_skips_without_neo4j(warehouse, monkeypatch):
    # Point at an unreachable bolt port; loader should return False, not raise.
    monkeypatch.setattr(load_graph, "NEO4J_URI", "bolt://127.0.0.1:59999")
    assert load_graph.load(db_path=warehouse, require=False) is False