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
    cases = (
        ("basic", module.slugify("Hello World") == "hello-world"),
        ("collapse", module.slugify("  API---Contract  ") == "api-contract"),
        ("punctuation", module.slugify("one_two.three") == "one-two-three"),
        ("digits", module.slugify("Release 2.0") == "release-2-0"),
        ("empty", module.slugify("***") == ""),
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
                "summary": "ASCII slug edge cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
