from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import cast

from pydantic import JsonValue, ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.analyst.models import (
    AnalysisScope,
    CompareCellsArgs,
    EvidenceRef,
    GetAblationArgs,
    GetTaskContractArgs,
    InspectFailureArgs,
    InspectTraceArgs,
    QueryRunsArgs,
    ToolEvidence,
    ToolName,
    safe_public_text,
)
from harnesslab.db.models.experiment import (
    ExperimentAblationRecord,
    ExperimentRecord,
    ExperimentRunRecord,
)
from harnesslab.evidence.reader import (
    EvidenceReadError,
    load_normalized_trace,
    load_verified_manifest,
)
from harnesslab.experiment.plan import ExperimentPlan
from harnesslab.experiment.report import ExperimentReportError, build_experiment_report
from harnesslab.tasks.package import TaskPackage, TaskPackageError


class AnalystEvidenceError(RuntimeError):
    """The bound experiment or requested evidence is unavailable or out of scope."""


def _json_safe(value: object) -> JsonValue:
    if value is None or isinstance(value, bool | int | float):
        return cast(JsonValue, value)
    if isinstance(value, str):
        return safe_public_text(value, limit=4_000)
    if isinstance(value, dict):
        return cast(
            JsonValue,
            {
                safe_public_text(str(key), limit=200): _json_safe(item)
                for key, item in value.items()
            },
        )
    if isinstance(value, list | tuple):
        return cast(JsonValue, [_json_safe(item) for item in value])
    return safe_public_text(str(value), limit=4_000)


def _data(**values: object) -> dict[str, JsonValue]:
    return {key: _json_safe(value) for key, value in values.items()}


def _trace_summary(event: dict[str, object]) -> str | None:
    if event.get("type") == "REASONING_PRESENT":
        return "Reasoning was present; private content is withheld."
    if isinstance(event.get("file_changes"), list):
        return f"{len(cast(list[object], event['file_changes']))} file change(s) recorded."
    for key in ("text", "command", "public_output", "native_event_type"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return safe_public_text(value, limit=500)
    return None


class AnalystEvidenceRepository:
    """Experiment-bound repository with no write, execution, or arbitrary query surface."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        experiment_id: str,
        repository_root: Path,
        artifact_roots: tuple[Path, ...],
    ) -> None:
        self._session = session
        self._experiment_id = experiment_id
        self._repository_root = repository_root.resolve()
        self._artifact_roots = artifact_roots
        self._read_only_started = False
        self._plan: ExperimentPlan | None = None

    async def _ensure_read_only(self) -> None:
        if self._read_only_started:
            return
        bind = self._session.get_bind()
        if bind.dialect.name == "postgresql":
            await self._session.execute(text("SET TRANSACTION READ ONLY"))
        self._read_only_started = True

    async def _load_plan(self) -> ExperimentPlan:
        await self._ensure_read_only()
        if self._plan is not None:
            return self._plan
        record = await self._session.get(ExperimentRecord, self._experiment_id)
        if record is None:
            raise AnalystEvidenceError("bound experiment does not exist")
        try:
            plan = ExperimentPlan.model_validate(record.plan_json)
        except ValidationError as exc:
            raise AnalystEvidenceError("persisted experiment plan is invalid") from exc
        if plan.experiment_id != record.id or plan.digest != record.plan_digest:
            raise AnalystEvidenceError("persisted experiment plan identity does not match")
        self._plan = plan
        return plan

    async def _runs(self) -> tuple[ExperimentRunRecord, ...]:
        plan = await self._load_plan()
        runs = tuple(
            (
                await self._session.scalars(
                    select(ExperimentRunRecord)
                    .where(ExperimentRunRecord.experiment_id == self._experiment_id)
                    .order_by(ExperimentRunRecord.slot_order)
                )
            ).all()
        )
        if len(runs) != len(plan.run_slots):
            raise AnalystEvidenceError("persisted experiment run set is incomplete")
        return runs

    async def scope(self) -> AnalysisScope:
        plan = await self._load_plan()
        runs = await self._runs()
        return AnalysisScope(
            experiment_id=plan.experiment_id,
            plan_digest=plan.digest,
            cell_ids=tuple(cell.id for cell in plan.cells),
            task_ids=tuple(task.task_id for task in plan.tasks),
            run_ids=tuple(run.run_id for run in runs),
            ablation_ids=tuple(ablation.id for ablation in plan.ablations),
        )

    async def _run(self, run_id: str) -> ExperimentRunRecord:
        run = await self._session.get(ExperimentRunRecord, run_id)
        if run is None or run.experiment_id != self._experiment_id:
            raise AnalystEvidenceError("run is outside the bound experiment")
        return run

    async def query_runs(self, args: QueryRunsArgs) -> tuple[ToolEvidence, ...]:
        scope = await self.scope()
        if args.cell_id is not None and args.cell_id not in scope.cell_ids:
            raise AnalystEvidenceError("cell is outside the bound experiment")
        if args.task_id is not None and args.task_id not in scope.task_ids:
            raise AnalystEvidenceError("task is outside the bound experiment")
        runs = await self._runs()
        selected = tuple(
            run
            for run in runs
            if (args.cell_id is None or run.cell_id == args.cell_id)
            and (args.task_id is None or run.task_id == args.task_id)
            and (args.status is None or run.status == args.status)
            and (args.outcome is None or run.normalized_outcome == args.outcome)
        )[: args.limit]
        return tuple(
            ToolEvidence(
                ref=EvidenceRef(id=f"run:{run.run_id}"),
                tool=ToolName.QUERY_RUNS,
                digest_bindings=tuple(
                    item for item in (scope.plan_digest, run.evidence_digest) if item is not None
                ),
                data=_data(
                    experiment_id=run.experiment_id,
                    run_id=run.run_id,
                    cell_id=run.cell_id,
                    task_id=run.task_id,
                    task_version=run.task_version,
                    repeat_index=run.repeat_index,
                    lane=run.lane,
                    status=run.status,
                    normalized_outcome=run.normalized_outcome,
                    source_outcome=run.source_outcome,
                    duration_ms=run.duration_ms,
                    input_tokens=run.input_tokens,
                    output_tokens=run.output_tokens,
                    steps=run.steps,
                    tool_calls=run.tool_calls,
                ),
            )
            for run in selected
        )

    async def compare_cells(self, args: CompareCellsArgs) -> tuple[ToolEvidence, ...]:
        scope = await self.scope()
        if args.left_cell_id == args.right_cell_id:
            raise AnalystEvidenceError("cell comparison requires two distinct cells")
        if args.left_cell_id not in scope.cell_ids or args.right_cell_id not in scope.cell_ids:
            raise AnalystEvidenceError("cell is outside the bound experiment")
        try:
            report = await build_experiment_report(
                self._session,
                self._experiment_id,
                artifact_path_guard=lambda path: self._trusted(path),
            )
        except (ExperimentReportError, EvidenceReadError) as exc:
            raise AnalystEvidenceError(
                "verified experiment report evidence is unavailable"
            ) from exc
        cells = {cell.cell_id: cell for cell in report.cells}
        plan = await self._load_plan()
        relevant_pair_ids = {
            definition.id
            for definition in plan.paired_comparisons
            if {definition.left_cell_id, definition.right_cell_id}
            == {args.left_cell_id, args.right_cell_id}
        }
        relevant_pairs = tuple(pair for pair in report.pairs if pair.pair_id in relevant_pair_ids)
        entries = [
            ToolEvidence(
                ref=EvidenceRef(id=f"cell:{self._experiment_id}:{cell_id}"),
                tool=ToolName.COMPARE_CELLS,
                digest_bindings=(scope.plan_digest, report.digest),
                data=_data(statistics=cells[cell_id].model_dump(mode="json")),
            )
            for cell_id in (args.left_cell_id, args.right_cell_id)
        ]
        entries.extend(
            ToolEvidence(
                ref=EvidenceRef(id=f"pair:{self._experiment_id}:{pair.pair_id}"),
                tool=ToolName.COMPARE_CELLS,
                digest_bindings=(scope.plan_digest, report.digest),
                data=_data(statistics=pair.model_dump(mode="json")),
            )
            for pair in relevant_pairs
        )
        return tuple(entries)

    def _trusted(self, path: Path) -> Path:
        from harnesslab.evidence.reader import trusted_artifact_path

        return trusted_artifact_path(path, self._artifact_roots)

    async def inspect_trace(self, args: InspectTraceArgs) -> tuple[ToolEvidence, ...]:
        scope = await self.scope()
        run = await self._run(args.run_id)
        try:
            trace, trace_digest, coverage = load_normalized_trace(run, self._artifact_roots)
        except EvidenceReadError as exc:
            if "not reported" not in str(exc):
                raise AnalystEvidenceError("normalized trace evidence is unavailable") from exc
            return (
                ToolEvidence(
                    ref=EvidenceRef(id=f"run:{run.run_id}"),
                    tool=ToolName.INSPECT_TRACE,
                    digest_bindings=(scope.plan_digest,),
                    data=_data(trace_status="NOT_REPORTED"),
                ),
            )
        events = tuple(event for event in trace.events if event.ordinal >= args.start_ordinal)[
            : args.limit
        ]
        return tuple(
            ToolEvidence(
                ref=EvidenceRef(id=f"trace:{run.run_id}#event:{event.ordinal}"),
                tool=ToolName.INSPECT_TRACE,
                digest_bindings=(scope.plan_digest, trace_digest),
                data=_data(
                    run_id=run.run_id,
                    ordinal=event.ordinal,
                    type=event.type.value,
                    status=event.status,
                    summary=_trace_summary(event.model_dump(mode="json", exclude_none=True)),
                    exit_code=event.exit_code,
                    coverage=coverage,
                ),
            )
            for event in events
        )

    async def inspect_failure(self, args: InspectFailureArgs) -> tuple[ToolEvidence, ...]:
        scope = await self.scope()
        run = await self._run(args.run_id)
        verifier_passed: object = None
        verifier_score: object = None
        summary: object = None
        if run.artifact_manifest_path is not None or run.evidence_digest is not None:
            try:
                raw = load_verified_manifest(run, self._artifact_roots).raw
            except EvidenceReadError as exc:
                raise AnalystEvidenceError("run failure evidence is unavailable") from exc
            verifier_passed = raw.get("verifier_passed")
            verifier_score = raw.get("verifier_score")
            summary = raw.get("summary")
        return (
            ToolEvidence(
                ref=EvidenceRef(id=f"run:{run.run_id}"),
                tool=ToolName.INSPECT_FAILURE,
                digest_bindings=tuple(
                    item for item in (scope.plan_digest, run.evidence_digest) if item is not None
                ),
                data=_data(
                    status=run.status,
                    normalized_outcome=run.normalized_outcome,
                    source_outcome=run.source_outcome,
                    failure_detail=run.failure_detail,
                    verifier_passed=verifier_passed,
                    verifier_score=verifier_score,
                    result_summary=summary,
                ),
            ),
        )

    async def get_task_contract(self, args: GetTaskContractArgs) -> tuple[ToolEvidence, ...]:
        scope = await self.scope()
        plan = await self._load_plan()
        matches = tuple(task for task in plan.tasks if task.task_id == args.task_id)
        if len(matches) != 1 or args.task_id not in scope.task_ids:
            raise AnalystEvidenceError("task is outside or ambiguous in the bound experiment")
        planned = matches[0]
        tasks_root = (self._repository_root / "tasks").resolve()
        candidate = (self._repository_root / planned.package_path).resolve()
        if tasks_root not in candidate.parents:
            raise AnalystEvidenceError("planned task package escapes the repository task root")
        try:
            package = TaskPackage.load(candidate)
        except TaskPackageError as exc:
            raise AnalystEvidenceError("planned task package cannot be reopened") from exc
        definition = package.definition
        if (
            definition.id != planned.task_id
            or definition.version != planned.task_version
            or definition.content_digest != planned.task_digest
            or package.verifier_digest != planned.verifier_identity
        ):
            raise AnalystEvidenceError("task package identity differs from the persisted plan")
        return (
            ToolEvidence(
                ref=EvidenceRef(id=f"task:{definition.id}@{definition.version}"),
                tool=ToolName.GET_TASK_CONTRACT,
                digest_bindings=(scope.plan_digest, definition.content_digest),
                data=_data(
                    task_id=definition.id,
                    task_version=definition.version,
                    task_digest=definition.content_digest,
                    instruction=definition.instruction,
                    domain=definition.domain,
                    lane_support=tuple(lane.value for lane in definition.lane_support),
                    budget=definition.budget.model_dump(mode="json"),
                    expected_tools=tuple(
                        tool.model_dump(mode="json") for tool in definition.expected_tools
                    ),
                    metadata=definition.metadata,
                    workspace_input_digest=planned.workspace_input_digest,
                    verifier_identity=planned.verifier_identity,
                ),
            ),
        )

    async def get_ablation(self, args: GetAblationArgs) -> tuple[ToolEvidence, ...]:
        scope = await self.scope()
        plan = await self._load_plan()
        matches = tuple(item for item in plan.ablations if item.id == args.ablation_id)
        if len(matches) != 1 or args.ablation_id not in scope.ablation_ids:
            raise AnalystEvidenceError("ablation is outside the bound experiment")
        definition = matches[0]
        persisted = await self._session.get(
            ExperimentAblationRecord, (self._experiment_id, args.ablation_id)
        )
        if persisted is None or persisted.definition_json != definition.model_dump(mode="json"):
            raise AnalystEvidenceError("persisted ablation differs from the immutable plan")
        try:
            report = await build_experiment_report(
                self._session,
                self._experiment_id,
                artifact_path_guard=lambda path: self._trusted(path),
            )
        except (ExperimentReportError, EvidenceReadError) as exc:
            raise AnalystEvidenceError("ablation report evidence is unavailable") from exc
        statistics = next(
            (item for item in report.ablations if item.ablation_id == args.ablation_id), None
        )
        if statistics is None:
            raise AnalystEvidenceError("ablation statistics are not reported")
        comparison = statistics.comparison
        limitations = tuple(
            f"{code}={count}" for code, count in comparison.excluded_reason_counts.items()
        )
        return (
            ToolEvidence(
                ref=EvidenceRef(id=f"ablation:{self._experiment_id}:{args.ablation_id}"),
                tool=ToolName.GET_ABLATION,
                digest_bindings=(scope.plan_digest, report.digest),
                data=_data(
                    base_cell_id=definition.base_cell_id,
                    variant_cell_id=definition.variant_cell_id,
                    changed_dimension=definition.changed_dimension,
                    evidence_tier=comparison.evidence_tier.value,
                    total_capability_pairs=comparison.total_capability_pairs,
                    comparable_pairs=comparison.comparable_pairs,
                    partially_comparable_pairs=comparison.partially_comparable_pairs,
                    not_comparable_pairs=comparison.not_comparable_pairs,
                    formal_eligible=comparison.formal_eligible,
                    binary=(
                        comparison.binary.model_dump(mode="json")
                        if comparison.binary is not None
                        else None
                    ),
                    limitations=limitations,
                    pair_identity=f"pair:{self._experiment_id}:{comparison.pair_id}",
                ),
            ),
        )

    async def failure_counts(self) -> Counter[str]:
        """Host-side deterministic hint for the fake backend; not an Agent tool."""

        return Counter(run.normalized_outcome or "NOT_REPORTED" for run in await self._runs())
