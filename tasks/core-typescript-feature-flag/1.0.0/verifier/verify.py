from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    uri = (workspace / "flags.ts").resolve().as_uri()
    source = f"""
import {{ parseFeatureFlag }} from {json.dumps(uri)};
let invalid = false;
try {{ parseFeatureFlag("enabled"); }} catch (error) {{ invalid = error instanceof TypeError; }}
console.log(JSON.stringify([
  ["true", "1", "YES", " on "].every(value => parseFeatureFlag(value)),
  ["false", "0", "NO", " off "].every(value => !parseFeatureFlag(value, true)),
  parseFeatureFlag(undefined, true) && !parseFeatureFlag(undefined, false),
  invalid
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
    names = ("truthy", "falsy", "defaults", "invalid")
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
                "summary": "TypeScript feature flag contract cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
