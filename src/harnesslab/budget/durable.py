from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.budget.plan import PhaseMResourceDimension, PlanBudgetEstimate, PlanBudgetStatus
from harnesslab.budget.reservation import (
    BudgetReservationRequest,
    ReservationDecision,
    ReservationReasonCode,
    ReservationScope,
    ReservationUnit,
    ResourceAmounts,
)
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Sha256Digest
from harnesslab.db.models.experiment import (
    BudgetReservationRecord,
    BudgetScopeLedgerRecord,
    ExperimentAttemptReconciliationRecord,
)
from harnesslab.experiment.methodology import BudgetDimensionStatus


class DurableBudgetError(RuntimeError):
    """Durable budget identity, locking, or reconciliation invariants were violated."""


_FIELDS = {
    PhaseMResourceDimension.WALL_TIME: "wall_time_seconds",
    PhaseMResourceDimension.OUTPUT_TOKENS: "output_tokens",
    PhaseMResourceDimension.MODEL_TURNS: "model_turns",
    PhaseMResourceDimension.TOOL_CALLS: "tool_calls",
    PhaseMResourceDimension.PROVIDER_REQUESTS: "provider_requests",
    PhaseMResourceDimension.MONETARY_COST: "monetary_cost_usd",
}


def resource_add(left: ResourceAmounts, right: ResourceAmounts) -> ResourceAmounts:
    values: dict[str, Decimal | None] = {}
    for field in _FIELDS.values():
        first = getattr(left, field)
        second = getattr(right, field)
        values[field] = None if first is None or second is None else first + second
    return ResourceAmounts(**values)


class DurableBudgetReservationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    request: BudgetReservationRequest
    decision: ReservationDecision
    reason_code: ReservationReasonCode
    reserved_before: ResourceAmounts
    consumed_at_decision: ResourceAmounts
    reserved_after: ResourceAmounts
    durable: Literal[True] = True
    provenance: Literal["POSTGRESQL_SERIALIZED_SCOPE_LEDGER"] = "POSTGRESQL_SERIALIZED_SCOPE_LEDGER"
    decided_at: datetime
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def receipt_is_truthful(self) -> DurableBudgetReservationReceipt:
        if self.decided_at.tzinfo is None or self.decided_at.utcoffset() is None:
            raise ValueError("durable reservation timestamp must be timezone-aware")
        expected = (
            self.reserved_before
            if self.decision is ReservationDecision.DENIED
            else resource_add(self.reserved_before, self.request.maximum_resources)
        )
        if self.reserved_after != expected:
            raise ValueError("durable reservation totals do not match its decision")
        if self.decision is ReservationDecision.ACCEPTED and (
            self.reason_code is not ReservationReasonCode.WITHIN_ENFORCED_CEILING
        ):
            raise ValueError("accepted durable reservation cannot claim a blocking reason")
        if self.receipt_digest != canonical_digest(self.payload()):
            raise ValueError("durable reservation digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"receipt_digest"})


async def initialize_budget_scope(
    session: AsyncSession,
    *,
    scope_id: str,
    estimate: PlanBudgetEstimate,
    scope: ReservationScope,
    preflight_digest: Sha256Digest,
    now: datetime,
) -> None:
    existing = await session.get(BudgetScopeLedgerRecord, scope_id, with_for_update=True)
    expected = {
        "plan_digest": estimate.candidate_plan.artifact_digest,
        "preflight_digest": preflight_digest,
        "budget_estimate_digest": estimate.estimate_digest,
        "stage": estimate.target_stage.value,
        "scope": scope.value,
    }
    if existing is not None:
        actual = {name: getattr(existing, name) for name in expected}
        if actual != expected:
            raise DurableBudgetError("budget scope already belongs to different frozen inputs")
        return
    if estimate.status is not PlanBudgetStatus.SAFE:
        raise DurableBudgetError("cannot initialize durable scope from blocked estimate")
    session.add(
        BudgetScopeLedgerRecord(
            scope_id=scope_id,
            **expected,
            ceilings_json=estimate.model_dump(mode="json"),
            reserved_totals_json=ResourceAmounts.zero().model_dump(mode="json"),
            consumed_totals_json=ResourceAmounts.zero().model_dump(mode="json"),
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()


def _reservation_reason(
    request: BudgetReservationRequest,
    estimate: PlanBudgetEstimate,
    unit: ReservationUnit,
    accepted_for_unit: BudgetReservationRecord | None,
    reserved: ResourceAmounts,
    consumed: ResourceAmounts,
) -> ReservationReasonCode | None:
    if accepted_for_unit is not None:
        return ReservationReasonCode.DUPLICATE_LOGICAL_UNIT_MISMATCH
    if request.plan != estimate.candidate_plan or (
        request.budget_estimate != estimate.as_reference()
    ):
        return ReservationReasonCode.PLAN_IDENTITY_MISMATCH
    if request.logical_unit_id != unit.logical_unit_id:
        return ReservationReasonCode.LOGICAL_UNIT_UNKNOWN
    if (
        request.resource_envelope_identity != unit.resource_envelope_identity
        or request.maximum_resources != unit.maximum_resources
    ):
        return ReservationReasonCode.UNIT_RESOURCE_ENVELOPE_MISMATCH
    projected = resource_add(resource_add(reserved, consumed), request.maximum_resources)
    for dimension in estimate.dimensions:
        if dimension.enforcement_status is not BudgetDimensionStatus.ENFORCED:
            continue
        value = getattr(projected, _FIELDS[dimension.dimension])
        if value is None or dimension.ceiling is None:
            return ReservationReasonCode.ENFORCED_DIMENSION_UNAVAILABLE
        if value > dimension.ceiling:
            return ReservationReasonCode.ENFORCED_CEILING_WOULD_BE_EXCEEDED
    return None


async def reserve_budget(
    session: AsyncSession,
    *,
    request: BudgetReservationRequest,
    estimate: PlanBudgetEstimate,
    unit: ReservationUnit,
    now: datetime,
) -> DurableBudgetReservationReceipt:
    """Serialize one scope row so concurrent PostgreSQL transactions cannot overspend."""

    ledger = await session.scalar(
        select(BudgetScopeLedgerRecord)
        .where(BudgetScopeLedgerRecord.scope_id == request.scope_id)
        .with_for_update()
    )
    if ledger is None:
        raise DurableBudgetError("durable budget scope is not initialized")
    if (
        ledger.plan_digest != estimate.candidate_plan.artifact_digest
        or ledger.budget_estimate_digest != estimate.estimate_digest
        or ledger.stage != request.stage.value
        or ledger.scope != request.scope.value
    ):
        raise DurableBudgetError("reservation does not match the frozen durable scope")
    if (
        request.plan != estimate.candidate_plan
        or request.budget_estimate != estimate.as_reference()
    ):
        raise DurableBudgetError("reservation request does not match the supplied estimate")
    if (
        request.logical_unit_id != unit.logical_unit_id
        or request.resource_envelope_identity != unit.resource_envelope_identity
        or request.maximum_resources != unit.maximum_resources
    ):
        raise DurableBudgetError("reservation request does not match the supplied logical unit")
    exact = await session.scalar(
        select(BudgetReservationRecord).where(
            BudgetReservationRecord.request_digest == request.request_digest
        )
    )
    if exact is not None:
        return DurableBudgetReservationReceipt.model_validate(exact.receipt_json)
    accepted_for_unit = await session.scalar(
        select(BudgetReservationRecord).where(
            BudgetReservationRecord.scope_id == request.scope_id,
            BudgetReservationRecord.logical_unit_id == request.logical_unit_id,
            BudgetReservationRecord.decision == ReservationDecision.ACCEPTED.value,
            ~select(ExperimentAttemptReconciliationRecord.reconciliation_digest)
            .where(
                ExperimentAttemptReconciliationRecord.reservation_digest
                == BudgetReservationRecord.reservation_digest
            )
            .exists(),
        )
    )
    reserved = ResourceAmounts.model_validate(ledger.reserved_totals_json)
    consumed = ResourceAmounts.model_validate(ledger.consumed_totals_json)
    reason = _reservation_reason(request, estimate, unit, accepted_for_unit, reserved, consumed)
    decision = ReservationDecision.ACCEPTED if reason is None else ReservationDecision.DENIED
    reason = reason or ReservationReasonCode.WITHIN_ENFORCED_CEILING
    after = (
        resource_add(reserved, request.maximum_resources)
        if decision is ReservationDecision.ACCEPTED
        else reserved
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "request": request.model_dump(mode="json"),
        "decision": decision.value,
        "reason_code": reason.value,
        "reserved_before": reserved.model_dump(mode="json"),
        "consumed_at_decision": consumed.model_dump(mode="json"),
        "reserved_after": after.model_dump(mode="json"),
        "durable": True,
        "provenance": "POSTGRESQL_SERIALIZED_SCOPE_LEDGER",
        "decided_at": TypeAdapter(datetime).dump_python(now, mode="json"),
    }
    payload["receipt_digest"] = canonical_digest(payload)
    receipt = DurableBudgetReservationReceipt.model_validate(payload)
    session.add(
        BudgetReservationRecord(
            reservation_digest=receipt.receipt_digest,
            scope_id=request.scope_id,
            logical_unit_id=request.logical_unit_id,
            request_digest=request.request_digest,
            decision=decision.value,
            reason_code=reason.value,
            receipt_json=receipt.model_dump(mode="json"),
            created_at=now,
        )
    )
    if decision is ReservationDecision.ACCEPTED:
        ledger.reserved_totals_json = after.model_dump(mode="json")
        ledger.updated_at = now
    await session.flush()
    return receipt


__all__ = [
    "DurableBudgetError",
    "DurableBudgetReservationReceipt",
    "initialize_budget_scope",
    "reserve_budget",
    "resource_add",
]
