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
import {{ Quota }} from {json.dumps(uri)};
const quota = new Quota(5);
const success = quota.consume(2) && quota.remaining === 3;
const boundary = quota.consume(3) && quota.remaining === 0;
const rejected = !quota.consume(1) && quota.remaining === 0;
let zero = false; let negative = false;
try {{ new Quota(3).consume(0); }} catch (error) {{ zero = error instanceof RangeError; }}
try {{ new Quota(3).consume(-1); }} catch (error) {{ negative = error instanceof RangeError; }}
console.log(JSON.stringify([success, boundary, rejected, zero, negative]));
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
        "success-mutates",
        "exact-boundary",
        "failure-no-mutation",
        "zero-invalid",
        "negative-invalid",
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
                "summary": "TypeScript quota lifecycle cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
