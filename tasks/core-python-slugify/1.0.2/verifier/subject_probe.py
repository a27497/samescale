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
        ("descending", value["ids"] == ["b", "a", "c", "d"]),
        ("stable-ties", value["stable_ties"] is True),
        ("input-list-unchanged", value["input_unchanged"] is True),
        ("fresh-list", value["fresh_list"] is True),
        ("invalid-priority", value["invalid_errors"] == ["ValueError"] * 3),
    )
    emit_cases(cases, "stable priority scheduling cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
