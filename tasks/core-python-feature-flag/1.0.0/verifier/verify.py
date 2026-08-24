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
    invalid = False
    try:
        module.parse_feature_flag("enabled")
    except ValueError:
        invalid = True
    cases = (
        ("truthy", all(module.parse_feature_flag(value) for value in ("true", "1", "YES", " on "))),
        (
            "falsy",
            not any(
                module.parse_feature_flag(value, True) for value in ("false", "0", "NO", " off ")
            ),
        ),
        ("none-default-true", module.parse_feature_flag(None, True) is True),
        ("none-default-false", module.parse_feature_flag(None, False) is False),
        ("invalid", invalid),
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
                "summary": "feature flag contract cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
