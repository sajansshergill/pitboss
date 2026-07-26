#!/usr/bin/env bash
# Run the full PitBoss pipeline end to end.
#
#   ./run_pipeline.sh              # clean run
#   ./run_pipeline.sh --bad-day    # inject duplicates + schema-drift + late-batch
#
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON:-python}"
INJECT=""
if [[ "${1:-}" == "--bad-day" ]]; then
  INJECT="--inject duplicates,schema-drift,late-batch"
fi

"$PYTHON_BIN" orchestration/pipeline.py --players "${PLAYERS:-200}" $INJECT

echo
echo "Pipeline complete. Launch the dashboard with:"
echo "  streamlit run app/dashboard.py"
