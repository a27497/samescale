from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from harnesslab.experiment.lifecycle import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    InfraRecoveryAuthorization,
    LifecycleRecoveryError,
    LifecycleState,
    LifecycleTransitionError,
    RunAttempt,
    RunLifecycle,
    lifecycle_state_from_persisted,
    persisted_status_for_lifecycle,
)

NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)


def _verified_infra_failure() -> RunLifecycle:
    lifecycle = RunLifecycle.queued(slot_id="slot-one", primary_attempt_identity="attempt-one")
    for offset, state in enumerate(
        (
            LifecycleState.PREPARING,
            LifecycleState.RUNNING,
            LifecycleState.VERIFYING,
        )
    ):
        lifecycle = lifecycle.transition(state, occurred_at=NOW + timedelta(seconds=offset))
    return lifecycle.transition(
        LifecycleState.FAILED_INFRA,
        occurred_at=NOW + timedelta(seconds=3),
        reason_code="ARTIFACT_PERSIST_FAILED",
    )


def _authorization(
    *, failed: str = "attempt-one", recovery: str = "attempt-two"
) -> InfraRecoveryAuthorization:
    return InfraRecoveryAuthorization(
        failed_attempt_identity=failed,
        recovery_attempt_identity=recovery,
        authorized_by="evaluation-operator",
        authorized_at=NOW + timedelta(minutes=1),
        reason_code="REPAIRED_ARTIFACT_STORE",
        repair_reference="repair-ticket-123",
    )


def test_lifecycle_state_set_is_exact_and_terminals_have_no_transitions() -> None:
    assert {state.value for state in LifecycleState} == {
        "QUEUED",
        "PREPARING",
        "RUNNING",
        "VERIFYING",
        "COMPLETED",
        "FAILED_CAPABILITY",
        "FAILED_INFRA",
        "CANCELLED",
        "BUDGET_EXHAUSTED",
    }
    assert {
        LifecycleState.COMPLETED,
        LifecycleState.FAILED_CAPABILITY,
        LifecycleState.FAILED_INFRA,
        LifecycleState.CANCELLED,
        LifecycleState.BUDGET_EXHAUSTED,
    } == TERMINAL_STATES
    assert all(not ALLOWED_TRANSITIONS[state] for state in TERMINAL_STATES)


def test_valid_happy_path_reaches_completed() -> None:
    lifecycle = RunLifecycle.queued(slot_id="slot-one", primary_attempt_identity="attempt-one")
    for offset, state in enumerate(
        (
            LifecycleState.PREPARING,
            LifecycleState.RUNNING,
            LifecycleState.VERIFYING,
            LifecycleState.COMPLETED,
        )
    ):
        lifecycle = lifecycle.transition(state, occurred_at=NOW + timedelta(seconds=offset))
    assert lifecycle.state is LifecycleState.COMPLETED
    assert [event.to_state for event in lifecycle.primary_attempt.transitions] == [
        LifecycleState.PREPARING,
        LifecycleState.RUNNING,
        LifecycleState.VERIFYING,
        LifecycleState.COMPLETED,
    ]


def test_invalid_transition_and_terminal_reentry_are_rejected() -> None:
    lifecycle = RunLifecycle.queued(slot_id="slot-one", primary_attempt_identity="attempt-one")
    with pytest.raises(LifecycleTransitionError, match="QUEUED->RUNNING"):
        lifecycle.transition(LifecycleState.RUNNING, occurred_at=NOW)

    cancelled = lifecycle.transition(
        LifecycleState.CANCELLED,
        occurred_at=NOW,
        reason_code="OPERATOR_CANCELLED",
    )
    with pytest.raises(LifecycleTransitionError, match="CANCELLED->QUEUED"):
        cancelled.transition(LifecycleState.QUEUED, occurred_at=NOW + timedelta(seconds=1))


@pytest.mark.parametrize(
    "terminal",
    (
        LifecycleState.FAILED_CAPABILITY,
        LifecycleState.FAILED_INFRA,
        LifecycleState.CANCELLED,
        LifecycleState.BUDGET_EXHAUSTED,
    ),
)
def test_non_success_terminal_transition_requires_reason_code(
    terminal: LifecycleState,
) -> None:
    if terminal is LifecycleState.FAILED_CAPABILITY:
        lifecycle = RunLifecycle.queued(slot_id="slot-one", primary_attempt_identity="attempt-one")
        for state in (
            LifecycleState.PREPARING,
            LifecycleState.RUNNING,
            LifecycleState.VERIFYING,
        ):
            lifecycle = lifecycle.transition(state, occurred_at=NOW)
    elif terminal is LifecycleState.FAILED_INFRA:
        lifecycle = RunLifecycle.queued(
            slot_id="slot-one", primary_attempt_identity="attempt-one"
        ).transition(LifecycleState.PREPARING, occurred_at=NOW)
    else:
        lifecycle = RunLifecycle.queued(slot_id="slot-one", primary_attempt_identity="attempt-one")
    with pytest.raises(ValidationError, match="require a reason code"):
        lifecycle.transition(terminal, occurred_at=NOW)


def test_infra_recovery_requires_explicit_eligible_authorization() -> None:
    failed = _verified_infra_failure()
    recovered = failed.recover_infrastructure_failure(_authorization())

    assert recovered.state is LifecycleState.QUEUED
    assert len(recovered.attempts) == 2
    assert recovered.current_attempt.attempt_identity == "attempt-two"
    assert recovered.current_attempt.recovery_authorization == _authorization()
    assert recovered.current_attempt.transitions == ()


def test_primary_attempt_is_immutable_when_recovery_is_created() -> None:
    failed = _verified_infra_failure()
    primary_dump = failed.primary_attempt.model_dump(mode="json")
    recovered = failed.recover_infrastructure_failure(_authorization())

    assert failed.state is LifecycleState.FAILED_INFRA
    assert recovered.primary_attempt is failed.primary_attempt
    assert recovered.primary_attempt.model_dump(mode="json") == primary_dump
    with pytest.raises(ValidationError, match="frozen"):
        recovered.primary_attempt.state = LifecycleState.QUEUED  # type: ignore[misc]


def test_capability_failure_is_terminal_for_recovery() -> None:
    lifecycle = RunLifecycle.queued(slot_id="slot-one", primary_attempt_identity="attempt-one")
    for state in (
        LifecycleState.PREPARING,
        LifecycleState.RUNNING,
        LifecycleState.VERIFYING,
    ):
        lifecycle = lifecycle.transition(state, occurred_at=NOW)
    failed = lifecycle.transition(
        LifecycleState.FAILED_CAPABILITY,
        occurred_at=NOW,
        reason_code="VERIFIER_REJECTED_SUBJECT",
    )
    with pytest.raises(LifecycleRecoveryError, match="capability failure is terminal"):
        failed.recover_infrastructure_failure(_authorization())


def test_infra_recovery_checks_failed_identity_and_limit() -> None:
    failed = _verified_infra_failure()
    with pytest.raises(LifecycleRecoveryError, match="does not identify"):
        failed.recover_infrastructure_failure(_authorization(failed="some-other-attempt"))

    recovered = failed.recover_infrastructure_failure(_authorization())
    for offset, state in enumerate(
        (
            LifecycleState.PREPARING,
            LifecycleState.RUNNING,
            LifecycleState.FAILED_INFRA,
        )
    ):
        recovered = recovered.transition(
            state,
            occurred_at=NOW + timedelta(minutes=2, seconds=offset),
            reason_code="SECOND_INFRA_FAILURE" if state is LifecycleState.FAILED_INFRA else None,
        )
    with pytest.raises(LifecycleRecoveryError, match="limit is exhausted"):
        recovered.recover_infrastructure_failure(
            _authorization(failed="attempt-two", recovery="attempt-three")
        )


def test_recovery_cannot_execute_before_its_authorization() -> None:
    recovered = _verified_infra_failure().recover_infrastructure_failure(_authorization())
    with pytest.raises(ValidationError, match="before its authorization"):
        recovered.transition(
            LifecycleState.PREPARING,
            occurred_at=NOW + timedelta(seconds=30),
        )


def test_attempt_ledger_rejects_recovery_after_non_infra_attempt() -> None:
    completed = RunAttempt(
        attempt_identity="attempt-one",
        attempt_number=1,
        state=LifecycleState.COMPLETED,
        transitions=(
            # Construct through the public transition API to retain full validation.
            RunAttempt(attempt_identity="builder", attempt_number=1)
            .transition(LifecycleState.PREPARING, occurred_at=NOW)
            .transition(LifecycleState.RUNNING, occurred_at=NOW)
            .transition(LifecycleState.VERIFYING, occurred_at=NOW)
            .transition(LifecycleState.COMPLETED, occurred_at=NOW)
            .transitions
        ),
    )
    recovery = RunAttempt(
        attempt_identity="attempt-two",
        attempt_number=2,
        recovery_authorization=_authorization(),
    )
    with pytest.raises(ValidationError, match="only a failed infrastructure"):
        RunLifecycle(slot_id="slot-one", attempts=(completed, recovery))


@pytest.mark.parametrize(
    ("persisted", "expected"),
    (
        ("queued", LifecycleState.QUEUED),
        ("claimed", LifecycleState.PREPARING),
        ("scoring", LifecycleState.VERIFYING),
        ("failed_subject", LifecycleState.FAILED_CAPABILITY),
        ("FAILED_INFRA", LifecycleState.FAILED_INFRA),
        ("budget_exhausted", LifecycleState.BUDGET_EXHAUSTED),
    ),
)
def test_historical_persistence_statuses_remain_readable(
    persisted: str, expected: LifecycleState
) -> None:
    assert lifecycle_state_from_persisted(persisted) is expected


def test_phase_m_states_write_backward_compatible_status_values() -> None:
    assert persisted_status_for_lifecycle(LifecycleState.FAILED_CAPABILITY) == "failed_subject"
    assert persisted_status_for_lifecycle(LifecycleState.VERIFYING) == "verifying"
    assert persisted_status_for_lifecycle(LifecycleState.BUDGET_EXHAUSTED) == "budget_exhausted"


def test_naive_timestamps_and_unknown_persistence_states_fail_closed() -> None:
    lifecycle = RunLifecycle.queued(slot_id="slot-one", primary_attempt_identity="attempt-one")
    with pytest.raises(ValidationError, match="timezone-aware"):
        lifecycle.transition(LifecycleState.PREPARING, occurred_at=datetime(2026, 8, 30))
    with pytest.raises(ValueError, match="unsupported persisted"):
        lifecycle_state_from_persisted("mystery")
