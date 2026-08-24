from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    uri = (workspace / "settings.ts").resolve().as_uri()
    source = f"""
import {{ buildSettings }} from {json.dumps(uri)};
const overrides = {{ timeout: 5, feature: true }};
const before = JSON.stringify(overrides);
const result = buildSettings(overrides);
console.log(JSON.stringify([
  result.timeout === 5,
  result.retries === 2 && result.region === "local",
  result.feature === true,
  JSON.stringify(overrides) === before,
  buildSettings({{}}) !== result
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
        "override-wins",
        "defaults-retained",
        "unknown-retained",
        "input-unchanged",
        "fresh-result",
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
                "summary": "TypeScript layered settings cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
