"""PitBoss dashboard — pipeline health + responsible-gaming signals.

Reads the DuckDB warehouse the pipeline produces. Run after a pipeline pass:

    streamlit run app/dashboard.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DUCKDB_PATH  # noqa: E402

st.set_page_config(page_title="PitBoss", layout="wide")
st.title("PitBoss — Casino Pipeline Health & Responsible-Gaming Signals")

if not DUCKDB_PATH.exists():
    st.warning("No warehouse found. Run the pipeline first: "
               "`python orchestration/pipeline.py`")
    st.stop()

con = duckdb.connect(str(DUCKDB_PATH), read_only=True)


def q(sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


# ---- Top-line volumes ----------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Players", int(q("SELECT count(*) n FROM dim_player").n[0]))
c2.metric("Wagers", int(q("SELECT count(*) n FROM fact_wager").n[0]))
c3.metric("Bonus claims", int(q("SELECT count(*) n FROM fact_bonus_claim").n[0]))
c4.metric("Sessions", int(q("SELECT count(*) n FROM fact_session").n[0]))

# ---- Quality gate history ------------------------------------------------
st.subheader("Data-quality gate")
try:
    results = q(
        """
        SELECT check_name, severity, violations, passed
        FROM quality_results
        WHERE run_ts = (SELECT max(run_ts) FROM quality_results)
        ORDER BY severity, check_name
        """
    )
    failed = results[(results.severity == "ERROR") & (~results.passed)]
    if failed.empty:
        st.success("All ERROR-severity gates passed — batch published.")
    else:
        st.error(f"{len(failed)} gate(s) failed — batch would be quarantined.")
    st.dataframe(results, use_container_width=True, hide_index=True)
except duckdb.CatalogException:
    st.info("No quality results yet — run the quality stage.")

# ---- Responsible-gaming signals -----------------------------------------
st.subheader("Responsible-gaming signals")
rg = q(
    """
    SELECT w.player_id,
           count(*)         AS post_exclusion_wagers,
           sum(w.stake_amount) AS staked_after_exclusion
    FROM fact_wager w
    JOIN dim_player p ON p.player_id = w.player_id
    WHERE p.is_self_excluded AND w.event_ts > p.self_excluded_ts
    GROUP BY w.player_id
    ORDER BY post_exclusion_wagers DESC
    """
)
if rg.empty:
    st.write("No post-self-exclusion wagering detected.")
else:
    st.dataframe(rg, use_container_width=True, hide_index=True)

# ---- Shared-payment fan-out (graph preview in SQL) ----------------------
st.subheader("Shared-payment fan-out (bonus-abuse candidates)")
st.caption("Payment instruments used by 3+ 'distinct' players — the SQL shadow "
           "of the Neo4j bonus-abuse-ring query.")
rings = q(
    """
    SELECT primary_card AS shared_card, count(*) AS accounts,
           list(player_id) AS players
    FROM dim_player
    WHERE primary_card IS NOT NULL
    GROUP BY primary_card
    HAVING count(*) >= 3
    ORDER BY accounts DESC
    """
)
st.dataframe(rings, use_container_width=True, hide_index=True)

con.close()