"""Native command-hook entry: consumes stdin, persists only redacted metadata."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harnesslab.episodes.hooks import MAX_INPUT, receive_hook


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("codex", "claude"), required=True)
    parser.add_argument("--spool", type=Path, required=True)
    args = parser.parse_args()
    try:
        receive_hook(sys.stdin.buffer.read(MAX_INPUT + 1), args.source, args.spool)
    except (ValueError, OSError, TypeError):
        # No raw exceptions/payloads, no permission/continuation feedback to the agent.
        print("Hook capture failed closed", file=sys.stderr)
        return 1
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
