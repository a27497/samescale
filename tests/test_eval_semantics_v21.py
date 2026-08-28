from __future__ import annotations

import hashlib
import json

from harnesslab.experiment.methodology import RecoveryEligibility, recovery_authorization
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.semantics_v21 import (
    SemanticV21Reason,
    reinterpret_manifest_v21,
)
from harnesslab.harness_lane.models import SanitizedNativeEvent


def _digest(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_historical_incomplete_without_safe_reason_stays_immutable_infra() -> None:
    raw: dict[str, object] = {
        "outcome": "provider_error",
        "provider_failure": "incomplete_response",
        "provider_error": {
            "category": "incomplete_response",
            "response_status": "incomplete",
        },
    }
    before = _digest(raw)

    interpretation = reinterpret_manifest_v21(raw)

    assert interpretation.original_outcome is StatisticalOutcome.INFRA_FAILURE
    assert interpretation.v21_outcome is StatisticalOutcome.INFRA_FAILURE
    assert interpretation.reason is SemanticV21Reason.INCOMPLETE_REASON_NOT_OBSERVED
    assert _digest(raw) == before


def test_persisted_max_output_reason_is_reinterpreted_as_capability_budget() -> None:
    raw: dict[str, object] = {
        "outcome": "provider_error",
        "provider_failure": "incomplete_response",
        "provider_error": {
            "category": "incomplete_response",
            "response_status": "incomplete",
            "incomplete_reason": "max_output_tokens",
        },
    }

    interpretation = reinterpret_manifest_v21(raw)
    recovery = recovery_authorization(
        slot_id="slot",
        original_attempt_identity="attempt",
        outcome=interpretation.v21_outcome,
        recovery_attempt_count=0,
    )

    assert interpretation.v21_outcome is StatisticalOutcome.CAPABILITY_FAIL
    assert interpretation.v21_source_taxonomy == "subject_output_error"
    assert interpretation.reason is SemanticV21Reason.INCOMPLETE_REASON_MAX_OUTPUT_TOKENS
    assert recovery.eligibility is RecoveryEligibility.CAPABILITY_TERMINAL_NO_RETRY
    assert recovery.recovery_attempt_identity is None


def test_unknown_incomplete_reason_remains_one_recovery_eligible_infra() -> None:
    raw: dict[str, object] = {
        "outcome": "provider_error",
        "provider_failure": "incomplete_response",
        "provider_error": {
            "category": "incomplete_response",
            "response_status": "incomplete",
            "incomplete_reason": "unknown",
        },
    }

    interpretation = reinterpret_manifest_v21(raw)
    recovery = recovery_authorization(
        slot_id="slot",
        original_attempt_identity="attempt",
        outcome=interpretation.v21_outcome,
        recovery_attempt_count=0,
    )

    assert interpretation.v21_outcome is StatisticalOutcome.INFRA_FAILURE
    assert interpretation.reason is SemanticV21Reason.INCOMPLETE_REASON_REMAINS_INFRA
    assert recovery.eligibility is RecoveryEligibility.ELIGIBLE
    assert recovery.recovery_attempt_identity is not None


def test_healthy_claude_timeout_is_reinterpreted_without_rewriting_source() -> None:
    raw: dict[str, object] = {
        "outcome": "harness_error",
        "harness_failure": "timeout",
        "timed_out": True,
        "cancelled": False,
        "terminal_native_event": None,
        "observed_model": "observed-model",
        "retry_count": 0,
    }
    events = (
        SanitizedNativeEvent(ordinal=1, event_type="system.init"),
        SanitizedNativeEvent(ordinal=2, event_type="tool.Bash"),
        SanitizedNativeEvent(ordinal=3, event_type="user.tool_result", status="completed"),
    )
    before = _digest(raw)

    interpretation = reinterpret_manifest_v21(raw, safe_claude_events=events)

    assert interpretation.original_outcome is StatisticalOutcome.INFRA_FAILURE
    assert interpretation.v21_outcome is StatisticalOutcome.CAPABILITY_FAIL
    assert interpretation.v21_source_taxonomy == "harness_error:execution_budget_exhausted"
    assert interpretation.reason is SemanticV21Reason.HEALTHY_PROGRESS_EXECUTION_BUDGET_EXHAUSTED
    assert _digest(raw) == before


def test_ambiguous_claude_timeout_remains_infra() -> None:
    raw: dict[str, object] = {
        "outcome": "harness_error",
        "harness_failure": "timeout",
        "timed_out": True,
        "cancelled": False,
        "terminal_native_event": None,
        "observed_model": "observed-model",
        "retry_count": 0,
    }

    interpretation = reinterpret_manifest_v21(
        raw,
        safe_claude_events=(SanitizedNativeEvent(ordinal=1, event_type="system.init"),),
    )

    assert interpretation.v21_outcome is StatisticalOutcome.INFRA_FAILURE
    assert interpretation.reason is SemanticV21Reason.TIMEOUT_PROGRESS_NOT_PROVEN
