"""Read-only evidence consistency checks; never execute the saved workspace."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assertions(name, total, passed):
    data = read(name)
    rows = [a for suite in data["testResults"] for a in suite["assertionResults"]]
    assert len(rows) == data["numTotalTests"] == total
    assert sum(a["status"] == "passed" for a in rows) == data["numPassedTests"] == passed
    assert all(a["status"] in ("passed", "failed") for a in rows)
    assert data.get("numPendingTests", 0) == data.get("numTodoTests", 0) == 0
    assert data.get("numRuntimeErrorTestSuites", 0) == 0
    return rows


def main():
    index = read("sha256.json")
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()}
    assert actual == set(index) | {"sha256.json"}
    for name, expected in index.items():
        path = ROOT / name
        assert not path.is_symlink() and path.is_file() and digest(path) == expected
    source_index = read("source-audit-sha256.json")
    provenance = read("provenance.json")
    assert digest(ROOT / "source-audit-sha256.json") == provenance["source_audit_manifest_sha256"]
    for name, source in provenance["copied_files"].items():
        assert digest(ROOT / name) == source["sha256"]
        if source["source_relative_path"] != "sha256.json":
            assert source_index[source["source_relative_path"]] == source["sha256"]
    for kind in ("episode", "request"):
        path = ROOT / provenance[f"original_{kind}_reference"]
        assert digest(path) == provenance[f"original_{kind}_sha256"]
    episode = read("../l1-a-candidate-real-20260921/episode.json")
    request = read("../l1-a-candidate-closeout-20260921/execution-request.json")
    result = read("result.json")
    assert episode["acceptance"] == result["original_attempt_status"] == "NOT_VERIFIED"
    assert episode["verifier_check_count"] == 0 and episode["verifier_manifest_digest"] is None
    assert episode["run_id"] == request["execution_id"]
    assert result["request_identity"] == request["request_identity"]
    assert result["workspace_output_digest"] == episode["workspace_output_digest"]
    assert result["task_identity"] == request["task_identity"]
    assert result["candidate_code_modified"] is result["episode_updated"] is False
    assert result["provider_calls"] == result["model_calls"] == result["judge_calls"] == 0
    references = read("../l1-a-candidate-real-20260921/references.json")
    original_workspace = {
        p.split("/workspace/", 1)[1]: h.removeprefix("sha256:")
        for p, h in references.items()
        if "/workspace/" in p
    }
    reconstructed = {
        p.removeprefix("workspace/"): h
        for p, h in source_index.items()
        if p.startswith("workspace/")
    }
    assert original_workspace == reconstructed and len(reconstructed) == 99
    saved = read("../l1-a-candidate-closeout-20260921/sha256.json")
    for name, expected in saved.items():
        if name.startswith("saved-files/"):
            assert reconstructed[name.removeprefix("saved-files/")] == expected
            assert digest(ROOT.parent / "l1-a-candidate-closeout-20260921" / name) == expected
    report = read("verifier-evidence/report.json")
    assert report["passed"] is False and len(report["checks"]) == 75
    assert sum(c["passed"] for c in report["checks"]) == 71
    business = assertions("verifier-evidence/business-vitest.json", 72, 68)
    failed = [a["fullName"] for a in business if a["status"] == "failed"]
    assert len(failed) == 4 and all(
        "duplicate variant" in n or "duplicate extension" in n for n in failed
    )
    assertions("verifier-evidence/public-vitest.json", 25, 25)
    assert [(s["stage"], s["exit_code"]) for s in read("verifier-evidence/stages.json")] == [
        ("business", 1),
        ("public-unit", 0),
        ("type-check", 0),
        ("build", 0),
    ]
    supplemental = assertions("supplemental-evidence/supplemental-vitest.json", 22, 12)
    for surface in ("detail", "upload"):
        row = next(
            a
            for a in supplemental
            if a["fullName"] == f"supplemental {surface} A4/A7 guaranteed valid BCP47 en-x-demo"
        )
        assert row["status"] == "failed"
        assert "expected 'und' to be 'en-x-demo'" in "\n".join(row["failureMessages"])
    diagnosis = read("diagnosis.json")
    assert diagnosis["comparison_decision"] == "INCONCLUSIVE"
    assert diagnosis["requirements"]["A7"].startswith("FAIL_OVERALL")
    assert "PermissionError" in (ROOT / "verifier-infrastructure-first.stderr").read_text()
    print(
        json.dumps(
            {
                "status": "PASS",
                "snapshot_files": len(index),
                "original_episode": "NOT_VERIFIED",
                "public": "25/25",
                "frozen_verifier": "71/75",
                "business": "68/72",
                "supplemental": "12/22",
                "reconstructed_files": 99,
                "external_artifact_reads": 0,
                "provider_model_judge_calls": 0,
                "acceptance_reruns": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
