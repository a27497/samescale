from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    spec = importlib.util.spec_from_file_location("subject_flags", workspace / "flags.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load flags.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def rejects(value: str, limit: int = 10) -> bool:
        try:
            module.parse_window(value, limit)
        except ValueError:
            return True
        return False

    cases = (
        ("basic", module.parse_window("2:7", 10) == (2, 7)),
        ("whitespace", module.parse_window(" 0 : 10 ", 10) == (0, 10)),
        ("reverse", rejects("8:3")),
        ("limit", rejects("2:11")),
        ("syntax", all(rejects(value) for value in ("2", "+2:3", "2:3:4", "a:3"))),
        ("negative-limit", rejects("0:0", -1)),
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
                "summary": "bounded window parser cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
