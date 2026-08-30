from __future__ import annotations

import hashlib
import json
from pathlib import Path

from harnesslab.budget import PricingAvailability, estimate_matrix_budget
from harnesslab.preflight import MatrixPreflightSpecification, PreflightAuthorizationLevel
from harnesslab.release.contracts import (
    load_core_corpus,
    load_real_evidence_plan,
    load_real_smoke_plan,
)
from harnesslab.release.smoke import load_smoke_continuation_policy

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"


def test_v4_successor_is_new_frozen_630_plus_63_plan_on_task_v102() -> None:
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan-v4.json")
    smoke = load_real_smoke_plan(RELEASE / "core-real-smoke-plan-v4.json")
    corpus = load_core_corpus(RELEASE / "core-corpus-v4.json")

    assert plan.plan_id == "core-real-evidence-v4"
    assert plan.supersedes_plan_id == "core-real-evidence-v3"
    assert plan.experiment_id == "core-real-matrix-v4"
    assert plan.corpus_digest == corpus.digest
    assert len(plan.cells) == 7
    assert sum(int(cell.planned_runs) for cell in plan.cells) == 630
    assert plan.judge.planned_calls == 63
    assert {task.version for task in corpus.tasks} == {"1.0.2"}
    assert smoke.plan_id == "core-real-smoke-v4"
    assert smoke.release_plan_digest == plan.digest
    assert len(smoke.calls) == 8


def test_split_preflights_have_disjoint_authority_and_heterogeneous_budget() -> None:
    canary = MatrixPreflightSpecification.model_validate_json(
        (RELEASE / "kb2r-canary-preflight.json").read_text(encoding="utf-8")
    )
    full = MatrixPreflightSpecification.model_validate_json(
        (RELEASE / "kb2r-full-matrix-preflight.json").read_text(encoding="utf-8")
    )
    canary_estimate = estimate_matrix_budget(canary.matrix_budget)
    full_estimate = estimate_matrix_budget(full.matrix_budget)

    assert canary.authorization_level is PreflightAuthorizationLevel.CANARY_PREFLIGHT
    assert canary.spend_authorized is True
    assert (canary.fixed_subject_call_count, canary.fixed_judge_call_count) == (7, 1)
    assert full.authorization_level is PreflightAuthorizationLevel.FULL_MATRIX_PREFLIGHT
    assert full.spend_authorized is False
    assert (full.fixed_subject_call_count, full.fixed_judge_call_count) == (630, 63)
    assert len({item.resource_ceiling for item in full.matrix_budget.subject_cells}) == 2
    assert canary_estimate.estimated_cost_availability is PricingAvailability.UNKNOWN
    assert full_estimate.estimated_cost_availability is PricingAvailability.UNKNOWN
    assert full_estimate.projected_worst_case.amount_usd is None


def test_dossier_records_hard_stop_without_rewriting_history() -> None:
    dossier = json.loads((RELEASE / "kb2r-authorization-dossier.json").read_text(encoding="utf-8"))
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan-v4.json")

    assert dossier["decision"] == "HARD_STOPPED"
    assert dossier["historical_scores_used_for_selection"] is False
    assert len(dossier["candidate_designs"]) == 2
    assert dossier["successor"]["plan_digest"] == plan.digest
    assert dossier["canary_execution"]["attempted_subject_launches"] == 4
    assert dossier["canary_execution"]["attempted_judge_launches"] == 0
    assert dossier["canary_execution"]["recovery_attempts"] == 0
    assert dossier["canary_execution"]["failure_category"] == "OBSERVED_MODEL_CONFLICT"
    assert dossier["full_matrix_projection"]["total_cost_usd"] is None
    assert dossier["full_matrix_projection"]["cost_status"] == "UNKNOWN_NOT_ZERO"
    assert dossier["invariants"] == {
        "old_matrix_resumed": False,
        "v3r1_mutated": False,
        "historical_evidence_rewritten": False,
        "full_matrix_executed": False,
        "historic_qwen_timeout_root_cause": "UNRESOLVED",
    }


def test_r1_append_only_dossier_preserves_history_and_terminal_suffix() -> None:
    expected_sha256 = {
        "core-real-evidence-plan-v4.json": (
            "5de29e88ff9482a34111e6639eb6a139045d812466614a5ceaeb6e796c76f90d"
        ),
        "core-real-smoke-plan-v4.json": (
            "cc3a8d9fd4df7e47d8f55df0dd7d7b922e2b972307f9ac11f86e9648a0df69ec"
        ),
        "kb2r-authorization-dossier.json": (
            "1c5ca81022d2a389637f9718254e746e81733b56819bef2d87bd62015eaf33e8"
        ),
    }
    for name, expected in expected_sha256.items():
        assert hashlib.sha256((RELEASE / name).read_bytes()).hexdigest() == expected

    policy = load_smoke_continuation_policy(RELEASE / "kb2r-r1-continuation-policy.json")
    dossier = json.loads(
        (RELEASE / "kb2r-r1-authorization-dossier.json").read_text(encoding="utf-8")
    )
    assert policy.allowed_suffix_call_ids == (
        "smoke-5-harness-codex-gpt56-high",
        "smoke-6-harness-claude-qwen38-opencode-go",
        "smoke-7-harness-deepseek-v4flash",
        "smoke-8-judge-glm52-opencode-go",
    )
    assert dossier["decision"] == "HARD_STOPPED"
    assert len(dossier["subject_calls"]) == 7
    assert dossier["continuation"]["reran_calls_1_to_4"] is False
    assert dossier["continuation"]["recovery_attempts"] == 0
    assert dossier["continuation"]["new_judge_launches"] == 0
    assert dossier["hard_stop"]["call_id"] == "smoke-7-harness-deepseek-v4flash"
    assert dossier["comparability"]["formal_90_pair_requirement_preserved"] is True
    assert dossier["comparability"]["uplift_claim_authorized"] is False
    assert dossier["full_matrix_projection"]["cost_status"] == "UNKNOWN_NOT_ZERO"
    assert dossier["full_matrix_projection"]["full_matrix_executed"] is False
