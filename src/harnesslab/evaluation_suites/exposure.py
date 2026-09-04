from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.evaluation_suites.admission import GovernanceNamespace
from harnesslab.release.models import CoreCorpusManifest
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.quality import TaskIdentity, TaskQualityMetadata, TaskSourceKind


class ExposureGovernanceError(ValueError):
    """Exposure history is incomplete, non-append-only, or identity-inconsistent."""


class ExposureType(StrEnum):
    DEVELOPMENT_TASK_ACCESS = "DEVELOPMENT_TASK_ACCESS"
    DEVELOPMENT_LINEAGE_USE = "DEVELOPMENT_LINEAGE_USE"
    HIDDEN_ASSET_ACCESS = "HIDDEN_ASSET_ACCESS"
    PUBLIC_DISCLOSURE = "PUBLIC_DISCLOSURE"
    HOLDOUT_EVALUATION = "HOLDOUT_EVALUATION"
    QUALIFICATION_AUDIT = "QUALIFICATION_AUDIT"
    HISTORICAL_CORE_DEVELOPMENT = "HISTORICAL_CORE_DEVELOPMENT"


class AccessPurpose(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    HOLDOUT_EVALUATION = "HOLDOUT_EVALUATION"
    QUALIFICATION_AUDIT = "QUALIFICATION_AUDIT"
    RELEASE_AUDIT = "RELEASE_AUDIT"


class AssetVisibility(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    SEALED_HOLDOUT = "SEALED_HOLDOUT"
    PUBLIC = "PUBLIC"


class ExposureCoverage(StrEnum):
    COMPLETE = "COMPLETE"
    UNKNOWN = "UNKNOWN"


class ExposureState(StrEnum):
    NOT_EXPOSED = "NOT_EXPOSED"
    EXPOSED = "EXPOSED"
    UNKNOWN = "UNKNOWN"


class ExposureMatchKind(StrEnum):
    EXACT_TASK_OR_VERSION_FAMILY = "EXACT_TASK_OR_VERSION_FAMILY"
    LINEAGE = "LINEAGE"


_DISQUALIFYING_EXPOSURES = frozenset(
    {
        ExposureType.DEVELOPMENT_TASK_ACCESS,
        ExposureType.DEVELOPMENT_LINEAGE_USE,
        ExposureType.HIDDEN_ASSET_ACCESS,
        ExposureType.PUBLIC_DISCLOSURE,
        ExposureType.HISTORICAL_CORE_DEVELOPMENT,
    }
)


class TaskLineageReference(BaseModel):
    """Exact task plus allowlisted lineage identities; never includes hidden material."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: TaskIdentity
    quality_identity: Sha256Digest
    source_kind: TaskSourceKind
    lineage_identities: tuple[Sha256Digest, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def lineage_is_canonical(self) -> TaskLineageReference:
        if tuple(sorted(set(self.lineage_identities))) != self.lineage_identities:
            raise ValueError("lineage identities must be unique and canonical")
        return self


class ExposureEvent(BaseModel):
    """One timestamp-free append-only event ordered by sequence and predecessor digest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    ledger_id: Identifier
    sequence: int = Field(ge=1)
    previous_event_identity: Sha256Digest | None
    task_lineage: TaskLineageReference
    exposure_type: ExposureType
    purpose: AccessPurpose
    actor_identity: Sha256Digest
    source_identity: Sha256Digest | None = None
    event_identity: Sha256Digest

    @model_validator(mode="after")
    def event_is_self_identifying(self) -> ExposureEvent:
        if self.sequence == 1 and self.previous_event_identity is not None:
            raise ValueError("first exposure event cannot have a predecessor")
        if self.sequence > 1 and self.previous_event_identity is None:
            raise ValueError("later exposure events require a predecessor identity")
        required_purpose = {
            ExposureType.DEVELOPMENT_TASK_ACCESS: AccessPurpose.DEVELOPMENT,
            ExposureType.DEVELOPMENT_LINEAGE_USE: AccessPurpose.DEVELOPMENT,
            ExposureType.HOLDOUT_EVALUATION: AccessPurpose.HOLDOUT_EVALUATION,
            ExposureType.HISTORICAL_CORE_DEVELOPMENT: AccessPurpose.DEVELOPMENT,
            ExposureType.PUBLIC_DISCLOSURE: AccessPurpose.RELEASE_AUDIT,
        }.get(self.exposure_type)
        if required_purpose is not None and self.purpose is not required_purpose:
            raise ValueError("exposure type and purpose are inconsistent")
        if self.exposure_type is ExposureType.QUALIFICATION_AUDIT and self.purpose not in (
            AccessPurpose.QUALIFICATION_AUDIT,
            AccessPurpose.RELEASE_AUDIT,
        ):
            raise ValueError("qualification audit event has an inconsistent purpose")
        if self.event_identity != canonical_digest(self.payload()):
            raise ValueError("exposure event identity does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"event_identity"})


class ExposureHistory(BaseModel):
    """Immutable snapshot of an append-only exposure-event chain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    ledger_id: Identifier
    coverage: ExposureCoverage
    coverage_evidence_identity: Sha256Digest | None = None
    events: tuple[ExposureEvent, ...] = ()
    predecessor_history_digest: Sha256Digest | None = None
    history_digest: Sha256Digest

    @model_validator(mode="after")
    def history_is_a_valid_chain(self) -> ExposureHistory:
        if self.coverage is ExposureCoverage.COMPLETE and self.coverage_evidence_identity is None:
            raise ValueError("complete exposure coverage requires immutable evidence")
        if not self.events and self.predecessor_history_digest is not None:
            raise ValueError("empty exposure history cannot have a predecessor")
        if self.events and self.predecessor_history_digest is None:
            raise ValueError("non-empty exposure history requires its predecessor digest")
        previous: ExposureEvent | None = None
        identities: set[str] = set()
        for expected_sequence, event in enumerate(self.events, start=1):
            if event.ledger_id != self.ledger_id:
                raise ValueError("exposure event belongs to a different ledger")
            if event.sequence != expected_sequence:
                raise ValueError("exposure event sequence must be contiguous and append-only")
            expected_previous = None if previous is None else previous.event_identity
            if event.previous_event_identity != expected_previous:
                raise ValueError("exposure event predecessor identity does not match the chain")
            if event.event_identity in identities:
                raise ValueError("duplicate exposure event identity")
            identities.add(event.event_identity)
            previous = event
        if self.history_digest != canonical_digest(self.payload()):
            raise ValueError("exposure history digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"history_digest"})

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )


class ExposureAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    task_lineage: TaskLineageReference
    history_digest: Sha256Digest
    state: ExposureState
    matched_event_identities: tuple[Sha256Digest, ...]
    match_kinds: tuple[ExposureMatchKind, ...]
    assessment_digest: Sha256Digest

    @model_validator(mode="after")
    def assessment_is_canonical(self) -> ExposureAssessment:
        if tuple(sorted(set(self.matched_event_identities))) != self.matched_event_identities:
            raise ValueError("matched exposure events must be unique and canonical")
        if tuple(sorted(set(self.match_kinds), key=lambda item: item.value)) != self.match_kinds:
            raise ValueError("exposure match kinds must be unique and canonical")
        if self.state is ExposureState.EXPOSED and not self.matched_event_identities:
            raise ValueError("exposed assessment requires matching event evidence")
        if self.state is not ExposureState.EXPOSED and (
            self.matched_event_identities or self.match_kinds
        ):
            raise ValueError("unexposed/unknown assessment cannot cite exposure matches")
        if self.assessment_digest != canonical_digest(self.payload()):
            raise ValueError("exposure assessment digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"assessment_digest"})


class VisibilityPolicy(BaseModel):
    """Keyless visibility boundary; authorization and file serving remain out of scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    policy_id: Identifier
    policy_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    namespace: GovernanceNamespace
    task_lineage: TaskLineageReference
    visibility: AssetVisibility
    allowed_purposes: tuple[AccessPurpose, ...]
    policy_digest: Sha256Digest

    @model_validator(mode="after")
    def visibility_is_canonical_and_fail_closed(self) -> VisibilityPolicy:
        if tuple(sorted(set(self.allowed_purposes), key=lambda item: item.value)) != (
            self.allowed_purposes
        ):
            raise ValueError("allowed access purposes must be unique and canonical")
        if (
            self.visibility is AssetVisibility.SEALED_HOLDOUT
            and AccessPurpose.DEVELOPMENT in self.allowed_purposes
        ):
            raise ValueError("sealed Holdout policy cannot allow development access")
        if self.policy_digest != canonical_digest(self.payload()):
            raise ValueError("visibility policy digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"policy_digest"})


class AccessStatus(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"


class AccessReasonCode(StrEnum):
    PURPOSE_ALLOWED = "PURPOSE_ALLOWED"
    PURPOSE_NOT_ALLOWED = "PURPOSE_NOT_ALLOWED"
    SEALED_HOLDOUT_DEVELOPMENT_ACCESS_FORBIDDEN = "SEALED_HOLDOUT_DEVELOPMENT_ACCESS_FORBIDDEN"


class AccessDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    request_id: Identifier
    task: TaskIdentity
    purpose: AccessPurpose
    actor_identity: Sha256Digest
    visibility_policy_identity: Sha256Digest
    status: AccessStatus
    reason_code: AccessReasonCode
    decision_digest: Sha256Digest

    @model_validator(mode="after")
    def access_decision_is_self_identifying(self) -> AccessDecision:
        if self.decision_digest != canonical_digest(self.payload()):
            raise ValueError("access decision digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"decision_digest"})


def task_lineage_from_quality(quality: TaskQualityMetadata) -> TaskLineageReference:
    return TaskLineageReference(
        task=quality.task,
        quality_identity=quality.quality_identity,
        source_kind=quality.provenance.source_kind,
        lineage_identities=tuple(sorted(quality.provenance.lineage_identities)),
    )


def build_exposure_history(
    ledger_id: str,
    *,
    coverage: ExposureCoverage,
    coverage_evidence_identity: str | None = None,
    events: tuple[ExposureEvent, ...] = (),
    predecessor_history_digest: str | None = None,
) -> ExposureHistory:
    payload = {
        "schema_version": 1,
        "ledger_id": ledger_id,
        "coverage": coverage.value,
        "coverage_evidence_identity": coverage_evidence_identity,
        "events": [event.model_dump(mode="json") for event in events],
        "predecessor_history_digest": predecessor_history_digest,
    }
    payload["history_digest"] = canonical_digest(payload)
    try:
        return ExposureHistory.model_validate(payload)
    except ValueError as exc:
        raise ExposureGovernanceError(str(exc)) from exc


def append_exposure_event(
    history: ExposureHistory,
    *,
    task_lineage: TaskLineageReference,
    exposure_type: ExposureType,
    purpose: AccessPurpose,
    actor_identity: str,
    source_identity: str | None = None,
) -> ExposureHistory:
    sequence = len(history.events) + 1
    event_payload = {
        "schema_version": 1,
        "ledger_id": history.ledger_id,
        "sequence": sequence,
        "previous_event_identity": (
            None if not history.events else history.events[-1].event_identity
        ),
        "task_lineage": task_lineage.model_dump(mode="json"),
        "exposure_type": exposure_type.value,
        "purpose": purpose.value,
        "actor_identity": actor_identity,
        "source_identity": source_identity,
    }
    event_payload["event_identity"] = canonical_digest(event_payload)
    try:
        event = ExposureEvent.model_validate(event_payload)
        return build_exposure_history(
            history.ledger_id,
            coverage=history.coverage,
            coverage_evidence_identity=history.coverage_evidence_identity,
            events=(*history.events, event),
            predecessor_history_digest=history.history_digest,
        )
    except ValueError as exc:
        if isinstance(exc, ExposureGovernanceError):
            raise
        raise ExposureGovernanceError(str(exc)) from exc


def assess_exposure(
    task_lineage: TaskLineageReference, history: ExposureHistory
) -> ExposureAssessment:
    matched: list[str] = []
    kinds: set[ExposureMatchKind] = set()
    lineage = set(task_lineage.lineage_identities)
    for event in history.events:
        if (
            event.purpose is not AccessPurpose.DEVELOPMENT
            and event.exposure_type not in _DISQUALIFYING_EXPOSURES
        ):
            continue
        event_lineage = event.task_lineage
        if event_lineage.task.task_id == task_lineage.task.task_id:
            matched.append(event.event_identity)
            kinds.add(ExposureMatchKind.EXACT_TASK_OR_VERSION_FAMILY)
        elif lineage & set(event_lineage.lineage_identities):
            matched.append(event.event_identity)
            kinds.add(ExposureMatchKind.LINEAGE)
    matched_identities = tuple(sorted(set(matched)))
    if matched_identities:
        state = ExposureState.EXPOSED
    elif history.coverage is ExposureCoverage.UNKNOWN:
        state = ExposureState.UNKNOWN
    else:
        state = ExposureState.NOT_EXPOSED
    payload = {
        "schema_version": 1,
        "task_lineage": task_lineage.model_dump(mode="json"),
        "history_digest": history.history_digest,
        "state": state.value,
        "matched_event_identities": list(matched_identities),
        "match_kinds": [item.value for item in sorted(kinds, key=lambda item: item.value)],
    }
    payload["assessment_digest"] = canonical_digest(payload)
    return ExposureAssessment.model_validate(payload)


def validate_exposure_history_extension(
    previous: ExposureHistory, current: ExposureHistory
) -> None:
    """Prove that current is exactly one append and never a rewrite or truncation."""

    if current.ledger_id != previous.ledger_id:
        raise ExposureGovernanceError("exposure history extension changed ledger identity")
    if current.coverage is not previous.coverage:
        raise ExposureGovernanceError("exposure history extension changed coverage semantics")
    if current.coverage_evidence_identity != previous.coverage_evidence_identity:
        raise ExposureGovernanceError("exposure history extension changed coverage evidence")
    if current.predecessor_history_digest != previous.history_digest:
        raise ExposureGovernanceError("exposure history predecessor digest is stale or mismatched")
    if len(current.events) != len(previous.events) + 1:
        raise ExposureGovernanceError("exposure history extension must append exactly one event")
    if current.events[:-1] != previous.events:
        raise ExposureGovernanceError("exposure history extension rewrote prior events")


def build_visibility_policy(
    *,
    policy_id: str,
    policy_version: str,
    namespace: GovernanceNamespace,
    task_lineage: TaskLineageReference,
    visibility: AssetVisibility,
    allowed_purposes: tuple[AccessPurpose, ...],
) -> VisibilityPolicy:
    ordered = tuple(sorted(set(allowed_purposes), key=lambda item: item.value))
    payload = {
        "schema_version": 1,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "namespace": namespace.value,
        "task_lineage": task_lineage.model_dump(mode="json"),
        "visibility": visibility.value,
        "allowed_purposes": [item.value for item in ordered],
    }
    payload["policy_digest"] = canonical_digest(payload)
    try:
        return VisibilityPolicy.model_validate(payload)
    except ValueError as exc:
        raise ExposureGovernanceError(str(exc)) from exc


def evaluate_access(
    *,
    request_id: str,
    task: TaskIdentity,
    purpose: AccessPurpose,
    actor_identity: str,
    policy: VisibilityPolicy,
) -> AccessDecision:
    if task != policy.task_lineage.task:
        raise ExposureGovernanceError("access request task does not match visibility policy")
    if policy.visibility is AssetVisibility.SEALED_HOLDOUT and purpose is AccessPurpose.DEVELOPMENT:
        status = AccessStatus.DENIED
        reason = AccessReasonCode.SEALED_HOLDOUT_DEVELOPMENT_ACCESS_FORBIDDEN
    elif purpose not in policy.allowed_purposes:
        status = AccessStatus.DENIED
        reason = AccessReasonCode.PURPOSE_NOT_ALLOWED
    else:
        status = AccessStatus.ALLOWED
        reason = AccessReasonCode.PURPOSE_ALLOWED
    payload = {
        "schema_version": 1,
        "request_id": request_id,
        "task": task.model_dump(mode="json"),
        "purpose": purpose.value,
        "actor_identity": actor_identity,
        "visibility_policy_identity": policy.policy_digest,
        "status": status.value,
        "reason_code": reason.value,
    }
    payload["decision_digest"] = canonical_digest(payload)
    return AccessDecision.model_validate(payload)


def validate_access_decision(decision: AccessDecision, policy: VisibilityPolicy) -> None:
    expected = evaluate_access(
        request_id=decision.request_id,
        task=decision.task,
        purpose=decision.purpose,
        actor_identity=decision.actor_identity,
        policy=policy,
    )
    if decision != expected:
        raise ExposureGovernanceError("access decision is stale or inconsistent with policy")


def record_allowed_access(
    history: ExposureHistory,
    *,
    decision: AccessDecision,
    policy: VisibilityPolicy,
) -> ExposureHistory:
    """Append the semantic consequence of an allowed access without recording content."""

    validate_access_decision(decision, policy)
    if decision.status is not AccessStatus.ALLOWED:
        raise ExposureGovernanceError("denied access cannot create an allowed-access event")
    if decision.visibility_policy_identity != policy.policy_digest:
        raise ExposureGovernanceError("access decision uses a stale visibility policy")
    if decision.task != policy.task_lineage.task:
        raise ExposureGovernanceError("access decision task does not match visibility policy")
    exposure_type = {
        AccessPurpose.DEVELOPMENT: ExposureType.DEVELOPMENT_TASK_ACCESS,
        AccessPurpose.HOLDOUT_EVALUATION: ExposureType.HOLDOUT_EVALUATION,
        AccessPurpose.QUALIFICATION_AUDIT: ExposureType.QUALIFICATION_AUDIT,
        AccessPurpose.RELEASE_AUDIT: ExposureType.QUALIFICATION_AUDIT,
    }[decision.purpose]
    return append_exposure_event(
        history,
        task_lineage=policy.task_lineage,
        exposure_type=exposure_type,
        purpose=decision.purpose,
        actor_identity=decision.actor_identity,
        source_identity=decision.decision_digest,
    )


def core_development_exposure_history(
    repository_root: Path,
    corpus: CoreCorpusManifest,
    *,
    ledger_id: str = "core-development-exposure-v1",
) -> ExposureHistory:
    """Project known Core use into a new sidecar without altering historical evidence."""

    history = build_exposure_history(
        ledger_id,
        coverage=ExposureCoverage.COMPLETE,
        coverage_evidence_identity=corpus.digest,
    )
    for item in corpus.tasks:
        package = TaskPackage.load(repository_root / item.package_path)
        quality = TaskQualityMetadata.from_package(package)
        if (
            quality.task.task_id,
            quality.task.task_version,
            quality.task.task_digest,
            quality.task.workspace_digest,
            quality.task.verifier_digest,
        ) != (
            item.task_id,
            item.version,
            item.task_digest,
            item.workspace_input_identity,
            item.verifier_identity,
        ):
            raise ExposureGovernanceError("Core corpus task identity does not match its package")
        history = append_exposure_event(
            history,
            task_lineage=task_lineage_from_quality(quality),
            exposure_type=ExposureType.HISTORICAL_CORE_DEVELOPMENT,
            purpose=AccessPurpose.DEVELOPMENT,
            actor_identity=corpus.digest,
            source_identity=corpus.digest,
        )
    return history
