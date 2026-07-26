"""Build the dimensional model from raw_events.

Executes the SQL models in transform/models/ in dependency order. Each model
is a plain SELECT; we wrap it as CREATE OR REPLACE TABLE so the whole star
schema builds with no dbt dependency. The identical .sql files also run as
dbt-duckdb models (see transform/dbt_project.yml) for the production path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DUCKDB_PATH  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent / "models"

# Dimensions before facts.
BUILD_ORDER = [
    "dim_player",
    "dim_game",
    "fact_session",
    "fact_wager",
    "fact_bonus_claim",
]


def build(db_path: Path = DUCKDB_PATH) -> dict[str, int]:
    con = duckdb.connect(str(db_path))
    counts: dict[str, int] = {}
    for model in BUILD_ORDER:
        sql = (MODELS_DIR / f"{model}.sql").read_text()
        con.execute(f"CREATE OR REPLACE TABLE {model} AS {sql}")
        counts[model] = con.execute(f"SELECT count(*) FROM {model}").fetchone()[0]
    con.close()
    return counts


if __name__ == "__main__":
    for name, n in build().items():
        print(f"  {name:20} {n:>7} rows")