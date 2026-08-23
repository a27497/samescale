from __future__ import annotations

from enum import StrEnum
from typing import Any

from harnesslab.harness_lane.models import HarnessFailureCategory, HarnessLaneOutcome
from harnesslab.model_lane.models import DirectModelOutcome


class StatisticalOutcome(StrEnum):
    CAPABILITY_PASS = "capability_pass"
    CAPABILITY_FAIL = "capability_fail"
    INFRA_FAILURE = "infra_failure"
    CANCELLED = "cancelled"


def normalize_lane_evidence(evidence: Any) -> StatisticalOutcome:
    outcome = evidence.outcome
    if outcome in {DirectModelOutcome.VERIFIED_PASS, HarnessLaneOutcome.VERIFIED_PASS}:
        return StatisticalOutcome.CAPABILITY_PASS
    if outcome in {
        DirectModelOutcome.VERIFIED_FAIL,
        DirectModelOutcome.SUBJECT_REFUSAL,
        DirectModelOutcome.SUBJECT_OUTPUT_ERROR,
        HarnessLaneOutcome.VERIFIED_FAIL,
    }:
        return StatisticalOutcome.CAPABILITY_FAIL
    if outcome is HarnessLaneOutcome.HARNESS_ERROR:
        if evidence.harness_failure is HarnessFailureCategory.CANCELLED:
            return StatisticalOutcome.CANCELLED
        if evidence.harness_failure in {
            HarnessFailureCategory.MODEL_TURN_FAILED,
            HarnessFailureCategory.PROFILE_VIOLATION,
        }:
            return StatisticalOutcome.CAPABILITY_FAIL
        return StatisticalOutcome.INFRA_FAILURE
    if outcome in {
        DirectModelOutcome.PROVIDER_ERROR,
        DirectModelOutcome.INFRA_ERROR,
        DirectModelOutcome.ARTIFACT_ERROR,
        HarnessLaneOutcome.INFRA_ERROR,
    }:
        return StatisticalOutcome.INFRA_FAILURE
    raise ValueError(f"unsupported lane outcome: {outcome}")
