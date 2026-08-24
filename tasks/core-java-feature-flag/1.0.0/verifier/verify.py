from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = """
public final class HiddenVerifier {
    public static void main(String[] args) {
        boolean truthy = FeatureFlag.parse(" YES ", false) && FeatureFlag.parse("1", false) && FeatureFlag.parse("on", false);
        boolean falsy = !FeatureFlag.parse(" NO ", true) && !FeatureFlag.parse("0", true) && !FeatureFlag.parse("off", true);
        boolean defaults = FeatureFlag.parse(null, true) && !FeatureFlag.parse(null, false);
        boolean invalid = false;
        try { FeatureFlag.parse("enabled", false); } catch (IllegalArgumentException expected) { invalid = true; }
        System.out.println(truthy + "," + falsy + "," + defaults + "," + invalid);
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
            ["javac", "-d", str(build), str(workspace / "FeatureFlag.java"), str(harness)],
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
    names = ("truthy", "falsy", "defaults", "invalid")
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
                "summary": "Java feature flag contract cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
