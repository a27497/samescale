from __future__ import annotations

import io
import json
import sys
import types
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

PROTOCOL = "harnesslab-python-subject-execution-v2"


def _execute(workspace: Path) -> dict[str, Any]:
    source = workspace / "slug.py"
    module = types.ModuleType("subject_slug")
    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), module.__dict__)
    jobs = [
        {"id": "a", "priority": 2},
        {"id": "b", "priority": 5},
        {"id": "c", "priority": 2},
        {"id": "d", "priority": 1},
    ]
    before = [dict(job) for job in jobs]
    result = module.schedule(jobs)
    invalid_errors = []
    for bad in ({"id": "x"}, {"id": "x", "priority": "high"}, {"id": "x", "priority": True}):
        try:
            module.schedule([bad])
        except BaseException as error:
            invalid_errors.append(type(error).__name__)
        else:
            invalid_errors.append(None)
    return {
        "ids": [job["id"] for job in result],
        "stable_ties": result[1] is jobs[0] and result[2] is jobs[2],
        "input_unchanged": jobs == before,
        "fresh_list": result is not jobs,
        "invalid_errors": invalid_errors,
    }


def main() -> int:
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            observations = _execute(Path(sys.argv[1]).resolve())
        envelope = {"protocol": PROTOCOL, "kind": "SUBJECT_RESULT", "observations": observations}
    except BaseException as error:
        envelope = {
            "protocol": PROTOCOL,
            "kind": "SUBJECT_EXECUTION_FAILURE",
            "reason": f"SUBJECT_EXECUTION_FAILURE:{type(error).__name__}",
        }
    print(json.dumps(envelope, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
