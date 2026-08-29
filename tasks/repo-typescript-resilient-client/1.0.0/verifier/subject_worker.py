from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import subject_probe

PROTOCOL = "harnesslab-tier-b-subject-v1"


def failure(error: BaseException) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "passed": False,
        "score": 0.0,
        "checks": [
            {
                "name": "subject-execution",
                "passed": False,
                "score": 0.0,
                "detail": f"SUBJECT_EXECUTION_FAILURE:{type(error).__name__}",
            }
        ],
        "summary": "subject repository could not satisfy the hidden contract",
    }


def main(mode: str, workspace: Path) -> int:
    try:
        report = subject_probe.run(workspace)
    except BaseException as error:
        if mode == "health":
            raise
        report = failure(error)
    print(json.dumps({"protocol": PROTOCOL, "report": report}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], Path(sys.argv[2]).resolve()))
