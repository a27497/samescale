from __future__ import annotations

import pytest

from harnesslab.comparability.models import ComparabilityStatus
from harnesslab.contracts.run import RunStatus
from harnesslab.experiment.outcomes import (
    StatisticalOutcome,
    normalize_lane_evidence,
    normalize_manifest_evidence,
    terminal_status_for_outcome,
)
from harnesslab.experiment.statistics import (
    CellStatistics,
    EvidenceTier,
    PairObservation,
    RunObservation,
    continuous_statistics,
    evidence_tier,
    paired_binary_statistics,
    paired_continuous_statistics,
    pass_at_k,
    summarize_cell,
    summarize_pair,
    wilson_interval,
)
from harnesslab.harness_lane.models import HarnessFailureCategory, HarnessLaneOutcome
from harnesslab.model_lane.models import DirectModelOutcome


class _Evidence:
    def __init__(
        self,
        outcome: DirectModelOutcome | HarnessLaneOutcome,
        harness_failure: HarnessFailureCategory | None = None,
    ) -> None:
        self.outcome = outcome
        self.harness_failure = harness_failure


def observation(index: int, outcome: StatisticalOutcome, task_id: str = "task-a") -> RunObservation:
    return RunObservation(
        run_id=f"run-{index}",
        task_id=task_id,
        repeat_index=index,
        paired_slot_identity=f"pair-{index}",
        outcome=outcome,
        source_outcome=outcome.value,
        duration_ms=float(10 + index),
        input_tokens=float(100 + index),
        output_tokens=float(20 + index),
        tool_calls=float(index),
        steps=float(index + 1),
    )


def test_repeated_run_tiers_are_conservative() -> None:
    assert evidence_tier(1) is EvidenceTier.SMOKE
    assert evidence_tier(2) is EvidenceTier.INSUFFICIENT
    assert evidence_tier(3) is EvidenceTier.INFORMAL
    assert evidence_tier(4) is EvidenceTier.INFORMAL
    assert evidence_tier(5) is EvidenceTier.FORMAL
    assert evidence_tier(5, controls_valid=False) is EvidenceTier.INFORMAL


def test_lane_outcome_normalization_separates_subject_infra_and_cancellation() -> None:
    assert (
        normalize_lane_evidence(_Evidence(DirectModelOutcome.SUBJECT_OUTPUT_ERROR))
        is StatisticalOutcome.CAPABILITY_FAIL
    )
    assert (
        normalize_lane_evidence(_Evidence(DirectModelOutcome.PROVIDER_ERROR))
        is StatisticalOutcome.INFRA_FAILURE
    )
    assert (
        normalize_lane_evidence(
            _Evidence(HarnessLaneOutcome.HARNESS_ERROR, HarnessFailureCategory.PROCESS_ERROR)
        )
        is StatisticalOutcome.INFRA_FAILURE
    )
    assert (
        normalize_lane_evidence(
            _Evidence(HarnessLaneOutcome.HARNESS_ERROR, HarnessFailureCategory.PROFILE_VIOLATION)
        )
        is StatisticalOutcome.INFRA_FAILURE
    )
    assert (
        normalize_lane_evidence(
            _Evidence(HarnessLaneOutcome.HARNESS_ERROR, HarnessFailureCategory.CANCELLED)
        )
        is StatisticalOutcome.CANCELLED
    )


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (HarnessFailureCategory.MODEL_TURN_FAILED, StatisticalOutcome.CAPABILITY_FAIL),
        (
            HarnessFailureCategory.EXECUTION_BUDGET_EXHAUSTED,
            StatisticalOutcome.CAPABILITY_FAIL,
        ),
        (HarnessFailureCategory.PROCESS_ERROR, StatisticalOutcome.INFRA_FAILURE),
        (HarnessFailureCategory.TIMEOUT, StatisticalOutcome.INFRA_FAILURE),
        (HarnessFailureCategory.PROFILE_VIOLATION, StatisticalOutcome.INFRA_FAILURE),
        (HarnessFailureCategory.CANCELLED, StatisticalOutcome.CANCELLED),
    ],
)
def test_typed_and_persisted_harness_normalization_are_identical(
    failure: HarnessFailureCategory, expected: StatisticalOutcome
) -> None:
    typed = _Evidence(HarnessLaneOutcome.HARNESS_ERROR, failure)
    persisted = {
        "outcome": HarnessLaneOutcome.HARNESS_ERROR.value,
        "harness_failure": failure.value,
    }

    assert normalize_lane_evidence(typed) is expected
    normalized = normalize_manifest_evidence(persisted)
    assert normalized.outcome is expected
    assert normalized.source_taxonomy == f"harness_error:{failure.value}"


def test_execution_budget_exhaustion_maps_to_failed_subject_for_persistence() -> None:
    normalized = normalize_manifest_evidence(
        {
            "outcome": HarnessLaneOutcome.HARNESS_ERROR.value,
            "harness_failure": HarnessFailureCategory.EXECUTION_BUDGET_EXHAUSTED.value,
        }
    )
    ambiguous_timeout = normalize_manifest_evidence(
        {
            "outcome": HarnessLaneOutcome.HARNESS_ERROR.value,
            "harness_failure": HarnessFailureCategory.TIMEOUT.value,
        }
    )

    assert normalized.outcome is StatisticalOutcome.CAPABILITY_FAIL
    assert terminal_status_for_outcome(normalized.outcome) is RunStatus.FAILED_SUBJECT
    assert ambiguous_timeout.outcome is StatisticalOutcome.INFRA_FAILURE
    assert terminal_status_for_outcome(ambiguous_timeout.outcome) is RunStatus.FAILED_INFRA


def test_execution_budget_exhaustion_is_in_capability_denominator() -> None:
    budget_outcome = normalize_lane_evidence(
        _Evidence(
            HarnessLaneOutcome.HARNESS_ERROR,
            HarnessFailureCategory.EXECUTION_BUDGET_EXHAUSTED,
        )
    )
    timeout_outcome = normalize_lane_evidence(
        _Evidence(HarnessLaneOutcome.HARNESS_ERROR, HarnessFailureCategory.TIMEOUT)
    )
    summary = summarize_cell(
        "budget-denominator",
        3,
        (
            observation(0, StatisticalOutcome.CAPABILITY_PASS),
            observation(1, budget_outcome),
            observation(2, timeout_outcome),
        ),
        bootstrap_resamples=99,
    )

    assert summary.completed_capability_runs == 2
    assert summary.capability_passes == 1
    assert summary.capability_failures == 1
    assert summary.infra_failures == 1
    assert summary.success_rate == 0.5


def test_infrastructure_failures_are_not_capability_failures_or_denominator_members() -> None:
    observations = (
        observation(0, StatisticalOutcome.CAPABILITY_PASS),
        observation(1, StatisticalOutcome.CAPABILITY_PASS),
        observation(2, StatisticalOutcome.CAPABILITY_FAIL),
        observation(3, StatisticalOutcome.CAPABILITY_FAIL),
        observation(4, StatisticalOutcome.INFRA_FAILURE),
    )
    summary = summarize_cell("cell", 5, observations, bootstrap_resamples=99)

    assert summary.planned_runs == 5
    assert summary.completed_capability_runs == 4
    assert summary.capability_passes == 2
    assert summary.capability_failures == 2
    assert summary.infra_failures == 1
    assert summary.success_rate == 0.5
    assert summary.evidence_tier is EvidenceTier.INFORMAL
    assert summary.infra_failure_rate == 0.2


@pytest.mark.parametrize("successes,total", [(0, 5), (5, 5), (1, 1), (2, 5)])
def test_wilson_95_interval_is_bounded(successes: int, total: int) -> None:
    interval = wilson_interval(successes, total)
    assert interval is not None
    assert 0 <= interval.low <= interval.high <= 1


def test_pass_at_k_boundaries_and_macro_per_task() -> None:
    assert pass_at_k(5, 0, 1) == 0
    assert pass_at_k(5, 2, 3) == pytest.approx(0.9)
    assert pass_at_k(3, 1, 5) is None
    assert pass_at_k(5, 5, 5) == 1

    observations = tuple(
        observation(
            index,
            StatisticalOutcome.CAPABILITY_PASS
            if index in {0, 5}
            else StatisticalOutcome.CAPABILITY_FAIL,
            "a" if index < 5 else "b",
        )
        for index in range(10)
    )
    summary = summarize_cell("macro", 10, observations, bootstrap_resamples=99)
    assert summary.pass_at_k["pass@1"] == pytest.approx(0.2)
    assert summary.pass_at_k["pass@5"] == 1


def test_continuous_bootstrap_is_deterministic_and_paired() -> None:
    first = continuous_statistics((1.0, 2.0, 3.0, 8.0, 13.0), seed=7, resamples=199)
    second = continuous_statistics((1.0, 2.0, 3.0, 8.0, 13.0), seed=7, resamples=199)
    assert first == second
    assert first.p50 == 3
    assert first.p95 == pytest.approx(12.0)
    assert first.median_bootstrap_95 is not None

    paired = paired_continuous_statistics(
        ((1.0, 3.0), (2.0, 5.0), (10.0, 9.0)), seed=9, resamples=199
    )
    assert paired.paired_count == 3
    assert paired.mean_difference == pytest.approx(4 / 3)
    assert paired.median_difference == 2


def test_exact_mcnemar_and_comparability_gating() -> None:
    exact = paired_binary_statistics(((True, False), (False, True), (False, True)))
    assert exact.left_pass_right_fail == 1
    assert exact.left_fail_right_pass == 2
    assert exact.discordant_count == 3
    assert exact.exact_two_sided_p == 1.0

    no_discordance = paired_binary_statistics(((True, True), (False, False)))
    assert no_discordance.exact_two_sided_p == 1.0
    assert no_discordance.note == "no discordant pairs"

    observations = tuple(
        PairObservation(
            pair_id="controlled",
            task_id="task",
            repeat_index=index,
            paired_slot_identity=f"slot-{index}",
            left_pass=index < 2,
            right_pass=index < 4,
            left_duration_ms=10,
            right_duration_ms=8,
            comparability=(
                ComparabilityStatus.COMPARABLE if index < 5 else ComparabilityStatus.NOT_COMPARABLE
            ),
            reason_codes=() if index < 5 else ("HARD_CONTROL_MISMATCH",),
        )
        for index in range(6)
    )
    summary = summarize_pair("controlled", observations, bootstrap_resamples=99)
    assert summary.comparable_pairs == 5
    assert summary.not_comparable_pairs == 1
    assert summary.formal_eligible
    assert summary.binary is not None
    assert summary.binary.paired_count == 5
    assert summary.excluded_reason_counts == {"HARD_CONTROL_MISMATCH": 1}


def test_repetition_eligibility_is_per_task_and_never_pooled() -> None:
    def cell_summary(task_counts: dict[str, int]) -> CellStatistics:
        items = tuple(
            observation(index, StatisticalOutcome.CAPABILITY_PASS, task_id)
            for task_id, count in task_counts.items()
            for index in range(count)
        )
        return summarize_cell(
            "per-task",
            sum(task_counts.values()),
            items,
            intended_task_ids=tuple(task_counts),
            bootstrap_resamples=99,
        )

    pooled_smoke = cell_summary({f"task-{index}": 1 for index in range(5)})
    assert pooled_smoke.evidence_tier is EvidenceTier.SMOKE
    assert not pooled_smoke.formal_eligible
    assert cell_summary({"a": 3, "b": 3}).evidence_tier is EvidenceTier.INFORMAL
    assert cell_summary({"a": 5, "b": 5}).evidence_tier is EvidenceTier.FORMAL
    uneven = cell_summary({"a": 5, "b": 4})
    assert uneven.evidence_tier is EvidenceTier.INFORMAL
    assert not uneven.formal_eligible


def test_pair_repetition_eligibility_requires_comparable_pairs_per_task() -> None:
    def pair_item(task_id: str, index: int, status: ComparabilityStatus) -> PairObservation:
        return PairObservation(
            pair_id="per-task-pair",
            task_id=task_id,
            repeat_index=index,
            paired_slot_identity=f"{task_id}-{index}",
            left_pass=True,
            right_pass=True,
            comparability=status,
            reason_codes=() if status is ComparabilityStatus.COMPARABLE else ("LIMITATION",),
        )

    pooled = tuple(
        pair_item(f"task-{index}", 0, ComparabilityStatus.COMPARABLE) for index in range(5)
    )
    pooled_summary = summarize_pair(
        "pooled", pooled, intended_task_ids=tuple(f"task-{index}" for index in range(5))
    )
    assert pooled_summary.evidence_tier is EvidenceTier.SMOKE
    assert not pooled_summary.formal_eligible

    formal = tuple(
        pair_item(task_id, index, ComparabilityStatus.COMPARABLE)
        for task_id in ("a", "b")
        for index in range(5)
    )
    assert summarize_pair("formal", formal, intended_task_ids=("a", "b")).formal_eligible

    lost_pair = (
        *formal[:-1],
        pair_item("b", 4, ComparabilityStatus.PARTIALLY_COMPARABLE),
    )
    lost_summary = summarize_pair("lost", lost_pair, intended_task_ids=("a", "b"))
    assert not lost_summary.formal_eligible
    assert [item.comparable_pairs for item in lost_summary.per_task_evidence] == [5, 4]
