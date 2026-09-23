"""Read-only replay of the frozen natural-failure evidence; executes no subject or verifier."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from harnesslab.analyst.offline_replay import ReplayError, require
from harnesslab.evidence.offline_boundary import offline_guard

ROOT = Path(__file__).resolve().parents[1]
FREEZE_SHA256 = "a2a34894344177fb36407d5b5e93f5351089f67423779cfa485f7cf26bec9f0b"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> Any:
    return json.loads(path.read_text())


def _assertions(path: Path, total: int, passed: int) -> list[dict[str, Any]]:
    data = _read(path)
    rows = [assertion for suite in data["testResults"] for assertion in suite["assertionResults"]]
    require(len(rows) == data["numTotalTests"] == total, "D2 assertion count drift")
    require(
        sum(row["status"] == "passed" for row in rows) == data["numPassedTests"] == passed,
        "D2 assertion outcome drift",
    )
    require(all(row["status"] in ("passed", "failed") for row in rows), "D2 assertion status drift")
    require(data.get("numRuntimeErrorTestSuites", 0) == 0, "D2 assertion runtime error")
    return rows


def _check_snapshot(evidence: Path, audit: Path) -> None:
    """Rebuild source consistency with data reads only; never load evidence Python."""
    index = _read(audit / "sha256.json")
    observed = {p.relative_to(audit).as_posix() for p in audit.rglob("*") if p.is_file()}
    require(observed == set(index) | {"sha256.json"}, "D2 audit inventory drift")
    for relative, expected in index.items():
        path = audit / relative
        require(not path.is_symlink() and _sha256(path) == expected, "D2 audit digest drift")

    provenance = _read(audit / "provenance.json")
    source_index = _read(audit / "source-audit-sha256.json")
    require(
        _sha256(audit / "source-audit-sha256.json") == provenance["source_audit_manifest_sha256"],
        "D2 source audit drift",
    )
    for relative, source in provenance["copied_files"].items():
        require(_sha256(audit / relative) == source["sha256"], "D2 copied evidence drift")
        if source["source_relative_path"] != "sha256.json":
            require(
                source_index[source["source_relative_path"]] == source["sha256"],
                "D2 source inventory drift",
            )
    for kind in ("episode", "request"):
        require(
            _sha256(audit / provenance[f"original_{kind}_reference"])
            == provenance[f"original_{kind}_sha256"],
            "D2 original identity drift",
        )

    episode = _read(evidence / "l1-a-candidate-real-20260921/episode.json")
    request = _read(evidence / "l1-a-candidate-closeout-20260921/execution-request.json")
    audit_result = _read(audit / "result.json")
    require(
        episode["acceptance"] == audit_result["original_attempt_status"] == "NOT_VERIFIED",
        "D2 original grade drift",
    )
    require(
        episode["verifier_check_count"] == 0 and episode["verifier_manifest_digest"] is None,
        "D2 original verifier drift",
    )
    require(episode["run_id"] == request["execution_id"], "D2 execution identity drift")
    require(
        audit_result["request_identity"] == request["request_identity"], "D2 request identity drift"
    )
    require(
        audit_result["workspace_output_digest"] == episode["workspace_output_digest"],
        "D2 workspace identity drift",
    )
    require(audit_result["task_identity"] == request["task_identity"], "D2 task identity drift")
    require(
        not audit_result["candidate_code_modified"] and not audit_result["episode_updated"],
        "D2 historical evidence rewritten",
    )

    references = _read(evidence / "l1-a-candidate-real-20260921/references.json")
    original = {
        path.split("/workspace/", 1)[1]: digest.removeprefix("sha256:")
        for path, digest in references.items()
        if "/workspace/" in path
    }
    reconstructed = {
        path.removeprefix("workspace/"): digest
        for path, digest in source_index.items()
        if path.startswith("workspace/")
    }
    require(
        original == reconstructed and len(reconstructed) == 99, "D2 workspace reconstruction drift"
    )
    saved_root = evidence / "l1-a-candidate-closeout-20260921"
    saved = _read(saved_root / "sha256.json")
    saved_files = {
        path: digest for path, digest in saved.items() if path.startswith("saved-files/")
    }
    require(len(saved_files) == 5, "D2 saved-file inventory drift")
    for path, digest in saved_files.items():
        require(
            reconstructed[path.removeprefix("saved-files/")] == digest, "D2 saved workspace drift"
        )
        require(_sha256(saved_root / path) == digest, "D2 saved-file digest drift")

    report = _read(audit / "verifier-evidence/report.json")
    require(report["passed"] is False and len(report["checks"]) == 75, "D2 verifier report drift")
    require(sum(check["passed"] for check in report["checks"]) == 71, "D2 verifier outcome drift")
    business = _assertions(audit / "verifier-evidence/business-vitest.json", 72, 68)
    failed = [row["fullName"] for row in business if row["status"] == "failed"]
    require(
        len(failed) == 4
        and all("duplicate variant" in n or "duplicate extension" in n for n in failed),
        "D2 A3 diagnosis drift",
    )
    _assertions(audit / "verifier-evidence/public-vitest.json", 25, 25)
    supplemental = _assertions(audit / "supplemental-evidence/supplemental-vitest.json", 22, 12)
    for surface in ("detail", "upload"):
        name = f"supplemental {surface} A4/A7 guaranteed valid BCP47 en-x-demo"
        row = next((item for item in supplemental if item["fullName"] == name), None)
        if row is None:
            raise ReplayError("D2 A4 assertion missing")
        require(row["status"] == "failed", "D2 A4 diagnosis drift")
        require(
            "expected 'und' to be 'en-x-demo'" in "\n".join(row["failureMessages"]),
            "D2 A4 assertion drift",
        )


def replay(root: Path = ROOT) -> dict[str, Any]:
    evidence = root / "docs/evidence"
    freeze_path = evidence / "d2-natural-failure-20260923/freeze.json"
    require(
        _sha256(freeze_path) == FREEZE_SHA256,
        "D2 freeze drift",
    )
    freeze = json.loads(freeze_path.read_text())
    require(freeze["case"] == "A/candidate/1", "D2 case drift")
    for relative, expected in freeze["source_pins"].items():
        path = evidence / relative
        require(path.is_file() and not path.is_symlink(), f"missing D2 source: {relative}")
        require(
            _sha256(path) == expected,
            f"D2 source drift: {relative}",
        )

    audit = evidence / "l1-a-candidate-offline-audit-20260921"
    _check_snapshot(evidence, audit)

    episode = _read(evidence / "l1-a-candidate-real-20260921/episode.json")
    run = _read(evidence / "l1-a-candidate-real-20260921/result.json")
    audit_result = _read(audit / "result.json")
    report = _read(audit / "verifier-evidence/report.json")
    output: dict[str, Any] = {
        "schema_version": 1,
        "case": run["slot"],
        "original_episode": episode["acceptance"],
        "original_timeout_seconds": run["subject_timeout_seconds"],
        "original_duration_ms": run["duration_ms"],
        "original_verifier": "NOT_RUN" if not run["verifier_run"] else "RUN",
        "saved_changed_files": len(run["changed_paths"]),
        "reconstructed_files": audit_result["reconstructed_files_byte_identical"],
        "independent_verifier_passed": sum(check["passed"] for check in report["checks"]),
        "independent_verifier_total": len(report["checks"]),
        "independent_verifier_result": "FAILED_SAVED_WORKSPACE_ONLY",
        "workspace_contract": "DEFECTS_VERIFIED_A3_A4",
        "model_root_cause": "NOT_ESTABLISHED",
        "harness_root_cause": "NOT_ESTABLISHED",
    }
    require(
        output == {"schema_version": 1, "case": freeze["case"], **freeze["expected"]},
        "D2 frozen projection drift",
    )
    return output


def main() -> int:
    sys.addaudithook(offline_guard)
    try:
        print(json.dumps(replay(), sort_keys=True))
    except (AssertionError, ReplayError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL_CLOSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
