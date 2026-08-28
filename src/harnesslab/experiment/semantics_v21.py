from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from harnesslab.experiment.outcomes import (
    NormalizedEvidence,
    StatisticalOutcome,
    normalize_manifest_evidence,
)
from harnesslab.harness_lane.models import HarnessFailureCategory, SanitizedNativeEvent
from harnesslab.model_lane.models import ProviderIncompleteReason
from harnesslab.multi_harness.trace import (
    claude_execution_budget_exhausted_from_safe_progress,
)


class SemanticV21Reason(StrEnum):
    UNCHANGED = "UNCHANGED"
    INCOMPLETE_REASON_NOT_OBSERVED = "INCOMPLETE_REASON_NOT_OBSERVED"
    INCOMPLETE_REASON_MAX_OUTPUT_TOKENS = "INCOMPLETE_REASON_MAX_OUTPUT_TOKENS"
    INCOMPLETE_REASON_REMAINS_INFRA = "INCOMPLETE_REASON_REMAINS_INFRA"
    HEALTHY_PROGRESS_EXECUTION_BUDGET_EXHAUSTED = "HEALTHY_PROGRESS_EXECUTION_BUDGET_EXHAUSTED"
    TIMEOUT_PROGRESS_NOT_PROVEN = "TIMEOUT_PROGRESS_NOT_PROVEN"


class SemanticV21Interpretation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    original_outcome: StatisticalOutcome
    original_source_taxonomy: str
    v21_outcome: StatisticalOutcome
    v21_source_taxonomy: str
    reason: SemanticV21Reason


def reinterpret_manifest_v21(
    raw: dict[str, object],
    *,
    safe_claude_events: tuple[SanitizedNativeEvent, ...] = (),
) -> SemanticV21Interpretation:
    """Interpret immutable evidence under v2.1 without rewriting its original taxonomy."""

    original = normalize_manifest_evidence(raw)
    provider_error = raw.get("provider_error")
    if raw.get("provider_failure") == "incomplete_response":
        incomplete_reason = (
            provider_error.get("incomplete_reason") if isinstance(provider_error, dict) else None
        )
        if incomplete_reason == ProviderIncompleteReason.MAX_OUTPUT_TOKENS.value:
            return _interpretation(
                original,
                StatisticalOutcome.CAPABILITY_FAIL,
                "subject_output_error",
                SemanticV21Reason.INCOMPLETE_REASON_MAX_OUTPUT_TOKENS,
            )
        reason = (
            SemanticV21Reason.INCOMPLETE_REASON_NOT_OBSERVED
            if incomplete_reason is None
            else SemanticV21Reason.INCOMPLETE_REASON_REMAINS_INFRA
        )
        return _interpretation(original, original.outcome, original.source_taxonomy, reason)

    if (
        raw.get("outcome") == "harness_error"
        and raw.get("harness_failure") == HarnessFailureCategory.TIMEOUT.value
    ):
        terminal_value = raw.get("terminal_native_event")
        observed_value = raw.get("observed_model")
        retry_value = raw.get("retry_count")
        budget_exhausted = claude_execution_budget_exhausted_from_safe_progress(
            timed_out=raw.get("timed_out") is True,
            cancelled=raw.get("cancelled") is True,
            terminal_event=terminal_value if isinstance(terminal_value, str) else None,
            observed_model=observed_value if isinstance(observed_value, str) else None,
            retry_count=retry_value if isinstance(retry_value, int) else -1,
            events=safe_claude_events,
        )
        if budget_exhausted:
            source = f"harness_error:{HarnessFailureCategory.EXECUTION_BUDGET_EXHAUSTED.value}"
            return _interpretation(
                original,
                StatisticalOutcome.CAPABILITY_FAIL,
                source,
                SemanticV21Reason.HEALTHY_PROGRESS_EXECUTION_BUDGET_EXHAUSTED,
            )
        return _interpretation(
            original,
            original.outcome,
            original.source_taxonomy,
            SemanticV21Reason.TIMEOUT_PROGRESS_NOT_PROVEN,
        )
    return _interpretation(
        original,
        original.outcome,
        original.source_taxonomy,
        SemanticV21Reason.UNCHANGED,
    )


def _interpretation(
    original: NormalizedEvidence,
    outcome: StatisticalOutcome,
    source_taxonomy: str,
    reason: SemanticV21Reason,
) -> SemanticV21Interpretation:
    return SemanticV21Interpretation(
        original_outcome=original.outcome,
        original_source_taxonomy=original.source_taxonomy,
        v21_outcome=outcome,
        v21_source_taxonomy=source_taxonomy,
        reason=reason,
    )
