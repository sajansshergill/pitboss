"""Shared pytest fixtures.

`warehouse` builds a full clean star schema in a temp DuckDB from a small
generated event batch, so transform/quality tests run fast and isolated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generator import emit  # noqa: E402
from transform import load_raw, build_star  # noqa: E402


def _write_landing(events, landing: Path) -> None:
    landing.mkdir(parents=True, exist_ok=True)
    (landing / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n"
    )


@pytest.fixture
def clean_events():
    return emit.generate(n_players=50, seed=1)


@pytest.fixture
def warehouse(tmp_path, clean_events):
    landing = tmp_path / "landing"
    _write_landing(clean_events, landing)
    db = tmp_path / "wh.duckdb"
    load_raw.load(db_path=db, landing=landing)
    build_star.build(db_path=db)
    return db


@pytest.fixture
def dirty_warehouse(tmp_path):
    """Warehouse built from events with injected duplicates + late batch."""
    events = emit.generate(n_players=50, seed=1)
    events = emit.inject_failures(events, ["duplicates", "late-batch"])
    landing = tmp_path / "landing"
    _write_landing(events, landing)
    db = tmp_path / "wh.duckdb"
    load_raw.load(db_path=db, landing=landing)
    build_star.build(db_path=db)
    return db