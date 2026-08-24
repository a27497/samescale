from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    uri = (workspace / "events.ts").resolve().as_uri()
    source = f"""
import {{ parseCursor }} from {json.dumps(uri)};
const rejects = value => {{
  try {{ parseCursor(value); return false; }}
  catch (error) {{ return error instanceof TypeError; }}
}};
console.log(JSON.stringify([
  JSON.stringify(parseCursor("0@abc_DEF-9")) ===
    JSON.stringify({{ offset: 0, anchor: "abc_DEF-9" }}),
  parseCursor("42@x").offset === 42,
  ["01@x", "+1@x", "-1@x", "1@", "1@a=b", "1@x@y"].every(rejects),
  rejects("9007199254740992@x")
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
    names = ("zero-and-anchor", "positive-offset", "syntax", "safe-integer")
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
                "summary": "TypeScript pagination cursor cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
