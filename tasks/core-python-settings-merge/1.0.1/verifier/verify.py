from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROTOCOL = "harnesslab-subject-worker-v1"


def _subject_failure(reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "passed": False,
        "score": 0.0,
        "checks": [
            {
                "name": "subject-execution",
                "passed": False,
                "score": 0.0,
                "detail": reason,
            }
        ],
        "summary": "subject execution did not satisfy the declared task contract",
    }


def _worker_timeout(workspace: Path) -> int:
    if any(workspace.glob("*.java")):
        return 25
    if any(workspace.glob("*.ts")):
        return 17
    return 12


def _validated_report(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version",
        "passed",
        "score",
        "checks",
        "summary",
    }:
        raise RuntimeError("subject worker returned an invalid report shape")
    if raw["schema_version"] != 1 or not isinstance(raw["passed"], bool):
        raise RuntimeError("subject worker returned an invalid report header")
    score = raw["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
        raise RuntimeError("subject worker returned an invalid score")
    checks = raw["checks"]
    if not isinstance(checks, list) or not checks:
        raise RuntimeError("subject worker returned invalid checks")
    for check in checks:
        if not isinstance(check, dict) or not {"name", "passed", "score"} <= set(check):
            raise RuntimeError("subject worker returned an invalid check")
        if set(check) - {"name", "passed", "score", "detail"}:
            raise RuntimeError("subject worker returned an invalid check field")
        if not isinstance(check["name"], str) or not check["name"]:
            raise RuntimeError("subject worker returned an invalid check name")
        if not isinstance(check["passed"], bool):
            raise RuntimeError("subject worker returned an invalid check result")
        check_score = check["score"]
        if (
            isinstance(check_score, bool)
            or not isinstance(check_score, (int, float))
            or not 0 <= check_score <= 1
        ):
            raise RuntimeError("subject worker returned an invalid check score")
        if (
            "detail" in check
            and check["detail"] is not None
            and not isinstance(check["detail"], str)
        ):
            raise RuntimeError("subject worker returned an invalid check detail")
    if not isinstance(raw["summary"], str) or not raw["summary"]:
        raise RuntimeError("subject worker returned an invalid summary")
    return raw


def main() -> int:
    workspace = Path(sys.argv[1])
    worker = Path(__file__).with_name("subject_worker.py")
    try:
        completed = subprocess.run(
            [sys.executable, str(worker), str(workspace)],
            capture_output=True,
            text=True,
            timeout=_worker_timeout(workspace),
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(json.dumps(_subject_failure("SUBJECT_WORKER_TIMEOUT"), separators=(",", ":")))
        return 0
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        raise RuntimeError("subject worker failed outside its declared failure boundary")
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("subject worker returned malformed protocol output") from exc
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"protocol", "report"}
        or envelope.get("protocol") != PROTOCOL
    ):
        raise RuntimeError("subject worker protocol mismatch")
    report = _validated_report(envelope["report"])
    print(json.dumps(report, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
