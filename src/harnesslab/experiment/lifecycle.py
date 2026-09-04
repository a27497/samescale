from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LifecycleTransitionError(ValueError):
    """A requested run lifecycle transition is not methodologically valid."""


class LifecycleRecoveryError(ValueError):
    """A requested recovery would retry ineligible or immutable evidence."""


class LifecycleState(StrEnum):
    """Authoritative externally meaningful Phase M run states."""

    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED_CAPABILITY = "FAILED_CAPABILITY"
    FAILED_INFRA = "FAILED_INFRA"
    CANCELLED = "CANCELLED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


TERMINAL_STATES = frozenset(
    {
        LifecycleState.COMPLETED,
        LifecycleState.FAILED_CAPABILITY,
        LifecycleState.FAILED_INFRA,
        LifecycleState.CANCELLED,
        LifecycleState.BUDGET_EXHAUSTED,
    }
)

ALLOWED_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.QUEUED: frozenset(
        {
            LifecycleState.PREPARING,
            LifecycleState.FAILED_INFRA,
            LifecycleState.CANCELLED,
            LifecycleState.BUDGET_EXHAUSTED,
        }
    ),
    LifecycleState.PREPARING: frozenset(
        {
            LifecycleState.RUNNING,
            LifecycleState.FAILED_INFRA,
            LifecycleState.CANCELLED,
            LifecycleState.BUDGET_EXHAUSTED,
        }
    ),
    LifecycleState.RUNNING: frozenset(
        {
            LifecycleState.VERIFYING,
            LifecycleState.FAILED_INFRA,
            LifecycleState.CANCELLED,
            LifecycleState.BUDGET_EXHAUSTED,
        }
    ),
    LifecycleState.VERIFYING: frozenset(
        {
            LifecycleState.COMPLETED,
            LifecycleState.FAILED_CAPABILITY,
            LifecycleState.FAILED_INFRA,
            LifecycleState.CANCELLED,
            LifecycleState.BUDGET_EXHAUSTED,
        }
    ),
    LifecycleState.COMPLETED: frozenset(),
    LifecycleState.FAILED_CAPABILITY: frozenset(),
    LifecycleState.FAILED_INFRA: frozenset(),
    LifecycleState.CANCELLED: frozenset(),
    LifecycleState.BUDGET_EXHAUSTED: frozenset(),
}

_FAILURE_STATES = frozenset(
    {
        LifecycleState.FAILED_CAPABILITY,
        LifecycleState.FAILED_INFRA,
        LifecycleState.CANCELLED,
        LifecycleState.BUDGET_EXHAUSTED,
    }
)

# Phase G persistence remains readable without rewriting historical rows. CLAIMED and
# SCORING are lease/executor details, not additional externally meaningful lifecycle states.
_PERSISTED_TO_LIFECYCLE = {
    "planned": LifecycleState.QUEUED,
    "queued": LifecycleState.QUEUED,
    "claimed": LifecycleState.PREPARING,
    "preparing": LifecycleState.PREPARING,
    "running": LifecycleState.RUNNING,
    "verifying": LifecycleState.VERIFYING,
    "scoring": LifecycleState.VERIFYING,
    "completed": LifecycleState.COMPLETED,
    "failed_subject": LifecycleState.FAILED_CAPABILITY,
    "failed_capability": LifecycleState.FAILED_CAPABILITY,
    "failed_infra": LifecycleState.FAILED_INFRA,
    "cancelled": LifecycleState.CANCELLED,
    "budget_exhausted": LifecycleState.BUDGET_EXHAUSTED,
}

_LIFECYCLE_TO_PERSISTED = {
    LifecycleState.QUEUED: "queued",
    LifecycleState.PREPARING: "preparing",
    LifecycleState.RUNNING: "running",
    LifecycleState.VERIFYING: "verifying",
    LifecycleState.COMPLETED: "completed",
    # Keep the existing Phase G name on writes so old readers continue to work.
    LifecycleState.FAILED_CAPABILITY: "failed_subject",
    LifecycleState.FAILED_INFRA: "failed_infra",
    LifecycleState.CANCELLED: "cancelled",
    LifecycleState.BUDGET_EXHAUSTED: "budget_exhausted",
}


def lifecycle_state_from_persisted(status: str) -> LifecycleState:
    """Normalize a historical or Phase M persisted status without changing the row."""

    normalized = status.strip()
    try:
        return LifecycleState(normalized)
    except ValueError:
        try:
            return _PERSISTED_TO_LIFECYCLE[normalized.lower()]
        except KeyError as exc:
            raise ValueError(f"unsupported persisted run lifecycle status: {status!r}") from exc


def persisted_status_for_lifecycle(state: LifecycleState | str) -> str:
    """Return a persistence value compatible with existing Phase G readers."""

    return _LIFECYCLE_TO_PERSISTED[LifecycleState(state)]


def validate_transition(current: LifecycleState | str, target: LifecycleState | str) -> None:
    source = LifecycleState(current)
    destination = LifecycleState(target)
    if destination not in ALLOWED_TRANSITIONS[source]:
        raise LifecycleTransitionError(
            f"invalid run lifecycle transition: {source.value}->{destination.value}"
        )


class LifecycleTransition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    from_state: LifecycleState
    to_state: LifecycleState
    occurred_at: datetime
    reason_code: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def transition_is_valid(self) -> LifecycleTransition:
        validate_transition(self.from_state, self.to_state)
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("lifecycle transition timestamp must be timezone-aware")
        if self.to_state in _FAILURE_STATES and self.reason_code is None:
            raise ValueError("failure, cancellation, and budget transitions require a reason code")
        return self


class InfraRecoveryAuthorization(BaseModel):
    """Explicit evidence that a particular infrastructure attempt may be recovered."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    failed_attempt_identity: str = Field(min_length=1, max_length=200)
    recovery_attempt_identity: str = Field(min_length=1, max_length=200)
    authorized_by: str = Field(min_length=1, max_length=100)
    authorized_at: datetime
    reason_code: str = Field(min_length=1, max_length=100)
    repair_reference: str = Field(min_length=1, max_length=500)
    eligibility: Literal["ELIGIBLE"] = "ELIGIBLE"

    @model_validator(mode="after")
    def authorization_is_distinct_and_timestamped(self) -> InfraRecoveryAuthorization:
        if self.failed_attempt_identity == self.recovery_attempt_identity:
            raise ValueError("recovery attempt identity must differ from failed attempt identity")
        if self.authorized_at.tzinfo is None or self.authorized_at.utcoffset() is None:
            raise ValueError("recovery authorization timestamp must be timezone-aware")
        return self


class RunAttempt(BaseModel):
    """Immutable lifecycle evidence for one physical execution attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt_identity: str = Field(min_length=1, max_length=200)
    attempt_number: int = Field(ge=1)
    state: LifecycleState = LifecycleState.QUEUED
    transitions: tuple[LifecycleTransition, ...] = ()
    recovery_authorization: InfraRecoveryAuthorization | None = None

    @model_validator(mode="after")
    def history_reaches_declared_state(self) -> RunAttempt:
        expected = LifecycleState.QUEUED
        previous_at: datetime | None = None
        for event in self.transitions:
            if event.from_state is not expected:
                raise ValueError("attempt transition history is not contiguous")
            if previous_at is not None and event.occurred_at < previous_at:
                raise ValueError("attempt transition timestamps must be ordered")
            expected = event.to_state
            previous_at = event.occurred_at
        if expected is not self.state:
            raise ValueError("attempt state does not match transition history")
        if self.attempt_number == 1 and self.recovery_authorization is not None:
            raise ValueError("the primary attempt cannot carry recovery authorization")
        if self.attempt_number > 1 and self.recovery_authorization is None:
            raise ValueError("a recovery attempt requires explicit authorization")
        if (
            self.recovery_authorization is not None
            and self.recovery_authorization.recovery_attempt_identity != self.attempt_identity
        ):
            raise ValueError("recovery authorization does not identify this attempt")
        if (
            self.recovery_authorization is not None
            and self.transitions
            and self.transitions[0].occurred_at < self.recovery_authorization.authorized_at
        ):
            raise ValueError("recovery attempt cannot start before its authorization")
        return self

    def transition(
        self,
        target: LifecycleState,
        *,
        occurred_at: datetime,
        reason_code: str | None = None,
    ) -> RunAttempt:
        validate_transition(self.state, target)
        event = LifecycleTransition(
            from_state=self.state,
            to_state=target,
            occurred_at=occurred_at,
            reason_code=reason_code,
        )
        return RunAttempt(
            attempt_identity=self.attempt_identity,
            attempt_number=self.attempt_number,
            state=target,
            transitions=(*self.transitions, event),
            recovery_authorization=self.recovery_authorization,
        )


class RunLifecycle(BaseModel):
    """Immutable primary-attempt history plus any explicitly authorized infra recoveries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot_id: str = Field(min_length=1, max_length=200)
    attempts: tuple[RunAttempt, ...] = Field(min_length=1)
    maximum_recovery_attempts: int = Field(default=1, ge=0)

    @model_validator(mode="after")
    def attempt_ledger_is_consistent(self) -> RunLifecycle:
        identities = tuple(attempt.attempt_identity for attempt in self.attempts)
        if len(set(identities)) != len(identities):
            raise ValueError("attempt identities must be unique")
        if tuple(attempt.attempt_number for attempt in self.attempts) != tuple(
            range(1, len(self.attempts) + 1)
        ):
            raise ValueError("attempt numbers must be contiguous and ordered")
        for index in range(1, len(self.attempts)):
            previous = self.attempts[index - 1]
            recovery = self.attempts[index]
            authorization = recovery.recovery_authorization
            if previous.state is not LifecycleState.FAILED_INFRA:
                raise ValueError("only a failed infrastructure attempt may have a recovery")
            if (
                authorization is None
                or authorization.failed_attempt_identity != previous.attempt_identity
            ):
                raise ValueError("recovery authorization does not identify the preceding failure")
            if (
                previous.transitions
                and authorization.authorized_at < previous.transitions[-1].occurred_at
            ):
                raise ValueError("recovery cannot be authorized before the infrastructure failure")
        if len(self.attempts) - 1 > self.maximum_recovery_attempts:
            raise ValueError("recovery attempt limit exceeded")
        return self

    @classmethod
    def queued(cls, *, slot_id: str, primary_attempt_identity: str) -> RunLifecycle:
        return cls(
            slot_id=slot_id,
            attempts=(RunAttempt(attempt_identity=primary_attempt_identity, attempt_number=1),),
        )

    @property
    def primary_attempt(self) -> RunAttempt:
        return self.attempts[0]

    @property
    def current_attempt(self) -> RunAttempt:
        return self.attempts[-1]

    @property
    def state(self) -> LifecycleState:
        return self.current_attempt.state

    def transition(
        self,
        target: LifecycleState,
        *,
        occurred_at: datetime,
        reason_code: str | None = None,
    ) -> RunLifecycle:
        updated = self.current_attempt.transition(
            target,
            occurred_at=occurred_at,
            reason_code=reason_code,
        )
        return RunLifecycle(
            slot_id=self.slot_id,
            attempts=(*self.attempts[:-1], updated),
            maximum_recovery_attempts=self.maximum_recovery_attempts,
        )

    def recover_infrastructure_failure(
        self, authorization: InfraRecoveryAuthorization
    ) -> RunLifecycle:
        current = self.current_attempt
        if current.state is LifecycleState.FAILED_CAPABILITY:
            raise LifecycleRecoveryError("capability failure is terminal and cannot be retried")
        if current.state is not LifecycleState.FAILED_INFRA:
            raise LifecycleRecoveryError("only a failed infrastructure attempt may be recovered")
        if len(self.attempts) - 1 >= self.maximum_recovery_attempts:
            raise LifecycleRecoveryError("infrastructure recovery attempt limit is exhausted")
        if authorization.failed_attempt_identity != current.attempt_identity:
            raise LifecycleRecoveryError("authorization does not identify the failed attempt")
        if authorization.recovery_attempt_identity in {
            attempt.attempt_identity for attempt in self.attempts
        }:
            raise LifecycleRecoveryError("recovery attempt identity has already been used")
        recovery = RunAttempt(
            attempt_identity=authorization.recovery_attempt_identity,
            attempt_number=len(self.attempts) + 1,
            recovery_authorization=authorization,
        )
        return RunLifecycle(
            slot_id=self.slot_id,
            attempts=(*self.attempts, recovery),
            maximum_recovery_attempts=self.maximum_recovery_attempts,
        )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "InfraRecoveryAuthorization",
    "LifecycleRecoveryError",
    "LifecycleState",
    "LifecycleTransition",
    "LifecycleTransitionError",
    "RunAttempt",
    "RunLifecycle",
    "lifecycle_state_from_persisted",
    "persisted_status_for_lifecycle",
    "validate_transition",
]
