from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = """
import java.util.HashMap;
import java.util.Map;
public final class HiddenVerifier {
    public static void main(String[] args) {
        Map<String, Object> overrides = new HashMap<>();
        overrides.put("timeout", 5); overrides.put("feature", true);
        Map<String, Object> before = new HashMap<>(overrides);
        Map<String, Object> result = Settings.merge(overrides);
        boolean override = result.get("timeout").equals(5);
        boolean defaults = result.get("retries").equals(2) && result.get("region").equals("local");
        boolean unknown = result.get("feature").equals(true);
        boolean unchanged = overrides.equals(before);
        boolean fresh = Settings.merge(Map.of()) != result;
        System.out.println(override + "," + defaults + "," + unknown + "," + unchanged + "," + fresh);
    }
}
"""


def main() -> int:
    workspace = Path(sys.argv[1])
    with tempfile.TemporaryDirectory(prefix="harnesslab-java-") as temporary:
        build = Path(temporary)
        harness = build / "HiddenVerifier.java"
        harness.write_text(HARNESS, encoding="utf-8")
        sources = [str(path) for path in sorted(workspace.glob("*.java"))]
        compiled = subprocess.run(
            ["javac", "-d", str(build), *sources, str(harness)],
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
        "override-wins",
        "defaults-retained",
        "unknown-retained",
        "input-unchanged",
        "fresh-result",
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
                "summary": "Java layered settings cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
