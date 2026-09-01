from __future__ import annotations

import json
from pathlib import Path

from harnesslab.release.judge_j4 import (
    J4_APPLICATION_RETRY_COUNT,
    J4_CALLS,
    J4_COST_CEILING,
    J4_RELAY_MODEL_ALIASES,
    J4_REPEAT_COUNT,
    J4_SAFE_PARALLELISM,
    build_j4_plan,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "release/core-real-judge-v7-j4-plan.json"


def test_j4_is_objective_v2_and_zero_call_preregistered() -> None:
    plan = build_j4_plan(ROOT)
    frozen = json.loads(ARTIFACT.read_text())
    assert len(plan.slots) == J4_CALLS == 63
    assert plan.repeat_count == J4_REPEAT_COUNT == 3
    assert plan.qualification_policy.require_score_metrics is False
    assert plan.qualification_policy.require_spearman is False
    assert frozen["plan_digest"] == plan.plan_digest
    assert frozen["candidate"]["relay_observed_model_aliases"] == list(J4_RELAY_MODEL_ALIASES)
    assert frozen["methodology"]["safe_parallelism"] == J4_SAFE_PARALLELISM == 1
    assert frozen["methodology"]["application_retry_count"] == J4_APPLICATION_RETRY_COUNT == 0
    assert frozen["cost_control"]["ceiling"] == J4_COST_CEILING == "1.000000"
    assert frozen["evidence_reuse"]["j3r1_outputs_reused"] is False
    assert frozen["authorization"]["j4_real_judge_calls"] == "NOT_AUTHORIZED"
    assert frozen["authorization"]["formal_matrix"] == "NOT_AUTHORIZED"

RESULT = ROOT / "release/core-real-judge-v7-j4-result.json"


def test_j4_completed_and_correct_unknown_abstentions_are_not_errors() -> None:
    result = json.loads(RESULT.read_text())
    assert result["state"] == "QUALIFIED_FOR_SUITE"
    assert result["execution"]["completed_slots"] == 63
    assert result["execution"]["real_judge_calls"] == 63
    assert result["execution"]["real_matrix_calls"] == 0
    assert result["qualification"]["label_accuracy"] == 1.0
    assert result["qualification"]["pairwise_accuracy"] == 1.0
    assert result["qualification"]["abstain_output_error_rate"] == 0.0
    assert result["reporter_correction"]["provider_calls_added"] == 0
    assert result["formal_matrix_authorization"] == "NOT_AUTHORIZED"
