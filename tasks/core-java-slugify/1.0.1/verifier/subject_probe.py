from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = """
public final class HiddenVerifier {
    public static void main(String[] args) {
        var input = new java.util.ArrayList<>(java.util.List.of(1, 2, 3, 4, 5));
        var result = Slug.partition(input, 2);
        boolean shape = result.equals(java.util.List.of(java.util.List.of(1, 2), java.util.List.of(3, 4), java.util.List.of(5)));
        input.set(0, 9); boolean detached = result.get(0).get(0) == 1;
        boolean mutable = isMutable(result);
        boolean empty = Slug.partition(java.util.List.of(), 3).isEmpty();
        boolean invalid = rejects(0) && rejects(-1);
        System.out.println(shape + "," + detached + "," + mutable + "," + empty + "," + invalid);
    }
    private static boolean rejects(int size) {
        try { Slug.partition(java.util.List.of(1), size); return false; }
        catch (IllegalArgumentException expected) { return true; }
    }
    private static boolean isMutable(java.util.List<java.util.List<Integer>> result) {
        try { result.get(0).add(7); result.add(new java.util.ArrayList<>()); return result.size() == 4; }
        catch (UnsupportedOperationException error) { return false; }
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
            ["javac", "-d", str(build), str(workspace / "Slug.java"), str(harness)],
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
    names = ("shape", "detached", "mutable", "empty", "invalid-size")
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
                "summary": "Java batch partitioning cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
