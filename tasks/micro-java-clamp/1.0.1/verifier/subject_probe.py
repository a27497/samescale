from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = """
public final class HiddenVerifier {
    public static void main(String[] args) {
        boolean low = Range.clamp(-3, 0, 10) == 0;
        boolean high = Range.clamp(13, 0, 10) == 10;
        boolean middle = Range.clamp(5, 0, 10) == 5;
        System.out.println(low + "," + high + "," + middle);
    }
}
"""


def main() -> int:
    workspace = Path(sys.argv[1])
    with tempfile.TemporaryDirectory(prefix="harnesslab-java-") as temporary:
        build = Path(temporary)
        harness = build / "HiddenVerifier.java"
        harness.write_text(HARNESS, encoding="utf-8")
        compile_result = subprocess.run(
            ["javac", "-d", str(build), str(workspace / "Range.java"), str(harness)],
            capture_output=True,
            text=True,
            check=False,
        )
        if compile_result.returncode != 0:
            sys.stderr.write(compile_result.stderr)
            return compile_result.returncode
        run_result = subprocess.run(
            ["java", "-cp", str(build), "HiddenVerifier"],
            capture_output=True,
            text=True,
            check=False,
        )
        if run_result.returncode != 0:
            sys.stderr.write(run_result.stderr)
            return run_result.returncode
        values = run_result.stdout.strip().split(",")
    names = ("lower-bound", "upper-bound", "in-range")
    checks = [
        {"name": name, "passed": value == "true", "score": 1.0 if value == "true" else 0.0}
        for name, value in zip(names, values, strict=True)
    ]
    score = sum(check["score"] for check in checks) / len(checks)
    print(
        json.dumps(
            {
                "schema_version": 1,
                "passed": all(check["passed"] for check in checks),
                "score": score,
                "checks": checks,
                "summary": "deterministic Java clamp cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
