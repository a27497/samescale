from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from harnesslab.judgelab.models import (
    JudgeCalibrationPlan,
    JudgeCellSpec,
    JudgeDefinition,
    JudgeSuite,
    digest,
)
from harnesslab.judgelab.plan import (
    build_calibration_plan,
    load_calibration_spec,
    resolve_definitions,
    resolve_suite,
)
from harnesslab.release.judge_j3 import (
    J3_CELL_ID,
    J3_SCIENTIFIC_ROUTE_IDENTITY,
    configured_j3_profile,
)
from harnesslab.release.smoke import SmokeControlPlaneError

J3R1_CALIBRATION_ID = "core-real-judge-v6-j3r1"
J3R1_CALLS = 63
J3R1_REPEAT_COUNT = 3
J3R1_SAFE_PARALLELISM = 1
J3R1_APPLICATION_RETRY_COUNT = 0
J3R1_EXPECTED_OBSERVED_MODEL = "grok-4.6"
J3R1_ACCEPTED_OBSERVED_MODELS = ("grok-4.6", "grok-4.6-build")
J3R1_COST_UNIT = "RELAY_BILLING_UNIT"
J3R1_COST_CEILING = Decimal("1.000000")
J3R1_RATE_NONCACHED = Decimal("0.60")
J3R1_RATE_CACHED = Decimal("0.15")
J3R1_RATE_OUTPUT = Decimal("1.80")
J3R1_PLAN_DIGEST = "sha256:13bba26a841386580651413c322d6cad60abb8de548a140bed1907943d68b241"
J3R1_CONTROL_DIGEST = "PENDING"


class J3R1ControlPlaneError(SmokeControlPlaneError):
    """The authorized J3r1 successor differs from its preregistered controls."""


def _construct_j3r1_plan(
    repository_root: Path,
) -> tuple[JudgeCalibrationPlan, JudgeSuite, dict[str, JudgeDefinition]]:
    profile = configured_j3_profile()
    suite_root = repository_root / "judge_suites/core-calibration/1.0.0"
    base_spec = load_calibration_spec(suite_root / "calibration.yaml")
    suite = resolve_suite(base_spec, repository_root)
    base_definitions = resolve_definitions(base_spec, repository_root)
    source_cell = base_spec.judge_cells[0]
    definition = base_definitions[source_cell.id]
    cell = JudgeCellSpec(
        id=J3_CELL_ID,
        definition_reference=source_cell.definition_reference,
        definition_digest=source_cell.definition_digest,
        model_profile=profile,
        profile_identity=digest(profile),
        runner_contract="provider-adapter-v1",
    )
    spec = base_spec.model_copy(
        update={
            "calibration_id": J3R1_CALIBRATION_ID,
            "name": "HarnessLab Core Grok 4.6 aiwanwu Relay Judge Qualification V6 J3r1",
            "judge_cells": (cell,),
        }
    )
    plan = build_calibration_plan(spec, suite, {cell.id: definition})
    return plan, suite, {cell.id: definition}


def build_j3r1_plan(
    repository_root: Path,
) -> tuple[JudgeCalibrationPlan, JudgeSuite, dict[str, JudgeDefinition]]:
    plan, suite, definitions = _construct_j3r1_plan(repository_root)
    if len(plan.slots) != J3R1_CALLS or plan.repeat_count != J3R1_REPEAT_COUNT:
        raise J3R1ControlPlaneError("J3r1 must contain exactly 63 slots over three repeats")
    if J3R1_PLAN_DIGEST != "PENDING" and plan.plan_digest != J3R1_PLAN_DIGEST:
        raise J3R1ControlPlaneError("J3r1 qualification plan differs from frozen digest")
    return plan, suite, definitions


def normalize_j3r1_usage(
    *,
    input_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    cached_tokens: int | None,
    reasoning_tokens: int | None,
) -> dict[str, int | str | None]:
    if input_tokens is None or total_tokens is None:
        raise J3R1ControlPlaneError("J3r1 requires input_tokens and total_tokens for billing")
    cached = cached_tokens if cached_tokens is not None else 0
    if cached < 0 or cached > input_tokens:
        raise J3R1ControlPlaneError("J3r1 cached token accounting is invalid")
    billable_output = total_tokens - input_tokens
    if billable_output < 0:
        raise J3R1ControlPlaneError("J3r1 total token accounting is invalid")
    if completion_tokens is not None and billable_output < completion_tokens:
        raise J3R1ControlPlaneError("J3r1 billable output is below provider completion tokens")
    non_cached = input_tokens - cached
    cost = (
        Decimal(non_cached) * J3R1_RATE_NONCACHED
        + Decimal(cached) * J3R1_RATE_CACHED
        + Decimal(billable_output) * J3R1_RATE_OUTPUT
    ) / Decimal(1_000_000)
    return {
        "input_tokens": input_tokens,
        "non_cached_input_tokens": non_cached,
        "cached_input_tokens": cached,
        "completion_tokens_field": completion_tokens,
        "billable_output_tokens": billable_output,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "estimated_cost": format(cost, "f"),
        "unit": J3R1_COST_UNIT,
    }


def j3r1_control(plan: JudgeCalibrationPlan, suite: JudgeSuite) -> dict[str, object]:
    return {
        "schema_version": 1,
        "calibration_id": J3R1_CALIBRATION_ID,
        "plan_digest": plan.plan_digest,
        "profile_identity": plan.judge_cells[0].profile_identity,
        "suite_digest": suite.suite_digest,
        "qualification_policy_digest": digest(plan.qualification_policy),
        "scientific_route_identity": J3_SCIENTIFIC_ROUTE_IDENTITY,
        "expected_observed_model": J3R1_EXPECTED_OBSERVED_MODEL,
        "accepted_observed_models": list(J3R1_ACCEPTED_OBSERVED_MODELS),
        "safe_parallelism": J3R1_SAFE_PARALLELISM,
        "application_retry_count": J3R1_APPLICATION_RETRY_COUNT,
        "operator_cost_ceiling": format(J3R1_COST_CEILING, "f"),
        "cost_unit": J3R1_COST_UNIT,
        "usage_normalization": {
            "cached_input": "prompt_tokens_details.cached_tokens_or_zero",
            "non_cached_input": "input_tokens_minus_cached_input",
            "billable_output": "total_tokens_minus_input_tokens",
            "reasoning_tokens": "preserve_separately",
            "completion_field_check": "billable_output_gte_completion_tokens_when_present",
        },
        "predecessor_j3": {
            "state": "STOPPED_MODEL_IDENTITY_DRIFT",
            "completed_slots": 1,
            "observed_relay_model": "grok-4.6",
            "evidence_class": "DIAGNOSTIC_ONLY",
            "qualification_reuse_prohibited": True,
            "reconciled_cost": "0.0017712",
            "cost_unit": J3R1_COST_UNIT,
        },
        "formal_matrix_authorization": "NOT_AUTHORIZED",
        "real_matrix_calls": 0,
    }


def j3r1_control_digest(plan: JudgeCalibrationPlan, suite: JudgeSuite) -> str:
    value = digest(j3r1_control(plan, suite))
    if J3R1_CONTROL_DIGEST != "PENDING" and value != J3R1_CONTROL_DIGEST:
        raise J3R1ControlPlaneError("J3r1 control differs from frozen digest")
    return value
