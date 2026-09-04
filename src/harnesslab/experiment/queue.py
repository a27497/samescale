from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.budget.durable import DurableBudgetReservationReceipt, reserve_budget
from harnesslab.budget.plan import PlanBudgetEstimate
from harnesslab.budget.reservation import (
    ReservationDecision,
    ReservationScope,
    ReservationUnit,
    build_reservation_request,
)
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.run import RunStatus
from harnesslab.db.models.experiment import (
    BudgetScopeLedgerRecord,
    ExperimentAblationRecord,
    ExperimentAttemptReconciliationRecord,
    ExperimentCellRecord,
    ExperimentPairRecord,
    ExperimentRecord,
    ExperimentRunAttemptRecord,
    ExperimentRunRecord,
)
from harnesslab.experiment.authoritative import (
    ControlState,
    append_attempt_transition,
    control_state,
    current_attempt_record,
    durable_reservation_for_attempt,
    reconcile_attempt_resources,
    unavailable_resource_usage,
)
from harnesslab.experiment.lifecycle import TERMINAL_STATES, LifecycleState
from harnesslab.experiment.methodology import ProviderAvailability
from harnesslab.experiment.outcomes import StatisticalOutcome, terminal_status_for_outcome
from harnesslab.experiment.plan import (
    AnyExperimentPlan,
    ExperimentRunSlot,
    MethodologyV2ExperimentPlan,
    load_experiment_plan_payload,
)
from harnesslab.preflight.unified import (
    UnifiedPreflightReceipt,
    UnifiedPreflightSpecification,
    UnifiedPreflightStatus,
)


class ExperimentConflict(RuntimeError):
    """Immutable experiment identity, queue ownership, or lifecycle was violated."""


ACTIVE_STATUSES = (
    RunStatus.CLAIMED.value,
    RunStatus.PREPARING.value,
    RunStatus.RUNNING.value,
    RunStatus.VERIFYING.value,
    RunStatus.SCORING.value,
)
TERMINAL_STATUSES = {
    RunStatus.COMPLETED.value,
    RunStatus.FAILED_INFRA.value,
    RunStatus.FAILED_SUBJECT.value,
    RunStatus.CANCELLED.value,
    RunStatus.BUDGET_EXHAUSTED.value,
}
TRANSITIONS = {
    RunStatus.CLAIMED.value: {RunStatus.PREPARING.value},
    RunStatus.PREPARING.value: {RunStatus.RUNNING.value},
    RunStatus.RUNNING.value: {RunStatus.VERIFYING.value},
    RunStatus.VERIFYING.value: {RunStatus.SCORING.value},
}


@dataclass(frozen=True)
class EnqueueResult:
    experiment_id: str
    plan_digest: str
    logical_run_count: int
    created: bool


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    experiment_id: str
    cell_id: str
    slot_id: str
    slot_order: int
    slot: ExperimentRunSlot
    status: RunStatus
    attempt: int
    lease_owner: str | None
    lease_expires_at: datetime | None
    heartbeat_at: datetime | None
    cancellation_requested: bool
    artifact_manifest_path: str | None
    evidence_digest: str | None
    normalized_outcome: StatisticalOutcome | None
    source_outcome: str | None


@dataclass(frozen=True)
class AuthoritativeClaimGate:
    """M.6 configuration injected into the existing executor; it is not a second executor."""

    preflight: UnifiedPreflightReceipt
    specification: UnifiedPreflightSpecification
    estimate: PlanBudgetEstimate
    reservation_scope: ReservationScope
    reservation_scope_id: str
    reservation_units: tuple[ReservationUnit, ...]

    async def claim(
        self,
        session: AsyncSession,
        experiment_id: str,
        owner: str,
        *,
        now: datetime,
        ttl: timedelta,
        slot_ids: Collection[str] | None = None,
    ) -> RunSnapshot | None:
        claimed, _ = await claim_authoritative_run(
            session,
            experiment_id,
            owner,
            now=now,
            ttl=ttl,
            preflight=self.preflight,
            specification=self.specification,
            estimate=self.estimate,
            reservation_scope=self.reservation_scope,
            reservation_scope_id=self.reservation_scope_id,
            reservation_units=self.reservation_units,
            slot_ids=slot_ids,
        )
        return claimed


def _snapshot(run: ExperimentRunRecord) -> RunSnapshot:
    return RunSnapshot(
        run_id=run.run_id,
        experiment_id=run.experiment_id,
        cell_id=run.cell_id,
        slot_id=run.slot_id,
        slot_order=run.slot_order,
        slot=ExperimentRunSlot.model_validate(run.slot_json),
        status=RunStatus(run.status),
        attempt=run.attempt,
        lease_owner=run.lease_owner,
        lease_expires_at=run.lease_expires_at,
        heartbeat_at=run.heartbeat_at,
        cancellation_requested=run.cancellation_requested,
        artifact_manifest_path=run.artifact_manifest_path,
        evidence_digest=run.evidence_digest,
        normalized_outcome=(
            StatisticalOutcome(run.normalized_outcome) if run.normalized_outcome else None
        ),
        source_outcome=run.source_outcome,
    )


async def enqueue_plan(session: AsyncSession, plan: AnyExperimentPlan) -> EnqueueResult:
    existing = await session.get(ExperimentRecord, plan.experiment_id, with_for_update=True)
    if existing is not None:
        if existing.plan_digest != plan.digest:
            raise ExperimentConflict(
                "experiment id already belongs to a different immutable plan digest"
            )
        count = await session.scalar(
            select(func.count())
            .select_from(ExperimentRunRecord)
            .where(ExperimentRunRecord.experiment_id == plan.experiment_id)
        )
        if count != len(plan.run_slots):
            raise ExperimentConflict("persisted plan has an incomplete logical run set")
        return EnqueueResult(plan.experiment_id, plan.digest, int(count or 0), False)

    session.add(
        ExperimentRecord(
            id=plan.experiment_id,
            schema_version=plan.schema_version,
            name=plan.name,
            plan_digest=plan.digest,
            plan_json=plan.model_dump(mode="json"),
            status="queued",
        )
    )
    await session.flush()
    for cell in plan.cells:
        configuration = cell.model_dump(mode="json")
        session.add(
            ExperimentCellRecord(
                experiment_id=plan.experiment_id,
                cell_id=cell.id,
                lane=cell.lane.value,
                configuration_identity=canonical_digest(configuration),
                configuration_json=configuration,
                repeat_target=plan.repeat_count,
            )
        )
    await session.flush()
    for pair in plan.paired_comparisons:
        session.add(
            ExperimentPairRecord(
                experiment_id=plan.experiment_id,
                pair_id=pair.id,
                left_cell_id=pair.left_cell_id,
                right_cell_id=pair.right_cell_id,
                intent=pair.intent.value,
                definition_json=pair.model_dump(mode="json"),
            )
        )
    for ablation in plan.ablations:
        session.add(
            ExperimentAblationRecord(
                experiment_id=plan.experiment_id,
                ablation_id=ablation.id,
                base_cell_id=ablation.base_cell_id,
                variant_cell_id=ablation.variant_cell_id,
                changed_dimension=ablation.changed_dimension,
                definition_json=ablation.model_dump(mode="json"),
            )
        )
    for slot in plan.run_slots:
        session.add(
            ExperimentRunRecord(
                run_id=f"run-{slot.slot_id.removeprefix('sha256:')}",
                experiment_id=plan.experiment_id,
                cell_id=slot.cell_id,
                slot_id=slot.slot_id,
                slot_order=slot.slot_order,
                slot_json=slot.model_dump(mode="json"),
                lane=slot.lane.value,
                task_id=slot.task.task_id,
                task_version=slot.task.task_version,
                task_digest=slot.task.task_digest,
                repeat_index=slot.repeat_index,
                paired_slot_identity=slot.paired_slot_identity,
                status=RunStatus.QUEUED.value,
            )
        )
    await session.flush()
    return EnqueueResult(plan.experiment_id, plan.digest, len(plan.run_slots), True)


async def claim_next_run(
    session: AsyncSession,
    experiment_id: str,
    owner: str,
    *,
    now: datetime,
    ttl: timedelta,
    slot_ids: Collection[str] | None = None,
) -> RunSnapshot | None:
    if not owner or len(owner) > 100:
        raise ValueError("lease owner must be a non-empty bounded identity")
    if ttl <= timedelta(0):
        raise ValueError("lease ttl must be positive")
    reclaimable = and_(
        ExperimentRunRecord.status.in_(ACTIVE_STATUSES),
        ExperimentRunRecord.lease_expires_at <= now,
    )
    filters = [
        ExperimentRunRecord.experiment_id == experiment_id,
        ExperimentRunRecord.cancellation_requested.is_(False),
        or_(ExperimentRunRecord.status == RunStatus.QUEUED.value, reclaimable),
        ~exists().where(ExperimentRunAttemptRecord.run_id == ExperimentRunRecord.run_id),
    ]
    experiment = await session.get(ExperimentRecord, experiment_id)
    if experiment is None:
        return None
    if experiment.schema_version >= 2:
        try:
            plan = load_experiment_plan_payload(experiment.plan_json)
        except ValueError as exc:
            raise ExperimentConflict("persisted experiment plan is invalid") from exc
        if not isinstance(plan, MethodologyV2ExperimentPlan):
            raise ExperimentConflict("schema-v2 experiment lacks methodology-v2 plan")
        blocked_slot_ids = tuple(
            slot_id
            for block in plan.schedule_blocks
            if block.provider_availability is ProviderAvailability.PROVIDER_UNAVAILABLE
            for slot_id in block.slot_ids
        )
        if blocked_slot_ids:
            filters.append(ExperimentRunRecord.slot_id.not_in(blocked_slot_ids))
    if slot_ids is not None:
        selected = tuple(slot_ids)
        if not selected:
            return None
        filters.append(ExperimentRunRecord.slot_id.in_(selected))
    run = await session.scalar(
        select(ExperimentRunRecord)
        .where(*filters)
        .order_by(ExperimentRunRecord.slot_order)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if run is None:
        return None
    run.status = RunStatus.CLAIMED.value
    run.lease_owner = owner
    run.heartbeat_at = now
    run.lease_expires_at = now + ttl
    run.attempt += 1
    run.started_at = run.started_at or now
    await session.flush()
    return _snapshot(run)


async def expire_authoritative_leases(
    session: AsyncSession, experiment_id: str, *, now: datetime
) -> tuple[str, ...]:
    """Terminalize lost physical attempts; never reclaim or create a retry."""

    runs = tuple(
        (
            await session.scalars(
                select(ExperimentRunRecord)
                .where(
                    ExperimentRunRecord.experiment_id == experiment_id,
                    ExperimentRunRecord.status.in_(ACTIVE_STATUSES),
                    ExperimentRunRecord.lease_expires_at <= now,
                    exists().where(ExperimentRunAttemptRecord.run_id == ExperimentRunRecord.run_id),
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    expired: list[str] = []
    for run in runs:
        attempt = await current_attempt_record(session, run.run_id, lock=True)
        if attempt is None or LifecycleState(attempt.current_state) in TERMINAL_STATES:
            continue
        await append_attempt_transition(
            session,
            attempt_id=attempt.attempt_id,
            target=LifecycleState.FAILED_INFRA,
            occurred_at=now,
            reason_code="LEASE_EXPIRED",
        )
        reservation = await durable_reservation_for_attempt(session, attempt.attempt_id)
        if reservation is None:
            raise ExperimentConflict("expired authoritative attempt lacks its reservation")
        reconciled = await session.scalar(
            select(ExperimentAttemptReconciliationRecord.reconciliation_digest).where(
                ExperimentAttemptReconciliationRecord.attempt_id == attempt.attempt_id
            )
        )
        if reconciled is None:
            await reconcile_attempt_resources(
                session,
                attempt_id=attempt.attempt_id,
                reservation=reservation,
                usage=unavailable_resource_usage(),
                evidence_reference=None,
                now=now,
            )
        run.status = RunStatus.FAILED_INFRA.value
        run.lease_owner = None
        run.lease_expires_at = None
        run.heartbeat_at = now
        if attempt.role == "PRIMARY":
            run.normalized_outcome = StatisticalOutcome.INFRA_FAILURE.value
            run.source_outcome = "lease_expired"
            run.failure_detail = "authoritative physical attempt lease expired"
            run.finished_at = now
        expired.append(attempt.attempt_id)
    await session.flush()
    return tuple(expired)


async def claim_authoritative_run(
    session: AsyncSession,
    experiment_id: str,
    owner: str,
    *,
    now: datetime,
    ttl: timedelta,
    preflight: UnifiedPreflightReceipt,
    specification: UnifiedPreflightSpecification,
    estimate: PlanBudgetEstimate,
    reservation_scope: ReservationScope,
    reservation_scope_id: str,
    reservation_units: tuple[ReservationUnit, ...],
    slot_ids: Collection[str] | None = None,
) -> tuple[RunSnapshot | None, DurableBudgetReservationReceipt | None]:
    """Claim one authoritative slot only after exact preflight and durable reservation."""

    if not owner or len(owner) > 100 or ttl <= timedelta(0):
        raise ValueError("authoritative lease owner and ttl must be valid")
    experiment = await session.get(ExperimentRecord, experiment_id, with_for_update=True)
    if experiment is None:
        return None, None
    expected_specification = specification.specification_digest
    if (
        preflight.status is not UnifiedPreflightStatus.READY
        or preflight.specification.artifact_digest != expected_specification
        or preflight.candidate_plan.artifact_digest != experiment.plan_digest
        or preflight.target_material != specification.target_material
        or preflight.methodology != specification.methodology
        or preflight.budget_estimate != estimate
    ):
        raise ExperimentConflict("authoritative claim requires exact READY M.5 evidence")
    durable_scope = await session.get(BudgetScopeLedgerRecord, reservation_scope_id)
    if (
        durable_scope is None
        or durable_scope.plan_digest != experiment.plan_digest
        or durable_scope.preflight_digest != preflight.receipt_digest
        or durable_scope.budget_estimate_digest != estimate.estimate_digest
        or durable_scope.stage != preflight.target_stage.value
        or durable_scope.scope != reservation_scope.value
    ):
        raise ExperimentConflict("authoritative claim requires exact durable M.5 binding")
    if await control_state(session, experiment_id) is not ControlState.ACTIVE:
        return None, None
    await expire_authoritative_leases(session, experiment_id, now=now)
    filters = [
        ExperimentRunRecord.experiment_id == experiment_id,
        ExperimentRunRecord.status == RunStatus.QUEUED.value,
        ExperimentRunRecord.cancellation_requested.is_(False),
        exists().where(
            ExperimentRunAttemptRecord.run_id == ExperimentRunRecord.run_id,
            ExperimentRunAttemptRecord.current_state == LifecycleState.QUEUED.value,
        ),
    ]
    if slot_ids is not None:
        selected = tuple(slot_ids)
        if not selected:
            return None, None
        filters.append(ExperimentRunRecord.slot_id.in_(selected))
    run = await session.scalar(
        select(ExperimentRunRecord)
        .where(*filters)
        .order_by(ExperimentRunRecord.slot_order)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if run is None:
        return None, None
    attempt = await current_attempt_record(session, run.run_id, lock=True)
    if attempt is None or attempt.current_state != LifecycleState.QUEUED.value:
        raise ExperimentConflict("authoritative claim lacks an eligible physical attempt")
    units = {item.logical_unit_id: item for item in reservation_units}
    unit = units.get(run.slot_id)
    if unit is None:
        raise ExperimentConflict("authoritative claim lacks an exact reservation unit")
    request = build_reservation_request(
        request_id=f"claim-{attempt.attempt_id.removeprefix('sha256:')[:32]}",
        plan=preflight.candidate_plan,
        stage=preflight.target_stage,
        scope=reservation_scope,
        scope_id=reservation_scope_id,
        unit=unit,
        budget_estimate=estimate,
    )
    reservation = await reserve_budget(
        session, request=request, estimate=estimate, unit=unit, now=now
    )
    attempt.reservation_digest = reservation.receipt_digest
    if reservation.decision is ReservationDecision.DENIED:
        await append_attempt_transition(
            session,
            attempt_id=attempt.attempt_id,
            target=LifecycleState.BUDGET_EXHAUSTED,
            occurred_at=now,
            reason_code="CAMPAIGN_OR_STAGE_BUDGET_EXHAUSTED",
        )
        run.status = RunStatus.BUDGET_EXHAUSTED.value
        run.finished_at = now
        run.source_outcome = "campaign_or_stage_budget_exhausted"
        await session.flush()
        return None, reservation
    run.status = RunStatus.CLAIMED.value
    run.lease_owner = owner
    run.heartbeat_at = now
    run.lease_expires_at = now + ttl
    run.attempt = attempt.attempt_number
    run.started_at = run.started_at or now
    await session.flush()
    return _snapshot(run), reservation


async def _locked_run(session: AsyncSession, run_id: str) -> ExperimentRunRecord:
    run = await session.scalar(
        select(ExperimentRunRecord).where(ExperimentRunRecord.run_id == run_id).with_for_update()
    )
    if run is None:
        raise ExperimentConflict("experiment run does not exist")
    return run


def _require_active_owner(run: ExperimentRunRecord, owner: str, now: datetime) -> None:
    if run.lease_owner != owner:
        raise ExperimentConflict("only the active lease owner may mutate this run")
    if run.lease_expires_at is None or run.lease_expires_at <= now:
        raise ExperimentConflict("expired experiment lease cannot be used")


async def heartbeat_run(
    session: AsyncSession,
    run_id: str,
    owner: str,
    *,
    now: datetime,
    ttl: timedelta,
) -> RunSnapshot:
    if ttl <= timedelta(0):
        raise ValueError("lease ttl must be positive")
    run = await _locked_run(session, run_id)
    _require_active_owner(run, owner, now)
    if run.status not in ACTIVE_STATUSES:
        raise ExperimentConflict("terminal or queued run cannot heartbeat")
    authoritative = await current_attempt_record(session, run_id, lock=True)
    if run.cancellation_requested:
        if authoritative is not None:
            await append_attempt_transition(
                session,
                attempt_id=authoritative.attempt_id,
                target=LifecycleState.CANCELLED,
                occurred_at=now,
                reason_code="OPERATOR_CANCELLED",
            )
        run.status = RunStatus.CANCELLED.value
        run.normalized_outcome = StatisticalOutcome.CANCELLED.value
        run.source_outcome = "cancellation_requested"
        run.finished_at = now
        run.lease_owner = None
        run.lease_expires_at = None
        run.heartbeat_at = now
    else:
        run.heartbeat_at = now
        run.lease_expires_at = now + ttl
    await session.flush()
    return _snapshot(run)


async def release_run(
    session: AsyncSession, run_id: str, owner: str, *, now: datetime
) -> RunSnapshot:
    run = await _locked_run(session, run_id)
    _require_active_owner(run, owner, now)
    if await current_attempt_record(session, run_id, lock=True) is not None:
        raise ExperimentConflict("authoritative attempts cannot be released and silently reused")
    if run.status not in ACTIVE_STATUSES:
        raise ExperimentConflict("terminal or queued run cannot be released")
    run.status = RunStatus.QUEUED.value
    run.lease_owner = None
    run.lease_expires_at = None
    run.heartbeat_at = now
    await session.flush()
    return _snapshot(run)


async def request_run_cancellation(
    session: AsyncSession, run_id: str, *, now: datetime
) -> RunSnapshot:
    run = await _locked_run(session, run_id)
    authoritative = await current_attempt_record(session, run_id, lock=True)
    run.cancellation_requested = True
    if run.status == RunStatus.QUEUED.value:
        if authoritative is not None:
            await append_attempt_transition(
                session,
                attempt_id=authoritative.attempt_id,
                target=LifecycleState.CANCELLED,
                occurred_at=now,
                reason_code="OPERATOR_CANCELLED",
            )
        run.status = RunStatus.CANCELLED.value
        run.normalized_outcome = StatisticalOutcome.CANCELLED.value
        run.source_outcome = "cancellation_requested"
        run.finished_at = now
    await session.flush()
    return _snapshot(run)


async def requeue_failed_infra_after_repair(
    session: AsyncSession,
    run_id: str,
    *,
    expected_source_outcome: str,
    expected_failure_detail: str,
) -> RunSnapshot:
    """Authorize one new physical attempt without changing the logical slot or old artifacts."""

    run = await _locked_run(session, run_id)
    if await current_attempt_record(session, run_id, lock=True) is not None:
        raise ExperimentConflict("authoritative recovery requires a new immutable physical attempt")
    experiment = await session.get(ExperimentRecord, run.experiment_id)
    if experiment is None:
        raise ExperimentConflict("experiment does not exist")
    if experiment.schema_version >= 2:
        raise ExperimentConflict("methodology v2 recovery requires immutable new attempt evidence")
    if (
        run.status != RunStatus.FAILED_INFRA.value
        or run.normalized_outcome != StatisticalOutcome.INFRA_FAILURE.value
        or run.source_outcome != expected_source_outcome
        or run.failure_detail != expected_failure_detail
        or run.attempt < 1
        or run.artifact_manifest_path is not None
        or run.evidence_digest is not None
    ):
        raise ExperimentConflict("run is not the exact repair-affected infrastructure failure")
    run.status = RunStatus.QUEUED.value
    run.normalized_outcome = None
    run.source_outcome = None
    run.failure_detail = None
    run.duration_ms = None
    run.input_tokens = None
    run.output_tokens = None
    run.tool_calls = None
    run.steps = None
    run.explicit_cost = None
    run.lease_owner = None
    run.lease_expires_at = None
    run.heartbeat_at = None
    run.started_at = None
    run.finished_at = None
    await session.flush()
    return _snapshot(run)


async def transition_run(
    session: AsyncSession,
    run_id: str,
    owner: str,
    status: RunStatus,
    *,
    now: datetime,
) -> RunSnapshot:
    run = await _locked_run(session, run_id)
    _require_active_owner(run, owner, now)
    authoritative = await current_attempt_record(session, run_id, lock=True)
    if run.cancellation_requested:
        if authoritative is not None:
            await append_attempt_transition(
                session,
                attempt_id=authoritative.attempt_id,
                target=LifecycleState.CANCELLED,
                occurred_at=now,
                reason_code="OPERATOR_CANCELLED",
            )
        run.status = RunStatus.CANCELLED.value
        run.normalized_outcome = StatisticalOutcome.CANCELLED.value
        run.source_outcome = "cancellation_requested"
        run.finished_at = now
        run.lease_owner = None
        run.lease_expires_at = None
        run.heartbeat_at = now
    elif status.value not in TRANSITIONS.get(run.status, set()):
        raise ExperimentConflict(f"invalid run lifecycle transition: {run.status}->{status.value}")
    else:
        run.status = status.value
        target = {
            RunStatus.PREPARING: LifecycleState.PREPARING,
            RunStatus.RUNNING: LifecycleState.RUNNING,
            RunStatus.VERIFYING: LifecycleState.VERIFYING,
        }.get(status)
        if authoritative is not None and target is not None:
            await append_attempt_transition(
                session,
                attempt_id=authoritative.attempt_id,
                target=target,
                occurred_at=now,
            )
    await session.flush()
    return _snapshot(run)


async def finish_run(
    session: AsyncSession,
    run_id: str,
    owner: str,
    *,
    now: datetime,
    normalized_outcome: StatisticalOutcome,
    source_outcome: str,
    artifact_manifest_path: str | None,
    evidence_digest: str | None,
    failure_detail: str | None = None,
    duration_ms: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    tool_calls: int | None = None,
    steps: int | None = None,
) -> RunSnapshot:
    run = await _locked_run(session, run_id)
    _require_active_owner(run, owner, now)
    if run.status != RunStatus.SCORING.value:
        raise ExperimentConflict("a run may finish only after scoring")
    if run.cancellation_requested:
        normalized_outcome = StatisticalOutcome.CANCELLED
        source_outcome = "cancellation_requested"
        artifact_manifest_path = None
        evidence_digest = None
        failure_detail = None
    terminal = terminal_status_for_outcome(normalized_outcome)
    authoritative = await current_attempt_record(session, run_id, lock=True)
    if authoritative is not None:
        reconciled = await session.scalar(
            select(ExperimentAttemptReconciliationRecord.reconciliation_digest).where(
                ExperimentAttemptReconciliationRecord.attempt_id == authoritative.attempt_id
            )
        )
        if reconciled is None:
            raise ExperimentConflict(
                "authoritative attempt resources must reconcile before terminal outcome"
            )
        lifecycle_terminal = {
            StatisticalOutcome.CAPABILITY_PASS: LifecycleState.COMPLETED,
            StatisticalOutcome.CAPABILITY_FAIL: LifecycleState.FAILED_CAPABILITY,
            StatisticalOutcome.INFRA_FAILURE: LifecycleState.FAILED_INFRA,
            StatisticalOutcome.CANCELLED: LifecycleState.CANCELLED,
        }[normalized_outcome]
        await append_attempt_transition(
            session,
            attempt_id=authoritative.attempt_id,
            target=lifecycle_terminal,
            occurred_at=now,
            reason_code=(
                None
                if lifecycle_terminal is LifecycleState.COMPLETED
                else source_outcome.upper()[:100]
            ),
        )
        authoritative.artifact_manifest_path = artifact_manifest_path
        authoritative.evidence_digest = evidence_digest
    run.status = terminal.value
    if authoritative is None or authoritative.role == "PRIMARY":
        run.normalized_outcome = normalized_outcome.value
        run.source_outcome = source_outcome
        run.artifact_manifest_path = artifact_manifest_path
        run.evidence_digest = evidence_digest
        run.failure_detail = failure_detail
        run.duration_ms = duration_ms
        run.input_tokens = input_tokens
        run.output_tokens = output_tokens
        run.tool_calls = tool_calls
        run.steps = steps
    run.finished_at = now
    run.lease_owner = None
    run.lease_expires_at = None
    run.heartbeat_at = now
    await session.flush()
    return _snapshot(run)


async def inspect_run(session: AsyncSession, run_id: str) -> RunSnapshot:
    run = await session.get(ExperimentRunRecord, run_id)
    if run is None:
        raise ExperimentConflict("experiment run does not exist")
    return _snapshot(run)
