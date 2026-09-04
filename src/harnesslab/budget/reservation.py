from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from threading import Lock
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.budget.plan import (
    PhaseMResourceDimension,
    PlanBudgetEstimate,
    PlanBudgetStatus,
    PlanCellBudget,
    _known_unit_cost,
)
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.evaluation_suites.models import ImmutableArtifactReference
from harnesslab.experiment.funnel_v3 import FunnelV3Stage
from harnesslab.experiment.methodology import BudgetDimensionStatus, BudgetScope
from harnesslab.experiment.plan import ExperimentPlan


class BudgetReservationError(ValueError):
    """Reservation inputs or receipt identities are inconsistent."""


class ReservationScope(StrEnum):
    STAGE = "STAGE"
    CAMPAIGN = "CAMPAIGN"


class ReservationDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    DENIED = "DENIED"


class ReservationReasonCode(StrEnum):
    WITHIN_ENFORCED_CEILING = "WITHIN_ENFORCED_CEILING"
    ENFORCED_CEILING_WOULD_BE_EXCEEDED = "ENFORCED_CEILING_WOULD_BE_EXCEEDED"
    ENFORCED_DIMENSION_UNAVAILABLE = "ENFORCED_DIMENSION_UNAVAILABLE"
    PLAN_IDENTITY_MISMATCH = "PLAN_IDENTITY_MISMATCH"
    STAGE_OR_SCOPE_MISMATCH = "STAGE_OR_SCOPE_MISMATCH"
    LOGICAL_UNIT_UNKNOWN = "LOGICAL_UNIT_UNKNOWN"
    UNIT_RESOURCE_ENVELOPE_MISMATCH = "UNIT_RESOURCE_ENVELOPE_MISMATCH"
    DUPLICATE_LOGICAL_UNIT_MISMATCH = "DUPLICATE_LOGICAL_UNIT_MISMATCH"
    PREFLIGHT_BUDGET_BLOCKED = "PREFLIGHT_BUDGET_BLOCKED"


class ResourceAmounts(BaseModel):
    """Maximum or total resources; None remains unavailable and is never coerced to zero."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    wall_time_seconds: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_tokens: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    model_turns: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    tool_calls: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    provider_requests: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    monetary_cost_usd: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)

    @classmethod
    def zero(cls) -> ResourceAmounts:
        return cls(
            wall_time_seconds=0,
            output_tokens=0,
            model_turns=0,
            tool_calls=0,
            provider_requests=0,
            monetary_cost_usd=0,
        )


_AMOUNT_FIELDS = {
    PhaseMResourceDimension.WALL_TIME: "wall_time_seconds",
    PhaseMResourceDimension.OUTPUT_TOKENS: "output_tokens",
    PhaseMResourceDimension.MODEL_TURNS: "model_turns",
    PhaseMResourceDimension.TOOL_CALLS: "tool_calls",
    PhaseMResourceDimension.PROVIDER_REQUESTS: "provider_requests",
    PhaseMResourceDimension.MONETARY_COST: "monetary_cost_usd",
}


def _add(left: ResourceAmounts, right: ResourceAmounts) -> ResourceAmounts:
    values: dict[str, Decimal | None] = {}
    for field in _AMOUNT_FIELDS.values():
        left_value = getattr(left, field)
        right_value = getattr(right, field)
        values[field] = (
            None if left_value is None or right_value is None else left_value + right_value
        )
    return ResourceAmounts(**values)


class ReservationUnit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    logical_unit_id: Sha256Digest
    resource_envelope_identity: Sha256Digest
    maximum_resources: ResourceAmounts


class BudgetReservationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    request_id: Identifier
    plan: ImmutableArtifactReference
    stage: FunnelV3Stage
    scope: ReservationScope
    scope_id: Identifier
    logical_unit_id: Sha256Digest
    resource_envelope_identity: Sha256Digest
    budget_estimate: ImmutableArtifactReference
    maximum_resources: ResourceAmounts
    request_digest: Sha256Digest

    @model_validator(mode="after")
    def request_is_self_identifying(self) -> BudgetReservationRequest:
        if self.request_digest != canonical_digest(self.payload()):
            raise ValueError("reservation request digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"request_digest"})


class BudgetReservationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    receipt_id: Identifier
    request: BudgetReservationRequest
    decision: ReservationDecision
    reason_code: ReservationReasonCode
    reserved_before: ResourceAmounts
    consumed_at_decision: ResourceAmounts
    reserved_after: ResourceAmounts
    durable: Literal[False] = False
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def receipt_is_truthful_and_self_identifying(self) -> BudgetReservationReceipt:
        if self.decision is ReservationDecision.DENIED:
            if self.reason_code is ReservationReasonCode.WITHIN_ENFORCED_CEILING:
                raise ValueError("denied reservation requires a blocking reason")
            if self.reserved_after != self.reserved_before:
                raise ValueError("denied reservation must not mutate reserved totals")
        else:
            if self.reason_code is not ReservationReasonCode.WITHIN_ENFORCED_CEILING:
                raise ValueError("accepted reservation cannot claim a blocking reason")
            if self.reserved_after != _add(self.reserved_before, self.request.maximum_resources):
                raise ValueError("accepted reservation totals do not include the exact request")
        if self.receipt_digest != canonical_digest(self.payload()):
            raise ValueError("reservation receipt digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"receipt_digest"})

    def as_reference(self) -> ImmutableArtifactReference:
        return ImmutableArtifactReference(
            artifact_id=self.receipt_id,
            schema_version=self.schema_version,
            artifact_digest=self.receipt_digest,
        )


def build_reservation_request(
    *,
    request_id: str,
    plan: ImmutableArtifactReference,
    stage: FunnelV3Stage,
    scope: ReservationScope,
    scope_id: str,
    unit: ReservationUnit,
    budget_estimate: PlanBudgetEstimate,
) -> BudgetReservationRequest:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "request_id": request_id,
        "plan": plan.model_dump(mode="json"),
        "stage": stage.value,
        "scope": scope.value,
        "scope_id": scope_id,
        "logical_unit_id": unit.logical_unit_id,
        "resource_envelope_identity": unit.resource_envelope_identity,
        "budget_estimate": budget_estimate.as_reference().model_dump(mode="json"),
        "maximum_resources": unit.maximum_resources.model_dump(mode="json"),
    }
    payload["request_digest"] = canonical_digest(payload)
    return BudgetReservationRequest.model_validate(payload)


def reservation_units_for_plan(
    plan: ExperimentPlan,
    cell_budgets: tuple[PlanCellBudget, ...],
) -> tuple[ReservationUnit, ...]:
    budgets = {item.cell_id: item for item in cell_budgets}
    if {cell.id for cell in plan.cells} != set(budgets):
        raise BudgetReservationError("reservation units require every exact planned cell budget")
    units: list[ReservationUnit] = []
    for slot in plan.run_slots:
        cell = budgets[slot.cell_id]
        contract = cell.per_slot_budget

        values = {
            attribute: (
                None
                if getattr(contract, attribute).value is None
                else Decimal(str(getattr(contract, attribute).value))
            )
            for attribute in (
                "max_wall_time",
                "max_output_tokens",
                "max_model_turns",
                "max_tool_calls",
                "max_provider_requests",
            )
        }

        units.append(
            ReservationUnit(
                logical_unit_id=slot.slot_id,
                resource_envelope_identity=cell.resource_envelope_identity,
                maximum_resources=ResourceAmounts(
                    wall_time_seconds=values["max_wall_time"],
                    output_tokens=values["max_output_tokens"],
                    model_turns=values["max_model_turns"],
                    tool_calls=values["max_tool_calls"],
                    provider_requests=values["max_provider_requests"],
                    monetary_cost_usd=_known_unit_cost(cell),
                ),
            )
        )
    return tuple(sorted(units, key=lambda item: item.logical_unit_id))


class InMemoryBudgetReservationStore:
    """Thread-safe deterministic M.5 implementation; explicitly not durable product evidence."""

    def __init__(
        self,
        *,
        estimate: PlanBudgetEstimate,
        stage: FunnelV3Stage,
        scope: ReservationScope,
        scope_id: str,
        units: tuple[ReservationUnit, ...],
        consumed_totals: ResourceAmounts | None = None,
    ) -> None:
        if len({item.logical_unit_id for item in units}) != len(units):
            raise BudgetReservationError("reservation unit identities must be unique")
        if estimate.target_stage is not stage:
            raise BudgetReservationError("reservation stage must match the exact plan estimate")
        expected_scope = {
            ReservationScope.STAGE: BudgetScope.PER_STAGE,
            ReservationScope.CAMPAIGN: BudgetScope.PER_CAMPAIGN,
        }[scope]
        if estimate.ceiling_scope is not expected_scope:
            raise BudgetReservationError("reservation scope must match the exact plan estimate")
        self._estimate = estimate
        self._stage = stage
        self._scope = scope
        self._scope_id = scope_id
        self._units = {item.logical_unit_id: item for item in units}
        self._consumed = consumed_totals or ResourceAmounts.zero()
        self._reserved = ResourceAmounts.zero()
        self._receipts: dict[str, BudgetReservationReceipt] = {}
        self._lock = Lock()

    @property
    def reserved_totals(self) -> ResourceAmounts:
        with self._lock:
            return self._reserved

    @property
    def consumed_totals(self) -> ResourceAmounts:
        with self._lock:
            return self._consumed

    def reserve(self, request: BudgetReservationRequest) -> BudgetReservationReceipt:
        with self._lock:
            existing = self._receipts.get(request.logical_unit_id)
            if existing is not None and existing.request == request:
                return existing
            reason = self._validate_request(request, existing)
            if reason is None:
                reason = self._ceiling_reason(request.maximum_resources)
            accepted = reason is None
            reason = reason or ReservationReasonCode.WITHIN_ENFORCED_CEILING
            before = self._reserved
            after = _add(before, request.maximum_resources) if accepted else before
            payload: dict[str, Any] = {
                "schema_version": 1,
                "receipt_id": f"reservation-{request.request_digest.removeprefix('sha256:')[:24]}",
                "request": request.model_dump(mode="json"),
                "decision": (
                    ReservationDecision.ACCEPTED.value
                    if accepted
                    else ReservationDecision.DENIED.value
                ),
                "reason_code": reason.value,
                "reserved_before": before.model_dump(mode="json"),
                "consumed_at_decision": self._consumed.model_dump(mode="json"),
                "reserved_after": after.model_dump(mode="json"),
                "durable": False,
            }
            payload["receipt_digest"] = canonical_digest(payload)
            receipt = BudgetReservationReceipt.model_validate(payload)
            if accepted:
                self._reserved = after
                self._receipts[request.logical_unit_id] = receipt
            return receipt

    def _validate_request(
        self,
        request: BudgetReservationRequest,
        existing: BudgetReservationReceipt | None,
    ) -> ReservationReasonCode | None:
        if existing is not None:
            return ReservationReasonCode.DUPLICATE_LOGICAL_UNIT_MISMATCH
        if request.plan != self._estimate.candidate_plan or (
            request.budget_estimate != self._estimate.as_reference()
        ):
            return ReservationReasonCode.PLAN_IDENTITY_MISMATCH
        if (
            request.stage is not self._stage
            or request.scope is not self._scope
            or request.scope_id != self._scope_id
        ):
            return ReservationReasonCode.STAGE_OR_SCOPE_MISMATCH
        unit = self._units.get(request.logical_unit_id)
        if unit is None:
            return ReservationReasonCode.LOGICAL_UNIT_UNKNOWN
        if (
            request.resource_envelope_identity != unit.resource_envelope_identity
            or request.maximum_resources != unit.maximum_resources
        ):
            return ReservationReasonCode.UNIT_RESOURCE_ENVELOPE_MISMATCH
        if self._estimate.status is not PlanBudgetStatus.SAFE:
            return ReservationReasonCode.PREFLIGHT_BUDGET_BLOCKED
        return None

    def _ceiling_reason(self, requested: ResourceAmounts) -> ReservationReasonCode | None:
        projected = _add(_add(self._reserved, self._consumed), requested)
        for dimension in self._estimate.dimensions:
            if dimension.enforcement_status is not BudgetDimensionStatus.ENFORCED:
                continue
            field = _AMOUNT_FIELDS[dimension.dimension]
            amount = getattr(projected, field)
            if amount is None or dimension.ceiling is None:
                return ReservationReasonCode.ENFORCED_DIMENSION_UNAVAILABLE
            if amount > dimension.ceiling:
                return ReservationReasonCode.ENFORCED_CEILING_WOULD_BE_EXCEEDED
        return None


class BudgetReservationStore(Protocol):
    """Narrow M.5 persistence boundary; implementations decide their durability semantics."""

    @property
    def reserved_totals(self) -> ResourceAmounts: ...

    @property
    def consumed_totals(self) -> ResourceAmounts: ...

    def reserve(self, request: BudgetReservationRequest) -> BudgetReservationReceipt: ...


__all__ = [
    "BudgetReservationError",
    "BudgetReservationReceipt",
    "BudgetReservationRequest",
    "BudgetReservationStore",
    "InMemoryBudgetReservationStore",
    "ReservationDecision",
    "ReservationReasonCode",
    "ReservationScope",
    "ReservationUnit",
    "ResourceAmounts",
    "build_reservation_request",
    "reservation_units_for_plan",
]
