"""Transform tests: star schema shape, keys, and grain."""
from __future__ import annotations

import duckdb


def test_dim_player_has_unique_grain(warehouse):
    con = duckdb.connect(str(warehouse), read_only=True)
    total, distinct = con.execute(
        "SELECT count(*), count(DISTINCT player_id) FROM dim_player"
    ).fetchone()
    con.close()
    assert total == distinct, "dim_player must be one row per player"


def test_facts_are_populated(warehouse):
    con = duckdb.connect(str(warehouse), read_only=True)
    for table in ("fact_wager", "fact_session", "fact_bonus_claim"):
        n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        assert n > 0, f"{table} should not be empty"
    con.close()


def test_wager_foreign_keys_resolve(warehouse):
    con = duckdb.connect(str(warehouse), read_only=True)
    orphans = con.execute(
        """
        SELECT count(*) FROM fact_wager w
        LEFT JOIN dim_player p ON p.player_id = w.player_id
        WHERE p.player_id IS NULL
        """
    ).fetchone()[0]
    con.close()
    assert orphans == 0


def test_dim_game_category_derived(warehouse):
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = con.execute("SELECT game_id, game_category FROM dim_game").fetchall()
    con.close()
    assert rows
    for game_id, category in rows:
        assert game_id.startswith(category)