"""Load the identity graph into Neo4j and run collusion detections.

Builds Player / Device / PaymentInstrument / Fingerprint / Promotion nodes from
the DuckDB warehouse, plus REFERRED_BY edges from referrals.csv. If no Neo4j is
reachable, the stage skips cleanly (exit 0) so the lightweight local path and CI
don't require a running database — pass --require to make it a hard failure.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (  # noqa: E402
    DUCKDB_PATH, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, DATA_DIR,
)

CONSTRAINTS = [
    "CREATE CONSTRAINT player_id IF NOT EXISTS FOR (p:Player) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT device_id IF NOT EXISTS FOR (d:Device) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT card_id IF NOT EXISTS FOR (c:PaymentInstrument) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT fp_id IF NOT EXISTS FOR (f:Fingerprint) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT promo_id IF NOT EXISTS FOR (pr:Promotion) REQUIRE pr.id IS UNIQUE",
]


def _fetch(db_path: Path):
    con = duckdb.connect(str(db_path), read_only=True)
    players = con.execute(
        """
        SELECT player_id, primary_device, primary_card, primary_fingerprint,
               is_self_excluded
        FROM dim_player
        """
    ).fetchall()
    claims = con.execute(
        "SELECT player_id, promotion_id FROM fact_bonus_claim"
    ).fetchall()
    con.close()
    return players, claims


def _load_referrals(path: Path):
    if not path.exists():
        return []
    with open(path) as fh:
        return [(r["referrer"], r["referee"]) for r in csv.DictReader(fh)]


def load(db_path: Path = DUCKDB_PATH, require: bool = False) -> bool:
    try:
        from neo4j import GraphDatabase
    except ImportError:
        msg = "neo4j driver not installed"
        if require:
            raise
        print(f"[graph] skipped: {msg}")
        return False

    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001 — any connection issue -> clean skip
        if require:
            raise
        print(f"[graph] skipped: cannot reach Neo4j at {NEO4J_URI} ({exc})")
        return False

    players, claims = _fetch(db_path)
    referrals = _load_referrals(DATA_DIR / "referrals.csv")

    with driver.session() as session:
        for c in CONSTRAINTS:
            session.run(c)

        # Nodes + identity edges, batched via UNWIND.
        session.run(
            """
            UNWIND $rows AS row
            MERGE (p:Player {id: row.player_id})
              SET p.self_excluded = row.excluded
            FOREACH (_ IN CASE WHEN row.device IS NULL THEN [] ELSE [1] END |
                MERGE (d:Device {id: row.device})
                MERGE (p)-[:USES_DEVICE]->(d))
            FOREACH (_ IN CASE WHEN row.card IS NULL THEN [] ELSE [1] END |
                MERGE (c:PaymentInstrument {id: row.card})
                MERGE (p)-[:USES_CARD]->(c))
            FOREACH (_ IN CASE WHEN row.fp IS NULL THEN [] ELSE [1] END |
                MERGE (f:Fingerprint {id: row.fp})
                MERGE (p)-[:HAS_FINGERPRINT]->(f))
            """,
            rows=[
                {"player_id": p[0], "device": p[1], "card": p[2],
                 "fp": p[3], "excluded": bool(p[4])}
                for p in players
            ],
        )
        session.run(
            """
            UNWIND $rows AS row
            MATCH (p:Player {id: row.player_id})
            MERGE (pr:Promotion {id: row.promotion_id})
            MERGE (p)-[:CLAIMED]->(pr)
            """,
            rows=[{"player_id": c[0], "promotion_id": c[1]} for c in claims],
        )
        if referrals:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (a:Player {id: row.referrer})
                MATCH (b:Player {id: row.referee})
                MERGE (a)-[:REFERRED_BY]->(b)
                """,
                rows=[{"referrer": a, "referee": b} for a, b in referrals],
            )

        counts = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label"
        ).data()

    driver.close()
    print("[graph] loaded nodes:", {c["label"]: c["n"] for c in counts})
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--require", action="store_true",
                    help="fail (non-zero) if Neo4j is unreachable")
    args = ap.parse_args()
    ok = load(require=args.require)
    sys.exit(0 if (ok or not args.require) else 1)