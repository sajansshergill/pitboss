"""Quality-gate tests: clean data passes, dirty data is caught."""
from __future__ import annotations

import duckdb

from quality import contracts
from quality.suites import CHECKS, ERROR


def _violations(db):
    con = duckdb.connect(str(db), read_only=True)
    out = {c.name: (con.execute(c.sql).fetchone()[0] or 0) for c in CHECKS}
    con.close()
    return out


def test_clean_data_passes_all_error_checks(warehouse):
    v = _violations(warehouse)
    for chk in CHECKS:
        if chk.severity == ERROR:
            assert v[chk.name] == 0, f"{chk.name} should have no violations on clean data"


def test_gate_passes_on_clean_data(warehouse):
    assert contracts.run(db_path=warehouse) is True


def test_duplicates_fail_dedup_gate(dirty_warehouse):
    v = _violations(dirty_warehouse)
    assert v["dedup_event_id"] > 0


def test_late_batch_fails_freshness_gate(dirty_warehouse):
    v = _violations(dirty_warehouse)
    assert v["freshness"] > 0


def test_responsible_gaming_warning_has_demo_signal(warehouse):
    v = _violations(warehouse)
    assert v["rg_wager_after_exclusion"] > 0


def test_gate_blocks_on_dirty_data(dirty_warehouse):
    assert contracts.run(db_path=dirty_warehouse) is False


def test_results_table_written(warehouse):
    contracts.run(db_path=warehouse)
    con = duckdb.connect(str(warehouse), read_only=True)
    n = con.execute("SELECT count(*) FROM quality_results").fetchone()[0]
    con.close()
    assert n == len(CHECKS)