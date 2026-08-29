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
        ("lower-bound", value["lower"] == 0),
        ("upper-bound", value["upper"] == 10),
        ("in-range", value["middle"] == 5),
    )
    emit_cases(cases, "deterministic clamp cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
