from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = """
import java.util.List;
public final class HiddenVerifier {
    public static void main(String[] args) {
        var ordered = Events.deduplicate(List.of("z", "a", "z", "b"));
        boolean order = ordered.equals(List.of("z", "a", "b"));
        boolean adjacent = Events.deduplicate(List.of("a", "a", "b")).equals(List.of("a", "b"));
        boolean empty = Events.deduplicate(List.of()).isEmpty();
        ordered.add("new");
        boolean mutable = ordered.equals(List.of("z", "a", "b", "new"));
        System.out.println(order + "," + adjacent + "," + empty + "," + mutable);
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
    names = ("preserves-order", "adjacent", "empty", "mutable-result")
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
                "summary": "Java ordered deduplication cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
