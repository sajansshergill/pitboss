"""Load the validated landing zone into DuckDB as a typed raw_events table.

This is the boundary between the Node edge (JSONL files) and the analytics
warehouse (DuckDB). Events have heterogeneous fields per type, so we union by
name and null-fill the columns a given event type doesn't carry.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DUCKDB_PATH, LANDING_DIR  # noqa: E402

# Full column superset across all event types.
RAW_COLUMNS = [
    "event_id", "event_type", "player_id", "timestamp", "session_id",
    "device_id", "ip_fingerprint", "game_id", "amount", "payment_instrument",
    "promotion_id", "qualifying_deposit_amount",
]


def load(db_path: Path = DUCKDB_PATH, landing: Path = LANDING_DIR) -> int:
    files = sorted(landing.glob("*.jsonl"))
    if not files:
        raise FileNotFoundError(f"no landing files in {landing}")

    con = duckdb.connect(str(db_path))
    con.execute("DROP TABLE IF EXISTS raw_events")

    # union_by_name lets DuckDB reconcile the per-type field differences.
    con.execute(
        """
        CREATE TABLE raw_events AS
        SELECT * FROM read_json(
            ?,
            format = 'newline_delimited',
            union_by_name = true,
            maximum_object_size = 1048576
        )
        """,
        [str(landing / "*.jsonl")],
    )

    # Guarantee every expected column exists even if no event carried it.
    existing = {r[0] for r in con.execute("DESCRIBE raw_events").fetchall()}
    for col in RAW_COLUMNS:
        if col not in existing:
            typ = "DOUBLE" if col in ("amount", "qualifying_deposit_amount") else "VARCHAR"
            con.execute(f"ALTER TABLE raw_events ADD COLUMN {col} {typ}")

    # Normalise timestamp to a real TIMESTAMP for downstream time logic.
    con.execute(
        "ALTER TABLE raw_events ADD COLUMN event_ts TIMESTAMP"
    )
    con.execute(
        "UPDATE raw_events SET event_ts = try_cast(timestamp AS TIMESTAMP)"
    )

    n = con.execute("SELECT count(*) FROM raw_events").fetchone()[0]
    con.close()
    return n


if __name__ == "__main__":
    count = load()
    print(f"loaded {count} events into raw_events @ {DUCKDB_PATH}")