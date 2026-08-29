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
    sys.path.insert(0, str(workspace))
    source = workspace / "settings.py"
    module = types.ModuleType("subject_settings")
    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), module.__dict__)
    from defaults import CloseTracker

    tracker = CloseTracker()
    session = module.ManagedSession(tracker)
    send_value = session.send("alpha")
    sent = tracker.sent
    session.close()
    session.close()
    close_calls = tracker.close_calls
    rejected_error = None
    try:
        session.send("late")
    except BaseException as error:
        rejected_error = type(error).__name__
    context_tracker = CloseTracker()
    context_session = module.ManagedSession(context_tracker)
    entered_is_self = False
    exit_error = None
    try:
        with context_session as entered:
            entered_is_self = entered is context_session
            raise LookupError("exercise exceptional exit")
    except BaseException as error:
        exit_error = type(error).__name__
    return {
        "send_value": send_value,
        "sent": sent,
        "close_calls": close_calls,
        "rejected_error": rejected_error,
        "entered_is_self": entered_is_self,
        "exit_error": exit_error,
        "context_close_calls": context_tracker.close_calls,
        "context_closed": context_session.closed,
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
