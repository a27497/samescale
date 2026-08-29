from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

HARNESS = r"""
package bench;

public final class HiddenVerifier {
    private static WidgetRepository repository() {
        WidgetRepository repository = new WidgetRepository();
        repository.insert(new Widget("w1", "Before", 1));
        repository.insert(new Widget("other", "Other", 7));
        return repository;
    }
    private static WidgetApi api(WidgetRepository repository) {
        return new WidgetApi(new WidgetService(repository));
    }
    public static void main(String[] args) {
        WidgetRepository successRepo = repository();
        UpdateResponse success = api(successRepo).update(new UpdateRequest("w1", "  After  ", 1));
        boolean updated = success.status() == 200 && success.widget().version() == 2 && success.widget().name().equals("After") && successRepo.find("w1").orElseThrow().version() == 2;

        WidgetRepository staleRepo = repository();
        UpdateResponse stale = api(staleRepo).update(new UpdateRequest("w1", "Wrong", 0));
        boolean conflict = stale.status() == 409 && staleRepo.find("w1").orElseThrow().name().equals("Before") && staleRepo.find("w1").orElseThrow().version() == 1;

        WidgetRepository invalidRepo = repository();
        UpdateResponse invalid = api(invalidRepo).update(new UpdateRequest("w1", "   ", 1));
        boolean validation = invalid.status() == 400 && invalidRepo.find("w1").orElseThrow().version() == 1;

        WidgetRepository missingRepo = repository();
        boolean missing = api(missingRepo).update(new UpdateRequest("missing", "Name", 1)).status() == 404;

        WidgetRepository preserveRepo = repository();
        api(preserveRepo).update(new UpdateRequest("w1", "After", 1));
        boolean preserves = preserveRepo.find("other").orElseThrow().equals(new Widget("other", "Other", 7));

        WidgetRepository sequenceRepo = repository();
        WidgetApi sequenceApi = api(sequenceRepo);
        sequenceApi.update(new UpdateRequest("w1", "Second", 1));
        UpdateResponse third = sequenceApi.update(new UpdateRequest("w1", "Third", 2));
        UpdateResponse old = sequenceApi.update(new UpdateRequest("w1", "Old", 1));
        boolean sequence = third.status() == 200 && third.widget().version() == 3 && old.status() == 409 && sequenceRepo.find("w1").orElseThrow().version() == 3;
        System.out.println(updated + "," + conflict + "," + validation + "," + missing + "," + preserves + "," + sequence);
    }
}
"""


def report_failure(reason: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "passed": False,
        "score": 0.0,
        "checks": [
            {"name": "subject-build-or-run", "passed": False, "score": 0.0, "detail": reason}
        ],
        "summary": "Java repository contract could not execute",
    }


def run(workspace: Path) -> dict[str, object]:
    sources = sorted(workspace.rglob("*.java"))
    if not sources:
        return report_failure("SUBJECT_SOURCE_MISSING")
    with tempfile.TemporaryDirectory(prefix="widget-contract-") as temporary:
        build = Path(temporary)
        harness = build / "bench" / "HiddenVerifier.java"
        harness.parent.mkdir(parents=True)
        harness.write_text(HARNESS, encoding="utf-8")
        compiled = subprocess.run(
            ["javac", "-d", str(build), *(str(path) for path in sources), str(harness)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if compiled.returncode != 0:
            return report_failure("SUBJECT_COMPILE_FAILURE")
        executed = subprocess.run(
            ["java", "-cp", str(build), "bench.HiddenVerifier"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if executed.returncode != 0:
            return report_failure("SUBJECT_RUNTIME_FAILURE")
    values = executed.stdout.strip().split(",")
    names = (
        "update-persists-version",
        "stale-conflict-no-mutation",
        "validation-no-mutation",
        "missing-not-found",
        "preserve-unrelated",
        "version-sequence",
    )
    if len(values) != len(names):
        return report_failure("SUBJECT_OUTPUT_FAILURE")
    checks = [
        {"name": name, "passed": value == "true", "score": 1.0 if value == "true" else 0.0}
        for name, value in zip(names, values, strict=True)
    ]
    return {
        "schema_version": 1,
        "passed": all(item["passed"] for item in checks),
        "score": sum(item["score"] for item in checks) / len(checks),
        "checks": checks,
        "summary": "Java API/service/repository optimistic-update contract",
    }
