"""Custom technical qualification never substitutes for exposure or split evidence."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from harnesslab.comparability.models import canonical_digest
from harnesslab.evaluation_suites import (
    AccessPurpose,
    AdmissionCandidate,
    AdmissionGovernanceError,
    AssetVisibility,
    ExposureCoverage,
    ExposureType,
    GovernanceNamespace,
    HoldoutClaimContext,
    HoldoutEligibilityStatus,
    HoldoutReasonCode,
    append_exposure_event,
    build_admission_candidate,
    build_exposure_history,
    build_task_characteristics,
    build_visibility_policy,
    evaluate_holdout_eligibility,
    reference_task_split,
    task_lineage_from_quality,
)
from harnesslab.tasks.quality import (
    CUSTOM_TECHNICAL_CHECKS,
    BenchmarkTier,
    QualificationCheck,
    QualificationEvidence,
    QualificationStatus,
    TaskFamily,
    TaskIdentity,
    TaskProvenance,
    TaskQualification,
    TaskQualityError,
    TaskQualityMetadata,
    TaskSourceKind,
    qualify_task,
    unqualified_task,
)
from harnesslab.tasks.splits import (
    DevelopmentExposure,
    SplitRole,
    TaskSplitAssignment,
    TaskSplitError,
    freeze_split,
)


def _digest(label: str) -> str:
    return canonical_digest({"synthetic-custom-qualification-test": label})


def _quality(label: str = "heldout") -> TaskQualityMetadata:
    return TaskQualityMetadata(
        task=TaskIdentity(
            task_id=label,
            task_version="1.0.0",
            task_digest=_digest(label),
            workspace_digest=_digest(f"{label}-workspace"),
            verifier_digest=_digest(f"{label}-verifier"),
        ),
        family=TaskFamily.CUSTOM,
        benchmark_tier=BenchmarkTier.UNASSIGNED,
        provenance=TaskProvenance(
            source_kind=TaskSourceKind.CUSTOM, source_identity=_digest(f"{label}-source")
        ),
    )


def _qualify(
    quality: TaskQualityMetadata, missing: QualificationCheck | None = None
) -> TaskQualification:
    return qualify_task(
        quality,
        qualification_id=f"custom-technical-{quality.task.task_id}",
        evidence=tuple(
            QualificationEvidence(check=check, evidence_identity=_digest(check.value))
            for check in sorted(CUSTOM_TECHNICAL_CHECKS)
            if check != missing
        ),
    )


def test_custom_qualification_retains_category_and_historical_unqualified_identity() -> None:
    quality = _quality()
    previous = unqualified_task(quality)
    qualified = _qualify(quality)
    assert qualified.status is QualificationStatus.QUALIFIED
    assert qualified.quality == quality
    assert qualified.quality.benchmark_tier is BenchmarkTier.UNASSIGNED
    assert qualified.quality.provenance.source_kind is TaskSourceKind.CUSTOM
    assert TaskQualification.model_validate_json(qualified.model_dump_json()) == qualified
    assert unqualified_task(quality).qualification_identity == previous.qualification_identity
    assert QualificationCheck.DETERMINISTIC_HEALTH not in {e.check for e in qualified.evidence}


@pytest.mark.parametrize("missing", sorted(CUSTOM_TECHNICAL_CHECKS))
def test_custom_qualification_requires_every_technical_check(missing: QualificationCheck) -> None:
    with pytest.raises(TaskQualityError, match=missing.value):
        _qualify(_quality(), missing)


@pytest.mark.parametrize("exposure", [DevelopmentExposure.UNKNOWN, DevelopmentExposure.USED])
def test_custom_qualification_does_not_clear_split_exposure(exposure: DevelopmentExposure) -> None:
    with pytest.raises(TaskSplitError):
        freeze_split(
            "synthetic-blocked",
            (
                TaskSplitAssignment(
                    role=SplitRole.DEVELOPMENT,
                    qualification=_qualify(_quality("development")),
                    development_exposure=DevelopmentExposure.USED,
                ),
                TaskSplitAssignment(
                    role=SplitRole.HELD_OUT,
                    qualification=_qualify(_quality()),
                    development_exposure=exposure,
                ),
            ),
        )


@pytest.mark.parametrize("state", ["unknown", "missing-split", "exposed", "lineage", "clear"])
@pytest.mark.parametrize("namespace", list(GovernanceNamespace))
def test_custom_holdout_still_requires_independent_exposure_and_split(
    state: str, namespace: GovernanceNamespace
) -> None:
    quality = _quality()
    qualification = _qualify(quality)
    heldout = TaskSplitAssignment(
        role=SplitRole.HELD_OUT,
        qualification=qualification,
        development_exposure=DevelopmentExposure.NOT_USED,
    )
    split = freeze_split(
        "synthetic-split",
        (
            heldout,
            TaskSplitAssignment(
                role=SplitRole.DEVELOPMENT,
                qualification=_qualify(_quality("development")),
                development_exposure=DevelopmentExposure.USED,
            ),
        ),
    )
    history = build_exposure_history(
        "synthetic-history",
        coverage=ExposureCoverage.UNKNOWN if state == "unknown" else ExposureCoverage.COMPLETE,
        coverage_evidence_identity=None if state == "unknown" else _digest("coverage"),
    )
    if state in {"exposed", "lineage"}:
        accessed = quality
        if state == "lineage":
            accessed = _quality("related").model_copy(update={"provenance": quality.provenance})
        history = append_exposure_event(
            history,
            task_lineage=task_lineage_from_quality(accessed),
            exposure_type=ExposureType.DEVELOPMENT_TASK_ACCESS,
            purpose=AccessPurpose.DEVELOPMENT,
            actor_identity=_digest("tuner"),
        )
    result = evaluate_holdout_eligibility(
        evaluation_id="synthetic-evaluation",
        namespace=namespace,
        qualification=qualification,
        claim_id="synthetic-claim",
        claim_context=HoldoutClaimContext.FORMAL_COMPARISON,
        split_reference=(
            None if state == "missing-split" else reference_task_split(quality.task, split, heldout)
        ),
        split_freeze=None if state == "missing-split" else split,
        visibility_policy=build_visibility_policy(
            policy_id="synthetic-sealed",
            policy_version="1.0.0",
            namespace=GovernanceNamespace.CUSTOM,
            task_lineage=task_lineage_from_quality(quality),
            visibility=AssetVisibility.SEALED_HOLDOUT,
            allowed_purposes=(AccessPurpose.HOLDOUT_EVALUATION,),
        ),
        exposure_history=history,
    )
    assert HoldoutReasonCode.TASK_UNQUALIFIED not in result.reason_codes
    if namespace is GovernanceNamespace.OFFICIAL:
        assert result.status is HoldoutEligibilityStatus.INELIGIBLE
        assert HoldoutReasonCode.OFFICIAL_CUSTOM_ISOLATION in result.reason_codes
    elif state == "clear":
        assert result.status is HoldoutEligibilityStatus.ELIGIBLE
    elif state in {"unknown", "missing-split"}:
        assert result.status is HoldoutEligibilityStatus.UNKNOWN_BLOCKED
        reason = (
            HoldoutReasonCode.EXPOSURE_UNKNOWN
            if state == "unknown"
            else HoldoutReasonCode.SPLIT_EVIDENCE_MISSING
        )
        assert result.reason_codes == (reason,)
    else:
        assert result.status is HoldoutEligibilityStatus.INELIGIBLE
        assert result.exposure_assessment.state.value == "EXPOSED"


def test_admission_cannot_reuse_custom_qualification_for_another_source() -> None:
    quality = _quality()
    qualification = _qualify(quality)
    original = build_admission_candidate(build_task_characteristics(quality), qualification)
    official = TaskQualityMetadata(
        task=quality.task,
        family=TaskFamily.CORE,
        benchmark_tier=BenchmarkTier.TIER_A,
        provenance=TaskProvenance(
            source_kind=TaskSourceKind.HARNESSLAB, source_identity=_digest("official")
        ),
    )
    with pytest.raises(AdmissionGovernanceError, match="quality identity mismatch"):
        build_admission_candidate(build_task_characteristics(official), qualification)
    payload = original.model_dump(mode="json")
    payload["characteristics"] = build_task_characteristics(official).model_dump(mode="json")
    payload["candidate_identity"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "candidate_identity"}
    )
    with pytest.raises(ValidationError, match="exact quality identity"):
        AdmissionCandidate.model_validate(payload)
    relabeled = build_task_characteristics(quality).model_copy(
        update={"source_kind": TaskSourceKind.HARNESSLAB}
    )
    with pytest.raises(AdmissionGovernanceError, match="source category mismatch"):
        build_admission_candidate(relabeled, qualification)
