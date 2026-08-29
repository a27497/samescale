from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = """
public final class HiddenVerifier {
    public static void main(String[] args) {
        boolean value = FeatureFlag.fetch(key -> "value:" + key, "x").equals("value:x");
        boolean blank = rejectsBlank(null) && rejectsBlank("  ");
        var cause = new FeatureFlag.RepositoryException("offline");
        boolean wrapped = false;
        try { FeatureFlag.fetch(key -> { throw cause; }, "x"); }
        catch (FeatureFlag.ServiceException error) { wrapped = error.getCause() == cause; }
        var unrelated = new IllegalStateException("bug");
        boolean propagated = propagates(unrelated);
        System.out.println(value + "," + blank + "," + wrapped + "," + propagated);
    }
    private static boolean rejectsBlank(String key) {
        try { FeatureFlag.fetch(value -> "called", key); return false; }
        catch (IllegalArgumentException expected) { return true; }
        catch (RuntimeException error) { return false; }
    }
    private static boolean propagates(IllegalStateException expected) {
        try { FeatureFlag.fetch(key -> { throw expected; }, "x"); return false; }
        catch (RuntimeException error) { return error == expected; }
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
    names = ("returns-value", "blank-before-call", "preserves-cause", "unrelated-propagates")
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
                "summary": "Java exception propagation cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
