from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    spec = importlib.util.spec_from_file_location("subject_calculator", workspace / "calculator.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load calculator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = (
        ("lower-bound", module.clamp(-3, 0, 10) == 0),
        ("upper-bound", module.clamp(13, 0, 10) == 10),
        ("in-range", module.clamp(5, 0, 10) == 5),
    )
    checks = [
        {"name": name, "passed": passed, "score": 1.0 if passed else 0.0} for name, passed in cases
    ]
    score = sum(check["score"] for check in checks) / len(checks)
    print(
        json.dumps(
            {
                "schema_version": 1,
                "passed": all(passed for _, passed in cases),
                "score": score,
                "checks": checks,
                "summary": "deterministic clamp cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
