from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from harnesslab.budget import (
    CallResourceCeiling,
    JudgeCampaignBudget,
    MatrixBudgetEstimateRequest,
    MatrixCellBudget,
    PricingAvailability,
    ProviderPricing,
    estimate_matrix_budget,
)
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane, NetworkPolicy
from harnesslab.preflight import (
    ConfigurationKind,
    ConfigurationRequirement,
    FrozenResourceEnvelope,
    HarnessRequirement,
    MatrixCellRequirement,
    MatrixPreflightSpecification,
    ObservedModelExposure,
    PreflightAuthorizationLevel,
    PreflightObservations,
    PreflightSpecification,
    PreflightStatus,
    ProviderRouteRequirement,
    TraceSupport,
    assess_matrix_preflight,
)

ROUTE_A = "provider-a|responses|https://provider-a.invalid/v1/responses"
ROUTE_B = "provider-b|messages|https://provider-b.invalid/v1/messages"
JUDGE_ROUTE = "judge|chat_completions|https://judge.invalid/v1/chat/completions"
ENVELOPE = canonical_digest({"wall_seconds": 90, "requests": 2, "turns": 4})


def _pricing(route: str, known: bool) -> ProviderPricing:
    if not known:
        return ProviderPricing(route_identity=route, availability=PricingAvailability.UNKNOWN)
    return ProviderPricing(
        route_identity=route,
        availability=PricingAvailability.KNOWN,
        input_usd_per_million_tokens=Decimal("1"),
        output_usd_per_million_tokens=Decimal("2"),
        request_usd=Decimal("0.01"),
        evidence_reference=f"pricing:{route}",
    )


def _budget(*, runs: int, judge_calls: int, known: bool) -> MatrixBudgetEstimateRequest:
    direct = CallResourceCeiling(
        input_tokens=1_000,
        output_tokens=500,
        provider_requests=1,
        harness_turns=1,
    )
    harness = CallResourceCeiling(
        input_tokens=2_000,
        output_tokens=1_000,
        provider_requests=3,
        harness_turns=8,
    )
    return MatrixBudgetEstimateRequest(
        subject_cells=(
            MatrixCellBudget(
                cell_id="direct-a",
                planned_run_count=runs,
                route_identity=ROUTE_A,
                resource_ceiling=direct,
                pricing=_pricing(ROUTE_A, known),
            ),
            MatrixCellBudget(
                cell_id="harness-b",
                planned_run_count=runs,
                route_identity=ROUTE_B,
                resource_ceiling=harness,
                pricing=_pricing(ROUTE_B, known),
            ),
        ),
        judge_campaign=JudgeCampaignBudget(
            profile_id="judge-fixed",
            planned_call_count=judge_calls,
            route_identity=JUDGE_ROUTE,
            resource_ceiling=CallResourceCeiling(
                input_tokens=500,
                output_tokens=100,
                provider_requests=1,
                harness_turns=0,
            ),
            pricing=_pricing(JUDGE_ROUTE, known),
        ),
        budget_ceiling_usd=Decimal("1000") if known else None,
    )


def _specification(
    authorization_level: PreflightAuthorizationLevel,
    *,
    runs: int,
    judge_calls: int,
    known: bool,
    spend_authorized: bool,
) -> MatrixPreflightSpecification:
    prerequisites = PreflightSpecification(
        docker_required=False,
        database_required=False,
        minimum_free_bytes=0,
        configurations=(
            ConfigurationRequirement(reference="MATRIX_KEY", kind=ConfigurationKind.CREDENTIAL),
        ),
        provider_routes=(
            ProviderRouteRequirement(route_identity=ROUTE_A, expected_identity=ROUTE_A),
            ProviderRouteRequirement(route_identity=ROUTE_B, expected_identity=ROUTE_B),
            ProviderRouteRequirement(route_identity=JUDGE_ROUTE, expected_identity=JUDGE_ROUTE),
        ),
        harnesses=(
            HarnessRequirement(
                harness_id="direct-model",
                requested_model="model-a",
                supported_lanes=frozenset({EvaluationLane.MODEL}),
                selected_lane=EvaluationLane.MODEL,
                trace_support=TraceSupport.FINAL_OUTPUT_ONLY,
                required_trace_support=TraceSupport.FINAL_OUTPUT_ONLY,
            ),
            HarnessRequirement(
                harness_id="harness-b",
                requested_model="model-b",
                supported_lanes=frozenset({EvaluationLane.HARNESS}),
                selected_lane=EvaluationLane.HARNESS,
                trace_support=TraceSupport.FULL_STREAM,
                required_trace_support=TraceSupport.FULL_STREAM,
            ),
        ),
        network_policy=NetworkPolicy.ALLOWLIST,
    )
    envelope = FrozenResourceEnvelope(expected_identity=ENVELOPE, actual_identity=ENVELOPE)
    return MatrixPreflightSpecification(
        authorization_level=authorization_level,
        prerequisites=prerequisites,
        cells=(
            MatrixCellRequirement(
                cell_id="direct-a",
                roles=("M", "P"),
                route_identity=ROUTE_A,
                requested_model="model-a",
                harness_id="direct-model",
                runtime_profile_identity="direct-model-v1:model-a",
                trace_support=TraceSupport.FINAL_OUTPUT_ONLY,
                required_trace_support=TraceSupport.FINAL_OUTPUT_ONLY,
                observed_model_exposure=ObservedModelExposure.RUN_EVIDENCE_ONLY,
                resource_envelope=envelope,
            ),
            MatrixCellRequirement(
                cell_id="harness-b",
                roles=("H", "P"),
                route_identity=ROUTE_B,
                requested_model="model-b",
                harness_id="harness-b",
                runtime_profile_identity="harness-b-v1:model-b",
                trace_support=TraceSupport.FULL_STREAM,
                required_trace_support=TraceSupport.FULL_STREAM,
                observed_model_exposure=ObservedModelExposure.RUN_EVIDENCE_ONLY,
                resource_envelope=envelope,
            ),
        ),
        matrix_budget=_budget(runs=runs, judge_calls=judge_calls, known=known),
        fixed_subject_call_count=2 * runs,
        fixed_judge_call_count=judge_calls,
        spend_authorized=spend_authorized,
    )


def _observations() -> PreflightObservations:
    return PreflightObservations(
        disk_free_bytes=1,
        configuration_present={"MATRIX_KEY": True},
        configuration_valid={"MATRIX_KEY": True},
        harness_runtime_available={"direct-model": True, "harness-b": True},
    )


def test_matrix_budget_preserves_heterogeneous_cells_and_separate_judge() -> None:
    budget = _budget(runs=315, judge_calls=63, known=True)
    estimate = estimate_matrix_budget(budget)

    assert estimate.expected_subject_calls == 630
    assert estimate.expected_judge_calls == 63
    assert [component.kind for component in estimate.components] == [
        "SUBJECT",
        "SUBJECT",
        "JUDGE",
    ]
    assert estimate.components[0].provider_request_ceiling == 315
    assert estimate.components[1].provider_request_ceiling == 945
    assert estimate.token_ceiling.total == 1_455_300
    assert estimate.projected_worst_case.amount_usd is not None


def test_unknown_canary_pricing_warns_when_exact_calls_are_authorized() -> None:
    specification = _specification(
        PreflightAuthorizationLevel.CANARY_PREFLIGHT,
        runs=1,
        judge_calls=1,
        known=False,
        spend_authorized=True,
    )
    report = assess_matrix_preflight(specification, _observations())

    assert report.status is PreflightStatus.READY_WITH_WARNINGS
    assert report.provider_calls == report.judge_calls == 0
    assert "CANARY_PRICING_UNKNOWN" in {item.reason_code for item in report.findings}
    assert report.matrix_budget_estimate.projected_worst_case.amount_usd is None


def test_full_matrix_unknown_pricing_or_missing_authorization_blocks() -> None:
    report = assess_matrix_preflight(
        _specification(
            PreflightAuthorizationLevel.FULL_MATRIX_PREFLIGHT,
            runs=315,
            judge_calls=63,
            known=False,
            spend_authorized=False,
        ),
        _observations(),
    )

    assert report.status is PreflightStatus.BLOCKED
    assert {"FULL_MATRIX_PRICING_UNKNOWN", "FULL_MATRIX_BUDGET_NOT_AUTHORIZED"} <= {
        item.reason_code for item in report.findings
    }


def test_full_matrix_known_pricing_and_authorization_can_pass() -> None:
    report = assess_matrix_preflight(
        _specification(
            PreflightAuthorizationLevel.FULL_MATRIX_PREFLIGHT,
            runs=315,
            judge_calls=63,
            known=True,
            spend_authorized=True,
        ),
        _observations(),
    )

    assert report.status is PreflightStatus.READY


def test_canary_requires_exactly_one_launch_per_cell() -> None:
    with pytest.raises(ValidationError, match="exactly one launch per cell"):
        _specification(
            PreflightAuthorizationLevel.CANARY_PREFLIGHT,
            runs=2,
            judge_calls=1,
            known=False,
            spend_authorized=True,
        )
