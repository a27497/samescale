from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.budget.durable import (
    DurableBudgetReservationReceipt,
    resource_add,
)
from harnesslab.budget.plan import PhaseMResourceDimension, PlanBudgetEstimate
from harnesslab.budget.reservation import ReservationDecision, ResourceAmounts
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Sha256Digest
from harnesslab.contracts.run import RunStatus
from harnesslab.db.models.experiment import (
    BudgetReservationRecord,
    BudgetScopeLedgerRecord,
    ExperimentAttemptEventRecord,
    ExperimentAttemptReconciliationRecord,
    ExperimentControlEventRecord,
    ExperimentRecord,
    ExperimentResourceEventRecord,
    ExperimentRunAttemptRecord,
    ExperimentRunRecord,
)
from harnesslab.evaluation_suites.models import ImmutableArtifactReference
from harnesslab.experiment.funnel_v3 import FunnelV3Stage
from harnesslab.experiment.lifecycle import (
    TERMINAL_STATES,
    InfraRecoveryAuthorization,
    LifecycleRecoveryError,
    LifecycleState,
    LifecycleTransition,
    validate_transition,
)
from harnesslab.experiment.methodology import BudgetDimensionStatus
from harnesslab.experiment.outcomes import StatisticalOutcome


class AuthoritativeLifecycleError(RuntimeError):
    """The durable Phase-M event chain, controls, or projection is inconsistent."""


class AttemptRole(StrEnum):
    PRIMARY = "PRIMARY"
    RECOVERY = "RECOVERY"


class ControlType(StrEnum):
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    CANCEL = "CANCEL"
    RETRY_INFRA_SELECTED = "RETRY_INFRA_SELECTED"
    RUN_REMAINING = "RUN_REMAINING"


class ControlState(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class BudgetExhaustionSource(StrEnum):
    CAMPAIGN_OPERATOR_STAGE = "CAMPAIGN_OPERATOR_STAGE"
    TASK_COMPARABLE_ENVELOPE = "TASK_COMPARABLE_ENVELOPE"


def capability_outcome_for_attempt(
    state: LifecycleState,
    *,
    budget_source: BudgetExhaustionSource | None = None,
) -> StatisticalOutcome | None:
    """Project truthful statistics; campaign exhaustion never becomes capability failure."""

    if state is LifecycleState.FAILED_CAPABILITY:
        return StatisticalOutcome.CAPABILITY_FAIL
    if state is LifecycleState.FAILED_INFRA:
        return StatisticalOutcome.INFRA_FAILURE
    if state is LifecycleState.CANCELLED:
        return StatisticalOutcome.CANCELLED
    if state is LifecycleState.BUDGET_EXHAUSTED:
        if budget_source is BudgetExhaustionSource.TASK_COMPARABLE_ENVELOPE:
            raise AuthoritativeLifecycleError(
                "task-envelope failure must use its bound capability outcome policy"
            )
        return None
    return None


class AttemptSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt_id: Sha256Digest
    run_id: str
    plan_digest: Sha256Digest
    attempt_number: int = Field(ge=1)
    role: AttemptRole
    authorization: dict[str, Any] | None
    reservation_digest: Sha256Digest | None
    state: LifecycleState
    artifact_manifest_path: str | None
    evidence_digest: Sha256Digest | None
    terminal_reason: str | None
    created_at: datetime
    started_at: datetime | None
    terminal_at: datetime | None


class AttemptEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: Sha256Digest
    attempt_id: Sha256Digest
    sequence: int = Field(ge=0)
    from_state: LifecycleState
    to_state: LifecycleState
    reason_code: str | None
    previous_event_digest: Sha256Digest | None
    event_digest: Sha256Digest
    occurred_at: datetime


class AuthoritativeRunProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    slot_id: Sha256Digest
    compatibility_status: RunStatus
    primary_attempt: AttemptSnapshot
    recovery_attempts: tuple[AttemptSnapshot, ...]
    effective_attempt: AttemptSnapshot
    effective_selection_reason: Literal["LATEST_ATTEMPT_EXPLICIT"] = "LATEST_ATTEMPT_EXPLICIT"
    historical_compatibility_only: Literal[False] = False


def _attempt_snapshot(record: ExperimentRunAttemptRecord) -> AttemptSnapshot:
    return AttemptSnapshot(
        attempt_id=record.attempt_id,
        run_id=record.run_id,
        plan_digest=record.plan_digest,
        attempt_number=record.attempt_number,
        role=AttemptRole(record.role),
        authorization=record.authorization_json,
        reservation_digest=record.reservation_digest,
        state=LifecycleState(record.current_state),
        artifact_manifest_path=record.artifact_manifest_path,
        evidence_digest=record.evidence_digest,
        terminal_reason=record.terminal_reason,
        created_at=record.created_at,
        started_at=record.started_at,
        terminal_at=record.terminal_at,
    )


def primary_attempt_identity(plan_digest: str, run_id: str, slot_id: str) -> str:
    return canonical_digest(
        {
            "plan_digest": plan_digest,
            "run_id": run_id,
            "slot_id": slot_id,
            "attempt_number": 1,
            "role": AttemptRole.PRIMARY.value,
        }
    )


def recovery_attempt_identity(
    *,
    plan_digest: str,
    run_id: str,
    slot_id: str,
    attempt_number: int,
    failed_attempt_identity: str,
    authorization_identity: str,
) -> str:
    return canonical_digest(
        {
            "plan_digest": plan_digest,
            "run_id": run_id,
            "slot_id": slot_id,
            "attempt_number": attempt_number,
            "role": AttemptRole.RECOVERY.value,
            "failed_attempt_identity": failed_attempt_identity,
            "authorization_identity": authorization_identity,
        }
    )


async def initialize_authoritative_lifecycle(
    session: AsyncSession,
    *,
    experiment_id: str,
    plan_digest: str,
    now: datetime,
) -> tuple[AttemptSnapshot, ...]:
    experiment = await session.get(ExperimentRecord, experiment_id, with_for_update=True)
    if experiment is None or experiment.plan_digest != plan_digest:
        raise AuthoritativeLifecycleError("authoritative initialization requires the exact plan")
    runs = tuple(
        (
            await session.scalars(
                select(ExperimentRunRecord)
                .where(ExperimentRunRecord.experiment_id == experiment_id)
                .order_by(ExperimentRunRecord.slot_order)
                .with_for_update()
            )
        ).all()
    )
    existing = tuple(
        (
            await session.scalars(
                select(ExperimentRunAttemptRecord).where(
                    ExperimentRunAttemptRecord.run_id.in_(run.run_id for run in runs),
                    ExperimentRunAttemptRecord.attempt_number == 1,
                )
            )
        ).all()
    )
    if existing:
        if len(existing) != len(runs):
            raise AuthoritativeLifecycleError("authoritative attempt initialization is partial")
        by_run_id = {item.run_id: item for item in existing}
        return tuple(_attempt_snapshot(by_run_id[run.run_id]) for run in runs)
    attempts = []
    for run in runs:
        record = ExperimentRunAttemptRecord(
            attempt_id=primary_attempt_identity(plan_digest, run.run_id, run.slot_id),
            run_id=run.run_id,
            plan_digest=plan_digest,
            attempt_number=1,
            role=AttemptRole.PRIMARY.value,
            authorization_json=None,
            current_state=LifecycleState.QUEUED.value,
            created_at=now,
        )
        session.add(record)
        attempts.append(record)
    await session.flush()
    return tuple(_attempt_snapshot(item) for item in attempts)


async def current_attempt_record(
    session: AsyncSession, run_id: str, *, lock: bool = False
) -> ExperimentRunAttemptRecord | None:
    statement = (
        select(ExperimentRunAttemptRecord)
        .where(ExperimentRunAttemptRecord.run_id == run_id)
        .order_by(ExperimentRunAttemptRecord.attempt_number.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    result: ExperimentRunAttemptRecord | None = await session.scalar(statement)
    return result


async def durable_reservation_for_attempt(
    session: AsyncSession, attempt_id: str
) -> DurableBudgetReservationReceipt | None:
    attempt = await session.get(ExperimentRunAttemptRecord, attempt_id)
    if attempt is None:
        raise AuthoritativeLifecycleError("authoritative attempt does not exist")
    if attempt.reservation_digest is None:
        return None
    record = await session.get(BudgetReservationRecord, attempt.reservation_digest)
    if record is None:
        raise AuthoritativeLifecycleError("attempt reservation binding is not durable")
    return DurableBudgetReservationReceipt.model_validate(record.receipt_json)


async def append_attempt_transition(
    session: AsyncSession,
    *,
    attempt_id: str,
    target: LifecycleState,
    occurred_at: datetime,
    reason_code: str | None = None,
) -> AttemptEvent:
    attempt = await session.get(ExperimentRunAttemptRecord, attempt_id, with_for_update=True)
    if attempt is None:
        raise AuthoritativeLifecycleError("authoritative attempt does not exist")
    source = LifecycleState(attempt.current_state)
    validate_transition(source, target)
    LifecycleTransition(
        from_state=source,
        to_state=target,
        occurred_at=occurred_at,
        reason_code=reason_code,
    )
    previous = await session.scalar(
        select(ExperimentAttemptEventRecord)
        .where(ExperimentAttemptEventRecord.attempt_id == attempt_id)
        .order_by(ExperimentAttemptEventRecord.sequence.desc())
        .limit(1)
    )
    if occurred_at < attempt.created_at or (
        previous is not None and occurred_at < previous.occurred_at
    ):
        raise AuthoritativeLifecycleError("attempt lifecycle timestamp is not monotonic")
    sequence = 0 if previous is None else previous.sequence + 1
    previous_digest = None if previous is None else previous.event_digest
    payload: dict[str, Any] = {
        "attempt_id": attempt_id,
        "sequence": sequence,
        "from_state": source.value,
        "to_state": target.value,
        "reason_code": reason_code,
        "previous_event_digest": previous_digest,
        "occurred_at": occurred_at.isoformat(),
    }
    digest = canonical_digest(payload)
    record = ExperimentAttemptEventRecord(
        event_id=digest,
        attempt_id=attempt_id,
        sequence=sequence,
        from_state=source.value,
        to_state=target.value,
        reason_code=reason_code,
        previous_event_digest=previous_digest,
        event_digest=digest,
        occurred_at=occurred_at,
    )
    session.add(record)
    attempt.current_state = target.value
    if target is LifecycleState.PREPARING:
        attempt.started_at = occurred_at
    if target in TERMINAL_STATES:
        attempt.terminal_at = occurred_at
        attempt.terminal_reason = reason_code
    await session.flush()
    return AttemptEvent.model_validate({**payload, "event_id": digest, "event_digest": digest})


async def read_authoritative_projection(
    session: AsyncSession, run_id: str
) -> AuthoritativeRunProjection | None:
    run = await session.get(ExperimentRunRecord, run_id)
    if run is None:
        raise AuthoritativeLifecycleError("logical run does not exist")
    records = tuple(
        (
            await session.scalars(
                select(ExperimentRunAttemptRecord)
                .where(ExperimentRunAttemptRecord.run_id == run_id)
                .order_by(ExperimentRunAttemptRecord.attempt_number)
            )
        ).all()
    )
    if not records:
        return None
    if any(
        record.attempt_number != index
        or record.plan_digest != records[0].plan_digest
        or record.role != (AttemptRole.PRIMARY.value if index == 1 else AttemptRole.RECOVERY.value)
        for index, record in enumerate(records, start=1)
    ):
        raise AuthoritativeLifecycleError("physical attempt projection is not contiguous")
    for record in records:
        await _validate_attempt_event_chain(session, record)
    snapshots = tuple(_attempt_snapshot(item) for item in records)
    return AuthoritativeRunProjection(
        run_id=run.run_id,
        slot_id=run.slot_id,
        compatibility_status=RunStatus(run.status),
        primary_attempt=snapshots[0],
        recovery_attempts=snapshots[1:],
        effective_attempt=snapshots[-1],
    )


async def _validate_attempt_event_chain(
    session: AsyncSession, attempt: ExperimentRunAttemptRecord
) -> None:
    events = tuple(
        (
            await session.scalars(
                select(ExperimentAttemptEventRecord)
                .where(ExperimentAttemptEventRecord.attempt_id == attempt.attempt_id)
                .order_by(ExperimentAttemptEventRecord.sequence)
            )
        ).all()
    )
    state = LifecycleState.QUEUED
    previous_digest: str | None = None
    for sequence, event in enumerate(events):
        if (
            event.sequence != sequence
            or event.event_id != event.event_digest
            or event.previous_event_digest != previous_digest
            or event.from_state != state.value
        ):
            raise AuthoritativeLifecycleError("attempt lifecycle event chain is inconsistent")
        target = LifecycleState(event.to_state)
        validate_transition(state, target)
        state = target
        previous_digest = event.event_digest
    if state.value != attempt.current_state:
        raise AuthoritativeLifecycleError("attempt lifecycle cache differs from its event chain")


async def create_recovery_attempt(
    session: AsyncSession,
    *,
    run_id: str,
    authorization: InfraRecoveryAuthorization,
    plan_digest: str,
    now: datetime,
    maximum_recovery_attempts: int = 1,
) -> AttemptSnapshot:
    run = await session.get(ExperimentRunRecord, run_id, with_for_update=True)
    if run is None:
        raise LifecycleRecoveryError("logical run does not exist")
    attempts = tuple(
        (
            await session.scalars(
                select(ExperimentRunAttemptRecord)
                .where(ExperimentRunAttemptRecord.run_id == run_id)
                .order_by(ExperimentRunAttemptRecord.attempt_number)
                .with_for_update()
            )
        ).all()
    )
    if not attempts or attempts[-1].current_state != LifecycleState.FAILED_INFRA.value:
        raise LifecycleRecoveryError("only a failed infrastructure attempt may be recovered")
    if len(attempts) - 1 >= maximum_recovery_attempts:
        raise LifecycleRecoveryError("infrastructure recovery attempt limit is exhausted")
    failed = attempts[-1]
    if authorization.failed_attempt_identity != failed.attempt_id:
        raise LifecycleRecoveryError("authorization does not identify the failed attempt")
    number = len(attempts) + 1
    expected_identity = recovery_attempt_identity(
        plan_digest=plan_digest,
        run_id=run_id,
        slot_id=run.slot_id,
        attempt_number=number,
        failed_attempt_identity=failed.attempt_id,
        authorization_identity=canonical_digest(
            {
                "authorized_by": authorization.authorized_by,
                "authorized_at": authorization.authorized_at.isoformat(),
                "reason_code": authorization.reason_code,
                "repair_reference": authorization.repair_reference,
            }
        ),
    )
    if authorization.recovery_attempt_identity != expected_identity:
        raise LifecycleRecoveryError("recovery authorization identity is not canonical")
    record = ExperimentRunAttemptRecord(
        attempt_id=expected_identity,
        run_id=run_id,
        plan_digest=plan_digest,
        attempt_number=number,
        role=AttemptRole.RECOVERY.value,
        authorization_json=authorization.model_dump(mode="json"),
        current_state=LifecycleState.QUEUED.value,
        created_at=now,
    )
    session.add(record)
    run.status = RunStatus.QUEUED.value
    run.attempt = number - 1
    run.lease_owner = None
    run.lease_expires_at = None
    run.heartbeat_at = None
    run.cancellation_requested = False
    await session.flush()
    return _attempt_snapshot(record)


class ResourceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class ObservedResourceDimension(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    availability: ResourceAvailability
    value: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    unit: str

    @model_validator(mode="after")
    def availability_matches_value(self) -> ObservedResourceDimension:
        if (self.availability is ResourceAvailability.AVAILABLE) != (self.value is not None):
            raise ValueError("observed resource availability does not match its value")
        return self


class ObservedResourceUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    wall_time: ObservedResourceDimension
    output_tokens: ObservedResourceDimension
    model_turns: ObservedResourceDimension
    tool_calls: ObservedResourceDimension
    provider_requests: ObservedResourceDimension
    monetary_cost: ObservedResourceDimension

    @model_validator(mode="after")
    def units_are_canonical(self) -> ObservedResourceUsage:
        expected = {
            "wall_time": "seconds",
            "output_tokens": "tokens",
            "model_turns": "turns",
            "tool_calls": "calls",
            "provider_requests": "requests",
            "monetary_cost": "USD",
        }
        for field, unit in expected.items():
            if getattr(self, field).unit != unit:
                raise ValueError(f"{field} must use canonical unit {unit}")
        return self

    def amounts(self) -> ResourceAmounts:
        return ResourceAmounts(
            wall_time_seconds=self.wall_time.value,
            output_tokens=self.output_tokens.value,
            model_turns=self.model_turns.value,
            tool_calls=self.tool_calls.value,
            provider_requests=self.provider_requests.value,
            monetary_cost_usd=self.monetary_cost.value,
        )


def unavailable_resource_usage() -> ObservedResourceUsage:
    return ObservedResourceUsage(
        wall_time=ObservedResourceDimension(
            availability=ResourceAvailability.NOT_AVAILABLE, unit="seconds"
        ),
        output_tokens=ObservedResourceDimension(
            availability=ResourceAvailability.NOT_AVAILABLE, unit="tokens"
        ),
        model_turns=ObservedResourceDimension(
            availability=ResourceAvailability.NOT_AVAILABLE, unit="turns"
        ),
        tool_calls=ObservedResourceDimension(
            availability=ResourceAvailability.NOT_AVAILABLE, unit="calls"
        ),
        provider_requests=ObservedResourceDimension(
            availability=ResourceAvailability.NOT_AVAILABLE, unit="requests"
        ),
        monetary_cost=ObservedResourceDimension(
            availability=ResourceAvailability.NOT_AVAILABLE, unit="USD"
        ),
    )


class ReconciliationStatus(StrEnum):
    RECONCILED = "RECONCILED"
    RECONCILED_WITH_UNAVAILABLE = "RECONCILED_WITH_UNAVAILABLE"
    ENVELOPE_EXCEEDED = "ENVELOPE_EXCEEDED"


class ReconciliationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt_id: Sha256Digest
    resource_event_digest: Sha256Digest
    reservation_digest: Sha256Digest
    estimate_digest: Sha256Digest
    estimated: ImmutableArtifactReference
    reserved: ResourceAmounts
    actual: ObservedResourceUsage
    released: ResourceAmounts
    status: ReconciliationStatus
    reason_code: str
    reconciled_at: datetime
    reconciliation_digest: Sha256Digest

    @model_validator(mode="after")
    def digest_matches_payload(self) -> ReconciliationReceipt:
        if self.reconciliation_digest != canonical_digest(self.payload()):
            raise ValueError("reconciliation digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"reconciliation_digest"})


_USAGE_FIELDS = {
    PhaseMResourceDimension.WALL_TIME: ("wall_time", "wall_time_seconds"),
    PhaseMResourceDimension.OUTPUT_TOKENS: ("output_tokens", "output_tokens"),
    PhaseMResourceDimension.MODEL_TURNS: ("model_turns", "model_turns"),
    PhaseMResourceDimension.TOOL_CALLS: ("tool_calls", "tool_calls"),
    PhaseMResourceDimension.PROVIDER_REQUESTS: ("provider_requests", "provider_requests"),
    PhaseMResourceDimension.MONETARY_COST: ("monetary_cost", "monetary_cost_usd"),
}


async def reconcile_attempt_resources(
    session: AsyncSession,
    *,
    attempt_id: str,
    reservation: DurableBudgetReservationReceipt,
    usage: ObservedResourceUsage,
    evidence_reference: ImmutableArtifactReference | None,
    now: datetime,
) -> ReconciliationReceipt:
    attempt = await session.get(ExperimentRunAttemptRecord, attempt_id, with_for_update=True)
    if attempt is None:
        raise AuthoritativeLifecycleError("attempt does not exist")
    existing = await session.scalar(
        select(ExperimentAttemptReconciliationRecord).where(
            ExperimentAttemptReconciliationRecord.attempt_id == attempt_id
        )
    )
    if existing is not None:
        receipt = ReconciliationReceipt.model_validate(existing.receipt_json)
        resource_event = await session.get(
            ExperimentResourceEventRecord, receipt.resource_event_digest
        )
        expected_evidence = (
            None if evidence_reference is None else evidence_reference.model_dump(mode="json")
        )
        if (
            receipt.reservation_digest != reservation.receipt_digest
            or resource_event is None
            or resource_event.usage_json != usage.model_dump(mode="json")
            or resource_event.evidence_reference_json != expected_evidence
        ):
            raise AuthoritativeLifecycleError(
                "duplicate reconciliation does not match the immutable original"
            )
        return receipt
    if reservation.decision is not ReservationDecision.ACCEPTED:
        raise AuthoritativeLifecycleError("resource reconciliation requires accepted reservation")
    if attempt.reservation_digest != reservation.receipt_digest:
        raise AuthoritativeLifecycleError("reservation is not bound to this physical attempt")
    persisted_reservation = await session.get(BudgetReservationRecord, reservation.receipt_digest)
    if persisted_reservation is None:
        raise AuthoritativeLifecycleError("reservation is not durable")
    run = await session.get(ExperimentRunRecord, attempt.run_id)
    if run is None or reservation.request.logical_unit_id != run.slot_id:
        raise AuthoritativeLifecycleError("reservation belongs to a different logical slot")
    ledger = await session.get(
        BudgetScopeLedgerRecord, reservation.request.scope_id, with_for_update=True
    )
    if ledger is None:
        raise AuthoritativeLifecycleError("budget scope disappeared")
    estimate = PlanBudgetEstimate.model_validate(ledger.ceilings_json)
    exceeded = False
    release_values: dict[str, Decimal | None] = {}
    charged_values: dict[str, Decimal | None] = {}
    unavailable = False
    for dimension in estimate.dimensions:
        usage_field, amount_field = _USAGE_FIELDS[dimension.dimension]
        observed = getattr(usage, usage_field)
        maximum = getattr(reservation.request.maximum_resources, amount_field)
        if observed.availability is ResourceAvailability.NOT_AVAILABLE:
            unavailable = True
            release_values[amount_field] = Decimal(0)
            charged_values[amount_field] = maximum
            continue
        if dimension.enforcement_status is BudgetDimensionStatus.ENFORCED and (
            maximum is None or observed.value is None or observed.value > maximum
        ):
            exceeded = True
        release_values[amount_field] = (
            Decimal(0)
            if maximum is None or observed.value is None
            else max(Decimal(0), maximum - observed.value)
        )
        charged_values[amount_field] = observed.value
    released = ResourceAmounts(**release_values)
    charged = ResourceAmounts(**charged_values)
    resource_payload: dict[str, Any] = {
        "attempt_id": attempt_id,
        "reservation_digest": reservation.receipt_digest,
        "resource_envelope_identity": reservation.request.resource_envelope_identity,
        "usage": usage.model_dump(mode="json"),
        "evidence_reference": (
            None if evidence_reference is None else evidence_reference.model_dump(mode="json")
        ),
        "observed_at": now.isoformat(),
    }
    resource_digest = canonical_digest(resource_payload)
    session.add(
        ExperimentResourceEventRecord(
            event_id=resource_digest,
            attempt_id=attempt_id,
            reservation_digest=reservation.receipt_digest,
            resource_envelope_identity=reservation.request.resource_envelope_identity,
            usage_json=usage.model_dump(mode="json"),
            evidence_reference_json=(
                None if evidence_reference is None else evidence_reference.model_dump(mode="json")
            ),
            event_digest=resource_digest,
            observed_at=now,
        )
    )
    # The reconciliation row has a database FK to this append-only usage event.
    await session.flush()
    status = (
        ReconciliationStatus.ENVELOPE_EXCEEDED
        if exceeded
        else ReconciliationStatus.RECONCILED_WITH_UNAVAILABLE
        if unavailable
        else ReconciliationStatus.RECONCILED
    )
    reason = (
        "OBSERVED_ACTUAL_EXCEEDS_ENFORCED_RESERVATION"
        if exceeded
        else "OBSERVED_DIMENSION_NOT_AVAILABLE"
        if unavailable
        else "ESTIMATE_RESERVATION_ACTUAL_RECONCILED"
    )
    if not exceeded:
        reserved_before = ResourceAmounts.model_validate(ledger.reserved_totals_json)
        consumed_before = ResourceAmounts.model_validate(ledger.consumed_totals_json)
        ledger.reserved_totals_json = _subtract_exact(
            reserved_before, reservation.request.maximum_resources
        ).model_dump(mode="json")
        ledger.consumed_totals_json = resource_add(consumed_before, charged).model_dump(mode="json")
        ledger.updated_at = now
    payload: dict[str, Any] = {
        "attempt_id": attempt_id,
        "resource_event_digest": resource_digest,
        "reservation_digest": reservation.receipt_digest,
        "estimate_digest": estimate.estimate_digest,
        "estimated": estimate.as_reference().model_dump(mode="json"),
        "reserved": reservation.request.maximum_resources.model_dump(mode="json"),
        "actual": usage.model_dump(mode="json"),
        "released": released.model_dump(mode="json"),
        "status": status.value,
        "reason_code": reason,
        "reconciled_at": TypeAdapter(datetime).dump_python(now, mode="json"),
    }
    payload["reconciliation_digest"] = canonical_digest(payload)
    receipt = ReconciliationReceipt.model_validate(payload)
    session.add(
        ExperimentAttemptReconciliationRecord(
            reconciliation_digest=receipt.reconciliation_digest,
            attempt_id=attempt_id,
            resource_event_digest=resource_digest,
            reservation_digest=reservation.receipt_digest,
            status=status.value,
            reason_code=reason,
            released_json=released.model_dump(mode="json"),
            receipt_json=receipt.model_dump(mode="json"),
            reconciled_at=now,
        )
    )
    if exceeded and LifecycleState(attempt.current_state) not in TERMINAL_STATES:
        await append_attempt_transition(
            session,
            attempt_id=attempt_id,
            target=LifecycleState.FAILED_INFRA,
            occurred_at=now,
            reason_code=reason,
        )
        run.status = RunStatus.FAILED_INFRA.value
        run.lease_owner = None
        run.lease_expires_at = None
        run.heartbeat_at = now
        run.finished_at = now
        if attempt.role == AttemptRole.PRIMARY.value:
            run.normalized_outcome = StatisticalOutcome.INFRA_FAILURE.value
            run.source_outcome = "resource_envelope_exceeded"
            run.failure_detail = reason
    await session.flush()
    return receipt


def _subtract_exact(left: ResourceAmounts, right: ResourceAmounts) -> ResourceAmounts:
    values: dict[str, Decimal | None] = {}
    for _, amount_field in _USAGE_FIELDS.values():
        first = getattr(left, amount_field)
        second = getattr(right, amount_field)
        if first is None or second is None or second > first:
            raise AuthoritativeLifecycleError("reconciliation release exceeds reserved totals")
        values[amount_field] = first - second
    return ResourceAmounts(**values)


class ControlEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: Sha256Digest
    experiment_id: str
    sequence: int = Field(ge=0)
    plan_digest: Sha256Digest
    stage: FunnelV3Stage
    control_type: ControlType
    actor_identity: Sha256Digest
    authorization_identity: Sha256Digest
    reason: str
    selected_slot_ids: tuple[Sha256Digest, ...]
    preflight_digest: Sha256Digest | None
    budget_estimate_digest: Sha256Digest | None
    previous_event_digest: Sha256Digest | None
    event_digest: Sha256Digest
    occurred_at: datetime


async def control_state(session: AsyncSession, experiment_id: str) -> ControlState:
    events = tuple(
        (
            await session.scalars(
                select(ExperimentControlEventRecord)
                .where(ExperimentControlEventRecord.experiment_id == experiment_id)
                .order_by(ExperimentControlEventRecord.sequence)
            )
        ).all()
    )
    state = ControlState.ACTIVE
    previous_digest: str | None = None
    for sequence, event in enumerate(events):
        if (
            event.sequence != sequence
            or event.event_id != event.event_digest
            or event.previous_event_digest != previous_digest
        ):
            raise AuthoritativeLifecycleError("control event chain is inconsistent")
        control = ControlType(event.control_type)
        if control is ControlType.PAUSE:
            state = ControlState.PAUSED
        elif control is ControlType.RESUME:
            state = ControlState.ACTIVE
        elif control is ControlType.CANCEL and not event.selected_slot_ids_json:
            state = ControlState.CANCELLED
        previous_digest = event.event_digest
    return state


async def never_started_slot_ids(session: AsyncSession, experiment_id: str) -> tuple[str, ...]:
    rows = (
        await session.execute(
            select(ExperimentRunRecord.slot_id)
            .join(
                ExperimentRunAttemptRecord,
                ExperimentRunAttemptRecord.run_id == ExperimentRunRecord.run_id,
            )
            .where(
                ExperimentRunRecord.experiment_id == experiment_id,
                ExperimentRunAttemptRecord.attempt_number == 1,
                ExperimentRunAttemptRecord.current_state == LifecycleState.QUEUED.value,
                ~select(ExperimentAttemptEventRecord.event_id)
                .where(
                    ExperimentAttemptEventRecord.attempt_id == ExperimentRunAttemptRecord.attempt_id
                )
                .exists(),
            )
            .order_by(ExperimentRunRecord.slot_order)
        )
    ).scalars()
    return tuple(rows)


async def issue_control(
    session: AsyncSession,
    *,
    experiment_id: str,
    plan_digest: str,
    stage: FunnelV3Stage,
    control_type: ControlType,
    actor_identity: str,
    authorization_identity: str,
    reason: str,
    now: datetime,
    selected_slot_ids: tuple[str, ...] = (),
    preflight_digest: str | None = None,
    budget_estimate_digest: str | None = None,
) -> ControlEvent:
    experiment = await session.get(ExperimentRecord, experiment_id, with_for_update=True)
    if experiment is None or experiment.plan_digest != plan_digest:
        raise AuthoritativeLifecycleError("control requires the exact immutable plan")
    current = await control_state(session, experiment_id)
    if control_type is ControlType.RESUME:
        if current is not ControlState.PAUSED:
            raise AuthoritativeLifecycleError("resume requires the current PAUSED state")
        if preflight_digest is None or budget_estimate_digest is None:
            raise AuthoritativeLifecycleError("resume requires exact preflight and budget identity")
        previous_control = await session.scalar(
            select(ExperimentControlEventRecord)
            .where(ExperimentControlEventRecord.experiment_id == experiment_id)
            .order_by(ExperimentControlEventRecord.sequence.desc())
            .limit(1)
        )
        if (
            previous_control is None
            or previous_control.control_type != ControlType.PAUSE.value
            or previous_control.preflight_digest != preflight_digest
            or previous_control.budget_estimate_digest != budget_estimate_digest
        ):
            raise AuthoritativeLifecycleError(
                "resume preflight or budget identity differs from the paused control"
            )
    if control_type is ControlType.PAUSE:
        if current is not ControlState.ACTIVE:
            raise AuthoritativeLifecycleError("pause requires the current ACTIVE state")
        if preflight_digest is None or budget_estimate_digest is None:
            raise AuthoritativeLifecycleError("pause requires exact preflight and budget identity")
    if control_type in {
        ControlType.PAUSE,
        ControlType.RESUME,
        ControlType.RETRY_INFRA_SELECTED,
    }:
        if preflight_digest is None or budget_estimate_digest is None:
            raise AuthoritativeLifecycleError(
                f"{control_type.value} requires exact preflight and budget identity"
            )
        durable_scope = await session.scalar(
            select(BudgetScopeLedgerRecord).where(
                BudgetScopeLedgerRecord.plan_digest == plan_digest,
                BudgetScopeLedgerRecord.preflight_digest == preflight_digest,
                BudgetScopeLedgerRecord.budget_estimate_digest == budget_estimate_digest,
                BudgetScopeLedgerRecord.stage == stage.value,
            )
        )
        if durable_scope is None:
            raise AuthoritativeLifecycleError("control budget identity is not durable")
    if current is ControlState.CANCELLED and control_type is not ControlType.CANCEL:
        raise AuthoritativeLifecycleError("cancelled experiment cannot accept further controls")
    if control_type is ControlType.RUN_REMAINING:
        expected = await never_started_slot_ids(session, experiment_id)
        if selected_slot_ids and selected_slot_ids != expected:
            raise AuthoritativeLifecycleError(
                "run-remaining selection is not exact and deterministic"
            )
        selected_slot_ids = expected
    if control_type is ControlType.RETRY_INFRA_SELECTED and not selected_slot_ids:
        raise AuthoritativeLifecycleError("selected infrastructure retry requires slot IDs")
    if len(set(selected_slot_ids)) != len(selected_slot_ids):
        raise AuthoritativeLifecycleError("control slot selection must be unique")
    if (
        control_type is not ControlType.RUN_REMAINING
        and tuple(sorted(selected_slot_ids)) != selected_slot_ids
    ):
        raise AuthoritativeLifecycleError("control slot selection must be unique and canonical")
    unknown = await session.scalar(
        select(func.count())
        .select_from(ExperimentRunRecord)
        .where(
            ExperimentRunRecord.experiment_id == experiment_id,
            ExperimentRunRecord.slot_id.in_(selected_slot_ids),
        )
    )
    if selected_slot_ids and unknown != len(selected_slot_ids):
        raise AuthoritativeLifecycleError("control selected a slot outside the exact plan")
    previous = await session.scalar(
        select(ExperimentControlEventRecord)
        .where(ExperimentControlEventRecord.experiment_id == experiment_id)
        .order_by(ExperimentControlEventRecord.sequence.desc())
        .limit(1)
    )
    if previous is not None and now < previous.occurred_at:
        raise AuthoritativeLifecycleError("control timestamp is not monotonic")
    sequence = 0 if previous is None else previous.sequence + 1
    previous_digest = None if previous is None else previous.event_digest
    payload: dict[str, Any] = {
        "experiment_id": experiment_id,
        "sequence": sequence,
        "plan_digest": plan_digest,
        "stage": stage.value,
        "control_type": control_type.value,
        "actor_identity": actor_identity,
        "authorization_identity": authorization_identity,
        "reason": reason,
        "selected_slot_ids": list(selected_slot_ids),
        "preflight_digest": preflight_digest,
        "budget_estimate_digest": budget_estimate_digest,
        "previous_event_digest": previous_digest,
        "occurred_at": now.isoformat(),
    }
    digest = canonical_digest(payload)
    record = ExperimentControlEventRecord(
        event_id=digest,
        experiment_id=experiment_id,
        sequence=sequence,
        plan_digest=plan_digest,
        stage=stage.value,
        control_type=control_type.value,
        actor_identity=actor_identity,
        authorization_identity=authorization_identity,
        reason=reason,
        selected_slot_ids_json=list(selected_slot_ids),
        preflight_digest=preflight_digest,
        budget_estimate_digest=budget_estimate_digest,
        previous_event_digest=previous_digest,
        event_digest=digest,
        occurred_at=now,
    )
    session.add(record)
    if control_type is ControlType.RETRY_INFRA_SELECTED:
        for slot_id in selected_slot_ids:
            run = await session.scalar(
                select(ExperimentRunRecord)
                .where(
                    ExperimentRunRecord.experiment_id == experiment_id,
                    ExperimentRunRecord.slot_id == slot_id,
                )
                .with_for_update()
            )
            if run is None:
                raise AuthoritativeLifecycleError("selected retry slot disappeared")
            failed = await current_attempt_record(session, run.run_id, lock=True)
            if failed is None:
                raise LifecycleRecoveryError("selected retry lacks authoritative evidence")
            authorization_payload = {
                "authorized_by": actor_identity,
                "authorized_at": now.isoformat(),
                "reason_code": "RETRY_INFRA_SELECTED",
                "repair_reference": digest,
            }
            authorization_digest = canonical_digest(authorization_payload)
            recovery_id = recovery_attempt_identity(
                plan_digest=plan_digest,
                run_id=run.run_id,
                slot_id=run.slot_id,
                attempt_number=failed.attempt_number + 1,
                failed_attempt_identity=failed.attempt_id,
                authorization_identity=authorization_digest,
            )
            authorization = InfraRecoveryAuthorization(
                failed_attempt_identity=failed.attempt_id,
                recovery_attempt_identity=recovery_id,
                authorized_by=actor_identity,
                authorized_at=now,
                reason_code="RETRY_INFRA_SELECTED",
                repair_reference=digest,
            )
            await create_recovery_attempt(
                session,
                run_id=run.run_id,
                authorization=authorization,
                plan_digest=plan_digest,
                now=now,
            )
    if control_type is ControlType.CANCEL:
        attempts = tuple(
            (
                await session.scalars(
                    select(ExperimentRunAttemptRecord)
                    .join(
                        ExperimentRunRecord,
                        ExperimentRunRecord.run_id == ExperimentRunAttemptRecord.run_id,
                    )
                    .where(
                        ExperimentRunRecord.experiment_id == experiment_id,
                        *(
                            (ExperimentRunRecord.slot_id.in_(selected_slot_ids),)
                            if selected_slot_ids
                            else ()
                        ),
                    )
                )
            ).all()
        )
        for attempt in attempts:
            state = LifecycleState(attempt.current_state)
            run = await session.get(ExperimentRunRecord, attempt.run_id, with_for_update=True)
            if state is LifecycleState.QUEUED:
                await append_attempt_transition(
                    session,
                    attempt_id=attempt.attempt_id,
                    target=LifecycleState.CANCELLED,
                    occurred_at=now,
                    reason_code="OPERATOR_CANCELLED",
                )
                if run is not None:
                    run.status = RunStatus.CANCELLED.value
            elif state not in TERMINAL_STATES and run is not None:
                run.cancellation_requested = True
    await session.flush()
    return ControlEvent.model_validate({**payload, "event_id": digest, "event_digest": digest})


def checkpoint_resume_supported() -> Literal[False]:
    """M.6 explicitly has no generic deterministic checkpoint contract."""

    return False


__all__ = [
    "AttemptEvent",
    "AttemptRole",
    "AttemptSnapshot",
    "AuthoritativeLifecycleError",
    "AuthoritativeRunProjection",
    "BudgetExhaustionSource",
    "ControlEvent",
    "ControlState",
    "ControlType",
    "ObservedResourceDimension",
    "ObservedResourceUsage",
    "ReconciliationReceipt",
    "ReconciliationStatus",
    "ResourceAvailability",
    "append_attempt_transition",
    "capability_outcome_for_attempt",
    "checkpoint_resume_supported",
    "control_state",
    "create_recovery_attempt",
    "current_attempt_record",
    "durable_reservation_for_attempt",
    "initialize_authoritative_lifecycle",
    "issue_control",
    "never_started_slot_ids",
    "primary_attempt_identity",
    "read_authoritative_projection",
    "reconcile_attempt_resources",
    "recovery_attempt_identity",
    "unavailable_resource_usage",
]
