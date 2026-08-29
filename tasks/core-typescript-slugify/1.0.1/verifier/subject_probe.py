from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    uri = (workspace / "slug.ts").resolve().as_uri()
    source = f"""
import {{ Subscription }} from {json.dumps(uri)};
let listener; let subscribeCalls = 0; let unsubscribeCalls = 0; const values = [];
const subscription = new Subscription(callback => {{
  subscribeCalls += 1;
  listener = callback;
  return () => {{ unsubscribeCalls += 1; }};
}}, value => values.push(value));
listener("a"); subscription.dispose(); subscription.dispose(); listener("b");
const marker = new Error("subscribe failed"); let propagated = false; let handled = false;
try {{
  new Subscription(() => {{ throw marker; }}, () => {{ handled = true; }});
}} catch (error) {{ propagated = error === marker; }}
console.log(JSON.stringify([
  subscribeCalls === 1,
  JSON.stringify(values) === JSON.stringify(["a"]),
  unsubscribeCalls === 1,
  propagated,
  !handled
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
        "subscribe-once",
        "active-only",
        "dispose-idempotent",
        "subscribe-error",
        "no-handler-on-error",
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
                "summary": "TypeScript subscription disposal cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
