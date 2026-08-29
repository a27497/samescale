from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    uri = (workspace / "quota.ts").resolve().as_uri()
    source = f"""
import {{ retryDelays }} from {json.dumps(uri)};
const rejects = args => {{
  try {{ retryDelays(...args); return false; }}
  catch (error) {{ return error instanceof RangeError; }}
}};
console.log(JSON.stringify([
  JSON.stringify(retryDelays(1, 100, 1000)) === "[]",
  JSON.stringify(retryDelays(5, 100, 1000)) === JSON.stringify([100, 200, 400, 800]),
  JSON.stringify(retryDelays(7, 300, 1000)) === JSON.stringify([300, 600, 1000, 1000, 1000, 1000]),
  JSON.stringify(retryDelays(
    4, Number.MAX_SAFE_INTEGER - 1, Number.MAX_SAFE_INTEGER
  )) === JSON.stringify([
    Number.MAX_SAFE_INTEGER - 1, Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER
  ]),
  [[0,1,2], [2,0,2], [2,3,2], [2,1.5,3], [2,1,Infinity]].every(rejects)
]));
"""
    with tempfile.TemporaryDirectory(prefix="harnesslab-typescript-") as temporary:
        harness = Path(temporary) / "hidden-verifier.mjs"
        harness.write_text(source, encoding="utf-8")
        run = subprocess.run(["node", str(harness)], capture_output=True, text=True, check=False)
    if run.returncode:
        sys.stderr.write(run.stderr)
        return run.returncode
    values = json.loads(run.stdout)
    names = (
        "one-attempt",
        "doubling",
        "capping",
        "overflow-safe",
        "validation",
    )
    checks = [
        {"name": name, "passed": bool(value), "score": 1.0 if value else 0.0}
        for name, value in zip(names, values, strict=True)
    ]
    print(
        json.dumps(
            {
                "schema_version": 1,
                "passed": all(values),
                "score": sum(item["score"] for item in checks) / len(checks),
                "checks": checks,
                "summary": "TypeScript retry schedule cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
