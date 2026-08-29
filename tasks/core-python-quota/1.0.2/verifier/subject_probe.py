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
        ("hit-refreshes", value["hit_value"] == 1 and value["hit_keys"] == ["b", "a"]),
        (
            "evicts-lru",
            value["evicted_value"] is None and value["eviction_keys"] == ["a", "c"],
        ),
        ("update-refreshes", value["update_value"] == 4 and value["update_keys"] == ["c", "a"]),
        (
            "miss-stable",
            value["miss_value"] is None and value["after_miss"] == value["before_miss"],
        ),
        ("capacity-validation", value["invalid_error"] == "ValueError"),
    )
    emit_cases(cases, "LRU cache recency cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
