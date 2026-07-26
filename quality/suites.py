"""Data-quality check definitions.

Each check is a small SQL probe returning the count of *violating* rows. A
check with severity ERROR gates the pipeline (a failing batch is quarantined,
not published); severity WARN surfaces a signal without blocking — used for
responsible-gaming detections that are expected to be non-zero.
"""
from __future__ import annotations

from dataclasses import dataclass

ERROR = "ERROR"
WARN = "WARN"


@dataclass(frozen=True)
class Check:
    name: str
    severity: str
    description: str
    sql: str  # must SELECT a single integer: the count of violating rows


CHECKS: list[Check] = [
    Check(
        "ri_wager_player", ERROR,
        "every wager's player_id resolves to a known player",
        """
        SELECT count(*) FROM fact_wager w
        LEFT JOIN dim_player p ON p.player_id = w.player_id
        WHERE p.player_id IS NULL
        """,
    ),
    Check(
        "ri_bonus_player", ERROR,
        "every bonus claim's player_id resolves to a known player",
        """
        SELECT count(*) FROM fact_bonus_claim b
        LEFT JOIN dim_player p ON p.player_id = b.player_id
        WHERE p.player_id IS NULL
        """,
    ),
    Check(
        "inv_bonus_le_deposit", ERROR,
        "bonus never exceeds the deposit that qualified it",
        """
        SELECT count(*) FROM fact_bonus_claim
        WHERE bonus_amount > qualifying_deposit_amount
        """,
    ),
    Check(
        "inv_no_negative_amounts", ERROR,
        "no negative monetary amounts survive into the warehouse",
        "SELECT count(*) FROM raw_events WHERE amount < 0",
    ),
    Check(
        "dedup_event_id", ERROR,
        "event_id is unique (no duplicate delivery)",
        """
        SELECT coalesce(sum(c - 1), 0) FROM (
            SELECT event_id, count(*) AS c FROM raw_events
            GROUP BY event_id HAVING count(*) > 1
        )
        """,
    ),
    Check(
        "freshness", ERROR,
        "no events older than the freshness horizon (7 days)",
        """
        SELECT count(*) FROM raw_events
        WHERE event_ts < now() - INTERVAL 7 DAY
        """,
    ),
    # ---- Responsible-gaming detections (reported, non-blocking) ----
    Check(
        "rg_wager_after_exclusion", WARN,
        "wagers placed after a player self-excluded",
        """
        SELECT count(*) FROM fact_wager w
        JOIN dim_player p ON p.player_id = w.player_id
        WHERE p.is_self_excluded AND w.event_ts > p.self_excluded_ts
        """,
    ),
]