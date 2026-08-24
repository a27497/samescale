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
    cache = module.LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    hit = cache.get("a") == 1 and cache.keys() == ["b", "a"]
    cache.put("c", 3)
    eviction = cache.get("b") is None and cache.keys() == ["a", "c"]
    cache.put("a", 4)
    update = cache.get("a") == 4 and cache.keys() == ["c", "a"]
    before = cache.keys()
    miss = cache.get("missing") is None and cache.keys() == before
    invalid = False
    try:
        module.LRUCache(0)
    except ValueError:
        invalid = True
    cases = (
        ("hit-refreshes", hit),
        ("evicts-lru", eviction),
        ("update-refreshes", update),
        ("miss-stable", miss),
        ("capacity-validation", invalid),
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
                "summary": "LRU cache recency cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
