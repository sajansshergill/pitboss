"""Shared configuration for the PitBoss pipeline.

Single source of truth for filesystem paths and constants so every stage
(generator, ingest, transform, quality, graph) agrees on where data lives.
"""
from __future__ import annotations

import os
from pathlib import Path

# Repo root = directory containing this file.
ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
RAW_FIREHOSE = DATA_DIR / "raw_firehose.jsonl"      # generator output (pre-validation)
LANDING_DIR = DATA_DIR / "landing"                   # validated events (Node writes here)
QUARANTINE_DIR = DATA_DIR / "quarantine"             # rejected events
DUCKDB_PATH = DATA_DIR / "pitboss.duckdb"            # analytics warehouse

# Neo4j connection is read from env so the graph stage can be skipped cleanly
# when no database is running (e.g. CI, or the lightweight local path).
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "pitboss123")

EVENT_TYPES = (
    "session_start",
    "session_end",
    "wager",
    "win",
    "deposit",
    "withdrawal",
    "bonus_claim",
    "self_exclusion",
)

# Failure modes the generator can inject on demand for the "bad data day".
INJECTABLE_FAILURES = ("duplicates", "schema-drift", "late-batch")


def ensure_dirs() -> None:
    for d in (DATA_DIR, LANDING_DIR, QUARANTINE_DIR):
        d.mkdir(parents=True, exist_ok=True)