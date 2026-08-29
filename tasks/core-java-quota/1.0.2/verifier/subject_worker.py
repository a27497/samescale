from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Literal

import subject_probe

PROTOCOL = "harnesslab-subject-worker-v2"
WorkerMode = Literal["health", "candidate"]


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


def _is_external_toolchain_task(workspace: Path) -> bool:
    return any(workspace.glob("*.java")) or any(workspace.glob("*.ts"))


def main(mode: WorkerMode, workspace: Path) -> int:
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    original_argv = sys.argv
    sys.argv = [str(Path(subject_probe.__file__)), str(workspace)]
    try:
        with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
            exit_code = subject_probe.main()
    finally:
        sys.argv = original_argv
    if exit_code != 0:
        if mode == "candidate" and _is_external_toolchain_task(workspace):
            report = _subject_failure("SUBJECT_TOOL_PROCESS_NONZERO")
        else:
            sys.stderr.write(captured_stderr.getvalue())
            raise RuntimeError("verifier probe failed during self-health")
    else:
        lines = [line for line in captured_stdout.getvalue().splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("verifier probe produced no report")
        try:
            parsed = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise RuntimeError("verifier probe produced malformed report output") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("verifier probe report is not an object")
        report = parsed
    print(
        json.dumps(
            {"protocol": PROTOCOL, "kind": "SUBJECT_RESULT", "report": report},
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    if (
        len(sys.argv) != 3
        or sys.argv[1] not in {"health", "candidate"}
        or not Path(sys.argv[2]).is_dir()
    ):
        raise SystemExit("usage: subject_worker.py {health|candidate} WORKSPACE")
    raise SystemExit(main(sys.argv[1], Path(sys.argv[2]).resolve()))
