from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "release/kb3-evidence-reentry-audit.json"
DOSSIER_PATH = ROOT / "release/kb3-full-matrix-authorization-dossier.json"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_kb3_historical_checkpoint_is_immutable_and_secret_safe() -> None:
    result = subprocess.run(
        (sys.executable, "scripts/verify_kb3_evidence_reentry.py"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "K_B3_EVIDENCE_REENTRY_CHECKPOINT=PASS" in result.stdout


def test_kb3_hard_stop_prevents_successor_canary_recovery_and_matrix_calls() -> None:
    dossier = _load(DOSSIER_PATH)
    audit = _load(AUDIT_PATH)

    assert dossier["result"] == "HARD_STOPPED"
    assert dossier["successor"]["status"] == (
        "NOT_CREATED_BECAUSE_OPERATIONAL_RECONCILIATION_FAILED"
    )
    assert dossier["successor"]["experiment_id"] is None
    assert dossier["successor"]["plan_digest"] is None
    assert dossier["canary"] == {
        "judge_launches": 0,
        "recovery_attempts": 0,
        "status": "NOT_RUN_HARD_STOP",
        "subject_launches": 0,
    }
    assert dossier["authorization_boundary"]["full_matrix_executed"] is False
    assert dossier["authorization_boundary"]["matrix_launches_authorized_by_this_dossier"] == 0
    assert audit["qwen_route_reconciliation"]["reconciliation_result"] == ("UNRESOLVED_HARD_STOP")
    assert audit["evidence_boundary"]["secret_values_read_or_persisted"] is False


def test_kb3_cost_projection_does_not_reuse_historical_partial_evidence() -> None:
    dossier = _load(DOSSIER_PATH)
    projection = dossier["cost_latency_projection"]

    assert projection["estimated_per_run_cost"] == "NOT_AVAILABLE"
    assert projection["estimated_630_run_subject_cost"] == "NOT_AVAILABLE"
    assert projection["estimated_judge_campaign_cost"] == "NOT_AVAILABLE"
    assert projection["estimated_total_cost"] == "NOT_AVAILABLE"
    assert projection["expected_wall_clock"] == "NOT_AVAILABLE"
    assert projection["comparability_readiness"] == "NOT_READY_NO_SUCCESSOR_PLAN_OR_CANARY"
    assert dossier["actual_evidence"]["basis"] == (
        "HISTORICAL_V3R1_ONLY_NOT_TRANSFERABLE_TO_AN_UNCREATED_SUCCESSOR"
    )
