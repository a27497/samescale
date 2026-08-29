from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = """
public final class HiddenVerifier {
    public static void main(String[] args) {
        Quota committed = new Quota();
        boolean initial = committed.state() == Quota.State.NEW;
        committed.reserve(); committed.commit();
        boolean commitPath = committed.state() == Quota.State.COMMITTED;
        Quota cancelled = new Quota(); cancelled.reserve(); cancelled.cancel();
        boolean cancelPath = cancelled.state() == Quota.State.CANCELLED;
        boolean terminal = rejects(() -> committed.cancel()) && committed.state() == Quota.State.COMMITTED;
        Quota fresh = new Quota();
        boolean ordering = rejects(() -> fresh.commit()) && rejects(() -> fresh.cancel()) && fresh.state() == Quota.State.NEW;
        Quota duplicate = new Quota(); duplicate.reserve();
        boolean reserveOnce = rejects(() -> duplicate.reserve()) && duplicate.state() == Quota.State.RESERVED;
        System.out.println(initial + "," + commitPath + "," + cancelPath + "," + terminal + "," + ordering + "," + reserveOnce);
    }
    private static boolean rejects(Runnable action) {
        try { action.run(); return false; }
        catch (IllegalStateException expected) { return true; }
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
        "initial",
        "commit-path",
        "cancel-path",
        "terminal",
        "ordering",
        "reserve-once",
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
                "summary": "Java reservation state machine cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
