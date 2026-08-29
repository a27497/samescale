from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from harnesslab.comparability.engine import ComparabilityEngine
from harnesslab.comparability.models import (
    ComparabilityIntent,
    ComparabilityStatus,
    ReasonCode,
    canonical_digest,
)
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.report import VerifiedExperimentEvidence, VerifiedRunObservation
from harnesslab.experiment.statistics import EvidenceTier, aggregate_evidence_tier
from harnesslab.tasks.package import TaskPackage, TaskPackageError


class ModelComparisonAnalysisError(ValueError):
    """Persisted evidence cannot support the requested model-comparison view."""


class AnalysisModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class FailurePresentationCategory(StrEnum):
    CAPABILITY_FAILURE = "CAPABILITY_FAILURE"
    PROVIDER_INFRASTRUCTURE = "PROVIDER_INFRASTRUCTURE"
    VERIFIER_INFRASTRUCTURE = "VERIFIER_INFRASTRUCTURE"
    BUDGET_EXHAUSTION = "BUDGET_EXHAUSTION"
    INCOMPLETE_PROVIDER_OUTPUT = "INCOMPLETE_PROVIDER_OUTPUT"
    CONTROL_DRIFT = "CONTROL_DRIFT"
    OTHER_INFRASTRUCTURE = "OTHER_INFRASTRUCTURE"
    UNACQUIRED_SLOT = "UNACQUIRED_SLOT"


class RateEvidence(AnalysisModel):
    status: Literal[Availability.AVAILABLE, Availability.NOT_AVAILABLE]
    value: float | None = Field(default=None, ge=0.0, le=1.0)
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)


class TotalEvidence(AnalysisModel):
    status: Availability
    known_slots: int = Field(ge=0)
    expected_slots: int = Field(ge=0)
    known_total: float | None = Field(default=None, ge=0)
    total: float | None = Field(default=None, ge=0)
    unit: str
    reason: str | None = None


class IdentityCoverage(AnalysisModel):
    status: Availability
    counts: dict[str, int]
    missing_slots: int = Field(ge=0)


class TraceCoverageSummary(AnalysisModel):
    status: Availability
    counts: dict[str, int]
    missing_slots: int = Field(ge=0)


class UsageCostSummary(AnalysisModel):
    input_tokens: TotalEvidence
    output_tokens: TotalEvidence
    explicit_cost: TotalEvidence


class ModelOutcomeSummary(AnalysisModel):
    model_label: Literal["MODEL_A", "MODEL_B"]
    cell_id: str
    requested_model: str
    provider_route: str
    planned_slots: int = Field(ge=0)
    acquired_slots: int = Field(ge=0)
    unacquired_slots: int = Field(ge=0)
    capability_denominator: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    infra: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    pass_rate: RateEvidence
    evidence_tier: EvidenceTier
    failure_categories: dict[FailurePresentationCategory, int]
    observed_models: IdentityCoverage
    observed_providers: IdentityCoverage
    trace_coverage: TraceCoverageSummary
    usage_and_cost: UsageCostSummary


class PairOutcomeSummary(AnalysisModel):
    planned_pairs: int = Field(ge=0)
    matched_capability_pairs: int = Field(ge=0)
    both_pass: int = Field(ge=0)
    model_a_only_pass: int = Field(ge=0)
    model_b_only_pass: int = Field(ge=0)
    both_fail: int = Field(ge=0)
    infra_pairs: int = Field(ge=0)
    missing_pairs: int = Field(ge=0)
    infra_or_missing_pairs: int = Field(ge=0)
    raw_percentage_point_difference: float | None = Field(default=None, ge=-100.0, le=100.0)
    raw_difference_direction: Literal["MODEL_A_HIGHER", "MODEL_B_HIGHER", "EQUAL", "NOT_AVAILABLE"]


class ComparabilitySummary(AnalysisModel):
    category: Literal["COMPARABLE", "PARTIALLY_COMPARABLE", "NOT_COMPARABLE", "NOT_AVAILABLE"]
    assessed_pairs: int = Field(ge=0)
    category_counts: dict[ComparabilityStatus, int]
    reason_counts: dict[str, int]
    unassessed_planned_pairs: int = Field(ge=0)


class ControlDriftSummary(AnalysisModel):
    status: Literal["DETECTED", "NOT_DETECTED", "NOT_AVAILABLE"]
    affected_pairs: int = Field(ge=0)
    affected_runs: int = Field(ge=0)
    assessed_pairs: int = Field(ge=0)
    reason_counts: dict[str, int]


class BreakdownRow(AnalysisModel):
    dimension: Literal["language", "task_family"]
    value: str
    planned_pairs: int = Field(ge=0)
    matched_capability_pairs: int = Field(ge=0)
    both_pass: int = Field(ge=0)
    model_a_only_pass: int = Field(ge=0)
    model_b_only_pass: int = Field(ge=0)
    both_fail: int = Field(ge=0)
    infra_pairs: int = Field(ge=0)
    missing_pairs: int = Field(ge=0)
    model_a_pass_rate: RateEvidence
    model_b_pass_rate: RateEvidence


class RecoveryAttemptSummary(AnalysisModel):
    status: Literal[Availability.AVAILABLE, Availability.NOT_AVAILABLE]
    explicitly_marked_primary_acquisitions: int = Field(ge=0)
    explicitly_marked_recovery_acquisitions: int = Field(ge=0)
    unmarked_acquisitions: int = Field(ge=0)
    lease_claim_attempts: int = Field(ge=0)
    note: str


class ConclusionSemantics(AnalysisModel):
    scope: Literal["EXPLORATORY_DESCRIPTIVE", "DESCRIPTIVE"]
    evaluation_mode: str
    repeat_count: int = Field(ge=1)
    permitted_interpretation: str


class OverallOutcomeSummary(AnalysisModel):
    planned_slots: int = Field(ge=0)
    acquired_slots: int = Field(ge=0)
    unacquired_slots: int = Field(ge=0)
    capability_denominator: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    infra: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    failure_categories: dict[FailurePresentationCategory, int]


class ModelComparisonAnalysis(AnalysisModel):
    schema_version: Literal[1] = 1
    report_kind: Literal["MODEL_COMPARISON_CLOSEOUT"] = "MODEL_COMPARISON_CLOSEOUT"
    experiment_id: str
    plan_digest: str
    comparison_intent: Literal["MODEL_COMPARISON"] = "MODEL_COMPARISON"
    evidence_source: Literal["PERSISTED_IMMUTABLE_EXPERIMENT_EVIDENCE"] = (
        "PERSISTED_IMMUTABLE_EXPERIMENT_EVIDENCE"
    )
    conclusion_semantics: ConclusionSemantics
    overall: OverallOutcomeSummary
    models: tuple[ModelOutcomeSummary, ModelOutcomeSummary]
    pairs: PairOutcomeSummary
    comparability: ComparabilitySummary
    control_drift: ControlDriftSummary
    trace_coverage: TraceCoverageSummary
    observed_models: IdentityCoverage
    observed_providers: IdentityCoverage
    recovery_attempts: RecoveryAttemptSummary
    breakdowns: tuple[BreakdownRow, ...]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class ModelComparisonCloseout(AnalysisModel):
    schema_version: Literal[1] = 1
    analysis_digest: str
    analysis: ModelComparisonAnalysis

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


@dataclass(frozen=True)
class _PairRow:
    paired_slot_identity: str
    task_id: str
    model_a: VerifiedRunObservation | None
    model_b: VerifiedRunObservation | None
    category: Literal["CAPABILITY", "INFRA", "MISSING"]


CAPABILITY_OUTCOMES = {
    StatisticalOutcome.CAPABILITY_PASS,
    StatisticalOutcome.CAPABILITY_FAIL,
}
CONTROL_DRIFT_REASON_CODES = {
    ReasonCode.HARD_CONTROL_MISMATCH.value,
    ReasonCode.RESOURCE_ENVELOPE_MISMATCH.value,
    ReasonCode.VERIFIER_EXECUTION_MISMATCH.value,
    ReasonCode.VERIFIER_CONTROL_EXECUTION_MISMATCH.value,
}


def _rate(passed: int, denominator: int) -> RateEvidence:
    return RateEvidence(
        status=Availability.AVAILABLE if denominator else Availability.NOT_AVAILABLE,
        value=passed / denominator if denominator else None,
        numerator=passed,
        denominator=denominator,
    )


def _availability(known: int, expected: int) -> Availability:
    if expected > 0 and known == expected:
        return Availability.AVAILABLE
    if known > 0:
        return Availability.PARTIAL
    return Availability.NOT_AVAILABLE


def _identity_coverage(values: tuple[str | None, ...]) -> IdentityCoverage:
    counts = Counter(value for value in values if value is not None)
    return IdentityCoverage(
        status=_availability(sum(counts.values()), len(values)),
        counts=dict(sorted(counts.items())),
        missing_slots=len(values) - sum(counts.values()),
    )


def _trace_coverage(values: tuple[str | None, ...]) -> TraceCoverageSummary:
    counts = Counter(value for value in values if value is not None)
    return TraceCoverageSummary(
        status=_availability(sum(counts.values()), len(values)),
        counts=dict(sorted(counts.items())),
        missing_slots=len(values) - sum(counts.values()),
    )


def _complete_failure_counts(
    counts: Counter[FailurePresentationCategory],
) -> dict[FailurePresentationCategory, int]:
    return {category: counts[category] for category in FailurePresentationCategory}


def _total_evidence(
    values: tuple[int | float | None, ...], *, unit: str, incomplete_is_not_available: bool = False
) -> TotalEvidence:
    known = tuple(float(value) for value in values if value is not None)
    status = _availability(len(known), len(values))
    if incomplete_is_not_available and status is not Availability.AVAILABLE:
        status = Availability.NOT_AVAILABLE
    complete_total = float(sum(known)) if status is Availability.AVAILABLE else None
    return TotalEvidence(
        status=status,
        known_slots=len(known),
        expected_slots=len(values),
        known_total=float(sum(known)) if known else None,
        total=complete_total,
        unit=unit,
        reason=(
            "one or more acquired slots lack explicit cost evidence"
            if incomplete_is_not_available and status is Availability.NOT_AVAILABLE
            else None
        ),
    )


def _provider_identity(item: VerifiedRunObservation) -> str | None:
    raw = item.manifest
    if raw is None:
        return None
    provider = raw.get("provider")
    if isinstance(provider, str):
        return provider
    provider_result = raw.get("provider_result")
    if isinstance(provider_result, dict):
        nested = provider_result.get("provider")
        if isinstance(nested, str):
            return nested
    return None


def _recovery_marker(item: VerifiedRunObservation) -> str | None:
    candidates: tuple[dict[str, Any], ...] = tuple(
        value for value in (item.run.slot_json, item.manifest) if isinstance(value, dict)
    )
    for value in candidates:
        marker = value.get("acquisition_kind")
        if marker in {"PRIMARY", "RECOVERY"}:
            return str(marker)
        if value.get("recovery_attempt_identity") is not None:
            return "RECOVERY"
        if value.get("recovery_attempt_index") == 0:
            return "PRIMARY"
        if value.get("recovery_attempt_index") == 1:
            return "RECOVERY"
    return None


def _failure_category(
    item: VerifiedRunObservation | None,
) -> FailurePresentationCategory | None:
    if item is None:
        return FailurePresentationCategory.UNACQUIRED_SLOT
    outcome = item.observation.outcome
    raw = item.manifest or {}
    source = item.observation.source_outcome
    summary = raw.get("summary")
    summary_text = summary.lower() if isinstance(summary, str) else ""
    provider_failure = raw.get("provider_failure")
    provider_result = raw.get("provider_result")
    incomplete_reason: object = None
    stop_reason: object = None
    if isinstance(provider_result, dict):
        incomplete_reason = provider_result.get("incomplete_reason")
        stop_reason = provider_result.get("stop_reason")
    if (
        "execution_budget_exhausted" in source
        or incomplete_reason == "max_output_tokens"
        or stop_reason in {"max_tokens", "max_output_tokens", "length"}
        or "output-token budget" in summary_text
    ):
        return FailurePresentationCategory.BUDGET_EXHAUSTION
    if outcome is StatisticalOutcome.CAPABILITY_FAIL:
        return FailurePresentationCategory.CAPABILITY_FAILURE
    if outcome is StatisticalOutcome.CANCELLED:
        return FailurePresentationCategory.UNACQUIRED_SLOT
    if outcome is not StatisticalOutcome.INFRA_FAILURE:
        return None
    if source == "control_identity_mismatch" or source.startswith("control_identity_mismatch:"):
        return FailurePresentationCategory.CONTROL_DRIFT
    if provider_failure == "incomplete_response":
        return FailurePresentationCategory.INCOMPLETE_PROVIDER_OUTPUT
    if source == "provider_error" or isinstance(provider_failure, str):
        return FailurePresentationCategory.PROVIDER_INFRASTRUCTURE
    if "verification failed" in summary_text or "verifier" in source:
        return FailurePresentationCategory.VERIFIER_INFRASTRUCTURE
    return FailurePresentationCategory.OTHER_INFRASTRUCTURE


def _evaluation_mode(evidence: VerifiedExperimentEvidence) -> str:
    value = getattr(evidence.plan, "evaluation_mode", None)
    return value.value if value is not None else "NOT_AVAILABLE"


def _task_dimensions(
    evidence: VerifiedExperimentEvidence, repository_root: Path
) -> dict[str, dict[str, str]]:
    dimensions: dict[str, dict[str, str]] = {}
    for task in evidence.plan.tasks:
        metadata: dict[str, str] = {}
        try:
            package = TaskPackage.load(repository_root / task.package_path)
        except TaskPackageError:
            package = None
        if package is not None:
            raw = package.definition.metadata
            language = raw.get("language")
            family = raw.get("scenario_family") or raw.get("category")
            if language:
                metadata["language"] = language
            if family:
                metadata["task_family"] = family
        dimensions[task.task_id] = metadata
    return dimensions


def _pair_rows(
    evidence: VerifiedExperimentEvidence, model_a_cell: str, model_b_cell: str
) -> tuple[_PairRow, ...]:
    planned: dict[str, dict[str, str]] = defaultdict(dict)
    task_by_identity: dict[str, str] = {}
    for slot in evidence.plan.run_slots:
        if slot.cell_id not in {model_a_cell, model_b_cell}:
            continue
        planned[slot.paired_slot_identity][slot.cell_id] = slot.slot_id
        task_by_identity[slot.paired_slot_identity] = slot.task.task_id
    incomplete = [
        identity
        for identity, cells in planned.items()
        if set(cells) != {model_a_cell, model_b_cell}
    ]
    if incomplete:
        raise ModelComparisonAnalysisError(
            "model comparison plan does not contain a complete two-model slot pair"
        )
    observed = {
        (item.run.cell_id, item.run.paired_slot_identity): item for item in evidence.observations
    }
    rows: list[_PairRow] = []
    for identity in sorted(planned):
        model_a = observed.get((model_a_cell, identity))
        model_b = observed.get((model_b_cell, identity))
        outcomes = tuple(
            item.observation.outcome for item in (model_a, model_b) if item is not None
        )
        if len(outcomes) == 2 and all(outcome in CAPABILITY_OUTCOMES for outcome in outcomes):
            category = "CAPABILITY"
        elif StatisticalOutcome.INFRA_FAILURE in outcomes:
            category = "INFRA"
        else:
            category = "MISSING"
        rows.append(
            _PairRow(
                paired_slot_identity=identity,
                task_id=task_by_identity[identity],
                model_a=model_a,
                model_b=model_b,
                category=cast(Literal["CAPABILITY", "INFRA", "MISSING"], category),
            )
        )
    return tuple(rows)


def _model_summary(
    evidence: VerifiedExperimentEvidence,
    *,
    label: Literal["MODEL_A", "MODEL_B"],
    cell_id: str,
) -> ModelOutcomeSummary:
    cell = next(cell for cell in evidence.plan.cells if cell.id == cell_id)
    planned = tuple(slot for slot in evidence.plan.run_slots if slot.cell_id == cell_id)
    observations = tuple(item for item in evidence.observations if item.run.cell_id == cell_id)
    acquired = tuple(
        item
        for item in observations
        if item.observation.outcome is not StatisticalOutcome.CANCELLED
    )
    passed = sum(
        item.observation.outcome is StatisticalOutcome.CAPABILITY_PASS for item in acquired
    )
    failed = sum(
        item.observation.outcome is StatisticalOutcome.CAPABILITY_FAIL for item in acquired
    )
    infra = sum(item.observation.outcome is StatisticalOutcome.INFRA_FAILURE for item in acquired)
    cancelled = sum(
        item.observation.outcome is StatisticalOutcome.CANCELLED for item in observations
    )
    categories = Counter(
        category for item in acquired if (category := _failure_category(item)) is not None
    )
    missing = len(planned) - len(acquired)
    if missing:
        categories[FailurePresentationCategory.UNACQUIRED_SLOT] += missing
    observed_models = tuple(
        item.facts.observed_model if item.facts is not None else None for item in acquired
    )
    providers = tuple(_provider_identity(item) for item in acquired)
    traces = tuple(
        item.facts.trace_coverage if item.facts is not None else None for item in acquired
    )
    capability = passed + failed
    return ModelOutcomeSummary(
        model_label=label,
        cell_id=cell_id,
        requested_model=cell.requested_model,
        provider_route=cell.provider_route,
        planned_slots=len(planned),
        acquired_slots=len(acquired),
        unacquired_slots=missing,
        capability_denominator=capability,
        passed=passed,
        failed=failed,
        infra=infra,
        cancelled=cancelled,
        pass_rate=_rate(passed, capability),
        evidence_tier=aggregate_evidence_tier(
            tuple(
                sum(
                    item.run.task_id == task.task_id
                    and item.observation.outcome in CAPABILITY_OUTCOMES
                    for item in observations
                )
                for task in evidence.plan.tasks
            )
        ),
        failure_categories=_complete_failure_counts(categories),
        observed_models=_identity_coverage(observed_models),
        observed_providers=_identity_coverage(providers),
        trace_coverage=_trace_coverage(traces),
        usage_and_cost=UsageCostSummary(
            input_tokens=_total_evidence(
                tuple(item.run.input_tokens for item in acquired), unit="tokens"
            ),
            output_tokens=_total_evidence(
                tuple(item.run.output_tokens for item in acquired), unit="tokens"
            ),
            explicit_cost=_total_evidence(
                tuple(item.run.explicit_cost for item in acquired),
                unit="USD",
                incomplete_is_not_available=True,
            ),
        ),
    )


def _pair_summary(rows: tuple[_PairRow, ...]) -> PairOutcomeSummary:
    capability = tuple(row for row in rows if row.category == "CAPABILITY")
    both_pass = 0
    model_a_only = 0
    model_b_only = 0
    both_fail = 0
    for row in capability:
        assert row.model_a is not None and row.model_b is not None
        model_a_pass = row.model_a.observation.outcome is StatisticalOutcome.CAPABILITY_PASS
        model_b_pass = row.model_b.observation.outcome is StatisticalOutcome.CAPABILITY_PASS
        if model_a_pass and model_b_pass:
            both_pass += 1
        elif model_a_pass:
            model_a_only += 1
        elif model_b_pass:
            model_b_only += 1
        else:
            both_fail += 1
    if capability:
        difference = 100.0 * (model_b_only - model_a_only) / len(capability)
        direction = (
            "MODEL_B_HIGHER" if difference > 0 else "MODEL_A_HIGHER" if difference < 0 else "EQUAL"
        )
    else:
        difference = None
        direction = "NOT_AVAILABLE"
    infra = sum(row.category == "INFRA" for row in rows)
    missing = sum(row.category == "MISSING" for row in rows)
    return PairOutcomeSummary(
        planned_pairs=len(rows),
        matched_capability_pairs=len(capability),
        both_pass=both_pass,
        model_a_only_pass=model_a_only,
        model_b_only_pass=model_b_only,
        both_fail=both_fail,
        infra_pairs=infra,
        missing_pairs=missing,
        infra_or_missing_pairs=infra + missing,
        raw_percentage_point_difference=difference,
        raw_difference_direction=direction,
    )


def _comparability(
    rows: tuple[_PairRow, ...],
) -> tuple[ComparabilitySummary, ControlDriftSummary]:
    engine = ComparabilityEngine()
    statuses: Counter[ComparabilityStatus] = Counter()
    reasons: Counter[str] = Counter()
    drift_reasons: Counter[str] = Counter()
    affected_pairs = 0
    assessed = 0
    for row in rows:
        if row.model_a is None or row.model_b is None:
            continue
        if row.model_a.facts is None or row.model_b.facts is None:
            continue
        report = engine.assess(
            row.model_a.facts,
            row.model_b.facts,
            intent=ComparabilityIntent.MODEL_COMPARISON,
        )
        assessed += 1
        statuses[report.status] += 1
        pair_drift = False
        for reason in report.reasons:
            code = reason.code.value
            reasons[code] += 1
            if code in CONTROL_DRIFT_REASON_CODES:
                drift_reasons[code] += 1
                pair_drift = True
        if pair_drift:
            affected_pairs += 1
    if ComparabilityStatus.NOT_COMPARABLE in statuses:
        category = "NOT_COMPARABLE"
    elif ComparabilityStatus.PARTIALLY_COMPARABLE in statuses:
        category = "PARTIALLY_COMPARABLE"
    elif ComparabilityStatus.COMPARABLE in statuses:
        category = "COMPARABLE"
    else:
        category = "NOT_AVAILABLE"
    affected_runs = sum(
        _failure_category(item) is FailurePresentationCategory.CONTROL_DRIFT
        for row in rows
        for item in (row.model_a, row.model_b)
        if item is not None
    )
    drift_status = (
        "DETECTED"
        if affected_pairs or affected_runs
        else "NOT_DETECTED"
        if assessed
        else "NOT_AVAILABLE"
    )
    return (
        ComparabilitySummary(
            category=category,
            assessed_pairs=assessed,
            category_counts=dict(sorted(statuses.items(), key=lambda item: item[0].value)),
            reason_counts=dict(sorted(reasons.items())),
            unassessed_planned_pairs=len(rows) - assessed,
        ),
        ControlDriftSummary(
            status=drift_status,
            affected_pairs=affected_pairs,
            affected_runs=affected_runs,
            assessed_pairs=assessed,
            reason_counts=dict(sorted(drift_reasons.items())),
        ),
    )


def _breakdown(
    rows: tuple[_PairRow, ...], dimensions: dict[str, dict[str, str]]
) -> tuple[BreakdownRow, ...]:
    grouped: dict[tuple[str, str], list[_PairRow]] = defaultdict(list)
    for row in rows:
        for dimension, value in dimensions.get(row.task_id, {}).items():
            if dimension in {"language", "task_family"}:
                grouped[(dimension, value)].append(row)
    result: list[BreakdownRow] = []
    for (dimension, value), group in sorted(grouped.items()):
        pair = _pair_summary(tuple(group))
        model_a_passes = 0
        model_b_passes = 0
        for row in group:
            if row.category != "CAPABILITY":
                continue
            assert row.model_a is not None and row.model_b is not None
            model_a_passes += row.model_a.observation.outcome is StatisticalOutcome.CAPABILITY_PASS
            model_b_passes += row.model_b.observation.outcome is StatisticalOutcome.CAPABILITY_PASS
        result.append(
            BreakdownRow(
                dimension=cast(Literal["language", "task_family"], dimension),
                value=value,
                planned_pairs=pair.planned_pairs,
                matched_capability_pairs=pair.matched_capability_pairs,
                both_pass=pair.both_pass,
                model_a_only_pass=pair.model_a_only_pass,
                model_b_only_pass=pair.model_b_only_pass,
                both_fail=pair.both_fail,
                infra_pairs=pair.infra_pairs,
                missing_pairs=pair.missing_pairs,
                model_a_pass_rate=_rate(model_a_passes, pair.matched_capability_pairs),
                model_b_pass_rate=_rate(model_b_passes, pair.matched_capability_pairs),
            )
        )
    return tuple(result)


def analyze_model_comparison(
    evidence: VerifiedExperimentEvidence,
    *,
    repository_root: Path,
) -> ModelComparisonCloseout:
    """Build a deterministic closeout from persisted evidence without executing a subject."""

    if evidence.plan.comparison_intent != ComparabilityIntent.MODEL_COMPARISON.value:
        raise ModelComparisonAnalysisError("experiment is not a MODEL_COMPARISON")
    if len(evidence.plan.cells) != 2 or any(cell.lane.value != "M" for cell in evidence.plan.cells):
        raise ModelComparisonAnalysisError(
            "MODEL_COMPARISON analysis requires exactly two direct-model cells"
        )
    model_a_cell, model_b_cell = (cell.id for cell in evidence.plan.cells)
    rows = _pair_rows(evidence, model_a_cell, model_b_cell)
    model_a = _model_summary(evidence, label="MODEL_A", cell_id=model_a_cell)
    model_b = _model_summary(evidence, label="MODEL_B", cell_id=model_b_cell)
    pair_summary = _pair_summary(rows)
    comparability, drift = _comparability(rows)
    all_acquired = tuple(
        item
        for item in evidence.observations
        if item.observation.outcome is not StatisticalOutcome.CANCELLED
    )
    all_categories = Counter(
        category for item in all_acquired if (category := _failure_category(item)) is not None
    )
    unacquired = len(evidence.plan.run_slots) - len(all_acquired)
    if unacquired:
        all_categories[FailurePresentationCategory.UNACQUIRED_SLOT] += unacquired
    markers = Counter(
        marker for item in all_acquired if (marker := _recovery_marker(item)) is not None
    )
    marked = markers["PRIMARY"] + markers["RECOVERY"]
    recovery_status = (
        Availability.AVAILABLE
        if all_acquired and marked == len(all_acquired)
        else Availability.NOT_AVAILABLE
    )
    evaluation_mode = _evaluation_mode(evidence)
    analysis = ModelComparisonAnalysis(
        experiment_id=evidence.plan.experiment_id,
        plan_digest=evidence.plan.digest,
        conclusion_semantics=ConclusionSemantics(
            scope=(
                "EXPLORATORY_DESCRIPTIVE"
                if evaluation_mode == "QUICK" or evidence.plan.repeat_count == 1
                else "DESCRIPTIVE"
            ),
            evaluation_mode=evaluation_mode,
            repeat_count=evidence.plan.repeat_count,
            permitted_interpretation=(
                "QUICK n=1 results are exploratory/descriptive only."
                if evaluation_mode == "QUICK" or evidence.plan.repeat_count == 1
                else "Report observed outcomes and limitations without causal or universal claims."
            ),
        ),
        overall=OverallOutcomeSummary(
            planned_slots=len(evidence.plan.run_slots),
            acquired_slots=len(all_acquired),
            unacquired_slots=unacquired,
            capability_denominator=model_a.capability_denominator + model_b.capability_denominator,
            passed=model_a.passed + model_b.passed,
            failed=model_a.failed + model_b.failed,
            infra=model_a.infra + model_b.infra,
            cancelled=model_a.cancelled + model_b.cancelled,
            failure_categories=_complete_failure_counts(all_categories),
        ),
        models=(model_a, model_b),
        pairs=pair_summary,
        comparability=comparability,
        control_drift=drift,
        trace_coverage=_trace_coverage(
            tuple(
                item.facts.trace_coverage if item.facts is not None else None
                for item in all_acquired
            )
        ),
        observed_models=_identity_coverage(
            tuple(
                item.facts.observed_model if item.facts is not None else None
                for item in all_acquired
            )
        ),
        observed_providers=_identity_coverage(
            tuple(_provider_identity(item) for item in all_acquired)
        ),
        recovery_attempts=RecoveryAttemptSummary(
            status=recovery_status,
            explicitly_marked_primary_acquisitions=markers["PRIMARY"],
            explicitly_marked_recovery_acquisitions=markers["RECOVERY"],
            unmarked_acquisitions=len(all_acquired) - marked,
            lease_claim_attempts=sum(item.attempt for item in evidence.runs),
            note=(
                "Recovery classification uses explicit immutable markers only; database attempt "
                "counts are lease claims and are not treated as recovery evidence."
            ),
        ),
        breakdowns=_breakdown(rows, _task_dimensions(evidence, repository_root)),
    )
    return ModelComparisonCloseout(analysis_digest=analysis.digest, analysis=analysis)
