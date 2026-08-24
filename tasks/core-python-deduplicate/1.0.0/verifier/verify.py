from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    spec = importlib.util.spec_from_file_location("subject_events", workspace / "events.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load events.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = (
        ("preserves-order", module.deduplicate(["z", "a", "z", "b"]) == ["z", "a", "b"]),
        ("adjacent", module.deduplicate(["a", "a", "b"]) == ["a", "b"]),
        ("empty", module.deduplicate([]) == []),
        ("already-unique", module.deduplicate(["b", "a"]) == ["b", "a"]),
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
                "summary": "ordered deduplication edge cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
