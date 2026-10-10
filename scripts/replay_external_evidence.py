"""Offline external record replay, with an audit boundary forbidding network/process calls."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harnesslab.episodes.hooks import encode
from harnesslab.external_evidence.service import MAX_EXPORT, replay_export, safe_root
from scripts.replay_hook import offline_guard


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.addaudithook(offline_guard)
    try:
        safe_root(args.evidence)
        if args.evidence.stat().st_size > MAX_EXPORT:
            raise ValueError("oversized export")
        result = replay_export(args.evidence.read_bytes(), args.sha256)
        with args.output.open("xb") as stream:
            stream.write(encode(result))
    except (OSError, ValueError):
        print("Offline evidence verification rejected", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
