from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from enum import StrEnum
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from scipy.stats import binomtest, bootstrap, norm

from harnesslab.comparability.models import ComparabilityStatus
from harnesslab.experiment.outcomes import StatisticalOutcome


class EvidenceTier(StrEnum):
    INSUFFICIENT = "INSUFFICIENT"
    SMOKE = "SMOKE"
    INFORMAL = "INFORMAL"
    FORMAL = "FORMAL"


class ConfidenceInterval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    low: float = Field(ge=0.0, le=1.0)
    high: float = Field(ge=0.0, le=1.0)


class NumericInterval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    low: float
    high: float


class ContinuousStatistics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    count: int = Field(ge=0)
    p50: float | None
    p95: float | None
    median_bootstrap_95: NumericInterval | None


class RunObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    task_id: str
    repeat_index: int = Field(ge=0)
    paired_slot_identity: str
    outcome: StatisticalOutcome
    source_outcome: str
    duration_ms: float | None = Field(default=None, ge=0)
    input_tokens: float | None = Field(default=None, ge=0)
    output_tokens: float | None = Field(default=None, ge=0)
    tool_calls: float | None = Field(default=None, ge=0)
    steps: float | None = Field(default=None, ge=0)
    explicit_cost: float | None = Field(default=None, ge=0)


class TaskEvidenceStatistics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    capability_observations: int = Field(ge=0)
    evidence_tier: EvidenceTier


class CellStatistics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    cell_id: str
    planned_runs: int = Field(ge=0)
    completed_capability_runs: int = Field(ge=0)
    capability_passes: int = Field(ge=0)
    capability_failures: int = Field(ge=0)
    infra_failures: int = Field(ge=0)
    cancelled_runs: int = Field(ge=0)
    success_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    wilson_95: ConfidenceInterval | None
    pass_at_k: dict[str, float | None]
    latency_ms: ContinuousStatistics
    input_tokens: ContinuousStatistics
    output_tokens: ContinuousStatistics
    tool_calls: ContinuousStatistics
    steps: ContinuousStatistics
    infra_failure_rate: float = Field(ge=0.0, le=1.0)
    failure_taxonomy_counts: dict[str, int]
    per_task_evidence: tuple[TaskEvidenceStatistics, ...]
    evidence_tier: EvidenceTier
    controls_valid: bool
    formal_eligible: bool
    explicit_cost_status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    explicit_cost_total: float | None


class PairedBinaryStatistics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    paired_count: int = Field(ge=0)
    left_pass_right_fail: int = Field(ge=0)
    left_fail_right_pass: int = Field(ge=0)
    discordant_count: int = Field(ge=0)
    exact_two_sided_p: float | None = Field(default=None, ge=0.0, le=1.0)
    right_minus_left_success_rate: float | None = Field(default=None, ge=-1.0, le=1.0)
    note: str


class PairedContinuousStatistics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    paired_count: int = Field(ge=0)
    mean_difference: float | None
    median_difference: float | None
    median_difference_bootstrap_95: NumericInterval | None


class PairObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pair_id: str
    task_id: str
    repeat_index: int = Field(ge=0)
    paired_slot_identity: str
    left_pass: bool
    right_pass: bool
    left_duration_ms: float | None = Field(default=None, ge=0)
    right_duration_ms: float | None = Field(default=None, ge=0)
    comparability: ComparabilityStatus
    reason_codes: tuple[str, ...] = ()


class TaskPairEvidenceStatistics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    comparable_pairs: int = Field(ge=0)
    evidence_tier: EvidenceTier


class PairStatistics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pair_id: str
    total_capability_pairs: int = Field(ge=0)
    comparable_pairs: int = Field(ge=0)
    partially_comparable_pairs: int = Field(ge=0)
    not_comparable_pairs: int = Field(ge=0)
    excluded_reason_counts: dict[str, int]
    per_task_evidence: tuple[TaskPairEvidenceStatistics, ...]
    evidence_tier: EvidenceTier
    formal_eligible: bool
    binary: PairedBinaryStatistics | None
    duration_ms: PairedContinuousStatistics | None


def evidence_tier(
    valid_capability_observations: int, *, controls_valid: bool = True
) -> EvidenceTier:
    if valid_capability_observations >= 5 and controls_valid:
        return EvidenceTier.FORMAL
    if valid_capability_observations >= 3:
        return EvidenceTier.INFORMAL
    if valid_capability_observations == 1:
        return EvidenceTier.SMOKE
    return EvidenceTier.INSUFFICIENT


def aggregate_evidence_tier(
    per_task_counts: tuple[int, ...], *, controls_valid: bool = True
) -> EvidenceTier:
    """Conservatively tier a matrix without pooling repetitions across tasks."""

    if per_task_counts and controls_valid and all(count >= 5 for count in per_task_counts):
        return EvidenceTier.FORMAL
    if per_task_counts and all(count >= 3 for count in per_task_counts):
        return EvidenceTier.INFORMAL
    if per_task_counts and all(count == 1 for count in per_task_counts):
        return EvidenceTier.SMOKE
    return EvidenceTier.INSUFFICIENT


def wilson_interval(
    successes: int, total: int, confidence: float = 0.95
) -> ConfidenceInterval | None:
    if total <= 0:
        return None
    if successes < 0 or successes > total:
        raise ValueError("successes must be between zero and total")
    z = float(norm.ppf(1 - (1 - confidence) / 2))
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = (
        z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total) / denominator
    )
    return ConfidenceInterval(low=max(0.0, center - radius), high=min(1.0, center + radius))


def pass_at_k(sample_count: int, correct_count: int, k: int) -> float | None:
    if sample_count < 0 or correct_count < 0 or correct_count > sample_count or k <= 0:
        raise ValueError("invalid pass@k counts")
    if sample_count < k:
        return None
    if correct_count == 0:
        return 0.0
    if sample_count - correct_count < k:
        return 1.0
    return 1.0 - math.comb(sample_count - correct_count, k) / math.comb(sample_count, k)


def macro_pass_at_k(observations: tuple[RunObservation, ...], k: int) -> float | None:
    by_task: dict[str, list[RunObservation]] = defaultdict(list)
    for observation in observations:
        if observation.outcome in {
            StatisticalOutcome.CAPABILITY_PASS,
            StatisticalOutcome.CAPABILITY_FAIL,
        }:
            by_task[observation.task_id].append(observation)
    estimates: list[float] = []
    for task_observations in by_task.values():
        correct = sum(
            item.outcome is StatisticalOutcome.CAPABILITY_PASS for item in task_observations
        )
        estimate = pass_at_k(len(task_observations), correct, k)
        if estimate is None:
            return None
        estimates.append(estimate)
    return float(np.mean(estimates)) if estimates else None


def _derived_seed(seed: int, label: str) -> int:
    digest = hashlib.sha256(f"{seed}:{label}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _bootstrap_interval(
    values: tuple[float, ...], *, seed: int, resamples: int
) -> NumericInterval | None:
    if len(values) < 2:
        return None
    array = np.asarray(values, dtype=float)
    if np.all(array == array[0]):
        return NumericInterval(low=float(array[0]), high=float(array[0]))
    result = bootstrap(
        (array,),
        np.median,
        confidence_level=0.95,
        n_resamples=resamples,
        method="percentile",
        rng=np.random.default_rng(seed),
    )
    return NumericInterval(
        low=float(result.confidence_interval.low),
        high=float(result.confidence_interval.high),
    )


def continuous_statistics(
    values: tuple[float, ...], *, seed: int, resamples: int = 9_999
) -> ContinuousStatistics:
    if not values:
        return ContinuousStatistics(count=0, p50=None, p95=None, median_bootstrap_95=None)
    series = pd.Series(values, dtype="float64")
    return ContinuousStatistics(
        count=len(values),
        p50=float(series.quantile(0.50)),
        p95=float(series.quantile(0.95)),
        median_bootstrap_95=_bootstrap_interval(values, seed=seed, resamples=resamples),
    )


def summarize_cell(
    cell_id: str,
    planned_runs: int,
    observations: tuple[RunObservation, ...],
    *,
    intended_task_ids: tuple[str, ...] | None = None,
    controls_valid: bool = True,
    seed: int = 0,
    bootstrap_resamples: int = 9_999,
) -> CellStatistics:
    passes = sum(item.outcome is StatisticalOutcome.CAPABILITY_PASS for item in observations)
    failures = sum(item.outcome is StatisticalOutcome.CAPABILITY_FAIL for item in observations)
    infra = sum(item.outcome is StatisticalOutcome.INFRA_FAILURE for item in observations)
    cancelled = sum(item.outcome is StatisticalOutcome.CANCELLED for item in observations)
    capability_total = passes + failures
    taxonomy = Counter(item.source_outcome for item in observations)

    def continuous(field: str) -> ContinuousStatistics:
        values = tuple(
            float(value)
            for item in observations
            if (value := getattr(item, field)) is not None
            and item.outcome
            in {StatisticalOutcome.CAPABILITY_PASS, StatisticalOutcome.CAPABILITY_FAIL}
        )
        return continuous_statistics(
            values,
            seed=_derived_seed(seed, f"{cell_id}:{field}"),
            resamples=bootstrap_resamples,
        )

    task_ids = intended_task_ids or tuple(sorted({item.task_id for item in observations}))
    capability_by_task = Counter(
        item.task_id
        for item in observations
        if item.outcome in {StatisticalOutcome.CAPABILITY_PASS, StatisticalOutcome.CAPABILITY_FAIL}
    )
    per_task = tuple(
        TaskEvidenceStatistics(
            task_id=task_id,
            capability_observations=capability_by_task[task_id],
            evidence_tier=evidence_tier(capability_by_task[task_id], controls_valid=controls_valid),
        )
        for task_id in task_ids
    )
    tier = aggregate_evidence_tier(
        tuple(item.capability_observations for item in per_task),
        controls_valid=controls_valid,
    )
    costs = tuple(item.explicit_cost for item in observations)
    cost_available = bool(costs) and all(value is not None for value in costs)
    return CellStatistics(
        cell_id=cell_id,
        planned_runs=planned_runs,
        completed_capability_runs=capability_total,
        capability_passes=passes,
        capability_failures=failures,
        infra_failures=infra,
        cancelled_runs=cancelled,
        success_rate=passes / capability_total if capability_total else None,
        wilson_95=wilson_interval(passes, capability_total),
        pass_at_k={f"pass@{k}": macro_pass_at_k(observations, k) for k in (1, 3, 5)},
        latency_ms=continuous("duration_ms"),
        input_tokens=continuous("input_tokens"),
        output_tokens=continuous("output_tokens"),
        tool_calls=continuous("tool_calls"),
        steps=continuous("steps"),
        infra_failure_rate=infra / planned_runs if planned_runs else 0.0,
        failure_taxonomy_counts=dict(sorted(taxonomy.items())),
        per_task_evidence=per_task,
        evidence_tier=tier,
        controls_valid=controls_valid,
        formal_eligible=tier is EvidenceTier.FORMAL,
        explicit_cost_status="AVAILABLE" if cost_available else "NOT_AVAILABLE",
        explicit_cost_total=(
            float(sum(value for value in costs if value is not None)) if cost_available else None
        ),
    )


def paired_binary_statistics(pairs: tuple[tuple[bool, bool], ...]) -> PairedBinaryStatistics:
    if not pairs:
        return PairedBinaryStatistics(
            paired_count=0,
            left_pass_right_fail=0,
            left_fail_right_pass=0,
            discordant_count=0,
            exact_two_sided_p=None,
            right_minus_left_success_rate=None,
            note="no eligible capability pairs",
        )
    b = sum(left and not right for left, right in pairs)
    c = sum(not left and right for left, right in pairs)
    discordant = b + c
    p_value = 1.0 if discordant == 0 else float(binomtest(b, discordant, 0.5).pvalue)
    effect = float(np.mean([int(right) - int(left) for left, right in pairs]))
    return PairedBinaryStatistics(
        paired_count=len(pairs),
        left_pass_right_fail=b,
        left_fail_right_pass=c,
        discordant_count=discordant,
        exact_two_sided_p=p_value,
        right_minus_left_success_rate=effect,
        note="no discordant pairs" if discordant == 0 else "exact two-sided binomial test",
    )


def paired_continuous_statistics(
    pairs: tuple[tuple[float, float], ...], *, seed: int, resamples: int = 9_999
) -> PairedContinuousStatistics:
    if not pairs:
        return PairedContinuousStatistics(
            paired_count=0,
            mean_difference=None,
            median_difference=None,
            median_difference_bootstrap_95=None,
        )
    differences = tuple(right - left for left, right in pairs)
    return PairedContinuousStatistics(
        paired_count=len(differences),
        mean_difference=float(np.mean(differences)),
        median_difference=float(np.median(differences)),
        median_difference_bootstrap_95=_bootstrap_interval(
            differences, seed=seed, resamples=resamples
        ),
    )


def summarize_pair(
    pair_id: str,
    observations: tuple[PairObservation, ...],
    *,
    intended_task_ids: tuple[str, ...] | None = None,
    seed: int = 0,
    bootstrap_resamples: int = 9_999,
) -> PairStatistics:
    comparable = tuple(
        item for item in observations if item.comparability is ComparabilityStatus.COMPARABLE
    )
    partial = sum(
        item.comparability is ComparabilityStatus.PARTIALLY_COMPARABLE for item in observations
    )
    blocked = sum(item.comparability is ComparabilityStatus.NOT_COMPARABLE for item in observations)
    reasons = Counter(
        reason
        for item in observations
        if item.comparability is not ComparabilityStatus.COMPARABLE
        for reason in item.reason_codes
    )
    task_ids = intended_task_ids or tuple(sorted({item.task_id for item in observations}))
    comparable_by_task = Counter(item.task_id for item in comparable)
    per_task = tuple(
        TaskPairEvidenceStatistics(
            task_id=task_id,
            comparable_pairs=comparable_by_task[task_id],
            evidence_tier=evidence_tier(comparable_by_task[task_id]),
        )
        for task_id in task_ids
    )
    tier = aggregate_evidence_tier(tuple(item.comparable_pairs for item in per_task))
    latency_pairs = tuple(
        (item.left_duration_ms, item.right_duration_ms)
        for item in comparable
        if item.left_duration_ms is not None and item.right_duration_ms is not None
    )
    typed_latency_pairs = tuple((float(left), float(right)) for left, right in latency_pairs)
    return PairStatistics(
        pair_id=pair_id,
        total_capability_pairs=len(observations),
        comparable_pairs=len(comparable),
        partially_comparable_pairs=partial,
        not_comparable_pairs=blocked,
        excluded_reason_counts=dict(sorted(reasons.items())),
        per_task_evidence=per_task,
        evidence_tier=tier,
        formal_eligible=tier is EvidenceTier.FORMAL,
        binary=paired_binary_statistics(
            tuple((item.left_pass, item.right_pass) for item in comparable)
        ),
        duration_ms=paired_continuous_statistics(
            typed_latency_pairs,
            seed=_derived_seed(seed, f"{pair_id}:duration"),
            resamples=bootstrap_resamples,
        ),
    )
