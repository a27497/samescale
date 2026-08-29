from __future__ import annotations

import io
import json
import sys
import types
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

PROTOCOL = "harnesslab-python-subject-execution-v2"


def _load(workspace: Path) -> Any:
    source = workspace / "quota.py"
    module = types.ModuleType("subject_quota")
    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), module.__dict__)
    return module


def _execute(workspace: Path) -> dict[str, Any]:
    module = _load(workspace)
    cache = module.LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    hit_value = cache.get("a")
    hit_keys = cache.keys()
    cache.put("c", 3)
    evicted_value = cache.get("b")
    eviction_keys = cache.keys()
    cache.put("a", 4)
    update_value = cache.get("a")
    update_keys = cache.keys()
    before_miss = cache.keys()
    miss_value = cache.get("missing")
    after_miss = cache.keys()
    invalid_error = None
    try:
        module.LRUCache(0)
    except BaseException as error:
        invalid_error = type(error).__name__
    return {
        "hit_value": hit_value,
        "hit_keys": hit_keys,
        "evicted_value": evicted_value,
        "eviction_keys": eviction_keys,
        "update_value": update_value,
        "update_keys": update_keys,
        "before_miss": before_miss,
        "miss_value": miss_value,
        "after_miss": after_miss,
        "invalid_error": invalid_error,
    }


def main() -> int:
    workspace = Path(sys.argv[1]).resolve()
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    try:
        with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
            observations = _execute(workspace)
        envelope = {"protocol": PROTOCOL, "kind": "SUBJECT_RESULT", "observations": observations}
    except BaseException as error:
        envelope = {
            "protocol": PROTOCOL,
            "kind": "SUBJECT_EXECUTION_FAILURE",
            "reason": f"SUBJECT_EXECUTION_FAILURE:{type(error).__name__}",
        }
    print(json.dumps(envelope, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        raise SystemExit("usage: subject_execution.py WORKSPACE")
    raise SystemExit(main())
