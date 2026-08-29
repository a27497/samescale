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
    source = workspace / "calculator.py"
    module = types.ModuleType("subject_calculator")
    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), module.__dict__)
    return {
        "lower": module.clamp(-3, 0, 10),
        "upper": module.clamp(13, 0, 10),
        "middle": module.clamp(5, 0, 10),
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
