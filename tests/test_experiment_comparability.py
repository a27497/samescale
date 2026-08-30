from __future__ import annotations

from harnesslab.comparability.engine import ComparabilityEngine
from harnesslab.comparability.models import (
    ComparabilityIntent,
    ComparabilityStatus,
    ComparisonFacts,
    ReasonCode,
    canonical_digest,
)
from harnesslab.experiment.statistics import PairObservation, summarize_pair


def _facts(label: str, **changes: str | None) -> ComparisonFacts:
    values: dict[str, str | None] = {
        "task_id": "task",
        "task_version": "1.0.0",
        "task_digest": canonical_digest({"task": 1}),
        "workspace_input_digest": canonical_digest({"workspace": 1}),
        "context_identity": "NONE",
        "verifier_identity": canonical_digest({"verifier": 1}),
        "requested_model": "controlled-model",
        "observed_model": "controlled-model",
        "provider_route": "controlled-test-route",
        "budget_identity": canonical_digest({"budget": 1}),
        "resource_envelope_identity": canonical_digest({"resource-envelope": 1}),
        "network_policy": "deny",
        "harness": "direct-model",
        "harness_version": "1",
        "harness_profile_identity": canonical_digest({"profile": "left"}),
        "reasoning_effort": "medium",
        "prompt_identity": canonical_digest({"prompt": "left"}),
        "trace_coverage": "CONTROLLED_TEST",
    }
    values.update(changes)
    return ComparisonFacts(
        evidence_identity=canonical_digest({"evidence": label}),
        **values,
    )


def test_controlled_keyless_p_lane_and_negative_comparability_sensitivity() -> None:
    engine = ComparabilityEngine()
    left = _facts("left")
    right = _facts(
        "right",
        harness="controlled-harness",
        harness_version="2",
        harness_profile_identity=canonical_digest({"profile": "right"}),
        prompt_identity=canonical_digest({"prompt": "right"}),
    )
    comparable = engine.assess(left, right, intent=ComparabilityIntent.HARNESS_UPLIFT)
    assert comparable.status is ComparabilityStatus.COMPARABLE

    controlled = tuple(
        PairObservation(
            pair_id="controlled-keyless",
            task_id="task",
            repeat_index=index,
            paired_slot_identity=f"controlled-slot-{index}",
            left_pass=index < 2,
            right_pass=index < 4,
            left_duration_ms=10,
            right_duration_ms=8,
            comparability=comparable.status,
            reason_codes=tuple(reason.code.value for reason in comparable.reasons),
        )
        for index in range(5)
    )
    summary = summarize_pair("controlled-keyless", controlled, bootstrap_resamples=99)
    assert summary.formal_eligible
    assert summary.comparable_pairs == 5
    assert summary.binary is not None
    assert summary.binary.right_minus_left_success_rate == 0.4

    route_mismatch = engine.assess(
        left,
        right.model_copy(update={"provider_route": "different-route"}),
        intent=ComparabilityIntent.HARNESS_UPLIFT,
    )
    assert route_mismatch.status is ComparabilityStatus.NOT_COMPARABLE
    assert ReasonCode.HARD_CONTROL_MISMATCH in {reason.code for reason in route_mismatch.reasons}

    missing_observed = engine.assess(
        left,
        right.model_copy(update={"observed_model": None}),
        intent=ComparabilityIntent.HARNESS_UPLIFT,
    )
    assert missing_observed.status is ComparabilityStatus.PARTIALLY_COMPARABLE
    assert ReasonCode.OBSERVED_MODEL_MISSING in {reason.code for reason in missing_observed.reasons}

    task_mismatch = engine.assess(
        left,
        right.model_copy(update={"task_digest": canonical_digest({"task": 2})}),
        intent=ComparabilityIntent.HARNESS_UPLIFT,
    )
    assert task_mismatch.status is ComparabilityStatus.NOT_COMPARABLE
    assert ReasonCode.HARD_CONTROL_MISMATCH in {reason.code for reason in task_mismatch.reasons}
