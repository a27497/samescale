from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = """
public final class HiddenVerifier {
    public static void main(String[] args) {
        boolean roundTrip = decodes(Events.encode("alpha"), "alpha");
        boolean empty = Events.encode("").equals("0#") && decodes("0#", "");
        boolean delimiter = decodes("3#a#b", "a#b");
        boolean syntax = rejects("abc") && rejects("+1#a") && rejects("x#a");
        boolean mismatch = rejects("2#a") && rejects("1#ab");
        System.out.println(roundTrip + "," + empty + "," + delimiter + "," + syntax + "," + mismatch);
    }
    private static boolean rejects(String value) {
        try { Events.decode(value); return false; }
        catch (RuntimeException expected) { return true; }
    }
    private static boolean decodes(String value, String expected) {
        try { return Events.decode(value).equals(expected); }
        catch (RuntimeException error) { return false; }
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
            ["javac", "-d", str(build), str(workspace / "Events.java"), str(harness)],
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
    names = ("round-trip", "empty", "embedded-delimiter", "syntax", "length-mismatch")
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
                "summary": "Java length-prefixed codec cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
