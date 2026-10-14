#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 3 ]; then
  echo "Usage: bash run-swe-preflight.sh /new/external/campaign /locked/upstream/python /retained/pilot-summary.json" >&2
  exit 2
fi
eval_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$eval_repo_root"
uv run --locked python -m scripts.swe_mixed_eval prepare --root "$1" --upstream-python "$2" --retained-humaneval-summary "$3"
uv run --locked python -m scripts.swe_mixed_eval preflight --root "$1" --upstream-python "$2"
echo "STOP: REAL_CODEX remains closed; no Agent trial or full campaign was dispatched."
