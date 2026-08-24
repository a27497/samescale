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
import {{ validateRequest }} from {json.dumps(uri)};
const rejects = value => {{
  try {{ validateRequest(value); return false; }}
  catch (error) {{ return error instanceof TypeError; }}
}};
const read = {{ kind: "read", key: "a" }};
const readResult = validateRequest(read);
const write = validateRequest({{ kind: "write", key: "b", value: null }});
const inherited = Object.create({{ kind: "read" }}); inherited.key = "x";
console.log(JSON.stringify([
  readResult.kind === "read" && readResult.key === "a" && readResult !== read,
  write.kind === "write" && write.value === null,
  [
    null, [], {{kind:"read",key:" "}}, {{kind:"read",key:"x",extra:true}},
    {{kind:"write",key:"x"}}, inherited
  ].every(rejects),
  rejects({{kind:"other",key:"x"}})
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
    names = ("read-fresh", "write-null-value", "invalid-shapes", "unknown-kind")
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
                "summary": "TypeScript discriminated request cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
