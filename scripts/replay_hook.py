"""Replay a pinned CUSTOM native-hook regression case without execution."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from harnesslab.analyst.offline_replay import ReplayError
from harnesslab.episodes.hooks import encode, replay_hook_case


def offline_guard(event: str, args: tuple[Any, ...]) -> None:
    """Forbid network and process execution while reading a pinned Hook case."""
    if event.startswith(
        ("socket.", "subprocess.", "os.exec", "os.spawn", "os.posix_spawn")
    ) or event in {"os.system", "pty.spawn"}:
        raise ReplayError("offline boundary: network/process operation rejected")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.addaudithook(offline_guard)
    try:
        result = replay_hook_case(args.case, args.sha256)
        with args.output.open("xb") as stream:
            stream.write(encode(result))
    except (ValueError, OSError, TypeError, KeyError):
        print('{"status":"FAIL_CLOSED"}', file=sys.stderr)
        return 2
    print('{"status":"PASS","external_calls":0,"subject_executed":false}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
