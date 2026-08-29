from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = """
import java.util.LinkedHashMap;
import java.util.Map;
public final class HiddenVerifier {
    public static void main(String[] args) {
        Map<String, String> input = new LinkedHashMap<>();
        input.put(" Content-Type ", "  text/plain\t; charset=utf-8 "); input.put("X-ID", " 42 ");
        Map<String, String> before = new LinkedHashMap<>(input);
        Map<String, String> result = Settings.normalize(input);
        boolean normalized = result.equals(Map.of("content-type", "text/plain ; charset=utf-8", "x-id", "42"));
        boolean order = result.keySet().stream().toList().equals(java.util.List.of("content-type", "x-id"));
        boolean unchanged = input.equals(before) && result != input;
        boolean duplicate = rejects(map("X-ID", "1", " x-id ", "2"));
        boolean invalid = rejects(map(" ", "x")) && rejects(map("x", "a\\nb")) && rejects(map("x\\r", "a"));
        System.out.println(normalized + "," + order + "," + unchanged + "," + duplicate + "," + invalid);
    }
    private static Map<String, String> map(String... values) {
        Map<String, String> result = new LinkedHashMap<>();
        for (int index = 0; index < values.length; index += 2) result.put(values[index], values[index + 1]);
        return result;
    }
    private static boolean rejects(Map<String, String> value) {
        try { Settings.normalize(value); return false; }
        catch (IllegalArgumentException expected) { return true; }
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
        "normalizes",
        "preserves-order",
        "input-unchanged",
        "duplicate-rejected",
        "invalid-rejected",
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
                "summary": "Java HTTP header normalization cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
