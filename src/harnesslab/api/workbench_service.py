from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.api.workbench_models import (
    ComparabilityValue,
    CoreReadinessResponse,
    ExperimentCell,
    ExperimentDetail,
    ExperimentListResponse,
    ExperimentReportResponse,
    ExperimentStatusResponse,
    ExperimentSummary,
    ExperimentTask,
    IntegerEvidence,
    JudgeCalibrationDetail,
    JudgeCalibrationListResponse,
    JudgeCalibrationSummary,
    JudgeCellDetail,
    MatrixMetricSet,
    MatrixPoint,
    MatrixResponse,
    NumericEvidence,
    ReadinessCheck,
    RegressionCellComparison,
    RegressionCompareRequest,
    RegressionCompareResponse,
    RunDetail,
    RunListResponse,
    RunSummary,
    TraceEvent,
    TraceResponse,
)
from harnesslab.contracts.run import RunStatus
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.models.judgelab import JudgeCalibrationRecord
from harnesslab.experiment.plan import ExperimentPlan
from harnesslab.experiment.report import (
    ExperimentReport,
    ExperimentReportError,
    build_experiment_report,
)
from harnesslab.harness_lane.models import NormalizedTrace
from harnesslab.judgelab.report import JudgeCalibrationReport
from harnesslab.sandbox.artifacts import sha256_file

TERMINAL_RUN_STATUSES = {
    RunStatus.COMPLETED.value,
    RunStatus.FAILED_INFRA.value,
    RunStatus.FAILED_SUBJECT.value,
    RunStatus.CANCELLED.value,
}
TERMINAL_EXPERIMENT_STATUSES = {"completed", "failed", "cancelled"}
COMPARABILITY_ORDER: dict[str, int] = {
    "COMPARABLE": 0,
    "PARTIALLY_COMPARABLE": 1,
    "NOT_COMPARABLE": 2,
}


def numeric(value: object) -> NumericEvidence:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return NumericEvidence(status="REPORTED", value=float(value))
    return NumericEvidence(status="NOT_REPORTED", value=None)


def integer(value: object) -> IntegerEvidence:
    if isinstance(value, int) and not isinstance(value, bool):
        return IntegerEvidence(status="REPORTED", value=value)
    return IntegerEvidence(status="NOT_REPORTED", value=None)


def _comparability_value(value: str) -> ComparabilityValue:
    if value == "COMPARABLE":
        return "COMPARABLE"
    if value == "PARTIALLY_COMPARABLE":
        return "PARTIALLY_COMPARABLE"
    if value == "NOT_COMPARABLE":
        return "NOT_COMPARABLE"
    raise WorkbenchAPIError(409, "ARTIFACT_INTEGRITY_ERROR", "invalid comparability value")


def _plan(record: ExperimentRecord) -> ExperimentPlan:
    try:
        plan = ExperimentPlan.model_validate(record.plan_json)
    except ValidationError as exc:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "experiment plan is invalid"
        ) from exc
    if plan.digest != record.plan_digest or plan.experiment_id != record.id:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "experiment plan identity does not match"
        )
    return plan


async def _experiment(session: AsyncSession, experiment_id: str) -> ExperimentRecord:
    record = await session.get(ExperimentRecord, experiment_id)
    if record is None:
        raise WorkbenchAPIError(404, "NOT_FOUND", "experiment does not exist")
    return record


async def _report(session: AsyncSession, experiment_id: str) -> ExperimentReport:
    try:
        return await build_experiment_report(session, experiment_id)
    except ExperimentReportError as exc:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "experiment report evidence is unavailable"
        ) from exc


async def _run_counts(
    session: AsyncSession, experiment_ids: tuple[str, ...]
) -> dict[str, Counter[str]]:
    if not experiment_ids:
        return {}
    rows = (
        await session.execute(
            select(
                ExperimentRunRecord.experiment_id,
                ExperimentRunRecord.status,
                ExperimentRunRecord.normalized_outcome,
                func.count(),
            )
            .where(ExperimentRunRecord.experiment_id.in_(experiment_ids))
            .group_by(
                ExperimentRunRecord.experiment_id,
                ExperimentRunRecord.status,
                ExperimentRunRecord.normalized_outcome,
            )
        )
    ).all()
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for experiment_id, status, outcome, count in rows:
        counts[str(experiment_id)][f"status:{status}"] += int(count)
        if outcome is not None:
            counts[str(experiment_id)][f"outcome:{outcome}"] += int(count)
        counts[str(experiment_id)]["total"] += int(count)
    return counts


def _summary(
    record: ExperimentRecord, plan: ExperimentPlan, counts: Counter[str]
) -> ExperimentSummary:
    capability = counts["outcome:capability_pass"] + counts["outcome:capability_fail"]
    return ExperimentSummary(
        experiment_id=record.id,
        name=record.name,
        status=record.status,
        plan_digest=record.plan_digest,
        cell_count=len(plan.cells),
        task_count=len(plan.tasks),
        planned_run_count=len(plan.run_slots),
        completed_capability_count=capability,
        infra_count=counts["outcome:infra_failure"],
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


async def list_experiments(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status_filter: str | None,
    search: str | None,
) -> ExperimentListResponse:
    filters: list[ColumnElement[bool]] = []
    if status_filter:
        filters.append(ExperimentRecord.status == status_filter)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(ExperimentRecord.id.ilike(pattern), ExperimentRecord.name.ilike(pattern))
        )
    statement: Select[tuple[ExperimentRecord]] = select(ExperimentRecord)
    total_statement = select(func.count()).select_from(ExperimentRecord)
    for condition in filters:
        statement = statement.where(condition)
        total_statement = total_statement.where(condition)
    records = tuple(
        (
            await session.scalars(
                statement.order_by(ExperimentRecord.created_at.desc()).limit(limit).offset(offset)
            )
        ).all()
    )
    counts = await _run_counts(session, tuple(record.id for record in records))
    total = int(await session.scalar(total_statement) or 0)
    return ExperimentListResponse(
        items=tuple(
            _summary(record, _plan(record), counts.get(record.id, Counter())) for record in records
        ),
        total=total,
        limit=limit,
        offset=offset,
    )


async def experiment_detail(session: AsyncSession, experiment_id: str) -> ExperimentDetail:
    record = await _experiment(session, experiment_id)
    plan = _plan(record)
    counts = (await _run_counts(session, (record.id,))).get(record.id, Counter())
    summary = _summary(record, plan, counts)
    report: ExperimentReport | None = None
    if record.status in TERMINAL_EXPERIMENT_STATUSES:
        report = await _report(session, experiment_id)
    comparability = Counter[str]()
    if report is not None:
        comparability.update(item.comparability.value for item in report.pair_evidence)
    return ExperimentDetail(
        **summary.model_dump(),
        repeat_count=plan.repeat_count,
        execution_seed=plan.execution_seed,
        evidence_tiers=(tuple(cell.evidence_tier.value for cell in report.cells) if report else ()),
        comparability_summary=dict(sorted(comparability.items())),
        report_digest=report.digest if report else None,
        cells=tuple(
            ExperimentCell(
                cell_id=cell.id,
                lane=cell.lane.value,
                requested_model=cell.requested_model,
                provider_route=cell.provider_route,
                harness=cell.harness,
                harness_version=cell.harness_version,
                repeat_target=plan.repeat_count,
            )
            for cell in plan.cells
        ),
        tasks=tuple(
            ExperimentTask(
                task_id=task.task_id,
                task_version=task.task_version,
                task_digest=task.task_digest,
            )
            for task in plan.tasks
        ),
    )


async def experiment_status(session: AsyncSession, experiment_id: str) -> ExperimentStatusResponse:
    record = await _experiment(session, experiment_id)
    rows = (
        await session.execute(
            select(ExperimentRunRecord.status, func.count())
            .where(ExperimentRunRecord.experiment_id == experiment_id)
            .group_by(ExperimentRunRecord.status)
        )
    ).all()
    return ExperimentStatusResponse(
        experiment_id=record.id,
        status=record.status,
        terminal=record.status in TERMINAL_EXPERIMENT_STATUSES,
        run_status_counts={str(status): int(count) for status, count in rows},
        refreshed_at=datetime.now(UTC),
    )


def _cell_comparability(
    plan: ExperimentPlan, report: ExperimentReport
) -> dict[str, tuple[ComparabilityValue, tuple[str, ...]]]:
    pair_cells = {
        pair.id: (pair.left_cell_id, pair.right_cell_id) for pair in plan.paired_comparisons
    }
    pair_cells.update(
        {
            f"ablation-{ablation.id}": (ablation.base_cell_id, ablation.variant_cell_id)
            for ablation in plan.ablations
        }
    )
    statuses: dict[str, list[str]] = defaultdict(list)
    reasons: dict[str, set[str]] = defaultdict(set)
    for item in report.pair_evidence:
        for cell_id in pair_cells.get(item.pair_id, ()):
            statuses[cell_id].append(item.comparability.value)
            reasons[cell_id].update(item.reason_codes)
    result: dict[str, tuple[ComparabilityValue, tuple[str, ...]]] = {}
    for cell in plan.cells:
        values = statuses.get(cell.id, ["COMPARABLE"])
        worst = max(values, key=COMPARABILITY_ORDER.__getitem__)
        result[cell.id] = (cast(ComparabilityValue, worst), tuple(sorted(reasons[cell.id])))
    return result


async def matrix(session: AsyncSession, experiment_id: str) -> MatrixResponse:
    record = await _experiment(session, experiment_id)
    plan = _plan(record)
    report = await _report(session, experiment_id)
    by_cell = {cell.cell_id: cell for cell in report.cells}
    comparability = _cell_comparability(plan, report)
    single_task = len(plan.tasks) == 1
    points: list[MatrixPoint] = []
    for task in plan.tasks:
        for planned_cell in plan.cells:
            cell = by_cell[planned_cell.id]
            task_evidence = next(
                item for item in cell.per_task_evidence if item.task_id == task.task_id
            )
            reported = single_task
            point_metrics = MatrixMetricSet(
                success_rate=numeric(cell.success_rate if reported else None),
                latency_p50_ms=numeric(cell.latency_ms.p50 if reported else None),
                latency_p95_ms=numeric(cell.latency_ms.p95 if reported else None),
                infra_rate=numeric(cell.infra_failure_rate if reported else None),
                pass_at_1=numeric(cell.pass_at_k.get("pass@1") if reported else None),
                pass_at_3=numeric(cell.pass_at_k.get("pass@3") if reported else None),
                pass_at_5=numeric(cell.pass_at_k.get("pass@5") if reported else None),
            )
            status, reasons = comparability[planned_cell.id]
            points.append(
                MatrixPoint(
                    task_id=task.task_id,
                    cell_id=planned_cell.id,
                    n=task_evidence.capability_observations,
                    tier=task_evidence.evidence_tier.value,
                    comparability=status,
                    reason_codes=reasons,
                    metrics=point_metrics,
                )
            )
    return MatrixResponse(
        experiment_id=record.id,
        plan_digest=record.plan_digest,
        report_digest=report.digest,
        tasks=tuple(task.task_id for task in plan.tasks),
        cells=tuple(cell.id for cell in plan.cells),
        points=tuple(points),
        infra_count=sum(cell.infra_failures for cell in report.cells),
    )


async def experiment_report(session: AsyncSession, experiment_id: str) -> ExperimentReportResponse:
    report = await _report(session, experiment_id)
    return ExperimentReportResponse(
        experiment_id=report.experiment_id,
        plan_digest=report.plan_digest,
        report_digest=report.digest,
        planned_runs=report.plan_run_count,
        formal_ranking=report.formal_ranking,
        formal_ranking_note=report.formal_ranking_note,
        cells=tuple(cast(dict[str, object], cell.model_dump(mode="json")) for cell in report.cells),
        pairs=tuple(cast(dict[str, object], pair.model_dump(mode="json")) for pair in report.pairs),
    )


def _run_summary(run: ExperimentRunRecord) -> RunSummary:
    return RunSummary(
        run_id=run.run_id,
        experiment_id=run.experiment_id,
        cell_id=run.cell_id,
        task_id=run.task_id,
        task_version=run.task_version,
        lane=run.lane,
        repeat_index=run.repeat_index,
        status=run.status,
        normalized_outcome=run.normalized_outcome,
        attempt=run.attempt,
        duration_ms=integer(run.duration_ms),
    )


async def list_runs(
    session: AsyncSession,
    experiment_id: str,
    *,
    limit: int,
    offset: int,
    cell: str | None,
    task: str | None,
    lane: str | None,
    status_filter: str | None,
    outcome: str | None,
) -> RunListResponse:
    await _experiment(session, experiment_id)
    filters = [ExperimentRunRecord.experiment_id == experiment_id]
    if cell:
        filters.append(ExperimentRunRecord.cell_id == cell)
    if task:
        filters.append(ExperimentRunRecord.task_id == task)
    if lane:
        filters.append(ExperimentRunRecord.lane == lane)
    if status_filter:
        filters.append(ExperimentRunRecord.status == status_filter)
    if outcome:
        filters.append(ExperimentRunRecord.normalized_outcome == outcome)
    statement = select(ExperimentRunRecord).where(*filters)
    runs = tuple(
        (
            await session.scalars(
                statement.order_by(ExperimentRunRecord.slot_order).limit(limit).offset(offset)
            )
        ).all()
    )
    total = int(
        await session.scalar(select(func.count()).select_from(ExperimentRunRecord).where(*filters))
        or 0
    )
    return RunListResponse(
        items=tuple(_run_summary(run) for run in runs), total=total, limit=limit, offset=offset
    )


def _safe_manifest(run: ExperimentRunRecord) -> tuple[dict[str, Any], Path]:
    if run.artifact_manifest_path is None or run.evidence_digest is None:
        raise WorkbenchAPIError(409, "ARTIFACT_UNAVAILABLE", "run artifact is not reported")
    manifest_path = Path(run.artifact_manifest_path)
    try:
        if not manifest_path.is_file() or sha256_file(manifest_path) != run.evidence_digest:
            raise WorkbenchAPIError(
                409, "ARTIFACT_INTEGRITY_ERROR", "run artifact digest does not match"
            )
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except WorkbenchAPIError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "run artifact cannot be verified"
        ) from exc
    suffix = f"-a{run.attempt}"
    expected_run_id = f"{run.run_id}{suffix}"
    if len(expected_run_id) > 100:
        identity_digest = hashlib.sha256(expected_run_id.encode()).hexdigest()[:16]
        prefix_length = 100 - len(suffix) - len(identity_digest) - 1
        expected_run_id = f"{run.run_id[:prefix_length]}-{identity_digest}{suffix}"
    if not isinstance(raw, dict) or raw.get("run_id") != expected_run_id:
        raise WorkbenchAPIError(409, "ARTIFACT_INTEGRITY_ERROR", "run artifact identity mismatch")
    return raw, manifest_path.resolve()


async def run_detail(session: AsyncSession, run_id: str) -> RunDetail:
    run = await session.get(ExperimentRunRecord, run_id)
    if run is None:
        raise WorkbenchAPIError(404, "NOT_FOUND", "run does not exist")
    raw: dict[str, Any] = {}
    if run.artifact_manifest_path is not None or run.evidence_digest is not None:
        raw, _ = _safe_manifest(run)
    slot = run.slot_json
    verifier = raw.get("verifier_sandbox_manifest")
    verifier_passed = raw.get("verifier_passed")
    verifier_score = raw.get("verifier_score")
    if not isinstance(verifier, dict):
        verifier = {}
    report = (
        await _report(session, run.experiment_id) if run.status in TERMINAL_RUN_STATUSES else None
    )
    comparison_status: ComparabilityValue | None = None
    reason_codes: set[str] = set()
    if report is not None:
        evidence = [
            item
            for item in report.pair_evidence
            if run.run_id in {item.left_run_id, item.right_run_id}
        ]
        if evidence:
            selected: ComparabilityValue = "COMPARABLE"
            for item in evidence:
                value = _comparability_value(item.comparability.value)
                if COMPARABILITY_ORDER[value] > COMPARABILITY_ORDER[selected]:
                    selected = value
            comparison_status = selected
            reason_codes.update(code for item in evidence for code in item.reason_codes)
    observed_model = raw.get("observed_model")
    trace_coverage = raw.get("trace_coverage")
    summary = raw.get("summary")
    return RunDetail(
        **_run_summary(run).model_dump(),
        slot_id=run.slot_id,
        source_outcome=run.source_outcome,
        requested_model=cast(str | None, slot.get("requested_model")),
        observed_model=observed_model if isinstance(observed_model, str) else None,
        provider_route=cast(str | None, slot.get("provider_route")),
        harness=cast(str | None, slot.get("harness")),
        harness_version=cast(str | None, slot.get("harness_version")),
        trace_coverage=trace_coverage if isinstance(trace_coverage, str) else None,
        evidence_digest=run.evidence_digest,
        artifact_name="manifest.json" if run.artifact_manifest_path else None,
        verifier_passed=verifier_passed if isinstance(verifier_passed, bool) else None,
        verifier_score=numeric(verifier_score),
        summary=summary if isinstance(summary, str) else None,
        input_tokens=integer(run.input_tokens),
        output_tokens=integer(run.output_tokens),
        explicit_cost=numeric(run.explicit_cost),
        comparability=comparison_status,
        comparability_reason_codes=tuple(sorted(reason_codes)),
    )


def _trace_summary(event: dict[str, Any]) -> str | None:
    event_type = event.get("type")
    if event_type == "REASONING_PRESENT":
        return "Reasoning was present; private content is withheld."
    for key in ("text", "command", "public_output", "native_event_type"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value[:500]
    return None


async def trace_detail(session: AsyncSession, run_id: str) -> TraceResponse:
    run = await session.get(ExperimentRunRecord, run_id)
    if run is None:
        raise WorkbenchAPIError(404, "NOT_FOUND", "run does not exist")
    if run.artifact_manifest_path is None and run.evidence_digest is None:
        return TraceResponse(
            run_id=run_id,
            status="NOT_REPORTED",
            coverage=None,
            trace_digest=None,
            events=(),
        )
    raw, manifest_path = _safe_manifest(run)
    trace_digest = raw.get("normalized_trace_digest")
    coverage = raw.get("trace_coverage")
    if not isinstance(trace_digest, str):
        return TraceResponse(
            run_id=run_id,
            status="NOT_REPORTED",
            coverage=coverage if isinstance(coverage, str) else None,
            trace_digest=None,
            events=(),
        )
    root = manifest_path.parent
    trace_path = (root / "trace" / "normalized.json").resolve()
    if root not in trace_path.parents:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "normalized trace escapes its run artifact"
        )
    try:
        if not trace_path.is_file() or sha256_file(trace_path) != trace_digest:
            raise WorkbenchAPIError(
                409, "ARTIFACT_INTEGRITY_ERROR", "normalized trace digest does not match"
            )
        trace = NormalizedTrace.model_validate_json(trace_path.read_text(encoding="utf-8"))
    except WorkbenchAPIError:
        raise
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "normalized trace cannot be verified"
        ) from exc
    return TraceResponse(
        run_id=run_id,
        status="REPORTED",
        coverage=coverage if isinstance(coverage, str) else None,
        trace_digest=trace_digest,
        events=tuple(
            TraceEvent(
                ordinal=event.ordinal,
                type=event.type.value,
                status=event.status,
                summary=_trace_summary(event.model_dump(mode="json", exclude_none=True)),
                exit_code=event.exit_code,
            )
            for event in trace.events
        ),
    )


def _judge_report(record: JudgeCalibrationRecord) -> JudgeCalibrationReport:
    if record.report_json_path is None or record.report_digest is None:
        raise WorkbenchAPIError(409, "ARTIFACT_UNAVAILABLE", "Judge report is not reported")
    path = Path(record.report_json_path)
    try:
        report = JudgeCalibrationReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "Judge report cannot be verified"
        ) from exc
    if report.calibration_id != record.id or report.report_digest != record.report_digest:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "Judge report identity does not match"
        )
    return report


async def list_judge_calibrations(
    session: AsyncSession, *, limit: int, offset: int
) -> JudgeCalibrationListResponse:
    records = tuple(
        (
            await session.scalars(
                select(JudgeCalibrationRecord)
                .order_by(JudgeCalibrationRecord.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    items: list[JudgeCalibrationSummary] = []
    for record in records:
        plan = record.plan_json
        report: JudgeCalibrationReport | None = None
        if record.report_json_path and record.report_digest:
            try:
                report = _judge_report(record)
            except WorkbenchAPIError:
                report = None
        cells = plan.get("judge_cells")
        cell_count = len(cells) if isinstance(cells, list) else 0
        items.append(
            JudgeCalibrationSummary(
                calibration_id=record.id,
                suite_id=str(plan.get("suite_id", "UNKNOWN")),
                suite_version=str(plan.get("suite_version", "UNKNOWN")),
                plan_digest=record.plan_digest,
                report_digest=record.report_digest,
                status=record.status,
                judge_cell_count=cell_count,
                qualifications=(
                    tuple(cell.qualification_status.value for cell in report.cells)
                    if report
                    else ()
                ),
                created_at=record.created_at,
                finished_at=record.finished_at,
            )
        )
    total = int(await session.scalar(select(func.count()).select_from(JudgeCalibrationRecord)) or 0)
    return JudgeCalibrationListResponse(items=tuple(items), total=total, limit=limit, offset=offset)


async def judge_calibration_detail(
    session: AsyncSession, calibration_id: str
) -> JudgeCalibrationDetail:
    record = await session.get(JudgeCalibrationRecord, calibration_id)
    if record is None:
        raise WorkbenchAPIError(404, "NOT_FOUND", "Judge calibration does not exist")
    report = _judge_report(record)
    cells = tuple(
        JudgeCellDetail(
            judge_cell_id=cell.judge_cell_id,
            requested_judge_model=cell.requested_judge_model,
            qualification=cell.qualification_status.value,
            qualification_scope=f"{report.suite_id}@{report.suite_version}",
            coverage=numeric(cell.label_metrics.get("coverage")),
            label_accuracy=numeric(cell.label_metrics.get("accuracy")),
            macro_f1=numeric(cell.label_metrics.get("macro_f1")),
            score_mae=numeric(cell.score_metrics.get("mae")),
            spearman_rho=numeric(cell.score_metrics.get("spearman_rho")),
            pairwise_accuracy=numeric(cell.pairwise_metrics.get("gold_accuracy")),
            position_consistency=numeric(cell.pairwise_metrics.get("position_consistency_rate")),
            verbosity_bias_rate=numeric(cell.pairwise_metrics.get("verbosity_bias_rate")),
            repeat_consistency=numeric(cell.label_metrics.get("repeat_consistency")),
            provider_infra=int(cell.run_counts.get("provider_failures", 0)),
            l0_disagreements=cell.l0_judge_disagreement_count,
            l0_overrides=cell.l0_override_count,
            qualification_reasons=cell.qualification_reasons,
        )
        for cell in report.cells
    )
    return JudgeCalibrationDetail(
        calibration_id=report.calibration_id,
        suite_id=report.suite_id,
        suite_version=report.suite_version,
        suite_digest=report.suite_digest,
        plan_digest=report.plan_digest,
        report_digest=report.report_digest,
        status=record.status,
        real_judge_smoke=report.real_judge_smoke,
        cells=cells,
        limitations=report.limitations,
    )


async def regression_compare(
    session: AsyncSession, request: RegressionCompareRequest
) -> RegressionCompareResponse:
    baseline_record = await _experiment(session, request.baseline_experiment_id)
    candidate_record = await _experiment(session, request.candidate_experiment_id)
    baseline_plan = _plan(baseline_record)
    candidate_plan = _plan(candidate_record)
    baseline_report = await _report(session, baseline_record.id)
    candidate_report = await _report(session, candidate_record.id)
    baseline_cells = {cell.cell_id: cell for cell in baseline_report.cells}
    candidate_cells = {cell.cell_id: cell for cell in candidate_report.cells}
    baseline_config = {cell.id: cell for cell in baseline_plan.cells}
    candidate_config = {cell.id: cell for cell in candidate_plan.cells}
    baseline_task_controls = {
        task.task_id: task.model_dump(mode="json", exclude={"package_path"})
        for task in baseline_plan.tasks
    }
    candidate_task_controls = {
        task.task_id: task.model_dump(mode="json", exclude={"package_path"})
        for task in candidate_plan.tasks
    }
    task_controls_equal = baseline_task_controls == candidate_task_controls
    mapping = request.cell_mapping or {
        cell_id: cell_id for cell_id in sorted(set(baseline_cells) & set(candidate_cells))
    }
    if not mapping:
        raise WorkbenchAPIError(
            422, "INVALID_REGRESSION_REQUEST", "experiments have no mapped logical cells"
        )
    comparisons: list[RegressionCellComparison] = []
    for baseline_id, candidate_id in sorted(mapping.items()):
        if baseline_id not in baseline_cells or candidate_id not in candidate_cells:
            raise WorkbenchAPIError(
                422, "INVALID_REGRESSION_REQUEST", "cell mapping references an unknown cell"
            )
        left = baseline_cells[baseline_id]
        right = candidate_cells[candidate_id]
        cell_controls_equal = baseline_config[baseline_id].model_dump(
            mode="json", exclude={"id", "profile_reference"}
        ) == candidate_config[candidate_id].model_dump(
            mode="json", exclude={"id", "profile_reference"}
        )
        reasons = tuple(
            code
            for condition, code in (
                (not cell_controls_equal, "HARD_CONTROL_MISMATCH"),
                (not task_controls_equal, "TASK_CONTROL_MISMATCH"),
            )
            if condition
        )
        status: ComparabilityValue = "COMPARABLE" if not reasons else "NOT_COMPARABLE"
        left_value = numeric(left.success_rate)
        right_value = numeric(right.success_rate)
        if left_value.value is None or right_value.value is None:
            delta = numeric(None)
            direction = "NOT_REPORTED"
        else:
            delta_value = right_value.value - left_value.value
            delta = numeric(delta_value)
            direction = (
                "IMPROVED" if delta_value > 0 else "DECREASED" if delta_value < 0 else "UNCHANGED"
            )
        comparisons.append(
            RegressionCellComparison(
                baseline_cell_id=baseline_id,
                candidate_cell_id=candidate_id,
                baseline_value=left_value,
                candidate_value=right_value,
                delta=delta,
                direction=cast(Any, direction),
                baseline_tier=left.evidence_tier.value,
                candidate_tier=right.evidence_tier.value,
                comparability=status,
                reason_codes=reasons,
                baseline_infra_count=left.infra_failures,
                candidate_infra_count=right.infra_failures,
            )
        )
    common_tasks = tuple(
        sorted(
            task_id
            for task_id in set(baseline_task_controls) & set(candidate_task_controls)
            if baseline_task_controls[task_id] == candidate_task_controls[task_id]
        )
    )
    return RegressionCompareResponse(
        baseline_experiment_id=baseline_record.id,
        candidate_experiment_id=candidate_record.id,
        baseline_plan_digest=baseline_report.plan_digest,
        candidate_plan_digest=candidate_report.plan_digest,
        baseline_report_digest=baseline_report.digest,
        candidate_report_digest=candidate_report.digest,
        common_tasks=common_tasks,
        comparisons=tuple(comparisons),
        limitation=(
            "Directional evidence only; no causal attribution or new significance claim is made."
        ),
    )


async def core_readiness(session: AsyncSession) -> CoreReadinessResponse:
    experiments = tuple(
        (
            await session.scalars(
                select(ExperimentRecord)
                .where(ExperimentRecord.status == "completed")
                .order_by(ExperimentRecord.finished_at.desc())
                .limit(25)
            )
        ).all()
    )
    plans = tuple(_plan(record) for record in experiments)
    reports: list[ExperimentReport] = []
    for record in experiments:
        reports.append(await _report(session, record.id))
    task_ids = {task.task_id for plan in plans for task in plan.tasks}
    matrix_available = any(report.plan_run_count > 0 for report in reports)
    formal_available = any(any(cell.formal_eligible for cell in report.cells) for report in reports)
    paired_available = any(bool(report.pairs) for report in reports)
    ablation_available = any(bool(report.ablations) for report in reports)
    judge_count = int(
        await session.scalar(
            select(func.count())
            .select_from(JudgeCalibrationRecord)
            .where(JudgeCalibrationRecord.status == "completed")
        )
        or 0
    )
    checks = (
        ReadinessCheck(
            key="TASK_CORPUS",
            label="Persisted task corpus",
            status="READY" if task_ids else "NOT_REPORTED",
            evidence=f"{len(task_ids)} persisted task identities",
        ),
        ReadinessCheck(
            key="MATRIX_EVIDENCE",
            label="Matrix evidence",
            status="READY" if matrix_available else "NOT_REPORTED",
            evidence=f"{len(reports)} completed persisted experiment reports",
        ),
        ReadinessCheck(
            key="FORMAL_REPEATED_EVIDENCE",
            label="Formal repeated evidence",
            status="READY" if formal_available else "NOT_VERIFIED",
            evidence="FORMAL tier is derived from persisted report contracts",
        ),
        ReadinessCheck(
            key="PAIRED_EVIDENCE",
            label="Paired evidence",
            status="READY" if paired_available else "NOT_REPORTED",
            evidence="Persisted Phase G pair definitions and report evidence",
        ),
        ReadinessCheck(
            key="ABLATION_EVIDENCE",
            label="Ablation evidence",
            status="READY" if ablation_available else "NOT_REPORTED",
            evidence="Persisted Phase G ablation definitions and report evidence",
        ),
        ReadinessCheck(
            key="JUDGE_CALIBRATION",
            label="Judge calibration evidence",
            status="READY" if judge_count else "NOT_REPORTED",
            evidence=f"{judge_count} completed persisted calibrations",
        ),
        ReadinessCheck(
            key="REAL_MATRIX_EVIDENCE",
            label="Real Matrix evidence",
            status="NOT_VERIFIED",
            evidence="REAL_MATRIX_EVIDENCE=NOT_RUN",
        ),
        ReadinessCheck(
            key="REAL_JUDGE_EVIDENCE",
            label="Real Judge evidence",
            status="NOT_VERIFIED",
            evidence="REAL_JUDGE_SMOKE=NOT_RUN",
        ),
        ReadinessCheck(
            key="PHASE_J",
            label="Phase J analyst evidence",
            status="BLOCKED",
            evidence="Phase J is intentionally outside the current completed scope",
        ),
        ReadinessCheck(
            key="RELEASE_DOCUMENTATION",
            label="Release documentation",
            status="NOT_REPORTED",
            evidence="No structured release-candidate artifact is persisted",
        ),
    )
    blockers = tuple(check.key for check in checks if check.status != "READY")
    return CoreReadinessResponse(
        status="NOT_READY" if blockers else "READY",
        task_corpus_size=len(task_ids),
        checks=checks,
        blockers=blockers,
        evaluated_at=datetime.now(UTC),
    )
