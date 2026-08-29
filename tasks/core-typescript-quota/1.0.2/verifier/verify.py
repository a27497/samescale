from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

PROTOCOL = "harnesslab-subject-worker-v2"
WorkerMode = Literal["health", "candidate"]


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


def _run_worker(mode: WorkerMode, workspace: Path) -> dict[str, Any]:
    worker = Path(__file__).with_name("subject_worker.py")
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, str(worker), mode, str(workspace)],
            capture_output=True,
            text=True,
            env=environment,
            timeout=_worker_timeout(workspace),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"VERIFIER_TIMEOUT:{mode}") from exc
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        raise RuntimeError(f"VERIFIER_FAILURE:{mode}")
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("VERIFIER_PROTOCOL_FAILURE:malformed-json") from exc
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"protocol", "kind", "report"}
        or envelope.get("protocol") != PROTOCOL
        or envelope.get("kind") != "SUBJECT_RESULT"
    ):
        raise RuntimeError("VERIFIER_PROTOCOL_FAILURE:envelope")
    return _validated_report(envelope["report"])


@contextmanager
def _oracle_workspace() -> Iterator[Path]:
    verifier = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="harnesslab-verifier-health-") as temporary:
        workspace = Path(temporary) / "workspace"
        shutil.copytree(
            verifier / "health_workspace",
            workspace,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        yield workspace


def main() -> int:
    workspace = Path(sys.argv[1]).resolve()
    with _oracle_workspace() as oracle:
        health = _run_worker("health", oracle)
        if not health["passed"]:
            raise RuntimeError("VERIFIER_SELF_HEALTH_FAILED")
    report = _run_worker("candidate", workspace)
    print(json.dumps(report, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        raise SystemExit("usage: verify.py WORKSPACE")
    raise SystemExit(main())
