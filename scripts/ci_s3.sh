#!/usr/bin/env bash
# Linux prerequisite: locked .venv, sudo, unshare and setpriv. No online fallback.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $# != 1 ]]; then
  echo 'usage: bash scripts/ci_s3.sh NEW_OUTPUT_DIRECTORY' >&2
  exit 2
fi
output="$(realpath -m -- "$1")"
mkdir -- "$output"
mkdir -- "$output/home"
cd -- "$root"
# Privilege is used only to create the namespace; Python runs as the calling user.
exec sudo -n unshare --net -- setpriv \
  --reuid="$(id -u)" --regid="$(id -g)" --clear-groups --no-new-privs \
  env -i HOME="$output/home" PATH="$root/.venv/bin:/usr/bin:/bin" \
  LANG=C.UTF-8 PYTHONPATH="$root/src:$root" PYTHONDONTWRITEBYTECODE=1 \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 UV_OFFLINE=1 \
  "$root/.venv/bin/python" scripts/verify_s3_regression.py --output "$output"
