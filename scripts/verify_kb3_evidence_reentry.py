from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "release/kb3-evidence-reentry-audit.json"
DOSSIER_PATH = ROOT / "release/kb3-full-matrix-authorization-dossier.json"
AUDIT_SHA256 = "c25cfcbabb56f43e4cb3d23ecfabe638c5afdb3543c34871320a71b52a829c20"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.relative_to(ROOT)} must contain one JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _result_key_count(value: object) -> int:
    if isinstance(value, dict):
        total = 0
        for key, item in value.items():
            if isinstance(key, str) and key == "result":
                total += 1
            total += _result_key_count(item)
        return total
    if isinstance(value, list):
        return sum(_result_key_count(item) for item in value)
    return 0


def verify_checkpoint() -> None:
    audit = _load(AUDIT_PATH)
    dossier = _load(DOSSIER_PATH)
    if _sha256(AUDIT_PATH) != AUDIT_SHA256:
        raise RuntimeError("K-B3 historical audit identity drifted")
    if dossier.get("result") != "HARD_STOPPED" or _result_key_count(dossier) != 1:
        raise RuntimeError(
            "K-B3 authorization dossier must contain exactly one HARD_STOPPED result"
        )
    if dossier.get("historical_audit", {}).get("sha256") != f"sha256:{AUDIT_SHA256}":
        raise RuntimeError("K-B3 dossier is not bound to the immutable historical audit")

    historical = audit.get("historical_artifact_identities", {})
    for experiment in historical.values():
        if not isinstance(experiment, dict):
            continue
        artifacts = experiment.get("artifacts", {})
        if not isinstance(artifacts, dict):
            raise RuntimeError("K-B3 artifact identity set is malformed")
        for relative, expected in artifacts.items():
            path = ROOT / relative
            actual = f"sha256:{_sha256(path)}"
            if actual != expected:
                raise RuntimeError(f"immutable historical artifact drifted: {relative}")

    matrix = historical["core_real_matrix_v3"]
    v3 = historical["model_chat_v3"]
    v3r1 = historical["model_chat_v3r1"]
    route = audit["qwen_route_reconciliation"]
    if matrix["matrix_resumed_by_lane_a"] is not False:
        raise RuntimeError("historical core Matrix must remain unresumed")
    if v3["real_subject_acquisition"] != 0 or v3["operator_database_state"] != "ABSENT":
        raise RuntimeError("original Model Chat v3 must remain a zero-acquisition stop")
    if (
        v3r1["status"] != "HARD_STOPPED_PARTIAL_EXPLORATORY_EVIDENCE"
        or v3r1["logical_runs_attempted"] != 18
        or v3r1["logical_runs_untouched"] != 18
        or v3r1["recovery_attempts"] != 0
        or v3r1["original_evidence_mutated_by_lane_a"] is not False
    ):
        raise RuntimeError("Model Chat v3r1 hard-stop accounting drifted")
    if (
        route["reconciliation_result"] != "UNRESOLVED_HARD_STOP"
        or route["present_failure_classification"] != "CREDENTIAL_OPERATOR_CONFIGURATION_PROBLEM"
        or route["semantic_retry_attempted"] is not False
        or route["route_changed"] is not False
    ):
        raise RuntimeError("Qwen route hard-stop boundary drifted")

    successor = dossier["successor"]
    canary = dossier["canary"]
    calls = dossier["real_call_accounting"]
    if successor != {
        "experiment_id": None,
        "plan_digest": None,
        "planned_subject_runs": 0,
        "status": "NOT_CREATED_BECAUSE_OPERATIONAL_RECONCILIATION_FAILED",
    }:
        raise RuntimeError("K-B3 must not invent a successor after failed reconciliation")
    if canary["subject_launches"] != 0 or canary["judge_launches"] != 0:
        raise RuntimeError("K-B3 hard-stop dossier cannot contain canary launches")
    if any(calls[name] != 0 for name in ("subject_calls", "judge_calls", "provider_requests")):
        raise RuntimeError("K-B3 hard-stop dossier cannot contain real calls")

    tracked = subprocess.run(
        ("git", "ls-files", "--error-unmatch", "CHATGPT_PROJECT_HANDOFF_2026-08-27.md"),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if tracked.returncode == 0:
        raise RuntimeError("protected handoff file must remain untracked")

    source = AUDIT_PATH.read_text(encoding="utf-8") + DOSSIER_PATH.read_text(encoding="utf-8")
    forbidden = (
        "api_key_value",
        '"authorization"',
        "Bearer ",
        "postgresql+psycopg://",
        "sk-",
        "workspace-sentinel",
    )
    if any(fragment.casefold() in source.casefold() for fragment in forbidden):
        raise RuntimeError("K-B3 checkpoint contains protected runtime material")


def main() -> int:
    verify_checkpoint()
    print("K_B3_EVIDENCE_REENTRY_CHECKPOINT=PASS")
    print("AUTHORIZATION_DECISION=HARD_STOPPED")
    print("REAL_CANARY_SUBJECT_CALLS=0 REAL_JUDGE_CALLS=0 RECOVERY_ATTEMPTS=0")
    print("FULL_MATRIX_EXECUTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
