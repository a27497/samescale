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
        ("first-records", value["first"] is True),
        ("identical-retry-idempotent", value["duplicate"] is False),
        ("conflict-rejected", value["conflict_error"] == "ValueError"),
        ("conflict-preserves-original", value["preserved"] == "created"),
        ("empty-key-rejected", value["empty_error"] == "ValueError"),
    )
    emit_cases(cases, "idempotent retry-ledger cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
