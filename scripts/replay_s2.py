"""Offline-only S2 reader: pinned inputs, no subprocesses, no socket operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from harnesslab.analyst.offline_replay import (
    ReplayError,
    compare_replays,
    decode,
    read_pinned,
    render_diagnosis,
    replay_bundle,
    require,
    safe_path,
)


def offline_guard(event: str, args: tuple[Any, ...]) -> None:
    if event.startswith(
        ("socket.", "subprocess.", "os.exec", "os.spawn", "os.posix_spawn")
    ) or event in {
        "os.system",
        "pty.spawn",
    }:
        raise ReplayError("offline boundary: network/process operation rejected")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument(
        "--sha256", required=True, help="Trusted inputs.json digest, retained separately"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="New output directory; never overwrites"
    )
    args = parser.parse_args()
    sys.addaudithook(offline_guard)
    try:
        inputs = decode(read_pinned(args.inputs, args.sha256))
        require(inputs["schema_version"] == 1, "unsupported input version")
        require(set(inputs["bundles"]) == {"codex", "claude"}, "expected two S1 bundles")
        roots = {
            name: safe_path(args.inputs.parent, b["path"]) for name, b in inputs["bundles"].items()
        }
        require(
            not any(
                args.output.resolve().is_relative_to(root.resolve()) for root in roots.values()
            ),
            "output must not modify an input bundle",
        )
        replays = {
            name: replay_bundle(roots[name], b["sha256"]) for name, b in inputs["bundles"].items()
        }
        diff = compare_replays(replays["codex"], replays["claude"])
        # Output is created only after BOTH bundles and their comparison passed all checks.
        args.output.mkdir(parents=True, exist_ok=False)
        for name, value in {**replays, "trace-diff": diff}.items():
            (args.output / f"{name}.json").write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n"
            )
        (args.output / "diagnosis.md").write_text(render_diagnosis(diff))
        (args.output / "offline-boundary.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "external_calls": 0,
                    "provider_calls": 0,
                    "model_calls": 0,
                    "claude_calls": 0,
                    "judge_calls": 0,
                    "guard": "CPython audit hook denies socket and process operations",
                    "subject_executed": False,
                    "verifier_executed": False,
                },
                indent=2,
            )
            + "\n"
        )
    except (ReplayError, OSError, ValueError, KeyError, TypeError) as exc:
        print(
            json.dumps({"status": "FAIL_CLOSED", "category": type(exc).__name__}), file=sys.stderr
        )
        return 2
    print(json.dumps({"status": "PASS", "replayed_runs": 2, "external_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
