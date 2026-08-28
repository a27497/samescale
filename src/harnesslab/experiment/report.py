from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.comparability.engine import ComparabilityEngine
from harnesslab.comparability.manifest import load_manifest_facts
from harnesslab.comparability.models import (
    ComparabilityIntent,
    ComparabilityStatus,
    ComparisonFacts,
)
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.experiment.evidence import (
    ManifestControlMismatch,
    validate_manifest_against_slot,
)
from harnesslab.experiment.outcomes import (
    StatisticalOutcome,
    normalize_manifest_evidence,
)
from harnesslab.experiment.plan import (
    AnyExperimentPlan,
    ExperimentRunSlot,
    load_experiment_plan_payload,
)
from harnesslab.experiment.spec import ExperimentSpecError
from harnesslab.experiment.statistics import (
    CellStatistics,
    PairObservation,
    PairStatistics,
    RunObservation,
    summarize_cell,
    summarize_pair,
)
from harnesslab.sandbox.artifacts import sha256_file


class ExperimentReportError(RuntimeError):
    """Persisted experiment evidence is incomplete, mutable, or incoherent."""


@dataclass(frozen=True)
class VerifiedRunObservation:
    """One persisted run after its slot, digest, controls, and outcome agree."""

    run: ExperimentRunRecord
    observation: RunObservation
    facts: ComparisonFacts | None


@dataclass(frozen=True)
class VerifiedExperimentEvidence:
    """Shared verified-observation input for reports and read-only consumers."""

    plan: AnyExperimentPlan
    runs: tuple[ExperimentRunRecord, ...]
    observations: tuple[VerifiedRunObservation, ...]


class PairEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pair_id: str
    paired_slot_identity: str
    task_id: str
    repeat_index: int
    left_run_id: str
    right_run_id: str
    comparability: ComparabilityStatus
    reason_codes: tuple[str, ...]


class AblationStatistics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ablation_id: str
    base_cell_id: str
    variant_cell_id: str
    changed_dimension: str
    comparison: PairStatistics


class StatisticalConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    confidence_level: float = 0.95
    bootstrap_resamples: int
    bootstrap_seed: int
    pass_at_k: tuple[int, ...] = (1, 3, 5)
    capability_denominator: Literal["capability_passes_plus_capability_failures"] = (
        "capability_passes_plus_capability_failures"
    )


class ExperimentReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    experiment_id: str
    plan_digest: str
    plan_run_count: int
    statistical_configuration: StatisticalConfiguration
    cells: tuple[CellStatistics, ...]
    pair_evidence: tuple[PairEvidence, ...]
    pairs: tuple[PairStatistics, ...]
    ablations: tuple[AblationStatistics, ...]
    formal_ranking: tuple[str, ...]
    formal_ranking_note: str

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode()).hexdigest()

    def markdown(self) -> str:
        lines = [
            f"# Experiment {self.experiment_id}",
            "",
            f"Plan digest: `{self.plan_digest}`",
            f"Report digest: `{self.digest}`",
            "",
            "## Cells",
            "",
            "| Cell | Planned | Capability n | Pass | Fail | Infra | Cancelled | Tier |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        for cell in self.cells:
            lines.append(
                f"| {cell.cell_id} | {cell.planned_runs} | "
                f"{cell.completed_capability_runs} | {cell.capability_passes} | "
                f"{cell.capability_failures} | {cell.infra_failures} | "
                f"{cell.cancelled_runs} | {cell.evidence_tier.value} |"
            )
        lines.extend(["", "## Paired comparisons", ""])
        if not self.pairs:
            lines.append("No paired comparisons were declared.")
        for pair in self.pairs:
            lines.append(
                f"- `{pair.pair_id}`: comparable={pair.comparable_pairs}, "
                f"partial={pair.partially_comparable_pairs}, "
                f"not_comparable={pair.not_comparable_pairs}, "
                f"tier={pair.evidence_tier.value}, formal={str(pair.formal_eligible).lower()}"
            )
            if pair.excluded_reason_counts:
                reasons = ", ".join(
                    f"{code}={count}" for code, count in pair.excluded_reason_counts.items()
                )
                lines.append(f"  Exclusions/limitations: {reasons}")
        lines.extend(["", "## Ablations", ""])
        if not self.ablations:
            lines.append("No ablations were declared.")
        for ablation in self.ablations:
            lines.append(
                f"- `{ablation.ablation_id}` changed `{ablation.changed_dimension}`: "
                f"comparable={ablation.comparison.comparable_pairs}, "
                f"formal={str(ablation.comparison.formal_eligible).lower()}"
            )
        lines.extend(
            [
                "",
                "## Formal ranking",
                "",
                self.formal_ranking_note,
            ]
        )
        for index, cell_id in enumerate(self.formal_ranking, start=1):
            lines.append(f"{index}. `{cell_id}`")
        lines.extend(
            [
                "",
                "Infrastructure failures are disclosed separately and are excluded from the "
                "capability success-rate denominator.",
                "",
            ]
        )
        return "\n".join(lines)


def _number(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _manifest_metrics(raw: dict[str, Any]) -> dict[str, float | None]:
    provider_result = raw.get("provider_result")
    usage: object = raw.get("usage")
    duration: object = raw.get("duration_ms")
    steps: object = raw.get("trace_event_count")
    tool_calls: object = None
    if isinstance(provider_result, dict):
        usage = provider_result.get("usage")
        duration = provider_result.get("latency_ms")
        steps = 1
        tool_calls = 0
    event_types = raw.get("trace_event_types")
    if isinstance(event_types, list):
        tool_calls = sum(
            event in {"COMMAND_EXECUTION", "FILE_CHANGE", "MCP_TOOL_CALL"} for event in event_types
        )
    input_tokens: object = None
    output_tokens: object = None
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
    return {
        "duration_ms": _number(duration),
        "input_tokens": _number(input_tokens),
        "output_tokens": _number(output_tokens),
        "tool_calls": _number(tool_calls),
        "steps": _number(steps),
    }


def _load_persisted_manifest(
    run: ExperimentRunRecord,
    artifact_path_guard: Callable[[Path], Path] | None = None,
) -> tuple[dict[str, Any], ComparisonFacts]:
    if run.artifact_manifest_path is None or run.evidence_digest is None:
        raise ExperimentReportError(f"run {run.run_id} lacks persisted artifact identity")
    path = Path(run.artifact_manifest_path)
    if artifact_path_guard is not None:
        path = artifact_path_guard(path)
    if not path.is_file() or sha256_file(path) != run.evidence_digest:
        raise ExperimentReportError(f"run {run.run_id} artifact digest is unavailable or changed")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExperimentReportError(f"run {run.run_id} manifest is unreadable") from exc
    if not isinstance(raw, dict):
        raise ExperimentReportError(f"run {run.run_id} manifest must contain an object")
    return raw, load_manifest_facts(path)


async def load_verified_experiment_evidence(
    session: AsyncSession,
    experiment_id: str,
    *,
    artifact_path_guard: Callable[[Path], Path] | None = None,
) -> VerifiedExperimentEvidence:
    """Load immutable run observations once without calculating any statistics."""

    experiment = await session.get(ExperimentRecord, experiment_id)
    if experiment is None:
        raise ExperimentReportError("experiment does not exist")
    try:
        plan = load_experiment_plan_payload(experiment.plan_json)
    except ExperimentSpecError as exc:
        raise ExperimentReportError("persisted experiment plan is invalid") from exc
    if plan.digest != experiment.plan_digest:
        raise ExperimentReportError("persisted plan digest does not match plan bytes")
    runs = tuple(
        (
            await session.scalars(
                select(ExperimentRunRecord)
                .where(ExperimentRunRecord.experiment_id == experiment_id)
                .order_by(ExperimentRunRecord.slot_order)
            )
        ).all()
    )
    if len(runs) != len(plan.run_slots):
        raise ExperimentReportError("persisted experiment run set is incomplete")

    verified: list[VerifiedRunObservation] = []
    for run in runs:
        if run.normalized_outcome is None or run.source_outcome is None:
            continue
        normalized = StatisticalOutcome(run.normalized_outcome)
        metrics: dict[str, float | None] = {
            "duration_ms": None,
            "input_tokens": None,
            "output_tokens": None,
            "tool_calls": None,
            "steps": None,
        }
        facts: ComparisonFacts | None = None
        has_artifact = run.artifact_manifest_path is not None or run.evidence_digest is not None
        if has_artifact:
            raw, facts = _load_persisted_manifest(run, artifact_path_guard)
            slot = ExperimentRunSlot.model_validate(run.slot_json)
            try:
                validate_manifest_against_slot(raw, facts, slot)
            except ManifestControlMismatch as exc:
                raise ExperimentReportError(str(exc)) from exc
            try:
                manifest_evidence = normalize_manifest_evidence(raw)
            except ValueError as exc:
                raise ExperimentReportError(
                    f"unsupported persisted source outcome: {raw.get('outcome')!r}"
                ) from exc
            if normalized is not manifest_evidence.outcome:
                raise ExperimentReportError(
                    f"run {run.run_id} normalized outcome disagrees with immutable evidence"
                )
            if manifest_evidence.source_taxonomy != run.source_outcome:
                raise ExperimentReportError(
                    f"run {run.run_id} source outcome disagrees with immutable evidence"
                )
            metrics = _manifest_metrics(raw)
        elif normalized in {
            StatisticalOutcome.CAPABILITY_PASS,
            StatisticalOutcome.CAPABILITY_FAIL,
        }:
            raise ExperimentReportError(
                f"run {run.run_id} capability outcome lacks immutable lane evidence"
            )
        verified.append(
            VerifiedRunObservation(
                run=run,
                observation=RunObservation(
                    run_id=run.run_id,
                    task_id=run.task_id,
                    repeat_index=run.repeat_index,
                    paired_slot_identity=run.paired_slot_identity,
                    outcome=normalized,
                    source_outcome=run.source_outcome,
                    duration_ms=metrics["duration_ms"],
                    input_tokens=metrics["input_tokens"],
                    output_tokens=metrics["output_tokens"],
                    tool_calls=metrics["tool_calls"],
                    steps=metrics["steps"],
                    explicit_cost=None,
                ),
                facts=facts,
            )
        )
    return VerifiedExperimentEvidence(plan=plan, runs=runs, observations=tuple(verified))


async def build_experiment_report(
    session: AsyncSession,
    experiment_id: str,
    *,
    bootstrap_resamples: int = 9_999,
    artifact_path_guard: Callable[[Path], Path] | None = None,
) -> ExperimentReport:
    evidence = await load_verified_experiment_evidence(
        session, experiment_id, artifact_path_guard=artifact_path_guard
    )
    plan = evidence.plan

    observations_by_cell: dict[str, list[RunObservation]] = defaultdict(list)
    observations_by_run: dict[str, RunObservation] = {}
    facts_by_run: dict[str, ComparisonFacts] = {}
    runs_by_cell_pair: dict[tuple[str, str], ExperimentRunRecord] = {}
    for item in evidence.observations:
        run = item.run
        observation = item.observation
        if item.facts is not None:
            facts_by_run[run.run_id] = item.facts
        observations_by_cell[run.cell_id].append(observation)
        observations_by_run[run.run_id] = observation
        runs_by_cell_pair[(run.cell_id, run.paired_slot_identity)] = run

    cells = tuple(
        summarize_cell(
            cell.id,
            sum(slot.cell_id == cell.id for slot in plan.run_slots),
            tuple(observations_by_cell[cell.id]),
            intended_task_ids=tuple(task.task_id for task in plan.tasks),
            seed=plan.execution_seed,
            bootstrap_resamples=bootstrap_resamples,
        )
        for cell in plan.cells
    )

    engine = ComparabilityEngine()
    pair_evidence: list[PairEvidence] = []
    pair_statistics: list[PairStatistics] = []

    def comparison_observations(
        pair_id: str,
        left_cell_id: str,
        right_cell_id: str,
        intent: ComparabilityIntent,
    ) -> tuple[PairObservation, ...]:
        paired: list[PairObservation] = []
        identities = sorted(
            {
                identity
                for cell_id, identity in runs_by_cell_pair
                if cell_id in {left_cell_id, right_cell_id}
            }
        )
        for identity in identities:
            left = runs_by_cell_pair.get((left_cell_id, identity))
            right = runs_by_cell_pair.get((right_cell_id, identity))
            if left is None or right is None:
                continue
            left_observation = observations_by_run.get(left.run_id)
            right_observation = observations_by_run.get(right.run_id)
            capability = {
                StatisticalOutcome.CAPABILITY_PASS,
                StatisticalOutcome.CAPABILITY_FAIL,
            }
            if (
                left_observation is None
                or right_observation is None
                or left_observation.outcome not in capability
                or right_observation.outcome not in capability
            ):
                continue
            report = engine.assess(
                facts_by_run[left.run_id], facts_by_run[right.run_id], intent=intent
            )
            reasons = tuple(reason.code.value for reason in report.reasons)
            pair_evidence.append(
                PairEvidence(
                    pair_id=pair_id,
                    paired_slot_identity=identity,
                    task_id=left.task_id,
                    repeat_index=left.repeat_index,
                    left_run_id=left.run_id,
                    right_run_id=right.run_id,
                    comparability=report.status,
                    reason_codes=reasons,
                )
            )
            paired.append(
                PairObservation(
                    pair_id=pair_id,
                    task_id=left.task_id,
                    repeat_index=left.repeat_index,
                    paired_slot_identity=identity,
                    left_pass=left_observation.outcome is StatisticalOutcome.CAPABILITY_PASS,
                    right_pass=right_observation.outcome is StatisticalOutcome.CAPABILITY_PASS,
                    left_duration_ms=left_observation.duration_ms,
                    right_duration_ms=right_observation.duration_ms,
                    comparability=report.status,
                    reason_codes=reasons,
                )
            )
        return tuple(paired)

    for pair in plan.paired_comparisons:
        observations = comparison_observations(
            pair.id, pair.left_cell_id, pair.right_cell_id, pair.intent
        )
        pair_statistics.append(
            summarize_pair(
                pair.id,
                observations,
                intended_task_ids=tuple(task.task_id for task in plan.tasks),
                seed=plan.execution_seed,
                bootstrap_resamples=bootstrap_resamples,
            )
        )

    ablations: list[AblationStatistics] = []
    for ablation in plan.ablations:
        pair_id = f"ablation-{ablation.id}"
        observations = comparison_observations(
            pair_id,
            ablation.base_cell_id,
            ablation.variant_cell_id,
            ComparabilityIntent.GENERAL,
        )
        ablations.append(
            AblationStatistics(
                ablation_id=ablation.id,
                base_cell_id=ablation.base_cell_id,
                variant_cell_id=ablation.variant_cell_id,
                changed_dimension=ablation.changed_dimension,
                comparison=summarize_pair(
                    pair_id,
                    observations,
                    intended_task_ids=tuple(task.task_id for task in plan.tasks),
                    seed=plan.execution_seed,
                    bootstrap_resamples=bootstrap_resamples,
                ),
            )
        )

    eligible_cells = {
        cell_id
        for pair, definition in zip(pair_statistics, plan.paired_comparisons, strict=True)
        if pair.formal_eligible
        for cell_id in (definition.left_cell_id, definition.right_cell_id)
    }
    formal = [cell for cell in cells if cell.formal_eligible and cell.cell_id in eligible_cells]
    formal.sort(
        key=lambda cell: (
            -(cell.success_rate if cell.success_rate is not None else -1.0),
            cell.cell_id,
        )
    )
    ranking = tuple(cell.cell_id for cell in formal)
    ranking_note = (
        "Only cells in FORMAL, COMPARABLE paired evidence are ordered."
        if ranking
        else "No cells have both FORMAL repetition evidence and a COMPARABLE formal pair."
    )
    return ExperimentReport(
        experiment_id=experiment_id,
        plan_digest=plan.digest,
        plan_run_count=len(plan.run_slots),
        statistical_configuration=StatisticalConfiguration(
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_seed=plan.execution_seed,
        ),
        cells=cells,
        pair_evidence=tuple(
            sorted(pair_evidence, key=lambda item: (item.pair_id, item.paired_slot_identity))
        ),
        pairs=tuple(pair_statistics),
        ablations=tuple(ablations),
        formal_ranking=ranking,
        formal_ranking_note=ranking_note,
    )
