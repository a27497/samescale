from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.evaluation_suites.models import (
    ImmutableArtifactReference,
    SuiteManifestReference,
    SuitePurpose,
    TaskArtifactReference,
    TaskQualificationReference,
    VersionedPolicyReference,
)
from harnesslab.tasks.quality import (
    BenchmarkTier,
    QualificationStatus,
    TaskFamily,
    TaskIdentity,
    TaskQualification,
    TaskQualityMetadata,
    TaskSourceKind,
)


class AdmissionGovernanceError(ValueError):
    """Admission policy, candidate, evidence, or decision is inconsistent."""


class GovernanceNamespace(StrEnum):
    OFFICIAL = "OFFICIAL"
    CUSTOM = "CUSTOM"


class DifficultyBand(StrEnum):
    UNASSESSED = "UNASSESSED"
    FOUNDATION = "FOUNDATION"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class StressDimension(StrEnum):
    LONG_TRAJECTORY = "LONG_TRAJECTORY"
    MULTI_FILE = "MULTI_FILE"
    TOOL_USE = "TOOL_USE"
    REPAIR_LOOP = "REPAIR_LOOP"
    DEPENDENCY_BUILD = "DEPENDENCY_BUILD"
    CONTEXT_LOAD = "CONTEXT_LOAD"
    PROTOCOL = "PROTOCOL"


class EvidenceKind(StrEnum):
    TASK_QUALIFICATION = "TASK_QUALIFICATION"
    PREREGISTRATION = "PREREGISTRATION"
    POLICY_EVALUATION = "POLICY_EVALUATION"
    CONTROLLED_COMPARISON = "CONTROLLED_COMPARISON"
    STRUCTURAL_STRESS = "STRUCTURAL_STRESS"
    STRESS_MEASUREMENT = "STRESS_MEASUREMENT"
    TIER_B_QUALIFICATION = "TIER_B_QUALIFICATION"
    HISTORICAL_MATRIX_PARTICIPATION = "HISTORICAL_MATRIX_PARTICIPATION"


class EvidenceRole(StrEnum):
    PRIMARY = "PRIMARY"
    RECOVERY = "RECOVERY"


class AdmissionStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"


class AdmissionReasonCode(StrEnum):
    ACCEPTANCE_CRITERIA_SATISFIED = "ACCEPTANCE_CRITERIA_SATISFIED"
    TASK_UNQUALIFIED = "TASK_UNQUALIFIED"
    MISSING_REQUIRED_EVIDENCE = "MISSING_REQUIRED_EVIDENCE"
    EVIDENCE_TASK_MISMATCH = "EVIDENCE_TASK_MISMATCH"
    POLICY_IDENTITY_MISMATCH = "POLICY_IDENTITY_MISMATCH"
    SUITE_IDENTITY_MISMATCH = "SUITE_IDENTITY_MISMATCH"
    NONCOMPARABLE_EVIDENCE = "NONCOMPARABLE_EVIDENCE"
    INSUFFICIENT_CONFIGURATION_COVERAGE = "INSUFFICIENT_CONFIGURATION_COVERAGE"
    UNSTABLE_DISCRIMINATION = "UNSTABLE_DISCRIMINATION"
    INSUFFICIENT_STRESS_DIMENSIONS = "INSUFFICIENT_STRESS_DIMENSIONS"
    STRESS_MEASUREMENT_MISSING = "STRESS_MEASUREMENT_MISSING"


class PolicyProvenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authority_identity: Sha256Digest
    source_revision_identity: Sha256Digest
    predecessor: VersionedPolicyReference | None = None
    provenance_identity: Sha256Digest

    @model_validator(mode="after")
    def identity_matches_payload(self) -> PolicyProvenance:
        if self.provenance_identity != canonical_digest(self.payload()):
            raise ValueError("policy provenance identity does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"provenance_identity"})


class CandidateRequirements(BaseModel):
    """Configuration-neutral requirements shared by both governed suite purposes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exact_task_identity_required: Literal[True] = True
    task_qualification_required: Literal[True] = True
    preregistration_required: Literal[True] = True
    configuration_neutral: Literal[True] = True
    deterministic_verifier_authoritative: Literal[True] = True


class DiscriminativeAcceptanceCriteria(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    criteria_type: Literal["DISCRIMINATIVE_V1"] = "DISCRIMINATIVE_V1"
    minimum_configurations: int = Field(ge=2, le=100)
    minimum_repetitions_per_configuration: int = Field(ge=2, le=100)
    minimum_pairwise_effect_absolute: float = Field(gt=0.0, le=1.0)
    maximum_rank_instability: float = Field(ge=0.0, lt=1.0)
    require_preregistered_symmetric_configuration_selection: Literal[True] = True
    require_pairwise_comparability: Literal[True] = True
    require_floor_and_ceiling_checks: Literal[True] = True
    require_stability_check: Literal[True] = True


class StressAcceptanceCriteria(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    criteria_type: Literal["STRESS_V1"] = "STRESS_V1"
    minimum_distinct_stress_dimensions: int = Field(ge=2, le=len(StressDimension))
    required_dimensions: tuple[StressDimension, ...] = Field(min_length=1)
    require_structural_evidence: Literal[True] = True
    require_behavioral_measurement: Literal[True] = True
    require_preregistered_thresholds: Literal[True] = True

    @model_validator(mode="after")
    def dimensions_are_canonical_and_sufficient(self) -> StressAcceptanceCriteria:
        if tuple(sorted(set(self.required_dimensions), key=lambda item: item.value)) != (
            self.required_dimensions
        ):
            raise ValueError("required stress dimensions must be unique and canonical")
        if len(self.required_dimensions) < self.minimum_distinct_stress_dimensions:
            raise ValueError("required stress dimensions do not satisfy the minimum")
        return self


AcceptanceCriteria = DiscriminativeAcceptanceCriteria | StressAcceptanceCriteria


_COMMON_EVIDENCE = frozenset(
    {
        EvidenceKind.TASK_QUALIFICATION,
        EvidenceKind.PREREGISTRATION,
        EvidenceKind.POLICY_EVALUATION,
    }
)
_PURPOSE_EVIDENCE = {
    SuitePurpose.DISCRIMINATIVE: _COMMON_EVIDENCE | {EvidenceKind.CONTROLLED_COMPARISON},
    SuitePurpose.STRESS: _COMMON_EVIDENCE
    | {EvidenceKind.STRUCTURAL_STRESS, EvidenceKind.STRESS_MEASUREMENT},
}
_COMMON_REJECTIONS = frozenset(
    {
        AdmissionReasonCode.TASK_UNQUALIFIED,
        AdmissionReasonCode.MISSING_REQUIRED_EVIDENCE,
        AdmissionReasonCode.EVIDENCE_TASK_MISMATCH,
        AdmissionReasonCode.POLICY_IDENTITY_MISMATCH,
        AdmissionReasonCode.SUITE_IDENTITY_MISMATCH,
    }
)
_PURPOSE_REJECTIONS = {
    SuitePurpose.DISCRIMINATIVE: _COMMON_REJECTIONS
    | {
        AdmissionReasonCode.NONCOMPARABLE_EVIDENCE,
        AdmissionReasonCode.INSUFFICIENT_CONFIGURATION_COVERAGE,
        AdmissionReasonCode.UNSTABLE_DISCRIMINATION,
    },
    SuitePurpose.STRESS: _COMMON_REJECTIONS
    | {
        AdmissionReasonCode.INSUFFICIENT_STRESS_DIMENSIONS,
        AdmissionReasonCode.STRESS_MEASUREMENT_MISSING,
    },
}


class AdmissionPolicy(BaseModel):
    """Immutable preregistration contract; it evaluates no provider or model output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    policy_id: Identifier
    policy_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    namespace: GovernanceNamespace
    suite_purpose: Literal[SuitePurpose.DISCRIMINATIVE, SuitePurpose.STRESS]
    candidate_requirements: CandidateRequirements
    acceptance_criteria: AcceptanceCriteria
    evidence_requirements: tuple[EvidenceKind, ...]
    rejection_reason_codes: tuple[AdmissionReasonCode, ...]
    provenance: PolicyProvenance
    policy_digest: Sha256Digest

    @model_validator(mode="after")
    def policy_is_canonical_neutral_and_self_identifying(self) -> AdmissionPolicy:
        if self.suite_purpose is SuitePurpose.DISCRIMINATIVE and not isinstance(
            self.acceptance_criteria, DiscriminativeAcceptanceCriteria
        ):
            raise ValueError("Discriminative policy requires Discriminative criteria")
        if self.suite_purpose is SuitePurpose.STRESS and not isinstance(
            self.acceptance_criteria, StressAcceptanceCriteria
        ):
            raise ValueError("Stress policy requires Stress criteria")
        expected_evidence = tuple(sorted(_PURPOSE_EVIDENCE[self.suite_purpose], key=str))
        if self.evidence_requirements != expected_evidence:
            raise ValueError("policy evidence requirements are incomplete or noncanonical")
        expected_rejections = tuple(sorted(_PURPOSE_REJECTIONS[self.suite_purpose], key=str))
        if self.rejection_reason_codes != expected_rejections:
            raise ValueError("policy rejection criteria are incomplete or noncanonical")
        if self.provenance.predecessor is not None:
            predecessor = self.provenance.predecessor
            if predecessor.policy_id != self.policy_id:
                raise ValueError("predecessor must reference the same policy id")
            if _version_key(predecessor.policy_version) >= _version_key(self.policy_version):
                raise ValueError("predecessor policy version must precede the new version")
            if predecessor.policy_digest == self.policy_digest:
                raise ValueError("policy cannot supersede its own digest")
        if self.policy_digest != canonical_digest(self.payload()):
            raise ValueError("admission policy digest does not match its canonical payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"policy_digest"})

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def as_reference(self) -> VersionedPolicyReference:
        return VersionedPolicyReference(
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            policy_digest=self.policy_digest,
        )


def _version_key(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


class TaskCharacteristics(BaseModel):
    """Orthogonal descriptive axes that never imply admission or holdout eligibility."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: TaskIdentity
    quality_identity: Sha256Digest
    family: TaskFamily
    benchmark_tier: BenchmarkTier
    source_kind: TaskSourceKind
    difficulty: DifficultyBand = DifficultyBand.UNASSESSED
    stress_dimensions: tuple[StressDimension, ...] = ()
    characteristics_digest: Sha256Digest

    @model_validator(mode="after")
    def characteristics_are_canonical(self) -> TaskCharacteristics:
        if tuple(sorted(set(self.stress_dimensions), key=lambda item: item.value)) != (
            self.stress_dimensions
        ):
            raise ValueError("stress dimensions must be unique and canonical")
        if self.characteristics_digest != canonical_digest(self.payload()):
            raise ValueError("task characteristics digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"characteristics_digest"})


class AdmissionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    characteristics: TaskCharacteristics
    task_qualification: TaskQualificationReference | None = None
    candidate_identity: Sha256Digest

    @model_validator(mode="after")
    def candidate_is_self_consistent(self) -> AdmissionCandidate:
        if (
            self.task_qualification is not None
            and self.task_qualification.task != self.characteristics.task
        ):
            raise ValueError("candidate qualification does not bind its exact task")
        if self.candidate_identity != canonical_digest(self.payload()):
            raise ValueError("candidate identity does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"candidate_identity"})


class AdmissionEvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EvidenceKind
    role: EvidenceRole = EvidenceRole.PRIMARY
    reference: TaskArtifactReference


def _evidence_key(item: AdmissionEvidenceReference) -> tuple[str, str, str, int, str]:
    artifact = item.reference.artifact
    return (
        item.kind.value,
        item.role.value,
        artifact.artifact_id,
        artifact.schema_version,
        artifact.artifact_digest,
    )


class AdmissionDecision(BaseModel):
    """Immutable candidate or final decision; evidence remains external and immutable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    decision_id: Identifier
    namespace: GovernanceNamespace
    status: AdmissionStatus
    candidate: AdmissionCandidate
    target_suite: SuiteManifestReference
    admission_policy: VersionedPolicyReference
    evidence: tuple[AdmissionEvidenceReference, ...] = ()
    reason_codes: tuple[AdmissionReasonCode, ...] = ()
    decision_digest: Sha256Digest

    @model_validator(mode="after")
    def decision_is_canonical_and_bound(self) -> AdmissionDecision:
        if self.target_suite.purpose not in (SuitePurpose.DISCRIMINATIVE, SuitePurpose.STRESS):
            raise ValueError("admission decisions target only governed suite purposes")
        if tuple(sorted(set(self.evidence), key=_evidence_key)) != self.evidence:
            raise ValueError("admission evidence must be unique and canonical")
        task = self.candidate.characteristics.task
        if any(item.reference.task != task for item in self.evidence):
            raise ValueError("decision evidence does not bind the candidate task")
        if tuple(sorted(set(self.reason_codes), key=str)) != self.reason_codes:
            raise ValueError("admission reason codes must be unique and canonical")
        if self.status is AdmissionStatus.CANDIDATE and self.reason_codes:
            raise ValueError("candidate records cannot carry a final decision reason")
        if self.status is AdmissionStatus.ADMITTED and self.reason_codes != (
            AdmissionReasonCode.ACCEPTANCE_CRITERIA_SATISFIED,
        ):
            raise ValueError("admitted decisions require the acceptance reason only")
        if self.status is AdmissionStatus.REJECTED and (
            not self.reason_codes
            or AdmissionReasonCode.ACCEPTANCE_CRITERIA_SATISFIED in self.reason_codes
        ):
            raise ValueError("rejected decisions require deterministic rejection reasons")
        if self.status is not AdmissionStatus.CANDIDATE and not self.evidence:
            raise ValueError("final admission decisions require exact evidence references")
        if self.decision_digest != canonical_digest(self.payload()):
            raise ValueError("admission decision digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"decision_digest"})

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def as_empirical_reference(self) -> TaskArtifactReference:
        if self.status is not AdmissionStatus.ADMITTED:
            raise AdmissionGovernanceError("only admitted decisions can be referenced as admission")
        return TaskArtifactReference(
            task=self.candidate.characteristics.task,
            artifact=ImmutableArtifactReference(
                artifact_id=self.decision_id,
                schema_version=self.schema_version,
                artifact_digest=self.decision_digest,
            ),
        )


class AdmissionDecisionRegister(BaseModel):
    """Canonical audit set that preserves candidates, admissions, and rejections."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    register_id: Identifier
    decisions: tuple[AdmissionDecision, ...]
    register_digest: Sha256Digest

    @model_validator(mode="after")
    def register_is_canonical_and_complete(self) -> AdmissionDecisionRegister:
        ordered = tuple(
            sorted(self.decisions, key=lambda item: (item.decision_id, item.decision_digest))
        )
        if ordered != self.decisions:
            raise ValueError("admission decisions must use canonical identity order")
        identities = tuple(item.decision_id for item in self.decisions)
        if len(set(identities)) != len(identities):
            raise ValueError("admission decision ids must be unique")
        if self.register_digest != canonical_digest(self.payload()):
            raise ValueError("admission register digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"register_digest"})


def build_policy_provenance(
    *,
    authority_identity: str,
    source_revision_identity: str,
    predecessor: VersionedPolicyReference | None = None,
) -> PolicyProvenance:
    payload = {
        "authority_identity": authority_identity,
        "source_revision_identity": source_revision_identity,
        "predecessor": None if predecessor is None else predecessor.model_dump(mode="json"),
    }
    payload["provenance_identity"] = canonical_digest(payload)
    return PolicyProvenance.model_validate(payload)


def build_admission_policy(
    *,
    policy_id: str,
    policy_version: str,
    namespace: GovernanceNamespace,
    suite_purpose: Literal[SuitePurpose.DISCRIMINATIVE, SuitePurpose.STRESS],
    acceptance_criteria: AcceptanceCriteria,
    provenance: PolicyProvenance,
) -> AdmissionPolicy:
    payload = {
        "schema_version": 1,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "namespace": namespace.value,
        "suite_purpose": suite_purpose.value,
        "candidate_requirements": CandidateRequirements().model_dump(mode="json"),
        "acceptance_criteria": acceptance_criteria.model_dump(mode="json"),
        "evidence_requirements": [
            item.value for item in sorted(_PURPOSE_EVIDENCE[suite_purpose], key=str)
        ],
        "rejection_reason_codes": [
            item.value for item in sorted(_PURPOSE_REJECTIONS[suite_purpose], key=str)
        ],
        "provenance": provenance.model_dump(mode="json"),
    }
    payload["policy_digest"] = canonical_digest(payload)
    try:
        return AdmissionPolicy.model_validate(payload)
    except ValueError as exc:
        raise AdmissionGovernanceError(str(exc)) from exc


def build_task_characteristics(
    quality: TaskQualityMetadata,
    *,
    difficulty: DifficultyBand = DifficultyBand.UNASSESSED,
    stress_dimensions: tuple[StressDimension, ...] = (),
) -> TaskCharacteristics:
    ordered_dimensions = tuple(sorted(set(stress_dimensions), key=lambda item: item.value))
    payload = {
        "task": quality.task.model_dump(mode="json"),
        "quality_identity": quality.quality_identity,
        "family": quality.family.value,
        "benchmark_tier": quality.benchmark_tier.value,
        "source_kind": quality.provenance.source_kind.value,
        "difficulty": difficulty.value,
        "stress_dimensions": [item.value for item in ordered_dimensions],
    }
    payload["characteristics_digest"] = canonical_digest(payload)
    return TaskCharacteristics.model_validate(payload)


def build_admission_candidate(
    characteristics: TaskCharacteristics,
    qualification: TaskQualification | None = None,
) -> AdmissionCandidate:
    qualification_reference: TaskQualificationReference | None = None
    if qualification is not None:
        if qualification.status is not QualificationStatus.QUALIFIED:
            raise AdmissionGovernanceError("candidate qualification is not qualified")
        if qualification.quality.task != characteristics.task:
            raise AdmissionGovernanceError("candidate qualification does not match the task")
        if qualification.qualification_id is None:
            raise AdmissionGovernanceError("qualified candidate is missing qualification id")
        qualification_reference = TaskQualificationReference(
            task=characteristics.task,
            qualification_id=qualification.qualification_id,
            qualification_identity=qualification.qualification_identity,
            quality_identity=qualification.quality.quality_identity,
        )
    payload: dict[str, Any] = {
        "characteristics": characteristics.model_dump(mode="json"),
        "task_qualification": (
            None
            if qualification_reference is None
            else qualification_reference.model_dump(mode="json")
        ),
    }
    payload["candidate_identity"] = canonical_digest(payload)
    return AdmissionCandidate.model_validate(payload)


def validate_admission_decision(
    decision: AdmissionDecision,
    *,
    policy: AdmissionPolicy,
    target_suite: SuiteManifestReference,
) -> None:
    if decision.admission_policy != policy.as_reference():
        raise AdmissionGovernanceError("admission decision policy identity is stale or mismatched")
    if decision.target_suite != target_suite:
        raise AdmissionGovernanceError("admission decision suite identity is stale or mismatched")
    if decision.namespace is not policy.namespace:
        raise AdmissionGovernanceError("admission namespace does not match policy namespace")
    if target_suite.purpose is not policy.suite_purpose:
        raise AdmissionGovernanceError("admission policy purpose does not match target suite")
    source_kind = decision.candidate.characteristics.source_kind
    if (
        policy.namespace is GovernanceNamespace.OFFICIAL
        and source_kind is not TaskSourceKind.HARNESSLAB
    ):
        raise AdmissionGovernanceError("Custom/imported evidence cannot satisfy Official admission")
    if decision.status is AdmissionStatus.ADMITTED:
        if decision.candidate.task_qualification is None:
            raise AdmissionGovernanceError("admission requires exact task qualification identity")
        actual = {item.kind for item in decision.evidence if item.role is EvidenceRole.PRIMARY}
        missing = set(policy.evidence_requirements) - actual
        if missing:
            labels = ", ".join(sorted(item.value for item in missing))
            raise AdmissionGovernanceError(f"admission evidence is missing: {labels}")
        qualification_evidence = tuple(
            item
            for item in decision.evidence
            if item.role is EvidenceRole.PRIMARY and item.kind is EvidenceKind.TASK_QUALIFICATION
        )
        expected_qualification = decision.candidate.task_qualification
        if len(qualification_evidence) != 1 or (
            qualification_evidence[0].reference.artifact.artifact_id
            != expected_qualification.qualification_id
            or qualification_evidence[0].reference.artifact.artifact_digest
            != expected_qualification.qualification_identity
        ):
            raise AdmissionGovernanceError(
                "task qualification evidence does not match the candidate qualification"
            )
    if decision.status is AdmissionStatus.REJECTED:
        allowed = set(policy.rejection_reason_codes)
        if not set(decision.reason_codes) <= allowed:
            raise AdmissionGovernanceError("decision uses a reason not defined by its policy")


def build_admission_decision(
    *,
    decision_id: str,
    status: AdmissionStatus,
    candidate: AdmissionCandidate,
    target_suite: SuiteManifestReference,
    policy: AdmissionPolicy,
    evidence: tuple[AdmissionEvidenceReference, ...] = (),
    reason_codes: tuple[AdmissionReasonCode, ...] = (),
) -> AdmissionDecision:
    ordered_evidence = tuple(sorted(evidence, key=_evidence_key))
    ordered_reasons = tuple(sorted(set(reason_codes), key=str))
    payload = {
        "schema_version": 1,
        "decision_id": decision_id,
        "namespace": policy.namespace.value,
        "status": status.value,
        "candidate": candidate.model_dump(mode="json"),
        "target_suite": target_suite.model_dump(mode="json"),
        "admission_policy": policy.as_reference().model_dump(mode="json"),
        "evidence": [item.model_dump(mode="json") for item in ordered_evidence],
        "reason_codes": [item.value for item in ordered_reasons],
    }
    payload["decision_digest"] = canonical_digest(payload)
    try:
        decision = AdmissionDecision.model_validate(payload)
        validate_admission_decision(decision, policy=policy, target_suite=target_suite)
        return decision
    except ValueError as exc:
        if isinstance(exc, AdmissionGovernanceError):
            raise
        raise AdmissionGovernanceError(str(exc)) from exc


def build_admission_decision_register(
    register_id: str, decisions: tuple[AdmissionDecision, ...]
) -> AdmissionDecisionRegister:
    ordered = tuple(sorted(decisions, key=lambda item: (item.decision_id, item.decision_digest)))
    payload = {
        "schema_version": 1,
        "register_id": register_id,
        "decisions": [item.model_dump(mode="json") for item in ordered],
    }
    payload["register_digest"] = canonical_digest(payload)
    try:
        return AdmissionDecisionRegister.model_validate(payload)
    except ValueError as exc:
        raise AdmissionGovernanceError(str(exc)) from exc
