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
    source = workspace / "flags.py"
    module = types.ModuleType("subject_flags")
    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), module.__dict__)

    def attempt(value: str, limit: int = 10) -> dict[str, Any]:
        try:
            return {"value": module.parse_window(value, limit), "error": None}
        except BaseException as error:
            return {"value": None, "error": type(error).__name__}

    return {
        "basic": attempt("2:7"),
        "whitespace": attempt(" 0 : 10 "),
        "reverse": attempt("8:3"),
        "limit": attempt("2:11"),
        "syntax": [attempt(value) for value in ("2", "+2:3", "2:3:4", "a:3")],
        "negative_limit": attempt("0:0", -1),
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
