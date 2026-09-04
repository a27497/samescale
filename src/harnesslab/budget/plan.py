from __future__ import annotations

import json
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.budget.models import PricingAvailability, ProviderPricing
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.evaluation_suites.models import ImmutableArtifactReference
from harnesslab.experiment.funnel_v3 import FunnelV3Stage, StageMaterialIdentity
from harnesslab.experiment.methodology import (
    BudgetContract,
    BudgetDimension,
    BudgetDimensionStatus,
    BudgetScope,
)
from harnesslab.experiment.plan import ExperimentPlan


class PlanBudgetError(ValueError):
    """Plan-derived resource estimation is incomplete, stale, or unsafe."""


class PhaseMResourceDimension(StrEnum):
    WALL_TIME = "WALL_TIME"
    OUTPUT_TOKENS = "OUTPUT_TOKENS"
    MODEL_TURNS = "MODEL_TURNS"
    TOOL_CALLS = "TOOL_CALLS"
    PROVIDER_REQUESTS = "PROVIDER_REQUESTS"
    MONETARY_COST = "MONETARY_COST"


class PlanBudgetStatus(StrEnum):
    SAFE = "SAFE"
    BLOCKED = "BLOCKED"


class PlanBudgetReasonCode(StrEnum):
    ALL_ENFORCED_DIMENSIONS_WITHIN_CEILING = "ALL_ENFORCED_DIMENSIONS_WITHIN_CEILING"
    ENFORCED_DIMENSION_EXCEEDS_CEILING = "ENFORCED_DIMENSION_EXCEEDS_CEILING"
    ENFORCED_DIMENSION_UNAVAILABLE = "ENFORCED_DIMENSION_UNAVAILABLE"
    ENFORCED_COST_PRICING_UNKNOWN = "ENFORCED_COST_PRICING_UNKNOWN"
    PRICING_EVIDENCE_MISSING = "PRICING_EVIDENCE_MISSING"
    UNIT_ENVELOPE_MISMATCH = "UNIT_ENVELOPE_MISMATCH"


class PlanCellBudget(BaseModel):
    """Frozen per-logical-slot maximum for one exact planned cell."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cell_id: Identifier
    resource_envelope_identity: Sha256Digest
    per_slot_budget: BudgetContract
    input_token_ceiling: int = Field(ge=0)
    pricing: ProviderPricing
    pricing_evidence: ImmutableArtifactReference | None = None

    @model_validator(mode="after")
    def pricing_is_evidence_bound(self) -> PlanCellBudget:
        for _, attribute, _ in _DIMENSIONS:
            dimension: BudgetDimension = getattr(self.per_slot_budget, attribute)
            if dimension.scopes is None:
                raise ValueError("M.5 per-slot dimensions require explicit scopes")
            if dimension.status is BudgetDimensionStatus.ENFORCED and (
                BudgetScope.PER_LOGICAL_RUN not in dimension.scopes
            ):
                raise ValueError("enforced per-slot dimensions require PER_LOGICAL_RUN scope")
        if self.pricing.availability is PricingAvailability.KNOWN:
            if self.pricing_evidence is None:
                raise ValueError("known pricing requires immutable pricing evidence")
        elif self.pricing_evidence is not None:
            raise ValueError("unknown pricing cannot claim immutable price evidence")
        return self


class PlanBudgetEstimateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    request_id: Identifier
    candidate_plan: ImmutableArtifactReference
    target_stage: FunnelV3Stage
    material_identity: StageMaterialIdentity
    ceiling_scope: Literal[BudgetScope.PER_STAGE, BudgetScope.PER_CAMPAIGN]
    stage_budget: BudgetContract
    cell_budgets: tuple[PlanCellBudget, ...]
    request_digest: Sha256Digest

    @model_validator(mode="after")
    def request_is_canonical_and_self_identifying(self) -> PlanBudgetEstimateRequest:
        ordered = tuple(sorted(self.cell_budgets, key=lambda item: item.cell_id))
        if self.cell_budgets != ordered or len({item.cell_id for item in ordered}) != len(ordered):
            raise ValueError("plan cell budgets must be unique and canonical")
        for _, attribute, _ in _DIMENSIONS:
            dimension: BudgetDimension = getattr(self.stage_budget, attribute)
            if dimension.scopes is None:
                raise ValueError("M.5 plan ceilings require explicit scopes")
            if dimension.status is BudgetDimensionStatus.ENFORCED and (
                self.ceiling_scope not in dimension.scopes
            ):
                raise ValueError("enforced plan ceilings require the exact declared scope")
        if self.request_digest != canonical_digest(self.payload()):
            raise ValueError("plan budget request digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"request_digest"})


class PlanBudgetDimensionEstimate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: PhaseMResourceDimension
    enforcement_status: BudgetDimensionStatus
    estimated_maximum: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    ceiling: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=40)
    within_ceiling: bool | None

    @model_validator(mode="after")
    def status_is_truthful(self) -> PlanBudgetDimensionEstimate:
        if self.enforcement_status is BudgetDimensionStatus.ENFORCED:
            if self.ceiling is None:
                raise ValueError("enforced plan budget dimension requires a ceiling")
            if self.within_ceiling != (
                self.estimated_maximum is not None and self.estimated_maximum <= self.ceiling
            ):
                raise ValueError("enforced dimension decision does not match estimate and ceiling")
        elif self.within_ceiling is not None:
            raise ValueError("non-enforced dimension cannot claim ceiling enforcement")
        if self.enforcement_status is BudgetDimensionStatus.NOT_AVAILABLE and (
            self.ceiling is not None
        ):
            raise ValueError("NOT_AVAILABLE dimension cannot contain a ceiling")
        return self


class PlanBudgetEstimate(BaseModel):
    """Six-dimensional conservative estimate, distinct from reservation and actual usage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    estimate_id: Identifier
    request_digest: Sha256Digest
    candidate_plan: ImmutableArtifactReference
    target_stage: FunnelV3Stage
    material_identity: StageMaterialIdentity
    ceiling_scope: Literal[BudgetScope.PER_STAGE, BudgetScope.PER_CAMPAIGN]
    stage_budget_identity: Sha256Digest
    logical_slot_count: int = Field(ge=1)
    cell_resource_envelope_identities: tuple[Sha256Digest, ...]
    dimensions: tuple[PlanBudgetDimensionEstimate, ...]
    input_token_projection: int = Field(ge=0)
    pricing_evidence: tuple[ImmutableArtifactReference, ...]
    status: PlanBudgetStatus
    reason_codes: tuple[PlanBudgetReasonCode, ...]
    estimate_digest: Sha256Digest

    @model_validator(mode="after")
    def estimate_is_complete_and_self_identifying(self) -> PlanBudgetEstimate:
        if tuple(item.dimension for item in self.dimensions) != tuple(PhaseMResourceDimension):
            raise ValueError("plan estimate must contain all six dimensions in canonical order")
        dimension_blocked = any(
            item.enforcement_status is BudgetDimensionStatus.ENFORCED
            and item.within_ceiling is not True
            for item in self.dimensions
        )
        reason_blocked = any(
            item is not PlanBudgetReasonCode.ALL_ENFORCED_DIMENSIONS_WITHIN_CEILING
            for item in self.reason_codes
        )
        if (self.status is PlanBudgetStatus.BLOCKED) != (dimension_blocked or reason_blocked):
            raise ValueError("plan budget status does not match enforced dimensions")
        if tuple(sorted(set(self.reason_codes), key=lambda item: item.value)) != self.reason_codes:
            raise ValueError("plan budget reasons must be unique and canonical")
        if (
            tuple(
                sorted(
                    set(self.pricing_evidence),
                    key=lambda item: (item.artifact_id, item.schema_version, item.artifact_digest),
                )
            )
            != self.pricing_evidence
        ):
            raise ValueError("pricing evidence references must be unique and canonical")
        if self.estimate_digest != canonical_digest(self.payload()):
            raise ValueError("plan budget estimate digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"estimate_digest"})

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def as_reference(self) -> ImmutableArtifactReference:
        return ImmutableArtifactReference(
            artifact_id=self.estimate_id,
            schema_version=self.schema_version,
            artifact_digest=self.estimate_digest,
        )


_DIMENSIONS: tuple[tuple[PhaseMResourceDimension, str, str], ...] = (
    (PhaseMResourceDimension.WALL_TIME, "max_wall_time", "seconds"),
    (PhaseMResourceDimension.OUTPUT_TOKENS, "max_output_tokens", "tokens"),
    (PhaseMResourceDimension.MODEL_TURNS, "max_model_turns", "turns"),
    (PhaseMResourceDimension.TOOL_CALLS, "max_tool_calls", "calls"),
    (PhaseMResourceDimension.PROVIDER_REQUESTS, "max_provider_requests", "requests"),
    (PhaseMResourceDimension.MONETARY_COST, "max_cost", "USD"),
)


def _decimal(value: int | float) -> Decimal:
    return Decimal(str(value))


def _known_unit_cost(cell: PlanCellBudget) -> Decimal | None:
    pricing = cell.pricing
    if pricing.availability is PricingAvailability.UNKNOWN:
        return None
    if (
        pricing.input_usd_per_million_tokens is None
        or pricing.output_usd_per_million_tokens is None
        or pricing.request_usd is None
    ):
        raise PlanBudgetError("known pricing is incomplete")
    output_value = cell.per_slot_budget.max_output_tokens.value
    requests_value = cell.per_slot_budget.max_provider_requests.value
    if output_value is None or requests_value is None:
        return None
    return (
        Decimal(cell.input_token_ceiling) * pricing.input_usd_per_million_tokens
        + _decimal(output_value) * pricing.output_usd_per_million_tokens
    ) / Decimal(1_000_000) + _decimal(requests_value) * pricing.request_usd


def build_plan_budget_request(
    *,
    request_id: str,
    plan: ExperimentPlan,
    target_stage: FunnelV3Stage,
    material_identity: StageMaterialIdentity,
    stage_budget: BudgetContract,
    cell_budgets: tuple[PlanCellBudget, ...],
    ceiling_scope: Literal[BudgetScope.PER_STAGE, BudgetScope.PER_CAMPAIGN] = BudgetScope.PER_STAGE,
) -> PlanBudgetEstimateRequest:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "request_id": request_id,
        "candidate_plan": {
            "artifact_id": plan.experiment_id,
            "schema_version": plan.schema_version,
            "artifact_digest": plan.digest,
        },
        "target_stage": target_stage.value,
        "material_identity": material_identity.model_dump(mode="json"),
        "ceiling_scope": ceiling_scope.value,
        "stage_budget": stage_budget.model_dump(mode="json"),
        "cell_budgets": [
            item.model_dump(mode="json")
            for item in sorted(cell_budgets, key=lambda item: item.cell_id)
        ],
    }
    payload["request_digest"] = canonical_digest(payload)
    return PlanBudgetEstimateRequest.model_validate(payload)


def _dimension_projection(
    plan: ExperimentPlan,
    cell_budgets: dict[str, PlanCellBudget],
    attribute: str,
) -> Decimal | None:
    total = Decimal(0)
    for slot in plan.run_slots:
        dimension: BudgetDimension = getattr(cell_budgets[slot.cell_id].per_slot_budget, attribute)
        if dimension.status is BudgetDimensionStatus.NOT_AVAILABLE or dimension.value is None:
            return None
        total += _decimal(dimension.value)
    return total


def estimate_plan_budget(
    request: PlanBudgetEstimateRequest,
    plan: ExperimentPlan,
) -> PlanBudgetEstimate:
    """Aggregate exact logical slots without performing pricing or provider network calls."""

    if request.candidate_plan.artifact_digest != plan.digest:
        raise PlanBudgetError("budget request candidate plan digest is stale or mismatched")
    cells = {cell.id: cell for cell in plan.cells}
    budgets = {item.cell_id: item for item in request.cell_budgets}
    if set(cells) != set(budgets):
        raise PlanBudgetError("every planned cell requires one exact resource budget")
    reasons: set[PlanBudgetReasonCode] = set()
    for cell_id, cell in cells.items():
        supplied = budgets[cell_id]
        if (
            cell.resource_envelope_identity is None
            or supplied.resource_envelope_identity != cell.resource_envelope_identity
            or supplied.per_slot_budget.identity != cell.resource_envelope_identity
            or supplied.pricing.route_identity != cell.provider_route
        ):
            reasons.add(PlanBudgetReasonCode.UNIT_ENVELOPE_MISMATCH)

    projections: dict[PhaseMResourceDimension, Decimal | None] = {}
    for dimension, attribute, _ in _DIMENSIONS[:-1]:
        projections[dimension] = _dimension_projection(plan, budgets, attribute)
    costs: list[Decimal] = []
    cost_unknown = False
    for slot in plan.run_slots:
        cost = _known_unit_cost(budgets[slot.cell_id])
        if cost is None:
            cost_unknown = True
        else:
            costs.append(cost)
    projections[PhaseMResourceDimension.MONETARY_COST] = (
        None if cost_unknown else sum(costs, Decimal(0))
    )

    dimension_results: list[PlanBudgetDimensionEstimate] = []
    for dimension, attribute, expected_unit in _DIMENSIONS:
        limit: BudgetDimension = getattr(request.stage_budget, attribute)
        if limit.unit != expected_unit:
            raise PlanBudgetError(f"{dimension.value} uses an unsupported unit")
        estimate = projections[dimension]
        ceiling = None if limit.value is None else _decimal(limit.value)
        within = None
        if limit.status is BudgetDimensionStatus.ENFORCED:
            within = estimate is not None and ceiling is not None and estimate <= ceiling
            if estimate is None:
                reasons.add(
                    PlanBudgetReasonCode.ENFORCED_COST_PRICING_UNKNOWN
                    if dimension is PhaseMResourceDimension.MONETARY_COST
                    else PlanBudgetReasonCode.ENFORCED_DIMENSION_UNAVAILABLE
                )
            elif not within:
                reasons.add(PlanBudgetReasonCode.ENFORCED_DIMENSION_EXCEEDS_CEILING)
        dimension_results.append(
            PlanBudgetDimensionEstimate(
                dimension=dimension,
                enforcement_status=limit.status,
                estimated_maximum=estimate,
                ceiling=ceiling,
                unit=expected_unit,
                within_ceiling=within,
            )
        )
    pricing_evidence = tuple(
        sorted(
            {
                item.pricing_evidence
                for item in request.cell_budgets
                if item.pricing_evidence is not None
            },
            key=lambda item: (item.artifact_id, item.schema_version, item.artifact_digest),
        )
    )
    if any(
        item.pricing.availability is PricingAvailability.KNOWN and item.pricing_evidence is None
        for item in request.cell_budgets
    ):
        reasons.add(PlanBudgetReasonCode.PRICING_EVIDENCE_MISSING)
    blocked = bool(reasons)
    if not blocked:
        reasons.add(PlanBudgetReasonCode.ALL_ENFORCED_DIMENSIONS_WITHIN_CEILING)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "estimate_id": f"plan-budget-{request.request_digest.removeprefix('sha256:')[:24]}",
        "request_digest": request.request_digest,
        "candidate_plan": request.candidate_plan.model_dump(mode="json"),
        "target_stage": request.target_stage.value,
        "material_identity": request.material_identity.model_dump(mode="json"),
        "ceiling_scope": request.ceiling_scope.value,
        "stage_budget_identity": request.stage_budget.identity,
        "logical_slot_count": len(plan.run_slots),
        "cell_resource_envelope_identities": sorted(
            item.resource_envelope_identity for item in request.cell_budgets
        ),
        "dimensions": [item.model_dump(mode="json") for item in dimension_results],
        "input_token_projection": sum(
            budgets[slot.cell_id].input_token_ceiling for slot in plan.run_slots
        ),
        "pricing_evidence": [item.model_dump(mode="json") for item in pricing_evidence],
        "status": PlanBudgetStatus.BLOCKED.value if blocked else PlanBudgetStatus.SAFE.value,
        "reason_codes": [item.value for item in sorted(reasons, key=lambda item: item.value)],
    }
    payload["estimate_digest"] = canonical_digest(payload)
    return PlanBudgetEstimate.model_validate(payload)


__all__ = [
    "PhaseMResourceDimension",
    "PlanBudgetDimensionEstimate",
    "PlanBudgetError",
    "PlanBudgetEstimate",
    "PlanBudgetEstimateRequest",
    "PlanBudgetReasonCode",
    "PlanBudgetStatus",
    "PlanCellBudget",
    "build_plan_budget_request",
    "estimate_plan_budget",
]
