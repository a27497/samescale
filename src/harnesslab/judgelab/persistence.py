from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.db.models.judgelab import JudgeCalibrationRecord, JudgeEvaluationRecord
from harnesslab.judgelab.models import JudgeCalibrationPlan, JudgeEvaluationSlot, JudgeEvidence


class JudgePersistenceError(RuntimeError):
    """Immutable calibration or evaluation persistence was violated."""


@dataclass(frozen=True)
class JudgeEnqueueResult:
    calibration_id: str
    plan_digest: str
    slot_count: int
    created: bool


async def enqueue_calibration(
    session: AsyncSession, plan: JudgeCalibrationPlan
) -> JudgeEnqueueResult:
    existing = await session.get(JudgeCalibrationRecord, plan.calibration_id, with_for_update=True)
    if existing is not None:
        if existing.plan_digest != plan.plan_digest:
            raise JudgePersistenceError("calibration id already belongs to another immutable plan")
        count = await session.scalar(
            select(func.count())
            .select_from(JudgeEvaluationRecord)
            .where(JudgeEvaluationRecord.calibration_id == plan.calibration_id)
        )
        if count != len(plan.slots):
            raise JudgePersistenceError("persisted calibration has an incomplete slot set")
        return JudgeEnqueueResult(plan.calibration_id, plan.plan_digest, int(count or 0), False)
    session.add(
        JudgeCalibrationRecord(
            id=plan.calibration_id,
            schema_version=plan.schema_version,
            plan_digest=plan.plan_digest,
            plan_json=plan.model_dump(mode="json"),
            status="running",
            started_at=datetime.now(UTC),
        )
    )
    await session.flush()
    cells = {cell.id: cell for cell in plan.judge_cells}
    for slot in plan.slots:
        cell = cells[slot.judge_cell_id]
        session.add(
            JudgeEvaluationRecord(
                evaluation_id=f"eval-{slot.slot_id.removeprefix('sha256:')}",
                calibration_id=plan.calibration_id,
                judge_cell_id=slot.judge_cell_id,
                case_id=slot.case_id,
                repeat_index=slot.repeat_index,
                order_variant=slot.order_variant.value,
                slot_id=slot.slot_id,
                slot_order=slot.slot_order,
                slot_json=slot.model_dump(mode="json"),
                status="queued",
                requested_judge_model=cell.model_profile.requested_model,
            )
        )
    await session.flush()
    return JudgeEnqueueResult(plan.calibration_id, plan.plan_digest, len(plan.slots), True)


async def pending_slots(
    session: AsyncSession, calibration_id: str
) -> tuple[JudgeEvaluationSlot, ...]:
    rows = (
        await session.scalars(
            select(JudgeEvaluationRecord)
            .where(
                JudgeEvaluationRecord.calibration_id == calibration_id,
                JudgeEvaluationRecord.status == "queued",
            )
            .order_by(JudgeEvaluationRecord.slot_order)
        )
    ).all()
    return tuple(JudgeEvaluationSlot.model_validate(row.slot_json) for row in rows)


async def persist_evidence_reference(
    session: AsyncSession,
    *,
    slot: JudgeEvaluationSlot,
    path: str | None,
    evidence: JudgeEvidence,
) -> None:
    record = await session.get(JudgeEvaluationRecord, evidence.evaluation_id, with_for_update=True)
    if record is None or record.slot_id != slot.slot_id:
        raise JudgePersistenceError("Judge evaluation slot identity is unavailable")
    if record.status == "completed":
        if (
            record.artifact_digest != evidence.artifact_digest
            or record.artifact_manifest_path != path
        ):
            raise JudgePersistenceError("completed Judge evaluation is immutable")
        return
    record.status = "completed"
    record.outcome = evidence.outcome.value
    record.artifact_manifest_path = path
    record.artifact_digest = evidence.artifact_digest
    record.observed_judge_model = evidence.observed_judge_model
    record.finished_at = datetime.now(UTC)
    await session.flush()


async def complete_calibration(
    session: AsyncSession,
    calibration_id: str,
    *,
    report_json_path: str,
    report_markdown_path: str,
    report_digest: str,
) -> None:
    record = await session.get(JudgeCalibrationRecord, calibration_id, with_for_update=True)
    if record is None:
        raise JudgePersistenceError("calibration does not exist")
    record.status = "completed"
    record.report_json_path = report_json_path
    record.report_markdown_path = report_markdown_path
    record.report_digest = report_digest
    record.finished_at = datetime.now(UTC)
    await session.flush()


async def evaluation_records(
    session: AsyncSession, calibration_id: str
) -> tuple[JudgeEvaluationRecord, ...]:
    return tuple(
        (
            await session.scalars(
                select(JudgeEvaluationRecord)
                .where(JudgeEvaluationRecord.calibration_id == calibration_id)
                .order_by(JudgeEvaluationRecord.slot_order)
            )
        ).all()
    )
