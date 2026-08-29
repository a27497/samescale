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

    def rejected(item: object) -> bool:
        return item == {"value": None, "error": "ValueError"}

    cases = (
        ("basic", value["basic"] == {"value": [2, 7], "error": None}),
        ("whitespace", value["whitespace"] == {"value": [0, 10], "error": None}),
        ("reverse", rejected(value["reverse"])),
        ("limit", rejected(value["limit"])),
        ("syntax", all(rejected(item) for item in value["syntax"])),
        ("negative-limit", rejected(value["negative_limit"])),
    )
    emit_cases(cases, "bounded window parser cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
