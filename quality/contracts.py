"""Run the data-quality contracts and gate the pipeline.

Executes every check in the suite, writes results to a quality_results table
(so the dashboard and history can read them), prints a report, and returns a
non-zero exit code if any ERROR-severity check fails — the gate.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DUCKDB_PATH  # noqa: E402
from quality.suites import CHECKS, ERROR  # noqa: E402


def run(db_path: Path = DUCKDB_PATH) -> bool:
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS quality_results (
            run_ts     TIMESTAMP,
            check_name VARCHAR,
            severity   VARCHAR,
            violations BIGINT,
            passed     BOOLEAN
        )
        """
    )

    run_ts = datetime.now(timezone.utc)
    gate_passed = True
    rows = []

    print(f"\nPitBoss quality gate  @ {run_ts.isoformat(timespec='seconds')}")
    print("-" * 68)
    for chk in CHECKS:
        violations = con.execute(chk.sql).fetchone()[0] or 0
        passed = violations == 0
        if chk.severity == ERROR and not passed:
            gate_passed = False
        rows.append((run_ts, chk.name, chk.severity, violations, passed))

        icon = "PASS" if passed else ("FAIL" if chk.severity == ERROR else "WARN")
        print(f"  [{icon}] {chk.name:26} {chk.severity:5} "
              f"violations={violations:<6} {chk.description}")

    con.executemany(
        "INSERT INTO quality_results VALUES (?, ?, ?, ?, ?)", rows
    )
    con.close()

    print("-" * 68)
    print(f"GATE: {'PASSED — batch may publish' if gate_passed else 'FAILED — batch quarantined'}\n")
    return gate_passed


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)