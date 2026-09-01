from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from harnesslab.judgelab.models import digest
from harnesslab.release.judge_j3r1 import (
    J3R1_ACCEPTED_OBSERVED_MODELS,
    J3R1_APPLICATION_RETRY_COUNT,
    J3R1_COST_CEILING,
    J3R1_EXPECTED_OBSERVED_MODEL,
    J3R1_PLAN_DIGEST,
    J3R1_REPEAT_COUNT,
    J3R1_SAFE_PARALLELISM,
    J3R1ControlPlaneError,
    build_j3r1_plan,
    normalize_j3r1_usage,
)

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "release/core-real-judge-v6-j3r1-plan.json"


def test_j3r1_plan_and_controls_are_exact() -> None:
    plan, suite, _ = build_j3r1_plan(ROOT)
    frozen = json.loads(FROZEN.read_text())
    assert plan.calibration_id == "core-real-judge-v6-j3r1"
    assert plan.plan_digest == J3R1_PLAN_DIGEST == frozen["plan_digest"]
    assert len(plan.slots) == frozen["slot_count"] == 63
    assert plan.repeat_count == J3R1_REPEAT_COUNT == frozen["repeat_count"] == 3
    assert plan.judge_cells[0].profile_identity == (
        "sha256:ceaa61e57ed362b9dab7825b0da33f7b283ba108ad014933f29eb39b852e305e"
    )
    assert suite.suite_digest == (
        "sha256:c2708196237eab94dac473581e3a06de2f7d0e2c50e8b55190b253e547fc43fb"
    )
    assert digest(plan.qualification_policy) == (
        "sha256:82b84e9f0e3330e9d2f3f9068e054d9041158ae3bd7bba38a0044530e8fe6170"
    )
    control = frozen["control"]
    assert control["expected_observed_model"] == J3R1_EXPECTED_OBSERVED_MODEL == "grok-4.6"
    assert tuple(control["accepted_observed_models"]) == J3R1_ACCEPTED_OBSERVED_MODELS
    assert control["safe_parallelism"] == J3R1_SAFE_PARALLELISM == 1
    assert control["application_retry_count"] == J3R1_APPLICATION_RETRY_COUNT == 0
    assert Decimal(control["operator_cost_ceiling"]) == J3R1_COST_CEILING == Decimal("1.000000")


def test_j3r1_predecessor_is_diagnostic_only_and_matrix_stays_closed() -> None:
    frozen = json.loads(FROZEN.read_text())
    predecessor = frozen["control"]["predecessor_j3"]
    assert predecessor["state"] == "STOPPED_MODEL_IDENTITY_DRIFT"
    assert predecessor["completed_slots"] == 1
    assert predecessor["evidence_class"] == "DIAGNOSTIC_ONLY"
    assert predecessor["qualification_reuse_prohibited"] is True
    assert frozen["qualification_evidence_reuse"] == {
        "predecessor_j3_slot": "PROHIBITED",
        "j3r1_slots": "FRESH_ONLY",
    }
    assert frozen["authorization"]["j3r1_qualification_authorized"] is True
    assert frozen["authorization"]["matrix_authorized"] is False
    assert frozen["authorization"]["real_matrix_calls"] == 0


def test_j3r1_usage_normalization_matches_observed_relay_semantics() -> None:
    usage = normalize_j3r1_usage(
        input_tokens=453,
        completion_tokens=25,
        total_tokens=1334,
        cached_tokens=192,
        reasoning_tokens=856,
    )
    assert usage["non_cached_input_tokens"] == 261
    assert usage["billable_output_tokens"] == 881
    assert usage["reasoning_tokens"] == 856
    assert usage["estimated_cost"] == "0.0017712"
    assert usage["unit"] == "RELAY_BILLING_UNIT"


def test_j3r1_usage_normalization_fails_closed_on_incoherent_totals() -> None:
    with pytest.raises(J3R1ControlPlaneError):
        normalize_j3r1_usage(
            input_tokens=100,
            completion_tokens=30,
            total_tokens=120,
            cached_tokens=0,
            reasoning_tokens=10,
        )
    with pytest.raises(J3R1ControlPlaneError):
        normalize_j3r1_usage(
            input_tokens=100,
            completion_tokens=10,
            total_tokens=120,
            cached_tokens=101,
            reasoning_tokens=10,
        )
