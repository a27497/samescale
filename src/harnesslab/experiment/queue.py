from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.run import RunStatus
from harnesslab.db.models.experiment import (
    ExperimentAblationRecord,
    ExperimentCellRecord,
    ExperimentPairRecord,
    ExperimentRecord,
    ExperimentRunRecord,
)
from harnesslab.experiment.outcomes import StatisticalOutcome, terminal_status_for_outcome
from harnesslab.experiment.plan import ExperimentPlan, ExperimentRunSlot


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


async def enqueue_plan(session: AsyncSession, plan: ExperimentPlan) -> EnqueueResult:
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
) -> RunSnapshot | None:
    if not owner or len(owner) > 100:
        raise ValueError("lease owner must be a non-empty bounded identity")
    if ttl <= timedelta(0):
        raise ValueError("lease ttl must be positive")
    reclaimable = and_(
        ExperimentRunRecord.status.in_(ACTIVE_STATUSES),
        ExperimentRunRecord.lease_expires_at <= now,
    )
    run = await session.scalar(
        select(ExperimentRunRecord)
        .where(
            ExperimentRunRecord.experiment_id == experiment_id,
            ExperimentRunRecord.cancellation_requested.is_(False),
            or_(ExperimentRunRecord.status == RunStatus.QUEUED.value, reclaimable),
        )
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
    if run.cancellation_requested:
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
    run.cancellation_requested = True
    if run.status == RunStatus.QUEUED.value:
        run.status = RunStatus.CANCELLED.value
        run.normalized_outcome = StatisticalOutcome.CANCELLED.value
        run.source_outcome = "cancellation_requested"
        run.finished_at = now
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
    if run.cancellation_requested:
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
    run.status = terminal.value
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
