from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROTOCOL = "harnesslab-python-subject-execution-v2"
SUBJECT_TIMEOUT_SECONDS = 3


@dataclass(frozen=True)
class SubjectExecution:
    observations: dict[str, Any] | None
    failure_reason: str | None


def run_subject_execution(workspace: Path) -> SubjectExecution:
    child = Path(__file__).with_name("subject_execution.py")
    try:
        completed = subprocess.run(
            [sys.executable, str(child), str(workspace)],
            capture_output=True,
            text=True,
            timeout=SUBJECT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return SubjectExecution(None, "SUBJECT_EXECUTION_TIMEOUT")
    if completed.returncode != 0:
        return SubjectExecution(None, "SUBJECT_EXECUTION_FAILURE:PROCESS_NONZERO")
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("VERIFIER_PROTOCOL_FAILURE:subject-child-json") from exc
    if not isinstance(envelope, dict) or envelope.get("protocol") != PROTOCOL:
        raise RuntimeError("VERIFIER_PROTOCOL_FAILURE:subject-child-envelope")
    kind = envelope.get("kind")
    if kind == "SUBJECT_RESULT" and set(envelope) == {"protocol", "kind", "observations"}:
        observations = envelope["observations"]
        if not isinstance(observations, dict):
            raise RuntimeError("VERIFIER_PROTOCOL_FAILURE:subject-observations")
        return SubjectExecution(observations, None)
    if kind == "SUBJECT_EXECUTION_FAILURE" and set(envelope) == {
        "protocol",
        "kind",
        "reason",
    }:
        reason = envelope["reason"]
        if not isinstance(reason, str) or not reason:
            raise RuntimeError("VERIFIER_PROTOCOL_FAILURE:subject-failure")
        return SubjectExecution(None, reason)
    raise RuntimeError("VERIFIER_PROTOCOL_FAILURE:subject-child-kind")


def subject_failure_report(reason: str) -> dict[str, Any]:
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


def emit_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, separators=(",", ":")))


def emit_cases(cases: tuple[tuple[str, bool], ...], summary: str) -> None:
    checks = [
        {"name": name, "passed": passed, "score": 1.0 if passed else 0.0} for name, passed in cases
    ]
    emit_report(
        {
            "schema_version": 1,
            "passed": all(value for _, value in cases),
            "score": sum(item["score"] for item in checks) / len(checks),
            "checks": checks,
            "summary": summary,
        }
    )
