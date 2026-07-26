"""PitBoss pipeline orchestrator.

Runs the full DAG in dependency order:

    generate -> ingest(Node) -> load_raw -> build_star -> quality_gate -> graph

This is a dependency-free runner suitable for local runs and CI. In production
each stage maps to an Airflow/Dagster op with the same ordering and the quality
gate as a blocking task (see docs/decisions.md). If the gate fails, the graph
load is skipped — bad data never reaches the served graph.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import (  # noqa: E402
    INJECTABLE_FAILURES,
    RAW_FIREHOSE,
    LANDING_DIR,
    QUARANTINE_DIR,
)
from generator import emit  # noqa: E402
from transform import load_raw, build_star  # noqa: E402
from quality import contracts  # noqa: E402
from graph import load_graph  # noqa: E402


def _step(title: str) -> None:
    print(f"\n{'=' * 70}\n▶ {title}\n{'=' * 70}")


def _clear_zones() -> None:
    """Each pipeline invocation is a fresh batch: clear prior landing/quarantine
    so re-runs don't accumulate (and inflate the dedup gate). Production would
    process incrementally; this is deliberate batch-demo semantics."""
    for d in (LANDING_DIR, QUARANTINE_DIR):
        for f in d.glob("*.jsonl"):
            f.unlink()


def run(players: int, inject: str, require_graph: bool) -> int:
    _step("1/6  Generate synthetic events")
    _clear_zones()
    events, world = emit.generate_with_world(players)
    emit.write_referrals(world, RAW_FIREHOSE.parent / "referrals.csv")
    if inject:
        modes = [m.strip() for m in inject.split(",") if m.strip()]
        bad_modes = sorted(set(modes) - set(INJECTABLE_FAILURES))
        if bad_modes:
            print(f"unknown failure mode(s): {', '.join(bad_modes)}", file=sys.stderr)
            print(f"valid modes: {', '.join(INJECTABLE_FAILURES)}", file=sys.stderr)
            return 2
        events = emit.inject_failures(events, modes)
        print(f"injected failures: {', '.join(modes)}")
    emit.write_file(events)
    print(f"wrote {len(events)} events")

    _step("2/6  Ingest via Node.js edge (schema validation)")
    node = subprocess.run(
        ["node", str(ROOT / "ingest" / "server.js"), "--batch", str(RAW_FIREHOSE)],
        capture_output=True, text=True,
    )
    print(node.stdout.strip() or node.stderr.strip())
    if node.returncode != 0:
        print("ingestion failed; stopping before warehouse load", file=sys.stderr)
        if node.stderr.strip():
            print(node.stderr.strip(), file=sys.stderr)
        return node.returncode

    _step("3/6  Load landing zone -> DuckDB raw_events")
    print(f"loaded {load_raw.load()} events")

    _step("4/6  Build dimensional model")
    for name, n in build_star.build().items():
        print(f"  {name:20} {n:>7} rows")

    _step("5/6  Quality gate")
    gate_passed = contracts.run()

    _step("6/6  Graph load (Neo4j)")
    if not gate_passed:
        print("gate failed — skipping graph load (bad data is not published)")
        return 1
    load_graph.load(require=require_graph)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run the PitBoss pipeline")
    ap.add_argument("--players", type=int, default=200)
    ap.add_argument("--inject", default="", help="comma list of failure modes")
    ap.add_argument("--require-graph", action="store_true")
    args = ap.parse_args()
    sys.exit(run(args.players, args.inject, args.require_graph))
