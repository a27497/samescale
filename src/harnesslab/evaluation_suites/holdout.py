from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.evaluation_suites.admission import GovernanceNamespace
from harnesslab.evaluation_suites.exposure import (
    AccessPurpose,
    AssetVisibility,
    ExposureAssessment,
    ExposureHistory,
    ExposureMatchKind,
    ExposureState,
    VisibilityPolicy,
    assess_exposure,
    task_lineage_from_quality,
)
from harnesslab.evaluation_suites.models import TaskSplitReference
from harnesslab.evaluation_suites.service import reference_task_split
from harnesslab.tasks.quality import (
    QualificationStatus,
    TaskIdentity,
    TaskQualification,
    TaskSourceKind,
)
from harnesslab.tasks.splits import DevelopmentExposure, SplitRole, TaskSplitFreeze


class HoldoutGovernanceError(ValueError):
    """Holdout eligibility inputs are stale, mismatched, or otherwise unsafe."""


class HoldoutClaimContext(StrEnum):
    FORMAL_COMPARISON = "FORMAL_COMPARISON"
    RELEASE_CLAIM = "RELEASE_CLAIM"
    CALIBRATION_CLAIM = "CALIBRATION_CLAIM"


class HoldoutEligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN_BLOCKED = "UNKNOWN_BLOCKED"


class HoldoutReasonCode(StrEnum):
    TASK_UNQUALIFIED = "TASK_UNQUALIFIED"
    SPLIT_EVIDENCE_MISSING = "SPLIT_EVIDENCE_MISSING"
    SPLIT_EVIDENCE_UNVERIFIED = "SPLIT_EVIDENCE_UNVERIFIED"
    DEVELOPMENT_ASSIGNMENT = "DEVELOPMENT_ASSIGNMENT"
    DEVELOPMENT_EXPOSURE_CONFIRMED = "DEVELOPMENT_EXPOSURE_CONFIRMED"
    LINEAGE_EXPOSURE_CONFIRMED = "LINEAGE_EXPOSURE_CONFIRMED"
    EXPOSURE_UNKNOWN = "EXPOSURE_UNKNOWN"
    VISIBILITY_NOT_SEALED = "VISIBILITY_NOT_SEALED"
    CLAIM_CONTEXT_NOT_ALLOWED = "CLAIM_CONTEXT_NOT_ALLOWED"
    OFFICIAL_CUSTOM_ISOLATION = "OFFICIAL_CUSTOM_ISOLATION"


_UNKNOWN_REASONS = frozenset(
    {
        HoldoutReasonCode.SPLIT_EVIDENCE_MISSING,
        HoldoutReasonCode.SPLIT_EVIDENCE_UNVERIFIED,
        HoldoutReasonCode.EXPOSURE_UNKNOWN,
    }
)


class HoldoutEligibilityResult(BaseModel):
    """Claim-scoped result; ELIGIBLE never generalizes beyond the bound claim context."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    evaluation_id: Identifier
    namespace: GovernanceNamespace
    task: TaskIdentity
    claim_id: Identifier
    claim_context: HoldoutClaimContext
    qualification_status: QualificationStatus
    qualification_identity: Sha256Digest
    split_reference: TaskSplitReference | None
    visibility_policy_identity: Sha256Digest
    exposure_assessment: ExposureAssessment
    status: HoldoutEligibilityStatus
    reason_codes: tuple[HoldoutReasonCode, ...]
    eligibility_digest: Sha256Digest

    @model_validator(mode="after")
    def result_is_canonical_and_self_identifying(self) -> HoldoutEligibilityResult:
        if self.split_reference is not None and self.split_reference.task != self.task:
            raise ValueError("holdout split reference does not bind the evaluated task")
        if self.exposure_assessment.task_lineage.task != self.task:
            raise ValueError("exposure assessment does not bind the evaluated task")
        if tuple(sorted(set(self.reason_codes), key=lambda item: item.value)) != self.reason_codes:
            raise ValueError("holdout reason codes must be unique and canonical")
        if self.status is HoldoutEligibilityStatus.ELIGIBLE and self.reason_codes:
            raise ValueError("eligible result cannot carry blocking reasons")
        if self.status is not HoldoutEligibilityStatus.ELIGIBLE and not self.reason_codes:
            raise ValueError("blocked holdout result requires reason codes")
        if self.eligibility_digest != canonical_digest(self.payload()):
            raise ValueError("holdout eligibility digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"eligibility_digest"})

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )


def evaluate_holdout_eligibility(
    *,
    evaluation_id: str,
    namespace: GovernanceNamespace,
    qualification: TaskQualification,
    claim_id: str,
    claim_context: HoldoutClaimContext,
    split_reference: TaskSplitReference | None,
    split_freeze: TaskSplitFreeze | None,
    visibility_policy: VisibilityPolicy,
    exposure_history: ExposureHistory,
) -> HoldoutEligibilityResult:
    """Evaluate exact, claim-scoped Holdout eligibility without reading task content."""

    quality = qualification.quality
    task = quality.task
    lineage = task_lineage_from_quality(quality)
    if visibility_policy.task_lineage != lineage:
        raise HoldoutGovernanceError("visibility policy task or lineage identity is stale")
    if split_reference is not None and split_reference.task != task:
        raise HoldoutGovernanceError("split reference does not match the evaluated task")
    if split_reference is not None and split_freeze is not None:
        assignments = tuple(
            assignment
            for assignment in split_freeze.assignments
            if assignment.qualification.quality.task == task
        )
        if len(assignments) != 1:
            raise HoldoutGovernanceError(
                "evaluated task does not have one exact assignment in the split freeze"
            )
        expected_split_reference = reference_task_split(task, split_freeze, assignments[0])
        if expected_split_reference != split_reference:
            raise HoldoutGovernanceError("split reference is stale or mismatched")

    reasons: set[HoldoutReasonCode] = set()
    if qualification.status is not QualificationStatus.QUALIFIED:
        reasons.add(HoldoutReasonCode.TASK_UNQUALIFIED)
    if split_reference is None:
        reasons.add(HoldoutReasonCode.SPLIT_EVIDENCE_MISSING)
    elif split_freeze is None:
        reasons.add(HoldoutReasonCode.SPLIT_EVIDENCE_UNVERIFIED)
    elif split_reference.role is SplitRole.DEVELOPMENT:
        reasons.add(HoldoutReasonCode.DEVELOPMENT_ASSIGNMENT)
    elif split_reference.development_exposure is DevelopmentExposure.USED:
        reasons.add(HoldoutReasonCode.DEVELOPMENT_EXPOSURE_CONFIRMED)
    elif split_reference.development_exposure is DevelopmentExposure.UNKNOWN:
        reasons.add(HoldoutReasonCode.EXPOSURE_UNKNOWN)

    assessment = assess_exposure(lineage, exposure_history)
    if assessment.state is ExposureState.EXPOSED:
        if ExposureMatchKind.LINEAGE in assessment.match_kinds:
            reasons.add(HoldoutReasonCode.LINEAGE_EXPOSURE_CONFIRMED)
        else:
            reasons.add(HoldoutReasonCode.DEVELOPMENT_EXPOSURE_CONFIRMED)
    elif assessment.state is ExposureState.UNKNOWN:
        reasons.add(HoldoutReasonCode.EXPOSURE_UNKNOWN)

    if visibility_policy.visibility is not AssetVisibility.SEALED_HOLDOUT:
        reasons.add(HoldoutReasonCode.VISIBILITY_NOT_SEALED)
    if AccessPurpose.HOLDOUT_EVALUATION not in visibility_policy.allowed_purposes:
        reasons.add(HoldoutReasonCode.CLAIM_CONTEXT_NOT_ALLOWED)
    if visibility_policy.namespace is not namespace:
        reasons.add(HoldoutReasonCode.OFFICIAL_CUSTOM_ISOLATION)
    if (
        namespace is GovernanceNamespace.OFFICIAL
        and quality.provenance.source_kind is not TaskSourceKind.HARNESSLAB
    ):
        reasons.add(HoldoutReasonCode.OFFICIAL_CUSTOM_ISOLATION)

    ordered_reasons = tuple(sorted(reasons, key=lambda item: item.value))
    hard_reasons = reasons - _UNKNOWN_REASONS
    if hard_reasons:
        status = HoldoutEligibilityStatus.INELIGIBLE
    elif reasons:
        status = HoldoutEligibilityStatus.UNKNOWN_BLOCKED
    else:
        status = HoldoutEligibilityStatus.ELIGIBLE

    payload = {
        "schema_version": 1,
        "evaluation_id": evaluation_id,
        "namespace": namespace.value,
        "task": task.model_dump(mode="json"),
        "claim_id": claim_id,
        "claim_context": claim_context.value,
        "qualification_status": qualification.status.value,
        "qualification_identity": qualification.qualification_identity,
        "split_reference": (
            None if split_reference is None else split_reference.model_dump(mode="json")
        ),
        "visibility_policy_identity": visibility_policy.policy_digest,
        "exposure_assessment": assessment.model_dump(mode="json"),
        "status": status.value,
        "reason_codes": [item.value for item in ordered_reasons],
    }
    payload["eligibility_digest"] = canonical_digest(payload)
    try:
        return HoldoutEligibilityResult.model_validate(payload)
    except ValueError as exc:
        raise HoldoutGovernanceError(str(exc)) from exc
