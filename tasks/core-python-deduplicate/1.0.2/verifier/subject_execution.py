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
    source = workspace / "events.py"
    module = types.ModuleType("subject_events")
    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), module.__dict__)
    ledger = module.RetryLedger()
    first = ledger.record_success("op-1", "created")
    duplicate = ledger.record_success("op-1", "created")
    conflict_error = None
    try:
        ledger.record_success("op-1", "different")
    except BaseException as error:
        conflict_error = type(error).__name__
    preserved = ledger.lookup("op-1")
    empty_error = None
    try:
        ledger.record_success("", "x")
    except BaseException as error:
        empty_error = type(error).__name__
    return {
        "first": first,
        "duplicate": duplicate,
        "conflict_error": conflict_error,
        "preserved": preserved,
        "empty_error": empty_error,
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
