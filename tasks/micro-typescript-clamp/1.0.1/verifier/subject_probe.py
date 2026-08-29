from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    module_uri = (workspace / "range.ts").resolve().as_uri()
    harness_source = f"""
import {{ clamp }} from {json.dumps(module_uri)};
console.log(JSON.stringify([
  clamp(-3, 0, 10) === 0,
  clamp(13, 0, 10) === 10,
  clamp(5, 0, 10) === 5
]));
"""
    with tempfile.TemporaryDirectory(prefix="harnesslab-typescript-") as temporary:
        harness = Path(temporary) / "hidden-verifier.mjs"
        harness.write_text(harness_source, encoding="utf-8")
        completed = subprocess.run(
            ["node", str(harness)], capture_output=True, text=True, check=False
        )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        return completed.returncode
    values = json.loads(completed.stdout)
    names = ("lower-bound", "upper-bound", "in-range")
    checks = [
        {"name": name, "passed": bool(value), "score": 1.0 if value else 0.0}
        for name, value in zip(names, values, strict=True)
    ]
    score = sum(check["score"] for check in checks) / len(checks)
    print(
        json.dumps(
            {
                "schema_version": 1,
                "passed": all(check["passed"] for check in checks),
                "score": score,
                "checks": checks,
                "summary": "deterministic TypeScript clamp cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
