from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import suppress
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
    MatrixComparabilityValue,
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
from harnesslab.comparability.engine import ComparabilityEngine
from harnesslab.comparability.models import ComparabilityIntent
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.models.judgelab import JudgeCalibrationRecord
from harnesslab.evidence.reader import (
    EvidenceReadError,
    load_normalized_trace,
    load_verified_manifest,
    trusted_artifact_path,
)
from harnesslab.experiment.model_comparison import (
    ModelComparisonAnalysisError,
    ModelComparisonCloseout,
    analyze_model_comparison,
)
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.plan import AnyExperimentPlan, load_experiment_plan_payload
from harnesslab.experiment.queue import TERMINAL_STATUSES as TERMINAL_RUN_STATUSES
from harnesslab.experiment.report import (
    ExperimentReport,
    ExperimentReportError,
    build_experiment_report,
    load_verified_experiment_evidence,
)
from harnesslab.experiment.spec import ExperimentSpecError
from harnesslab.experiment.statistics import summarize_cell
from harnesslab.judgelab.report import JudgeCalibrationReport
from harnesslab.release.badcases import verify_frozen_badcases
from harnesslab.release.contracts import (
    CoreReleaseError,
    load_badcase_plan,
    load_core_corpus,
    load_real_evidence_plan,
    load_release_evidence,
    load_resume_claim_map,
)
from harnesslab.release.models import EvidenceState
from harnesslab.release.reconciliation import load_accepted_plan, verify_candidate

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


def _plan(record: ExperimentRecord) -> AnyExperimentPlan:
    try:
        plan = load_experiment_plan_payload(record.plan_json)
    except (ValidationError, ExperimentSpecError) as exc:
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


def _trusted_artifact_path(raw_path: str | Path, roots: tuple[Path, ...]) -> Path:
    """Resolve an existing artifact and reject symlink or absolute-path root escapes."""

    try:
        return trusted_artifact_path(raw_path, roots)
    except EvidenceReadError as exc:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "artifact location cannot be verified"
        ) from exc


async def _confine_experiment_artifacts(
    session: AsyncSession, experiment_id: str, roots: tuple[Path, ...]
) -> None:
    paths = tuple(
        (
            await session.scalars(
                select(ExperimentRunRecord.artifact_manifest_path).where(
                    ExperimentRunRecord.experiment_id == experiment_id,
                    ExperimentRunRecord.artifact_manifest_path.is_not(None),
                )
            )
        ).all()
    )
    for path in paths:
        if path is not None:
            _trusted_artifact_path(path, roots)


async def _report(
    session: AsyncSession, experiment_id: str, roots: tuple[Path, ...]
) -> ExperimentReport:
    await _confine_experiment_artifacts(session, experiment_id, roots)
    try:
        return await build_experiment_report(
            session,
            experiment_id,
            artifact_path_guard=lambda path: _trusted_artifact_path(path, roots),
        )
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
    record: ExperimentRecord, plan: AnyExperimentPlan, counts: Counter[str]
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


async def experiment_detail(
    session: AsyncSession, experiment_id: str, roots: tuple[Path, ...]
) -> ExperimentDetail:
    record = await _experiment(session, experiment_id)
    plan = _plan(record)
    counts = (await _run_counts(session, (record.id,))).get(record.id, Counter())
    summary = _summary(record, plan, counts)
    report: ExperimentReport | None = None
    if record.status in TERMINAL_EXPERIMENT_STATUSES:
        report = await _report(session, experiment_id, roots)
    comparability = Counter[str]()
    if report is not None:
        comparability.update(item.comparability.value for item in report.pair_evidence)
    return ExperimentDetail(
        **summary.model_dump(),
        repeat_count=plan.repeat_count,
        execution_seed=plan.execution_seed,
        comparison_intent=plan.comparison_intent,
        evaluation_mode=(
            plan.evaluation_mode.value if hasattr(plan, "evaluation_mode") else "NOT_AVAILABLE"
        ),
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


def _task_cell_comparability(
    plan: AnyExperimentPlan, report: ExperimentReport
) -> dict[tuple[str, str], tuple[MatrixComparabilityValue, tuple[str, ...]]]:
    pair_cells = {
        pair.id: (pair.left_cell_id, pair.right_cell_id) for pair in plan.paired_comparisons
    }
    pair_cells.update(
        {
            f"ablation-{ablation.id}": (ablation.base_cell_id, ablation.variant_cell_id)
            for ablation in plan.ablations
        }
    )
    statuses: dict[tuple[str, str], list[str]] = defaultdict(list)
    reasons: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in report.pair_evidence:
        for cell_id in pair_cells.get(item.pair_id, ()):
            key = (item.task_id, cell_id)
            statuses[key].append(item.comparability.value)
            reasons[key].update(item.reason_codes)
    result: dict[tuple[str, str], tuple[MatrixComparabilityValue, tuple[str, ...]]] = {}
    for task in plan.tasks:
        for cell in plan.cells:
            key = (task.task_id, cell.id)
            values = statuses.get(key)
            if not values:
                result[key] = ("NOT_REPORTED", ())
                continue
            worst = max(values, key=COMPARABILITY_ORDER.__getitem__)
            result[key] = (cast(ComparabilityValue, worst), tuple(sorted(reasons[key])))
    return result


async def matrix(
    session: AsyncSession, experiment_id: str, roots: tuple[Path, ...]
) -> MatrixResponse:
    record = await _experiment(session, experiment_id)
    plan = _plan(record)
    report = await _report(session, experiment_id, roots)
    evidence = await load_verified_experiment_evidence(
        session,
        experiment_id,
        artifact_path_guard=lambda path: _trusted_artifact_path(path, roots),
    )
    observations = evidence.observations
    comparability = _task_cell_comparability(plan, report)
    points: list[MatrixPoint] = []
    for task in plan.tasks:
        for planned_cell in plan.cells:
            task_observations = tuple(
                item.observation
                for item in observations
                if item.run.task_id == task.task_id and item.run.cell_id == planned_cell.id
            )
            planned_runs = sum(
                slot.task.task_id == task.task_id and slot.cell_id == planned_cell.id
                for slot in plan.run_slots
            )
            task_cell = summarize_cell(
                f"{planned_cell.id}:{task.task_id}",
                planned_runs,
                task_observations,
                intended_task_ids=(task.task_id,),
                seed=plan.execution_seed,
            )
            point_metrics = MatrixMetricSet(
                success_rate=numeric(task_cell.success_rate),
                latency_p50_ms=numeric(task_cell.latency_ms.p50),
                latency_p95_ms=numeric(task_cell.latency_ms.p95),
                infra_rate=numeric(task_cell.infra_failure_rate),
                pass_at_1=numeric(task_cell.pass_at_k.get("pass@1")),
                pass_at_3=numeric(task_cell.pass_at_k.get("pass@3")),
                pass_at_5=numeric(task_cell.pass_at_k.get("pass@5")),
            )
            status, reasons = comparability[(task.task_id, planned_cell.id)]
            points.append(
                MatrixPoint(
                    task_id=task.task_id,
                    cell_id=planned_cell.id,
                    n=task_cell.completed_capability_runs,
                    tier=task_cell.evidence_tier.value,
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


async def experiment_report(
    session: AsyncSession, experiment_id: str, roots: tuple[Path, ...]
) -> ExperimentReportResponse:
    report = await _report(session, experiment_id, roots)
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


async def model_comparison_analysis(
    session: AsyncSession, experiment_id: str, roots: tuple[Path, ...]
) -> ModelComparisonCloseout:
    await _experiment(session, experiment_id)
    await _confine_experiment_artifacts(session, experiment_id, roots)
    try:
        evidence = await load_verified_experiment_evidence(
            session,
            experiment_id,
            artifact_path_guard=lambda path: _trusted_artifact_path(path, roots),
        )
        return analyze_model_comparison(
            evidence,
            repository_root=Path(__file__).resolve().parents[3],
        )
    except ModelComparisonAnalysisError as exc:
        raise WorkbenchAPIError(422, "ANALYSIS_NOT_APPLICABLE", str(exc)) from exc
    except ExperimentReportError as exc:
        raise WorkbenchAPIError(
            409,
            "ARTIFACT_INTEGRITY_ERROR",
            "model comparison evidence is unavailable",
        ) from exc


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


def _safe_manifest(
    run: ExperimentRunRecord, roots: tuple[Path, ...]
) -> tuple[dict[str, Any], Path]:
    try:
        manifest = load_verified_manifest(run, roots)
    except EvidenceReadError as exc:
        if "not reported" in str(exc):
            raise WorkbenchAPIError(
                409, "ARTIFACT_UNAVAILABLE", "run artifact is not reported"
            ) from exc
        if "outside trusted storage" in str(exc):
            raise WorkbenchAPIError(
                409, "ARTIFACT_INTEGRITY_ERROR", "artifact is outside trusted storage"
            ) from exc
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "run artifact cannot be verified"
        ) from exc
    return manifest.raw, manifest.path


async def run_detail(session: AsyncSession, run_id: str, roots: tuple[Path, ...]) -> RunDetail:
    run = await session.get(ExperimentRunRecord, run_id)
    if run is None:
        raise WorkbenchAPIError(404, "NOT_FOUND", "run does not exist")
    raw: dict[str, Any] = {}
    if run.artifact_manifest_path is not None or run.evidence_digest is not None:
        raw, _ = _safe_manifest(run, roots)
    slot = run.slot_json
    verifier = raw.get("verifier_sandbox_manifest")
    verifier_passed = raw.get("verifier_passed")
    verifier_score = raw.get("verifier_score")
    if not isinstance(verifier, dict):
        verifier = {}
    report = (
        await _report(session, run.experiment_id, roots)
        if run.status in TERMINAL_RUN_STATUSES
        else None
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


async def trace_detail(
    session: AsyncSession, run_id: str, roots: tuple[Path, ...]
) -> TraceResponse:
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
    raw, _ = _safe_manifest(run, roots)
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
    try:
        trace, verified_trace_digest, verified_coverage = load_normalized_trace(run, roots)
    except EvidenceReadError as exc:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "normalized trace cannot be verified"
        ) from exc
    if verified_trace_digest != trace_digest:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "normalized trace identity does not match"
        )
    return TraceResponse(
        run_id=run_id,
        status="REPORTED",
        coverage=verified_coverage,
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


def _judge_report(
    record: JudgeCalibrationRecord, roots: tuple[Path, ...]
) -> JudgeCalibrationReport:
    if record.report_json_path is None or record.report_digest is None:
        raise WorkbenchAPIError(409, "ARTIFACT_UNAVAILABLE", "Judge report is not reported")
    path = _trusted_artifact_path(record.report_json_path, roots)
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
    session: AsyncSession, *, limit: int, offset: int, roots: tuple[Path, ...]
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
        report_evidence_status: str = "NOT_REPORTED"
        if record.report_json_path and record.report_digest:
            try:
                report = _judge_report(record, roots)
            except WorkbenchAPIError:
                report_evidence_status = "INTEGRITY_ERROR"
            else:
                report_evidence_status = "REPORTED"
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
                report_evidence_status=cast(Any, report_evidence_status),
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
    session: AsyncSession, calibration_id: str, roots: tuple[Path, ...]
) -> JudgeCalibrationDetail:
    record = await session.get(JudgeCalibrationRecord, calibration_id)
    if record is None:
        raise WorkbenchAPIError(404, "NOT_FOUND", "Judge calibration does not exist")
    report = _judge_report(record, roots)
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
    session: AsyncSession, request: RegressionCompareRequest, roots: tuple[Path, ...]
) -> RegressionCompareResponse:
    baseline_record = await _experiment(session, request.baseline_experiment_id)
    candidate_record = await _experiment(session, request.candidate_experiment_id)
    baseline_report = await _report(session, baseline_record.id, roots)
    candidate_report = await _report(session, candidate_record.id, roots)

    def guard(path: Path) -> Path:
        return _trusted_artifact_path(path, roots)

    baseline_evidence = await load_verified_experiment_evidence(
        session, baseline_record.id, artifact_path_guard=guard
    )
    candidate_evidence = await load_verified_experiment_evidence(
        session, candidate_record.id, artifact_path_guard=guard
    )
    baseline_cells = {cell.cell_id: cell for cell in baseline_report.cells}
    candidate_cells = {cell.cell_id: cell for cell in candidate_report.cells}
    mapping = request.cell_mapping or {
        cell_id: cell_id for cell_id in sorted(set(baseline_cells) & set(candidate_cells))
    }
    if not mapping:
        raise WorkbenchAPIError(
            422, "INVALID_REGRESSION_REQUEST", "experiments have no mapped logical cells"
        )
    comparisons: list[RegressionCellComparison] = []
    common_task_ids: set[str] = set()
    for baseline_id, candidate_id in sorted(mapping.items()):
        if baseline_id not in baseline_cells or candidate_id not in candidate_cells:
            raise WorkbenchAPIError(
                422, "INVALID_REGRESSION_REQUEST", "cell mapping references an unknown cell"
            )
        left = baseline_cells[baseline_id]
        right = candidate_cells[candidate_id]
        capability = {
            StatisticalOutcome.CAPABILITY_PASS,
            StatisticalOutcome.CAPABILITY_FAIL,
        }
        baseline_by_slot = {
            (item.run.task_id, item.run.repeat_index): item
            for item in baseline_evidence.observations
            if item.run.cell_id == baseline_id
            and item.observation.outcome in capability
            and item.facts is not None
        }
        candidate_by_slot = {
            (item.run.task_id, item.run.repeat_index): item
            for item in candidate_evidence.observations
            if item.run.cell_id == candidate_id
            and item.observation.outcome in capability
            and item.facts is not None
        }
        paired_slots = sorted(set(baseline_by_slot) & set(candidate_by_slot))
        statuses: list[ComparabilityValue] = []
        reason_codes: set[str] = set()
        engine = ComparabilityEngine()
        for slot in paired_slots:
            baseline_item = baseline_by_slot[slot]
            candidate_item = candidate_by_slot[slot]
            assert baseline_item.facts is not None and candidate_item.facts is not None
            assessment = engine.assess(
                baseline_item.facts,
                candidate_item.facts,
                intent=request.intent,
            )
            statuses.append(_comparability_value(assessment.status.value))
            reason_codes.update(reason.code.value for reason in assessment.reasons)
        if not statuses:
            status: ComparabilityValue = "NOT_COMPARABLE"
            reason_codes.add("NO_PAIRED_CAPABILITY_EVIDENCE")
        else:
            status = max(statuses, key=COMPARABILITY_ORDER.__getitem__)
        if request.intent is ComparabilityIntent.GENERAL and status == "COMPARABLE":
            status = "PARTIALLY_COMPARABLE"
            reason_codes.add("GENERAL_EXPLORATORY_ONLY")
        reasons = tuple(sorted(reason_codes))
        common_task_ids.update(task_id for task_id, _repeat_index in paired_slots)
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
                paired_observations=len(paired_slots),
                baseline_infra_count=left.infra_failures,
                candidate_infra_count=right.infra_failures,
            )
        )
    return RegressionCompareResponse(
        baseline_experiment_id=baseline_record.id,
        candidate_experiment_id=candidate_record.id,
        baseline_plan_digest=baseline_report.plan_digest,
        candidate_plan_digest=candidate_report.plan_digest,
        baseline_report_digest=baseline_report.digest,
        candidate_report_digest=candidate_report.digest,
        intent=request.intent,
        common_tasks=tuple(sorted(common_task_ids)),
        comparisons=tuple(comparisons),
        limitation=(
            "Directional evidence only; no causal attribution or new significance claim is made."
        ),
    )


async def core_readiness(session: AsyncSession, roots: tuple[Path, ...]) -> CoreReadinessResponse:
    completed_judges = tuple(
        (
            await session.scalars(
                select(JudgeCalibrationRecord).where(JudgeCalibrationRecord.status == "completed")
            )
        ).all()
    )
    judge_count = 0
    for judge_record in completed_judges:
        try:
            _judge_report(judge_record, roots)
        except WorkbenchAPIError:
            continue
        judge_count += 1
    repository_root = Path(__file__).resolve().parents[3]
    badcases_ready = False
    accepted_v6 = False
    try:
        release_evidence = load_release_evidence(repository_root / "release/release-evidence.json")
        if release_evidence.schema_version == 2:
            release_evidence = verify_candidate(repository_root)
            accepted_plan = load_accepted_plan(repository_root)
            corpus = load_core_corpus(repository_root / accepted_plan.corpus_reference)
            release_plan = None
            accepted_v6 = True
        else:
            corpus = load_core_corpus(repository_root / "release/core-corpus.json")
            release_plan = load_real_evidence_plan(
                repository_root / "release/core-real-evidence-plan.json"
            )
        claim_map = load_resume_claim_map(repository_root / "release/resume-claim-evidence.json")
        badcases = load_badcase_plan(repository_root / "release/badcases.json")
        with suppress(OSError, ValueError):
            badcases_ready = badcases == verify_frozen_badcases(repository_root)
        corpus_ready = (
            release_evidence.core_corpus.state is EvidenceState.VERIFIED
            and release_evidence.core_corpus.digest == corpus.digest
            and len(corpus.tasks) == 18
            and all(not task.baseline.passed and task.oracle.passed for task in corpus.tasks)
        )
        matrix_plan_ready = accepted_v6 or (
            release_plan is not None and len(release_plan.cells) == 7
        )
        docs_ready = all(
            (repository_root / path).is_file()
            for path in (
                "docs/FAIRNESS_CONTRACT.md",
                "docs/BADCASES.md",
                "docs/INTERVIEW_GUIDE.md",
                "docs/SECURITY.md",
                "docs/RELEASE_EVIDENCE.md",
                "docs/REAL_EVIDENCE_AUTHORIZATION.md",
            )
        )
        phase_j_ready = (
            any(
                claim.source_phase == "J" and claim.status is EvidenceState.VERIFIED
                for claim in claim_map.claims
            )
            and (repository_root / "scripts/verify_gate_j.py").is_file()
        )
        release_contracts_available = True
    except CoreReleaseError:
        corpus = None
        release_plan = None
        release_evidence = None
        badcases = None
        accepted_v6 = False
        corpus_ready = matrix_plan_ready = docs_ready = phase_j_ready = False
        release_contracts_available = False
    release_task_count = len(corpus.tasks) if corpus is not None else 0
    real_matrix_state = (
        release_evidence.real_matrix.state.value if release_evidence is not None else "NOT_VERIFIED"
    )
    judge_release_state = (
        release_evidence.judge_report.state.value
        if release_evidence is not None
        else "NOT_VERIFIED"
    )
    checks: tuple[ReadinessCheck, ...] = (
        ReadinessCheck(
            key="TASK_CORPUS",
            label="Canonical Core task corpus",
            status="READY" if corpus_ready else "NOT_VERIFIED",
            evidence=(
                f"{release_task_count} digest-bound task identities; Core requirement is 15-25"
            ),
        ),
        ReadinessCheck(
            key="MODEL_ONLY_PROFILES",
            label="Frozen Model-only profiles",
            status="NOT_VERIFIED",
            evidence=(
                f"{len(release_plan.model_profile_slots) if release_plan else 0} strict slots; "
                "exact requested model selections remain NOT_VERIFIED"
            ),
        ),
        ReadinessCheck(
            key="HARNESS_MATRIX_PLAN",
            label="Core Harness Matrix plan",
            status="READY" if matrix_plan_ready else "NOT_VERIFIED",
            evidence="7 structurally validated cells; DeepSeek E2 is DEFERRED_NOT_VERIFIED",
        ),
        ReadinessCheck(
            key="REAL_MATRIX_EVIDENCE",
            label="Real Matrix evidence",
            status=(
                "READY"
                if release_evidence is not None
                and release_evidence.real_matrix.state is EvidenceState.VERIFIED
                else "NOT_VERIFIED"
            ),
            evidence=f"REAL_MATRIX_EVIDENCE={real_matrix_state}",
        ),
        ReadinessCheck(
            key="JUDGE_EVIDENCE",
            label="Core real Judge evidence",
            status=(
                "READY"
                if release_evidence is not None
                and release_evidence.judge_report.state is EvidenceState.VERIFIED
                else "NOT_VERIFIED"
            ),
            evidence=f"Judge suite is frozen; REAL_JUDGE_SMOKE={judge_release_state}",
        ),
        ReadinessCheck(
            key="JUDGE_CALIBRATION",
            label="Judge calibration evidence",
            status=(
                "READY" if judge_count else "NOT_VERIFIED" if completed_judges else "NOT_REPORTED"
            ),
            evidence=(
                f"{judge_count} integrity-validated completed calibrations "
                f"of {len(completed_judges)} completed records"
            ),
        ),
        ReadinessCheck(
            key="PAIRED_LANE",
            label="Comparable release P-Lane",
            status="NOT_VERIFIED",
            evidence="Planned direct /responses and Codex routes differ; uplift is not COMPARABLE",
        ),
        ReadinessCheck(
            key="ABLATION",
            label="Controlled real ablation",
            status="NOT_VERIFIED",
            evidence=(
                "Codex medium/high reasoning-effort plan is valid; real observations are NOT_RUN"
            ),
        ),
        ReadinessCheck(
            key="PHASE_J",
            label="Phase J analyst evidence",
            status="READY" if phase_j_ready else "NOT_VERIFIED",
            evidence="Approved bounded Analyst source and Gate J evidence mapping",
        ),
        ReadinessCheck(
            key="RELEASE_DOCUMENTATION",
            label="Release documentation",
            status="READY" if docs_ready else "NOT_VERIFIED",
            evidence="Core document set is checked from repository source",
        ),
        ReadinessCheck(
            key="BADCASE_EVIDENCE",
            label="Three real BadCases",
            status="READY" if badcases_ready else "NOT_VERIFIED",
            evidence=(
                "Three verifier-backed V6 BadCases frozen with checked source bindings; "
                "final release remains gated"
                if badcases_ready
                else "Canonical BadCase freeze is unavailable or fails validation"
            ),
        ),
        ReadinessCheck(
            key="RELEASE_EVIDENCE",
            label="Final release evidence manifest",
            status=(
                "READY"
                if release_evidence is not None and release_evidence.core_release_ready
                else "NOT_VERIFIED"
            ),
            evidence=(
                "Strict release contract loaded; CORE_RELEASE_READY=FALSE"
                if release_contracts_available
                else "Release contract is unavailable or invalid"
            ),
        ),
        ReadinessCheck(
            key="REMOTE_CI",
            label="Exact-head remote CI",
            status=(
                "READY"
                if release_evidence is not None
                and release_evidence.remote_ci.state is EvidenceState.VERIFIED
                else "NOT_VERIFIED"
            ),
            evidence="Final exact-head CI binding is not yet in release evidence",
        ),
        ReadinessCheck(
            key="CORE_TAG",
            label="v1.0.0-core tag",
            status="NOT_REPORTED",
            evidence="Tag creation is refused until final release verification passes",
        ),
    )
    if accepted_v6 and release_evidence is not None:
        # Show validated stable evidence; detached final authorization is not
        # persisted in this view and cannot make the committed candidate ready.
        current_checks = {
            "MODEL_ONLY_PROFILES": ReadinessCheck(
                key="MODEL_ONLY_PROFILES",
                label="Frozen Model-only profiles",
                status="READY",
                evidence="Frozen profiles bound to the accepted V6 ExperimentPlan",
            ),
            "HARNESS_MATRIX_PLAN": ReadinessCheck(
                key="HARNESS_MATRIX_PLAN",
                label="Core Harness Matrix plan",
                status="READY",
                evidence=(
                    "Accepted V6: 7 cells and 630 slots; DeepSeek Harness E1 is outside Core "
                    "scope and REAL_DEEPSEEK_SMOKE remains DEFERRED_NOT_VERIFIED"
                ),
            ),
            "PAIRED_LANE": ReadinessCheck(
                key="PAIRED_LANE",
                label="Real Pair evidence",
                status="READY",
                evidence=release_evidence.paired_lane.limitation or "",
            ),
            "ABLATION": ReadinessCheck(
                key="ABLATION",
                label="Real ablation evidence",
                status="READY",
                evidence=release_evidence.controlled_ablation.limitation or "",
            ),
        }
        checks = tuple(current_checks.get(check.key, check) for check in checks)
    blockers = tuple(check.key for check in checks if check.status != "READY")
    return CoreReadinessResponse(
        status="NOT_READY" if blockers else "READY",
        task_corpus_size=release_task_count,
        checks=checks,
        blockers=blockers,
        evaluated_at=datetime.now(UTC),
    )
