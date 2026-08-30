from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from harnesslab.budget import (
    BudgetEstimateRequest,
    BudgetMode,
    CallResourceCeiling,
    PricingAvailability,
    ProviderPricing,
)
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane, NetworkPolicy
from harnesslab.core.config import Settings
from harnesslab.preflight import (
    CheckStatus,
    ComparabilityControl,
    ConfigurationKind,
    ConfigurationRequirement,
    FrozenResourceEnvelope,
    HarnessRequirement,
    PreflightObservations,
    PreflightSpecification,
    PreflightStatus,
    ProviderRouteRequirement,
    TaskObservation,
    TaskRequirement,
    TraceSupport,
    assess_preflight,
    run_preflight,
)

TASK = "tasks/core-python-slugify/1.0.2"
ROUTE = "example-provider|responses|https://provider.invalid/v1/responses"
ENVELOPE = canonical_digest({"wall_seconds": 90, "provider_requests": 1})


def _budget() -> BudgetEstimateRequest:
    ceiling = CallResourceCeiling(input_tokens=100, output_tokens=100)
    pricing = ProviderPricing(
        route_identity=ROUTE,
        availability=PricingAvailability.KNOWN,
        input_usd_per_million_tokens=Decimal("1"),
        output_usd_per_million_tokens=Decimal("2"),
        request_usd=Decimal("0"),
        evidence_reference="pricing/test-v1.json",
    )
    return BudgetEstimateRequest(
        mode=BudgetMode.QUICK,
        task_count=1,
        subject_cell_count=1,
        judge_calls_per_subject=0,
        subject_ceiling=ceiling,
        judge_ceiling=ceiling,
        subject_pricing=pricing,
        judge_pricing=pricing,
        budget_ceiling_usd=Decimal("1"),
    )


def _specification(**updates: object) -> PreflightSpecification:
    specification = PreflightSpecification(
        minimum_free_bytes=100,
        required_images=("harnesslab:test",),
        configurations=(
            ConfigurationRequirement(
                reference="PHASE_M_PROVIDER_KEY",
                kind=ConfigurationKind.CREDENTIAL,
            ),
        ),
        provider_routes=(
            ProviderRouteRequirement(
                route_identity=ROUTE,
                expected_identity=ROUTE,
                requires_network=True,
            ),
        ),
        harnesses=(
            HarnessRequirement(
                harness_id="test-harness",
                executable="test-harness",
                requested_model="test-model",
                compatible_models=frozenset({"test-model"}),
                supported_lanes=frozenset({EvaluationLane.HARNESS}),
                selected_lane=EvaluationLane.HARNESS,
                trace_support=TraceSupport.FULL_STREAM,
                required_trace_support=TraceSupport.FULL_STREAM,
            ),
        ),
        tasks=(TaskRequirement(package_path=TASK, selected_lane=EvaluationLane.HARNESS),),
        network_policy=NetworkPolicy.ALLOWLIST,
        resource_envelope=FrozenResourceEnvelope(
            expected_identity=ENVELOPE,
            actual_identity=ENVELOPE,
        ),
        budget=_budget(),
    )
    return specification.model_copy(update=updates)


def _observations(**updates: object) -> PreflightObservations:
    observations = PreflightObservations(
        docker_available=True,
        database_ready=True,
        disk_free_bytes=100,
        image_available={"harnesslab:test": True},
        configuration_present={"PHASE_M_PROVIDER_KEY": True},
        configuration_valid={"PHASE_M_PROVIDER_KEY": True},
        harness_runtime_available={"test-harness": True},
        tasks={
            TASK: TaskObservation(
                valid=True,
                supported_lanes=frozenset({EvaluationLane.MODEL, EvaluationLane.HARNESS}),
            )
        },
    )
    return observations.model_copy(update=updates)


def _reasons(
    specification: PreflightSpecification, observations: PreflightObservations
) -> set[str]:
    return {item.reason_code for item in assess_preflight(specification, observations).findings}


def test_ready_preflight_is_keyless_and_has_exact_terminal_status() -> None:
    report = assess_preflight(_specification(), _observations())

    assert report.status is PreflightStatus.READY
    assert report.provider_calls == 0
    assert report.judge_calls == 0
    assert all(item.status is CheckStatus.PASS for item in report.findings)


def test_missing_docker_and_database_are_blocking() -> None:
    report = assess_preflight(
        _specification(),
        _observations(docker_available=False, database_ready=False),
    )

    assert report.status is PreflightStatus.BLOCKED
    assert {"DOCKER_RUNTIME_MISSING", "DATABASE_NOT_READY"} <= {
        item.reason_code for item in report.findings
    }


def test_uninspectable_disk_capacity_fails_closed() -> None:
    report = assess_preflight(_specification(), _observations(disk_free_bytes=None))

    assert report.status is PreflightStatus.BLOCKED
    assert "DISK_SPACE_UNAVAILABLE" in {item.reason_code for item in report.findings}


def test_missing_configuration_reports_only_reference_not_value() -> None:
    secret = "must-never-appear"
    report = assess_preflight(
        _specification(),
        _observations(
            configuration_present={"PHASE_M_PROVIDER_KEY": False},
            configuration_valid={"PHASE_M_PROVIDER_KEY": False},
        ),
    )

    assert report.status is PreflightStatus.BLOCKED
    assert "REQUIRED_CONFIGURATION_MISSING" in _reasons(
        _specification(),
        _observations(
            configuration_present={"PHASE_M_PROVIDER_KEY": False},
            configuration_valid={"PHASE_M_PROVIDER_KEY": False},
        ),
    )
    assert secret not in report.model_dump_json()


def test_invalid_route_identity_is_blocking() -> None:
    route = ProviderRouteRequirement(
        route_identity="provider|responses|http://unsafe.invalid/responses",
        requires_network=True,
    )
    report = assess_preflight(_specification(provider_routes=(route,)), _observations())

    assert report.status is PreflightStatus.BLOCKED
    assert "PROVIDER_ROUTE_IDENTITY_INVALID" in {item.reason_code for item in report.findings}


def test_unsupported_harness_lane_model_and_trace_are_blocking() -> None:
    harness = HarnessRequirement(
        harness_id="test-harness",
        executable="test-harness",
        requested_model="unsupported-model",
        compatible_models=frozenset({"test-model"}),
        supported_lanes=frozenset({EvaluationLane.MODEL}),
        selected_lane=EvaluationLane.HARNESS,
        trace_support=TraceSupport.FINAL_OUTPUT_ONLY,
        required_trace_support=TraceSupport.FULL_STREAM,
    )
    report = assess_preflight(_specification(harnesses=(harness,)), _observations())

    reasons = {item.reason_code for item in report.findings}
    assert report.status is PreflightStatus.BLOCKED
    assert {
        "HARNESS_CAPABILITY_UNSUPPORTED",
        "MODEL_HARNESS_INCOMPATIBLE",
        "REQUIRED_TRACE_UNSUPPORTED",
    } <= reasons


def test_invalid_task_and_unsupported_lane_are_blocking() -> None:
    observations = _observations(
        tasks={
            TASK: TaskObservation(
                valid=False,
                supported_lanes=frozenset({EvaluationLane.MODEL}),
            )
        }
    )
    report = assess_preflight(_specification(), observations)

    reasons = {item.reason_code for item in report.findings}
    assert {"TASK_INVALID", "TASK_LANE_UNSUPPORTED"} <= reasons


def test_network_policy_conflict_is_blocking() -> None:
    report = assess_preflight(
        _specification(network_policy=NetworkPolicy.DENY),
        _observations(),
    )

    assert report.status is PreflightStatus.BLOCKED
    assert "NETWORK_POLICY_CONFLICT" in {item.reason_code for item in report.findings}


def test_comparability_drift_is_a_warning_with_remediation() -> None:
    report = assess_preflight(
        _specification(
            comparability_controls=(
                ComparabilityControl(
                    name="prompt",
                    expected_identity="frozen-prompt",
                    actual_identity="changed-prompt",
                ),
            )
        ),
        _observations(),
    )

    assert report.status is PreflightStatus.READY_WITH_WARNINGS
    warning = next(item for item in report.findings if item.reason_code == "COMPARABILITY_RISK")
    assert warning.status is CheckStatus.WARNING
    assert warning.remediation


def test_resource_envelope_identity_mismatch_is_blocking() -> None:
    report = assess_preflight(
        _specification(
            resource_envelope=FrozenResourceEnvelope(
                expected_identity=ENVELOPE,
                actual_identity=canonical_digest({"wall_seconds": 120}),
            )
        ),
        _observations(),
    )

    assert report.status is PreflightStatus.BLOCKED
    assert "RESOURCE_ENVELOPE_IDENTITY_MISMATCH" in {item.reason_code for item in report.findings}


def test_unknown_pricing_is_never_treated_as_zero_cost() -> None:
    unknown = ProviderPricing(
        route_identity=ROUTE,
        availability=PricingAvailability.UNKNOWN,
    )
    budget = _budget().model_copy(update={"subject_pricing": unknown, "judge_pricing": unknown})
    report = assess_preflight(_specification(budget=budget), _observations())

    assert report.status is PreflightStatus.BLOCKED
    assert report.budget_estimate is not None
    assert report.budget_estimate.projected_worst_case.amount_usd is None
    assert {"PRICING_UNKNOWN", "BUDGET_CEILING_INDETERMINATE"} <= {
        item.reason_code for item in report.findings
    }


def test_projected_cost_above_ceiling_blocks_preflight() -> None:
    expensive = ProviderPricing(
        route_identity=ROUTE,
        availability=PricingAvailability.KNOWN,
        input_usd_per_million_tokens=Decimal("1000000"),
        output_usd_per_million_tokens=Decimal("1000000"),
        request_usd=Decimal("10"),
        evidence_reference="pricing/expensive-v1.json",
    )
    budget = _budget().model_copy(update={"subject_pricing": expensive, "judge_pricing": expensive})
    report = assess_preflight(_specification(budget=budget), _observations())

    assert report.status is PreflightStatus.BLOCKED
    assert "BUDGET_CEILING_EXCEEDED" in {item.reason_code for item in report.findings}


async def test_runtime_collector_checks_docker_and_database_without_provider_calls(
    tmp_path: Path,
) -> None:
    observed_database_url: list[str] = []

    async def docker_ready() -> object:
        return object()

    async def database_ready(settings: Settings) -> None:
        observed_database_url.append(settings.database_url_value)

    specification = PreflightSpecification(
        minimum_free_bytes=0,
        budget=_budget(),
    )
    database_url = "postgresql+psycopg://phase_m:private@db.invalid/harnesslab"
    report = await run_preflight(
        specification,
        tmp_path,
        {"DATABASE_URL": database_url},
        docker_check=docker_ready,
        database_check=database_ready,
    )

    assert report.status is PreflightStatus.READY
    assert observed_database_url == [database_url]
    assert "private" not in report.model_dump_json()
    assert report.provider_calls == report.judge_calls == 0


async def test_runtime_collector_validates_url_configuration_without_echoing_value(
    tmp_path: Path,
) -> None:
    invalid_value = "http://user:private@unsafe.invalid/path"
    specification = PreflightSpecification(
        docker_required=False,
        database_required=False,
        minimum_free_bytes=0,
        configurations=(
            ConfigurationRequirement(
                reference="PHASE_M_BASE_URL",
                kind=ConfigurationKind.HTTPS_URL,
            ),
        ),
        budget=_budget(),
    )

    report = await run_preflight(
        specification,
        tmp_path,
        {"PHASE_M_BASE_URL": invalid_value},
    )

    assert report.status is PreflightStatus.BLOCKED
    assert "CONFIGURATION_INVALID" in {item.reason_code for item in report.findings}
    assert invalid_value not in report.model_dump_json()
