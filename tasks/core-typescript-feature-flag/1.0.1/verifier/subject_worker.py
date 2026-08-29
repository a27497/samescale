from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import subject_probe

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


def _exception_reason(error: BaseException) -> str:
    name = type(error).__name__
    safe_name = "".join(character for character in name if character.isalnum() or character == "_")
    return f"SUBJECT_EXCEPTION_{safe_name[:80] or 'UNKNOWN'}"


def _path_is_in_workspace(filename: object, workspace: Path) -> bool:
    if not isinstance(filename, str) or not filename:
        return False
    candidate = Path(filename).resolve(strict=False)
    return candidate == workspace or workspace in candidate.parents


def _declared_subject_failure(error: BaseException, workspace: Path) -> bool:
    if _path_is_in_workspace(getattr(error, "filename", None), workspace):
        return True
    traceback = error.__traceback__
    while traceback is not None:
        if _path_is_in_workspace(traceback.tb_frame.f_code.co_filename, workspace):
            return True
        traceback = traceback.tb_next
    if isinstance(
        error, (SyntaxError, ImportError, AttributeError, KeyError, IndexError, TypeError)
    ):
        return True
    if isinstance(error, json.JSONDecodeError):
        return True
    if isinstance(error, ValueError) and str(error).startswith("zip() argument"):
        return True
    return isinstance(error, RuntimeError) and str(error).startswith("unable to load ")


def main() -> int:
    workspace = Path(sys.argv[1]).resolve()
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    try:
        with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
            exit_code = subject_probe.main()
    except (Exception, SystemExit) as error:
        if not _declared_subject_failure(error, workspace):
            raise
        report = _subject_failure(_exception_reason(error))
    else:
        if exit_code != 0:
            report = _subject_failure("SUBJECT_TOOL_PROCESS_NONZERO")
        else:
            lines = [line for line in captured_stdout.getvalue().splitlines() if line.strip()]
            if not lines:
                raise RuntimeError("subject probe produced no report")
            try:
                parsed = json.loads(lines[-1])
            except json.JSONDecodeError as exc:
                raise RuntimeError("subject probe produced malformed report output") from exc
            if not isinstance(parsed, dict):
                raise RuntimeError("subject probe report is not an object")
            report = parsed
    print(json.dumps({"protocol": PROTOCOL, "report": report}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        raise SystemExit("usage: subject_worker.py WORKSPACE")
    raise SystemExit(main())
