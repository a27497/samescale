from __future__ import annotations

import sys
from pathlib import Path

from python_subject_boundary import (
    emit_cases,
    emit_report,
    run_subject_execution,
    subject_failure_report,
)


def main() -> int:
    result = run_subject_execution(Path(sys.argv[1]).resolve())
    if result.failure_reason is not None:
        emit_report(subject_failure_report(result.failure_reason))
        return 0
    if result.observations is None:
        raise RuntimeError("VERIFIER_PROTOCOL_FAILURE:missing-observations")
    value = result.observations
    cases = (
        ("send-delegates", value["send_value"] == "sent:alpha" and value["sent"] == ["alpha"]),
        ("close-idempotent", value["close_calls"] == 1),
        ("send-after-close", value["rejected_error"] == "RuntimeError"),
        ("context-returns-self", value["entered_is_self"] is True),
        (
            "exceptional-exit-closes",
            value["exit_error"] == "LookupError"
            and value["context_close_calls"] == 1
            and value["context_closed"] is True,
        ),
    )
    emit_cases(cases, "managed session lifecycle cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
