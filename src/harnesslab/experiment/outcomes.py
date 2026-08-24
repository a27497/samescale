from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from harnesslab.contracts.run import RunStatus
from harnesslab.harness_lane.models import HarnessFailureCategory, HarnessLaneOutcome
from harnesslab.model_lane.models import DirectModelOutcome


class StatisticalOutcome(StrEnum):
    CAPABILITY_PASS = "capability_pass"
    CAPABILITY_FAIL = "capability_fail"
    INFRA_FAILURE = "infra_failure"
    CANCELLED = "cancelled"


TERMINAL_STATUS_BY_OUTCOME: dict[StatisticalOutcome, RunStatus] = {
    StatisticalOutcome.CAPABILITY_PASS: RunStatus.COMPLETED,
    StatisticalOutcome.CAPABILITY_FAIL: RunStatus.FAILED_SUBJECT,
    StatisticalOutcome.INFRA_FAILURE: RunStatus.FAILED_INFRA,
    StatisticalOutcome.CANCELLED: RunStatus.CANCELLED,
}


def terminal_status_for_outcome(outcome: StatisticalOutcome | str) -> RunStatus:
    """Return the authoritative Phase G terminal status for a statistical outcome."""

    return TERMINAL_STATUS_BY_OUTCOME[StatisticalOutcome(outcome)]


def validate_terminal_run_lifecycle(
    status: RunStatus | str, outcome: StatisticalOutcome | str
) -> None:
    """Fail closed unless a persisted terminal status/outcome pair matches Phase G."""

    persisted_status = RunStatus(status)
    persisted_outcome = StatisticalOutcome(outcome)
    expected_status = terminal_status_for_outcome(persisted_outcome)
    if persisted_status is not expected_status:
        raise ValueError(
            "inconsistent terminal run lifecycle: "
            f"{persisted_status.value}+{persisted_outcome.value}; "
            f"expected {expected_status.value}"
        )


@dataclass(frozen=True)
class NormalizedEvidence:
    outcome: StatisticalOutcome
    source_taxonomy: str


def normalize_source_evidence(
    source_outcome: str, harness_failure: str | None = None
) -> NormalizedEvidence:
    """Authoritative statistical policy for typed and persisted lane evidence."""

    if source_outcome == DirectModelOutcome.VERIFIED_PASS.value:
        normalized = StatisticalOutcome.CAPABILITY_PASS
    elif source_outcome in {
        DirectModelOutcome.VERIFIED_FAIL.value,
        DirectModelOutcome.SUBJECT_REFUSAL.value,
        DirectModelOutcome.SUBJECT_OUTPUT_ERROR.value,
    }:
        normalized = StatisticalOutcome.CAPABILITY_FAIL
    elif source_outcome == HarnessLaneOutcome.HARNESS_ERROR.value:
        if harness_failure == HarnessFailureCategory.MODEL_TURN_FAILED.value:
            normalized = StatisticalOutcome.CAPABILITY_FAIL
        elif harness_failure == HarnessFailureCategory.CANCELLED.value:
            normalized = StatisticalOutcome.CANCELLED
        else:
            normalized = StatisticalOutcome.INFRA_FAILURE
    elif source_outcome in {
        DirectModelOutcome.PROVIDER_ERROR.value,
        DirectModelOutcome.INFRA_ERROR.value,
        DirectModelOutcome.ARTIFACT_ERROR.value,
    }:
        normalized = StatisticalOutcome.INFRA_FAILURE
    else:
        raise ValueError(f"unsupported lane outcome: {source_outcome}")
    taxonomy = (
        f"{source_outcome}:{harness_failure}"
        if source_outcome == HarnessLaneOutcome.HARNESS_ERROR.value and harness_failure
        else source_outcome
    )
    return NormalizedEvidence(outcome=normalized, source_taxonomy=taxonomy)


def normalize_lane_evidence(evidence: Any) -> StatisticalOutcome:
    failure = getattr(evidence, "harness_failure", None)
    normalized = normalize_source_evidence(
        evidence.outcome.value,
        failure.value if isinstance(failure, HarnessFailureCategory) else None,
    )
    return normalized.outcome


def normalize_manifest_evidence(raw: Mapping[str, Any]) -> NormalizedEvidence:
    source_outcome = raw.get("outcome")
    harness_failure = raw.get("harness_failure")
    if not isinstance(source_outcome, str):
        raise ValueError(f"unsupported lane outcome: {source_outcome!r}")
    return normalize_source_evidence(
        source_outcome,
        harness_failure if isinstance(harness_failure, str) else None,
    )


def source_taxonomy_from_lane_evidence(evidence: Any) -> str:
    failure = getattr(evidence, "harness_failure", None)
    return normalize_source_evidence(
        evidence.outcome.value,
        failure.value if isinstance(failure, HarnessFailureCategory) else None,
    ).source_taxonomy
