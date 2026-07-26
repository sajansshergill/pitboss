"""Generator tests: envelope integrity, planted fraud, failure injection."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from generator import emit  # noqa: E402
from generator.schema import required_fields  # noqa: E402


def test_every_event_has_required_fields():
    events = emit.generate(n_players=30, seed=3)
    for e in events:
        for field in required_fields(e["event_type"]):
            assert field in e, f"{e['event_type']} missing {field}"


def test_determinism():
    def strip(evs):
        return [{k: v for k, v in e.items() if k != "timestamp"} for e in evs]
    # timestamps are wall-clock-anchored by design (freshness); ids + structure are deterministic
    assert strip(emit.generate(20, seed=9)) == strip(emit.generate(20, seed=9))


def test_bonus_abuse_ring_shares_one_card():
    events, world = emit.generate_with_world(n_players=100, seed=1)
    ring = world.rings[0]
    cards = {world.card[p] for p in ring}
    assert len(cards) == 1, "ring members should share exactly one card"
    assert len(ring) >= 3


def test_write_referrals_creates_parent_directory(tmp_path):
    _, world = emit.generate_with_world(n_players=30, seed=1)
    path = tmp_path / "nested" / "referrals.csv"
    emit.write_referrals(world, path)
    assert path.exists()
    assert path.read_text().startswith("referrer,referee\n")


def test_inject_duplicates_adds_repeat_event_ids():
    events = emit.generate(50, seed=1)
    dirty = emit.inject_failures(events, ["duplicates"])
    counts = Counter(e["event_id"] for e in dirty)
    assert any(c > 1 for c in counts.values())


def test_inject_schema_drift_breaks_some_events():
    events = emit.generate(50, seed=1)
    dirty = emit.inject_failures(events, ["schema-drift"])
    assert any("amt" in e for e in dirty), "drift should rename amount -> amt"


def test_inject_late_batch_backdates_events():
    events = emit.generate(50, seed=1)
    earliest_clean = min(e["timestamp"] for e in events)
    dirty = emit.inject_failures(events, ["late-batch"])
    assert min(e["timestamp"] for e in dirty) < earliest_clean