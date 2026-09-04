from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import TypedDict

import pytest
from pydantic import ValidationError

from harnesslab.budget.models import PricingAvailability, ProviderPricing
from harnesslab.budget.plan import (
    PhaseMResourceDimension,
    PlanBudgetError,
    PlanBudgetReasonCode,
    PlanCellBudget,
    build_plan_budget_request,
    estimate_plan_budget,
)
from harnesslab.budget.reservation import (
    BudgetReservationRequest,
    InMemoryBudgetReservationStore,
    ReservationDecision,
    ReservationReasonCode,
    ReservationScope,
    ReservationUnit,
    ResourceAmounts,
    build_reservation_request,
    reservation_units_for_plan,
)
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane
from harnesslab.evaluation_suites.admission import GovernanceNamespace
from harnesslab.evaluation_suites.models import ImmutableArtifactReference
from harnesslab.experiment.funnel_plan import build_funnel_v3_experiment_plan
from harnesslab.experiment.funnel_v3 import (
    DecisionActorAuthorization,
    FunnelMethodologyV3,
    FunnelV3Stage,
    StageDecisionValue,
    build_funnel_v3_methodology,
    build_stage_decision,
)
from harnesslab.experiment.methodology import (
    BudgetContract,
    BudgetDimension,
    BudgetDimensionStatus,
    BudgetScope,
)
from harnesslab.experiment.plan import ExperimentPlan, build_experiment_plan
from harnesslab.experiment.spec import ExperimentSpec
from harnesslab.preflight.models import PreflightObservations, TaskObservation
from harnesslab.preflight.unified import (
    CheckDecision,
    LocalImageIdentity,
    NormalizedCheckId,
    UnifiedPreflightError,
    UnifiedPreflightObservations,
    UnifiedPreflightReceipt,
    UnifiedPreflightSpecification,
    UnifiedPreflightStatus,
    assess_unified_preflight,
    build_runtime_selection,
    build_unified_preflight_specification,
    guard_pre_execution,
    stage_zero_evidence_from_receipt,
)
from tests.phase_g_helpers import ROOT, basic_spec, identity


class M5Fixture(TypedDict):
    spec: ExperimentSpec
    plan: ExperimentPlan
    cell_budgets: tuple[PlanCellBudget, ...]
    methodology: FunnelMethodologyV3
    unified: UnifiedPreflightSpecification
    observations: UnifiedPreflightObservations


def _dimension(
    value: int | float | None,
    unit: str,
    *,
    status: BudgetDimensionStatus = BudgetDimensionStatus.ENFORCED,
    stage: bool = False,
) -> BudgetDimension:
    scope = (
        BudgetScope.NOT_AVAILABLE
        if status is BudgetDimensionStatus.NOT_AVAILABLE
        else BudgetScope.OBSERVED_ONLY
        if status is BudgetDimensionStatus.OBSERVED_ONLY
        else BudgetScope.PER_STAGE
        if stage
        else BudgetScope.PER_LOGICAL_RUN
    )
    return BudgetDimension(status=status, value=value, unit=unit, scopes=(scope,))


def _contract(*, stage: bool = False, cost: int | float = 1) -> BudgetContract:
    multiplier = 10 if stage else 1
    return BudgetContract(
        max_wall_time=_dimension(10 * multiplier, "seconds", stage=stage),
        max_output_tokens=_dimension(100 * multiplier, "tokens", stage=stage),
        max_model_turns=_dimension(1 * multiplier, "turns", stage=stage),
        max_tool_calls=_dimension(2 * multiplier, "calls", stage=stage),
        max_provider_requests=_dimension(1 * multiplier, "requests", stage=stage),
        max_cost=_dimension(cost, "USD", stage=stage),
    )


def _artifact(label: str) -> ImmutableArtifactReference:
    return ImmutableArtifactReference(
        artifact_id=label,
        schema_version=1,
        artifact_digest=canonical_digest({"m5": label}),
    )


def _fixture(
    *,
    unknown_pricing: bool = False,
    stage_cost: float = 1,
    formal_comparability_required: bool = False,
    experiment_id: str = "phase-g-test",
) -> M5Fixture:
    per_slot = _contract()
    base = basic_spec(repeat_count=1).model_copy(update={"experiment_id": experiment_id})
    cells = tuple(
        cell.model_copy(
            update={
                "provider_route": "local|custom|https://provider.invalid/v1",
                "resource_envelope_identity": per_slot.identity,
            }
        )
        for cell in base.cells
    )
    spec = base.model_copy(update={"cells": cells})
    plan = build_experiment_plan(spec, ROOT)
    pricing = (
        ProviderPricing(
            route_identity=cells[0].provider_route,
            availability=PricingAvailability.UNKNOWN,
        )
        if unknown_pricing
        else ProviderPricing(
            route_identity=cells[0].provider_route,
            availability=PricingAvailability.KNOWN,
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("1"),
            request_usd=Decimal("0.01"),
            evidence_reference="pricing-2026-09-04",
        )
    )
    cell_budgets = tuple(
        PlanCellBudget(
            cell_id=cell.id,
            resource_envelope_identity=per_slot.identity,
            per_slot_budget=per_slot,
            input_token_ceiling=100,
            pricing=pricing,
            pricing_evidence=None if unknown_pricing else _artifact("pricing-snapshot"),
        )
        for cell in plan.cells
    )
    selections = tuple(
        build_runtime_selection(
            cell_id=cell.id,
            provider_route=cell.provider_route,
            provider_profile_identity=cell.profile_identity,
            route_configuration_identity=identity(f"route-config:{cell.id}"),
            credential_references=(),
            requires_network=False,
            harness_id=cell.harness,
            harness_version=cell.harness_version,
            harness_config_identity=cell.harness_config_identity,
            requested_model=cell.requested_model,
            supported_lanes=frozenset({cell.lane}),
            compatible_models=frozenset({cell.requested_model}),
            required_capabilities=frozenset({"final-output"}),
            resource_envelope_identity=per_slot.identity,
        )
        for cell in plan.cells
    )
    methodology = build_funnel_v3_methodology()
    unified = build_unified_preflight_specification(
        specification_id="m5-preflight",
        experiment_spec=spec,
        existing_plan=plan,
        repository_root=ROOT,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
        runtime_selections=selections,
        stage_budget=_contract(stage=True, cost=stage_cost),
        cell_budgets=cell_budgets,
        fixed_disk_bytes=1000,
        disk_bytes_per_slot=100,
        formal_comparability_required=formal_comparability_required,
    )
    local = PreflightObservations(
        docker_available=True,
        database_ready=True,
        disk_free_bytes=1200,
        harness_runtime_available={cell.id: True for cell in plan.cells},
        tasks={
            task.package_path: TaskObservation(
                valid=True,
                supported_lanes=frozenset({EvaluationLane.MODEL, EvaluationLane.HARNESS}),
            )
            for task in plan.tasks
        },
    )
    observations = UnifiedPreflightObservations(
        local=local,
        database_schema_ready=True,
        route_configuration_identities={
            item.cell_id: item.route_configuration_identity for item in selections
        },
        harness_runtime_selection_identities={
            item.cell_id: item.selection_digest for item in selections
        },
        harness_capabilities={cell.id: frozenset({"final-output"}) for cell in plan.cells},
        task_validation_identities={
            task.package_path: canonical_digest(task.model_dump(mode="json")) for task in plan.tasks
        },
        comparability_controls_match=True,
    )
    return {
        "spec": spec,
        "plan": plan,
        "cell_budgets": cell_budgets,
        "methodology": methodology,
        "unified": unified,
        "observations": observations,
    }


def _ready() -> tuple[M5Fixture, UnifiedPreflightReceipt]:
    fixture = _fixture()
    receipt = assess_unified_preflight(fixture["unified"], fixture["observations"])
    assert receipt.status is UnifiedPreflightStatus.READY
    return fixture, receipt


def _store(
    fixture: M5Fixture,
    receipt: UnifiedPreflightReceipt,
    *,
    consumed_totals: ResourceAmounts | None = None,
) -> tuple[InMemoryBudgetReservationStore, tuple[ReservationUnit, ...]]:
    plan = fixture["plan"]
    budgets = fixture["cell_budgets"]
    units = reservation_units_for_plan(plan, budgets)
    store = InMemoryBudgetReservationStore(
        estimate=receipt.budget_estimate,
        stage=FunnelV3Stage.SMOKE,
        scope=ReservationScope.STAGE,
        scope_id="smoke-campaign",
        units=units,
        consumed_totals=consumed_totals,
    )
    return store, units


def _request(
    receipt: UnifiedPreflightReceipt,
    unit: ReservationUnit,
    request_id: str = "reserve-one",
) -> BudgetReservationRequest:
    return build_reservation_request(
        request_id=request_id,
        plan=receipt.candidate_plan,
        stage=FunnelV3Stage.SMOKE,
        scope=ReservationScope.STAGE,
        scope_id="smoke-campaign",
        unit=unit,
        budget_estimate=receipt.budget_estimate,
    )


def test_ready_receipt_is_deterministic_complete_and_keyless() -> None:
    fixture, receipt = _ready()
    repeated = assess_unified_preflight(fixture["unified"], fixture["observations"])
    assert receipt == repeated
    assert tuple(item.check_id for item in receipt.checks) == tuple(NormalizedCheckId)
    assert receipt.provider_live_availability == "NOT_PROBED"
    call_counts = (
        receipt.provider_calls,
        receipt.harness_calls,
        receipt.judge_calls,
        receipt.matrix_calls,
    )
    assert call_counts == (
        0,
        0,
        0,
        0,
    )
    assert receipt.automatic_stage_decision is False
    assert receipt.external_execution_authorized is False
    assert "sk-test" not in receipt.model_dump_json().lower()


def test_specification_is_plan_derived_and_disk_scales_per_slot() -> None:
    fixture, _ = _ready()
    unified = fixture["unified"]
    assert unified.prerequisites.minimum_free_bytes == 1000 + 100 * len(unified.base_plan.run_slots)
    assert unified.candidate_plan.artifact_digest == unified.base_plan.digest
    assert unified.target_material.methodology == unified.methodology


def test_existing_plan_drift_fails_before_receipt() -> None:
    fixture = _fixture()
    stale = fixture["plan"].model_copy(update={"execution_seed": 99})
    with pytest.raises(UnifiedPreflightError, match="exact expansion"):
        build_unified_preflight_specification(
            specification_id="drift",
            experiment_spec=fixture["spec"],
            existing_plan=stale,
            repository_root=ROOT,
            methodology=fixture["methodology"],
            namespace=GovernanceNamespace.OFFICIAL,
            runtime_selections=fixture["unified"].runtime_selections,
            stage_budget=_contract(stage=True),
            cell_budgets=fixture["cell_budgets"],
            fixed_disk_bytes=1,
            disk_bytes_per_slot=1,
        )


def test_runtime_selection_drift_is_rejected() -> None:
    fixture = _fixture()
    unified = fixture["unified"]
    selection = unified.runtime_selections[0]
    drifted_payload = selection.payload()
    drifted_payload["requested_model"] = "substituted-model"
    drifted = build_runtime_selection(**drifted_payload)
    payload = unified.payload()
    payload["runtime_selections"][0] = drifted.model_dump(mode="json")
    payload["specification_digest"] = canonical_digest(payload)
    with pytest.raises(ValidationError, match="exact planned cell"):
        type(unified).model_validate(payload)


@pytest.mark.parametrize(
    ("field", "check_id"),
    [
        ("docker_available", NormalizedCheckId.DOCKER_RUNTIME),
        ("database_ready", NormalizedCheckId.DATABASE_SCHEMA),
        ("disk_free_bytes", NormalizedCheckId.DISK_CAPACITY),
    ],
)
def test_local_failures_block_normalized_check(field: str, check_id: NormalizedCheckId) -> None:
    fixture = _fixture()
    observations = fixture["observations"]
    value = 0 if field == "disk_free_bytes" else False
    local = observations.local.model_copy(update={field: value})
    receipt = assess_unified_preflight(
        fixture["unified"], observations.model_copy(update={"local": local})
    )
    check = next(item for item in receipt.checks if item.check_id is check_id)
    assert receipt.status is UnifiedPreflightStatus.BLOCKED
    assert check.decision is CheckDecision.BLOCKED


def test_task_lane_and_harness_capability_fail_closed() -> None:
    fixture = _fixture()
    observations = fixture["observations"]
    task_path = fixture["plan"].tasks[0].package_path
    local = observations.local.model_copy(
        update={
            "tasks": {
                task_path: TaskObservation(
                    valid=True, supported_lanes=frozenset({EvaluationLane.MODEL})
                )
            }
        }
    )
    changed = observations.model_copy(update={"local": local, "harness_capabilities": {}})
    receipt = assess_unified_preflight(fixture["unified"], changed)
    blocked = {item.check_id for item in receipt.checks if item.decision is CheckDecision.BLOCKED}
    assert NormalizedCheckId.LANE_SUPPORT in blocked
    assert NormalizedCheckId.HARNESS_RUNTIME_CAPABILITIES in blocked


def test_comparability_drift_blocks() -> None:
    fixture = _fixture(formal_comparability_required=True)
    observations = fixture["observations"].model_copy(
        update={"comparability_controls_match": False}
    )
    receipt = assess_unified_preflight(fixture["unified"], observations)
    check = next(
        item for item in receipt.checks if item.check_id is NormalizedCheckId.COMPARABILITY_RISK
    )
    assert check.decision is CheckDecision.BLOCKED


def test_network_policy_conflict_blocks_without_provider_probe() -> None:
    fixture = _fixture()
    unified = fixture["unified"]
    first = unified.runtime_selections[0]
    changed_payload = first.payload()
    changed_payload["requires_network"] = True
    changed = build_runtime_selection(**changed_payload)
    rebuilt = build_unified_preflight_specification(
        specification_id="network-conflict",
        experiment_spec=fixture["spec"],
        existing_plan=fixture["plan"],
        repository_root=ROOT,
        methodology=fixture["methodology"],
        namespace=GovernanceNamespace.OFFICIAL,
        runtime_selections=(changed, *unified.runtime_selections[1:]),
        stage_budget=_contract(stage=True),
        cell_budgets=fixture["cell_budgets"],
        fixed_disk_bytes=1000,
        disk_bytes_per_slot=100,
    )
    receipt = assess_unified_preflight(rebuilt, fixture["observations"])
    check = next(
        item for item in receipt.checks if item.check_id is NormalizedCheckId.NETWORK_POLICY
    )
    assert check.decision is CheckDecision.BLOCKED
    assert receipt.provider_calls == 0


def test_credential_value_never_enters_receipt() -> None:
    fixture = _fixture()
    unified = fixture["unified"]
    first = unified.runtime_selections[0]
    selected_payload = first.payload()
    selected_payload["credential_references"] = ("M5_API_KEY",)
    selected = build_runtime_selection(**selected_payload)
    rebuilt = build_unified_preflight_specification(
        specification_id="credential-reference",
        experiment_spec=fixture["spec"],
        existing_plan=fixture["plan"],
        repository_root=ROOT,
        methodology=fixture["methodology"],
        namespace=GovernanceNamespace.OFFICIAL,
        runtime_selections=(selected, *unified.runtime_selections[1:]),
        stage_budget=_contract(stage=True),
        cell_budgets=fixture["cell_budgets"],
        fixed_disk_bytes=1000,
        disk_bytes_per_slot=100,
    )
    secret = "sk-test-super-secret-material"
    local = fixture["observations"].local.model_copy(
        update={
            "configuration_present": {"M5_API_KEY": True},
            "configuration_valid": {"M5_API_KEY": True},
        }
    )
    receipt = assess_unified_preflight(
        rebuilt,
        fixture["observations"].model_copy(
            update={
                "local": local,
                "harness_runtime_selection_identities": {
                    **fixture["observations"].harness_runtime_selection_identities,
                    selected.cell_id: selected.selection_digest,
                },
            }
        ),
    )
    assert receipt.status is UnifiedPreflightStatus.READY
    assert secret not in receipt.model_dump_json()


def test_local_image_identity_and_platform_are_exact() -> None:
    fixture = _fixture()
    unified = fixture["unified"]
    expected = LocalImageIdentity(
        reference="runner@sha256:abcd",
        image_digest=canonical_digest({"image": "runner"}),
        platform="linux/amd64",
    )
    first = unified.runtime_selections[0]
    selected_payload = first.payload()
    selected_payload["image"] = expected
    selected = build_runtime_selection(**selected_payload)
    selections = (selected, *unified.runtime_selections[1:])
    rebuilt = build_unified_preflight_specification(
        specification_id="image-bound",
        experiment_spec=fixture["spec"],
        existing_plan=fixture["plan"],
        repository_root=ROOT,
        methodology=fixture["methodology"],
        namespace=GovernanceNamespace.OFFICIAL,
        runtime_selections=selections,
        stage_budget=_contract(stage=True),
        cell_budgets=fixture["cell_budgets"],
        fixed_disk_bytes=1000,
        disk_bytes_per_slot=100,
    )
    local = fixture["observations"].local.model_copy(
        update={"image_available": {expected.reference: True}}
    )
    wrong = expected.model_copy(update={"platform": "linux/arm64"})
    receipt = assess_unified_preflight(
        rebuilt,
        fixture["observations"].model_copy(update={"local": local, "local_images": (wrong,)}),
    )
    assert receipt.status is UnifiedPreflightStatus.BLOCKED


def test_budget_contains_six_dimensions_and_input_projection() -> None:
    fixture, receipt = _ready()
    assert tuple(item.dimension for item in receipt.budget_estimate.dimensions) == tuple(
        PhaseMResourceDimension
    )
    assert receipt.budget_estimate.input_token_projection == 200
    assert receipt.budget_estimate.logical_slot_count == len(fixture["plan"].run_slots)


def test_unknown_price_is_not_zero_and_blocks_enforced_cost() -> None:
    fixture = _fixture(unknown_pricing=True)
    receipt = assess_unified_preflight(fixture["unified"], fixture["observations"])
    cost = next(
        item
        for item in receipt.budget_estimate.dimensions
        if item.dimension is PhaseMResourceDimension.MONETARY_COST
    )
    assert cost.estimated_maximum is None
    assert PlanBudgetReasonCode.ENFORCED_COST_PRICING_UNKNOWN in (
        receipt.budget_estimate.reason_codes
    )
    assert receipt.status is UnifiedPreflightStatus.BLOCKED


def test_budget_preserves_observed_only_and_not_available() -> None:
    fixture = _fixture()
    request = fixture["unified"].budget_request
    stage = request.stage_budget.model_copy(
        update={
            "max_tool_calls": _dimension(
                20, "calls", status=BudgetDimensionStatus.OBSERVED_ONLY, stage=True
            ),
            "max_model_turns": _dimension(
                None, "turns", status=BudgetDimensionStatus.NOT_AVAILABLE, stage=True
            ),
        }
    )
    changed = request.model_copy(
        update={"stage_budget": stage, "request_digest": canonical_digest({})}
    )
    payload = changed.model_dump(mode="json", exclude={"request_digest"})
    payload["request_digest"] = canonical_digest(payload)
    estimate = estimate_plan_budget(type(request).model_validate(payload), fixture["plan"])
    by_dimension = {item.dimension: item for item in estimate.dimensions}
    assert (
        by_dimension[PhaseMResourceDimension.TOOL_CALLS].enforcement_status
        is BudgetDimensionStatus.OBSERVED_ONLY
    )
    assert (
        by_dimension[PhaseMResourceDimension.MODEL_TURNS].enforcement_status
        is BudgetDimensionStatus.NOT_AVAILABLE
    )


def test_budget_request_rejects_plan_digest_drift() -> None:
    fixture = _fixture()
    stale = fixture["plan"].model_copy(update={"execution_seed": 101})
    with pytest.raises(PlanBudgetError, match="candidate plan"):
        estimate_plan_budget(fixture["unified"].budget_request, stale)


def test_reservation_accepts_exact_unit_and_is_idempotent() -> None:
    fixture, receipt = _ready()
    store, units = _store(fixture, receipt)
    request = _request(receipt, units[0])
    first = store.reserve(request)
    repeated = store.reserve(request)
    assert first == repeated
    assert first.decision is ReservationDecision.ACCEPTED
    assert first.durable is False
    assert store.reserved_totals == first.reserved_after


def test_campaign_scope_is_explicit_and_enforced() -> None:
    fixture = _fixture()
    unified = fixture["unified"]
    stage_budget = unified.budget_request.stage_budget
    campaign_budget = BudgetContract(
        **{
            name: dimension.model_copy(update={"scopes": (BudgetScope.PER_CAMPAIGN,)})
            for name, dimension in stage_budget
        }
    )
    request = build_plan_budget_request(
        request_id="campaign-estimate",
        plan=fixture["plan"],
        target_stage=FunnelV3Stage.SMOKE,
        material_identity=unified.target_material,
        stage_budget=campaign_budget,
        cell_budgets=fixture["cell_budgets"],
        ceiling_scope=BudgetScope.PER_CAMPAIGN,
    )
    estimate = estimate_plan_budget(request, fixture["plan"])
    units = reservation_units_for_plan(fixture["plan"], fixture["cell_budgets"])
    store = InMemoryBudgetReservationStore(
        estimate=estimate,
        stage=FunnelV3Stage.SMOKE,
        scope=ReservationScope.CAMPAIGN,
        scope_id="campaign",
        units=units,
    )
    reservation = build_reservation_request(
        request_id="campaign-unit",
        plan=estimate.candidate_plan,
        stage=FunnelV3Stage.SMOKE,
        scope=ReservationScope.CAMPAIGN,
        scope_id="campaign",
        unit=units[0],
        budget_estimate=estimate,
    )
    assert store.reserve(reservation).decision is ReservationDecision.ACCEPTED


def test_duplicate_unit_with_different_request_is_denied_without_mutation() -> None:
    fixture, receipt = _ready()
    store, units = _store(fixture, receipt)
    accepted = store.reserve(_request(receipt, units[0]))
    denied = store.reserve(_request(receipt, units[0], "reserve-same-unit-again"))
    assert denied.decision is ReservationDecision.DENIED
    assert denied.reason_code is ReservationReasonCode.DUPLICATE_LOGICAL_UNIT_MISMATCH
    assert denied.reserved_before == denied.reserved_after == accepted.reserved_after


def test_reservation_accounts_consumed_and_denies_overspend_without_mutation() -> None:
    fixture, receipt = _ready()
    consumed = ResourceAmounts(
        wall_time_seconds=95,
        output_tokens=0,
        model_turns=0,
        tool_calls=0,
        provider_requests=0,
        monetary_cost_usd=0,
    )
    store, units = _store(fixture, receipt, consumed_totals=consumed)
    denied = store.reserve(_request(receipt, units[0]))
    assert denied.decision is ReservationDecision.DENIED
    assert denied.reason_code is ReservationReasonCode.ENFORCED_CEILING_WOULD_BE_EXCEEDED
    assert denied.reserved_before == denied.reserved_after == ResourceAmounts.zero()


def test_wrong_plan_and_wrong_unit_are_denied() -> None:
    fixture, receipt = _ready()
    store, units = _store(fixture, receipt)
    request = _request(receipt, units[0])
    wrong_plan = request.model_copy(
        update={"plan": _artifact("other-plan"), "request_digest": canonical_digest({})}
    )
    payload = wrong_plan.model_dump(mode="json", exclude={"request_digest"})
    payload["request_digest"] = canonical_digest(payload)
    denial = store.reserve(type(request).model_validate(payload))
    assert denial.reason_code is ReservationReasonCode.PLAN_IDENTITY_MISMATCH
    wrong_unit = request.model_copy(
        update={"logical_unit_id": identity("unknown-slot"), "request_digest": canonical_digest({})}
    )
    payload = wrong_unit.model_dump(mode="json", exclude={"request_digest"})
    payload["request_digest"] = canonical_digest(payload)
    denial = store.reserve(type(request).model_validate(payload))
    assert denial.reason_code is ReservationReasonCode.LOGICAL_UNIT_UNKNOWN


def test_concurrent_requests_cannot_overspend() -> None:
    fixture, receipt = _ready()
    consumed = ResourceAmounts(
        wall_time_seconds=85,
        output_tokens=0,
        model_turns=0,
        tool_calls=0,
        provider_requests=0,
        monetary_cost_usd=0,
    )
    store, units = _store(fixture, receipt, consumed_totals=consumed)
    requests = tuple(
        _request(receipt, unit, f"concurrent-{index}") for index, unit in enumerate(units)
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = tuple(executor.map(store.reserve, requests))
    assert sum(item.decision is ReservationDecision.ACCEPTED for item in decisions) == 1
    assert sum(item.decision is ReservationDecision.DENIED for item in decisions) == 1
    assert store.reserved_totals.wall_time_seconds == 10


def test_guard_requires_ready_exact_receipt_and_accepted_reservation() -> None:
    fixture, receipt = _ready()
    store, units = _store(fixture, receipt)
    reservation = store.reserve(_request(receipt, units[0]))
    result = guard_pre_execution(
        receipt=receipt,
        specification=fixture["unified"],
        budget_estimate=receipt.budget_estimate,
        reservation=reservation,
        logical_unit_id=units[0].logical_unit_id,
    )
    assert result.eligible is True
    assert result.execution_started is False
    with pytest.raises(UnifiedPreflightError, match="reservation"):
        guard_pre_execution(
            receipt=receipt,
            specification=fixture["unified"],
            budget_estimate=receipt.budget_estimate,
            reservation=reservation,
            logical_unit_id=units[1].logical_unit_id,
        )


def test_guard_rejects_stale_receipt_and_denied_reservation() -> None:
    fixture, receipt = _ready()
    store, units = _store(
        fixture,
        receipt,
        consumed_totals=ResourceAmounts(
            wall_time_seconds=95,
            output_tokens=0,
            model_turns=0,
            tool_calls=0,
            provider_requests=0,
            monetary_cost_usd=0,
        ),
    )
    denied = store.reserve(_request(receipt, units[0]))
    with pytest.raises(UnifiedPreflightError, match="accepted exact-plan reservation"):
        guard_pre_execution(
            receipt=receipt,
            specification=fixture["unified"],
            budget_estimate=receipt.budget_estimate,
            reservation=denied,
            logical_unit_id=units[0].logical_unit_id,
        )
    stale_spec = fixture["unified"].model_copy(
        update={
            "formal_comparability_required": True,
            "specification_digest": canonical_digest({"stale": True}),
        }
    )
    accepted_store, accepted_units = _store(fixture, receipt)
    accepted = accepted_store.reserve(_request(receipt, accepted_units[0]))
    drifted_budget = receipt.budget_estimate.model_copy(
        update={"estimate_digest": identity("drifted-budget")}
    )
    with pytest.raises(UnifiedPreflightError, match="receipt drifted"):
        guard_pre_execution(
            receipt=receipt,
            specification=fixture["unified"],
            budget_estimate=drifted_budget,
            reservation=accepted,
            logical_unit_id=accepted_units[0].logical_unit_id,
        )
    with pytest.raises(UnifiedPreflightError, match="receipt drifted"):
        guard_pre_execution(
            receipt=receipt,
            specification=stale_spec,
            budget_estimate=receipt.budget_estimate,
            reservation=accepted,
            logical_unit_id=accepted_units[0].logical_unit_id,
        )


def test_ready_receipt_adapts_to_m4_evidence_but_not_go() -> None:
    fixture, receipt = _ready()
    evidence = stage_zero_evidence_from_receipt(receipt, evidence_id="m5-stage-zero")
    assert evidence.stage is FunnelV3Stage.PREFLIGHT
    assert evidence.budget_preflight.preflight_passed is True
    assert evidence.source_report == receipt.as_reference()
    actor = DecisionActorAuthorization(
        actor_id="operator",
        actor_identity=identity("operator"),
        decision_authorization_identity=identity("operator-stage-decision"),
    )
    decision = build_stage_decision(
        decision_id="m5-explicit-go",
        decision=StageDecisionValue.GO,
        source_evidence=evidence,
        target_stage=FunnelV3Stage.SMOKE,
        target_material_identity=receipt.target_material,
        methodology=fixture["methodology"],
        actor_authorization=actor,
    )
    stage_one = build_funnel_v3_experiment_plan(
        fixture["spec"],
        ROOT,
        stage=FunnelV3Stage.SMOKE,
        methodology=fixture["methodology"],
        namespace=GovernanceNamespace.OFFICIAL,
        entry_decision=decision,
    )
    assert decision.external_execution_authorized is False
    assert stage_one.external_execution_authorized is False
    assert stage_one.base_plan.digest == fixture["plan"].digest
    assert decision == build_stage_decision(
        decision_id="m5-explicit-go",
        decision=StageDecisionValue.GO,
        source_evidence=evidence,
        target_stage=FunnelV3Stage.SMOKE,
        target_material_identity=receipt.target_material,
        methodology=fixture["methodology"],
        actor_authorization=actor,
    )


def test_unknown_fields_are_rejected_and_receipt_json_is_canonical() -> None:
    _, receipt = _ready()
    with pytest.raises(ValidationError):
        type(receipt).model_validate({**receipt.model_dump(mode="json"), "unknown": True})
    assert receipt == type(receipt).model_validate_json(receipt.model_dump_json())
    assert json.loads(receipt.model_dump_json())["status"] == "READY"


def test_frozen_methodology_evidence_hash_is_unchanged() -> None:
    payload = (ROOT / "release" / "evaluation-methodology-v2.json").read_bytes()
    assert hashlib.sha256(payload).hexdigest() == (
        "13f9f544c2d52c4b63da801c40a677a018b999fed33d914eb24b3563bc69de6a"
    )
