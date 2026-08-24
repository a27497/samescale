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
import {{ deduplicate }} from {json.dumps(uri)};
const input = ["z", "a", "z", "b"];
const output = deduplicate(input);
console.log(JSON.stringify([
  JSON.stringify(output) === JSON.stringify(["z", "a", "b"]),
  JSON.stringify(deduplicate(["a", "a", "b"])) === JSON.stringify(["a", "b"]),
  deduplicate([]).length === 0,
  output !== input && JSON.stringify(input) === JSON.stringify(["z", "a", "z", "b"])
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
    names = ("preserves-order", "adjacent", "empty", "fresh-no-mutation")
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
                "summary": "TypeScript ordered deduplication cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
