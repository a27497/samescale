from __future__ import annotations

import json
from pathlib import Path

from harnesslab.judgelab.models import GoldSource, JudgeMode, QualificationPolicy
from harnesslab.judgelab.report import _threshold_reasons
from harnesslab.release.judge_methodology_v2 import (
    OBJECTIVE_SLOT_COUNT,
    build_objective_v2_plan,
    objective_v2_methodology,
    objective_v2_policy,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN_ARTIFACT = ROOT / "release/core-real-judge-v7-methodology-plan.json"


def test_objective_v2_suite_has_only_deterministic_gold_and_63_slots() -> None:
    plan, suite, _ = build_objective_v2_plan(ROOT)
    assert len(plan.slots) == OBJECTIVE_SLOT_COUNT == 63
    assert plan.repeat_count == 3
    assert len(suite.public.cases) == 13
    assert sum(case.mode is JudgeMode.LABEL for case in suite.public.cases) == 5
    assert sum(case.mode is JudgeMode.PAIRWISE for case in suite.public.cases) == 8
    assert not any(case.mode is JudgeMode.SCORE for case in suite.public.cases)
    assert all(item.gold_source is GoldSource.DETERMINISTIC_L0 for item in suite.gold.gold)
    assert all(item.deterministic_authority == "L0_AUTHORITATIVE" for item in suite.gold.gold)
    assert plan.qualification_policy.require_score_metrics is False
    assert plan.qualification_policy.require_spearman is False


def test_objective_policy_skips_score_thresholds_but_historical_default_does_not() -> None:
    label = {"coverage": 1.0, "accuracy": 1.0, "macro_f1": 1.0, "repeat_consistency": 1.0}
    score = {"coverage": None, "mae": None, "spearman_rho": None}
    pairwise = {
        "coverage": 1.0,
        "gold_accuracy": 1.0,
        "position_consistency_rate": 1.0,
        "verbosity_bias_rate": 0.0,
        "repeat_consistency": 1.0,
    }
    capability = {"abstain_output_error_rate": 0.0}
    assert _threshold_reasons(label, score, pairwise, capability, objective_v2_policy()) == ()

    historical = objective_v2_policy().model_copy(
        update={"require_score_metrics": True, "require_spearman": True}
    )
    reasons = _threshold_reasons(label, score, pairwise, capability, historical)
    assert any("score coverage" in reason for reason in reasons)
    assert any("score MAE" in reason for reason in reasons)
    assert any("Spearman" in reason for reason in reasons)


def test_v2_methodology_artifact_removes_human_blocker_and_keeps_matrix_closed() -> None:
    artifact = json.loads(PLAN_ARTIFACT.read_text())
    method = objective_v2_methodology()
    assert artifact["state"] == "IMPLEMENTED_ZERO_PROVIDER_CALLS"
    assert artifact["suite"]["slot_count"] == 63
    assert artifact["suite"]["score_case_count"] == 0
    assert artifact["gold_authority"]["deterministic_l0_count"] == 13
    assert artifact["gold_authority"]["curated_human_l1_count"] == 0
    assert method["human_annotation_required"] is False
    assert method["absolute_score_metrics"] == "DIAGNOSTIC_ONLY_NOT_QUALIFICATION_BLOCKING"
    assert artifact["p1_multi_judge_jury"]["qualification_blocking"] is False
    assert artifact["authorization"]["new_real_judge_qualification"] == "NOT_AUTHORIZED"
    assert artifact["authorization"]["formal_matrix"] == "NOT_AUTHORIZED"


def test_historical_policy_serialization_remains_backward_compatible() -> None:
    raw = {
        "policy_id": "legacy",
        "version": "1",
        "minimum_coverage": 0.8,
        "minimum_label_accuracy": 0.8,
        "minimum_macro_f1": 0.95,
        "maximum_score_mae": 0.25,
        "minimum_spearman_rho": 0.95,
        "require_spearman": True,
        "minimum_pairwise_accuracy": 0.8,
        "minimum_position_consistency": 0.95,
        "minimum_repeat_consistency": 0.95,
        "maximum_abstain_error_rate": 0.15,
        "maximum_verbosity_bias_rate": 0.10,
        "qualification_rule": "ALL_REQUIRED_CHECKS_PASS",
    }
    parsed = QualificationPolicy.model_validate(raw)
    assert parsed.require_score_metrics is True
    assert "require_score_metrics" not in parsed.model_dump(mode="json")
