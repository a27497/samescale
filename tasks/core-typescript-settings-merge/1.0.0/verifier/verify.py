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
import {{ redact }} from {json.dumps(uri)};
const input = {{
  user: {{ Password: "secret", name: "Ada" }},
  items: [{{ token: "t", n: 1 }}],
  ok: true
}};
const before = JSON.stringify(input);
const result = redact(input);
const sparse = new Array(3); sparse[1] = {{ Authorization: "bearer" }};
const sparseResult = redact(sparse);
const cycle = {{}}; cycle.self = cycle; let circular = false;
try {{ redact(cycle); }} catch (error) {{ circular = error instanceof TypeError; }}
console.log(JSON.stringify([
  result.user.Password === "[REDACTED]" && result.items[0].token === "[REDACTED]",
  result.user.name === "Ada" && result.ok === true,
  JSON.stringify(input) === before && result !== input && result.user !== input.user,
  !(0 in sparseResult) && 1 in sparseResult && sparseResult[1].Authorization === "[REDACTED]",
  circular
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
        "nested-case-insensitive",
        "primitives-preserved",
        "deep-copy",
        "sparse-array",
        "cycle-rejected",
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
                "summary": "TypeScript recursive redaction cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
