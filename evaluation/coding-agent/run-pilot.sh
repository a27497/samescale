#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: bash run-pilot.sh /new/external/campaign /codex/vendor /existing/auth.json" >&2
  exit 2
fi

eval_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$eval_repo_root"
uv run --locked python scripts/coding_agent_eval.py prepare --root "$1"
uv run --locked python scripts/coding_agent_eval.py calibrate --root "$1" --codex-vendor "$2"
uv run --locked python scripts/coding_agent_eval.py pilot --root "$1" --codex-vendor "$2" --auth-file "$3"
uv run --locked python scripts/coding_agent_eval.py replay --root "$1"
echo "STOP: review the pilot results, usage and cost estimate with the user before any full run."
