from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = """
public final class HiddenVerifier {
    public static void main(String[] args) {
        boolean basic = Slug.slugify("Hello World").equals("hello-world");
        boolean collapse = Slug.slugify("  API---Contract  ").equals("api-contract");
        boolean punctuation = Slug.slugify("one_two.three").equals("one-two-three");
        boolean digits = Slug.slugify("Release 2.0").equals("release-2-0");
        boolean empty = Slug.slugify("***").equals("");
        System.out.println(basic + "," + collapse + "," + punctuation + "," + digits + "," + empty);
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
    names = ("basic", "collapse", "punctuation", "digits", "empty")
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
                "summary": "Java ASCII slug edge cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
