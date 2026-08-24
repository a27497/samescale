from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    spec = importlib.util.spec_from_file_location("subject_quota", workspace / "quota.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load quota.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    quota = module.Quota(5)
    first = quota.consume(2) is True and quota.remaining == 3
    boundary = quota.consume(3) is True and quota.remaining == 0
    rejected = quota.consume(1) is False and quota.remaining == 0
    invalid = []
    for units in (0, -1):
        try:
            module.Quota(3).consume(units)
        except ValueError:
            invalid.append(True)
    cases = (
        ("success-mutates", first),
        ("exact-boundary", boundary),
        ("failure-no-mutation", rejected),
        ("invalid-units", len(invalid) == 2),
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
                "summary": "quota lifecycle cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
