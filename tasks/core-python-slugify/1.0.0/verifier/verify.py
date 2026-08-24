from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    spec = importlib.util.spec_from_file_location("subject_slug", workspace / "slug.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load slug.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    jobs = [
        {"id": "a", "priority": 2},
        {"id": "b", "priority": 5},
        {"id": "c", "priority": 2},
        {"id": "d", "priority": 1},
    ]
    before = [dict(job) for job in jobs]
    result = module.schedule(jobs)
    invalid = []
    for bad in ({"id": "x"}, {"id": "x", "priority": "high"}, {"id": "x", "priority": True}):
        try:
            module.schedule([bad])
        except Exception as error:
            invalid.append(isinstance(error, ValueError))
    cases = (
        ("descending", [job["id"] for job in result] == ["b", "a", "c", "d"]),
        ("stable-ties", result[1] is jobs[0] and result[2] is jobs[2]),
        ("input-list-unchanged", jobs == before),
        ("fresh-list", result is not jobs),
        ("invalid-priority", len(invalid) == 3),
    )
    checks = [
        {"name": name, "passed": passed, "score": 1.0 if passed else 0.0} for name, passed in cases
    ]
    print(
        json.dumps(
            {
                "schema_version": 1,
                "passed": all(value for _, value in cases),
                "score": sum(item["score"] for item in checks) / len(checks),
                "checks": checks,
                "summary": "stable priority scheduling cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
