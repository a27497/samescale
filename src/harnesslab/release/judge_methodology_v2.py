from __future__ import annotations

from pathlib import Path

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.judgelab.models import (
    JudgeCalibrationPlan,
    JudgeCalibrationSpec,
    JudgeCellSpec,
    JudgeDefinition,
    JudgeSuite,
    QualificationPolicy,
    digest,
)
from harnesslab.judgelab.plan import build_calibration_plan
from harnesslab.judgelab.suite import load_judge_definition, load_judge_suite

OBJECTIVE_SUITE_REFERENCE = "judge_suites/core-calibration/2.0.0"
OBJECTIVE_REPEAT_COUNT = 3
OBJECTIVE_SLOT_COUNT = 63


def objective_v2_policy() -> QualificationPolicy:
    return QualificationPolicy(
        policy_id="core-objective-policy",
        version="2.0.0",
        minimum_coverage=0.80,
        minimum_label_accuracy=0.80,
        minimum_macro_f1=0.95,
        require_score_metrics=False,
        maximum_score_mae=0.25,
        minimum_spearman_rho=0.95,
        require_spearman=False,
        minimum_pairwise_accuracy=0.80,
        minimum_position_consistency=0.95,
        minimum_repeat_consistency=0.95,
        maximum_abstain_error_rate=0.15,
        maximum_verbosity_bias_rate=0.10,
        qualification_rule="ALL_REQUIRED_CHECKS_PASS",
    )


def build_objective_v2_plan(
    repository_root: Path,
) -> tuple[JudgeCalibrationPlan, JudgeSuite, dict[str, JudgeDefinition]]:
    suite_root = repository_root / OBJECTIVE_SUITE_REFERENCE
    suite = load_judge_suite(suite_root)
    definition = load_judge_definition(suite_root / "definition.yaml")
    profile = ModelProfile(
        requested_model="objective-v2-keyless-placeholder",
        provider="phase-h-fake",
        base_url="https://phase-h-fake.invalid/v1",
        route="/responses",
        protocol=Protocol.RESPONSES,
        reasoning=ReasoningProfile(temperature=0, max_output_tokens=256),
        request_timeout_seconds=30,
    )
    cell = JudgeCellSpec(
        id="objective-v2-keyless",
        definition_reference=f"{OBJECTIVE_SUITE_REFERENCE}/definition.yaml",
        definition_digest=definition.definition_digest,
        model_profile=profile,
        profile_identity=digest(profile),
        runner_contract="phase-h-fake-good-v1",
    )
    spec = JudgeCalibrationSpec(
        calibration_id="core-objective-keyless-v2",
        name="Core objective Judge calibration v2",
        suite_reference=OBJECTIVE_SUITE_REFERENCE,
        suite_digest=suite.suite_digest,
        judge_cells=(cell,),
        repeat_count=OBJECTIVE_REPEAT_COUNT,
        execution_seed=20260901,
        qualification_policy=objective_v2_policy(),
    )
    plan = build_calibration_plan(spec, suite, {cell.id: definition})
    if len(plan.slots) != OBJECTIVE_SLOT_COUNT:
        raise ValueError("objective v2 plan must contain exactly 63 slots")
    return plan, suite, {cell.id: definition}


def objective_v2_methodology() -> dict[str, object]:
    return {
        "schema_version": 1,
        "methodology": "OBJECTIVE_JUDGE_QUALIFICATION_V2",
        "core_qualification": [
            "deterministic_label_accuracy",
            "objective_pairwise_accuracy",
            "controlled_degradation_detection",
            "position_consistency",
            "repeat_consistency",
            "abstain_correctness",
            "verbosity_invariance",
        ],
        "absolute_score_metrics": "DIAGNOSTIC_ONLY_NOT_QUALIFICATION_BLOCKING",
        "multi_judge_jury": "P1_DIAGNOSTIC_ONLY_NOT_GOLD_AUTHORITY",
        "human_annotation_required": False,
        "formal_matrix_authorized": False,
        "rationale": (
            "Core qualification uses synthetic or embedded-reference L0 gold so candidate Judge "
            "outcomes cannot redefine the answer key."
        ),
    }
