from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = """
public final class HiddenVerifier {
    public static void main(String[] args) {
        Quota quota = new Quota(5);
        boolean success = quota.consume(2) && quota.remaining() == 3;
        boolean boundary = quota.consume(3) && quota.remaining() == 0;
        boolean rejected = !quota.consume(1) && quota.remaining() == 0;
        boolean zero = false; boolean negative = false;
        try { new Quota(3).consume(0); } catch (IllegalArgumentException expected) { zero = true; }
        try { new Quota(3).consume(-1); } catch (IllegalArgumentException expected) { negative = true; }
        System.out.println(success + "," + boundary + "," + rejected + "," + zero + "," + negative);
    }
}
"""


def main() -> int:
    workspace = Path(sys.argv[1])
    with tempfile.TemporaryDirectory(prefix="harnesslab-java-") as temporary:
        build = Path(temporary)
        harness = build / "HiddenVerifier.java"
        harness.write_text(HARNESS, encoding="utf-8")
        compiled = subprocess.run(
            ["javac", "-d", str(build), str(workspace / "Quota.java"), str(harness)],
            capture_output=True,
            text=True,
            check=False,
        )
        if compiled.returncode:
            sys.stderr.write(compiled.stderr)
            return compiled.returncode
        run = subprocess.run(
            ["java", "-cp", str(build), "HiddenVerifier"],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode:
            sys.stderr.write(run.stderr)
            return run.returncode
    values = run.stdout.strip().split(",")
    names = (
        "success-mutates",
        "exact-boundary",
        "failure-no-mutation",
        "zero-invalid",
        "negative-invalid",
    )
    checks = [
        {"name": name, "passed": value == "true", "score": 1.0 if value == "true" else 0.0}
        for name, value in zip(names, values, strict=True)
    ]
    print(
        json.dumps(
            {
                "schema_version": 1,
                "passed": all(item["passed"] for item in checks),
                "score": sum(item["score"] for item in checks) / len(checks),
                "checks": checks,
                "summary": "Java quota lifecycle cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
