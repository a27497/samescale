from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    sys.path.insert(0, str(workspace))
    spec = importlib.util.spec_from_file_location("subject_settings", workspace / "settings.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load settings.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    overrides = {"timeout": 5, "feature": True}
    before = dict(overrides)
    result = module.build_settings(overrides)
    cases = (
        ("override-wins", result["timeout"] == 5),
        ("default-retained", result["retries"] == 2 and result["region"] == "local"),
        ("unknown-retained", result["feature"] is True),
        ("input-not-mutated", overrides == before),
        ("fresh-result", module.build_settings({}) is not result),
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
                "summary": "layered settings cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
