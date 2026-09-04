from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from harnesslab.comparability.models import canonical_digest
from harnesslab.evaluation_suites import (
    AccessPurpose,
    AccessStatus,
    AdmissionCandidate,
    AdmissionDecision,
    AdmissionEvidenceReference,
    AdmissionGovernanceError,
    AdmissionPolicy,
    AdmissionReasonCode,
    AdmissionStatus,
    AssetVisibility,
    DifficultyBand,
    DiscriminativeAcceptanceCriteria,
    EvaluationSuiteMembership,
    EvidenceKind,
    ExposureCoverage,
    ExposureGovernanceError,
    ExposureHistory,
    ExposureState,
    ExposureType,
    GovernanceArtifactError,
    GovernanceNamespace,
    HoldoutClaimContext,
    HoldoutEligibilityStatus,
    HoldoutGovernanceError,
    HoldoutReasonCode,
    ImmutableArtifactReference,
    PolicyProvenance,
    StressAcceptanceCriteria,
    StressDimension,
    SuitePurpose,
    TaskArtifactReference,
    TaskLineageReference,
    TaskSplitReference,
    VersionedPolicyReference,
    VisibilityPolicy,
    append_exposure_event,
    assess_exposure,
    build_admission_candidate,
    build_admission_decision,
    build_admission_decision_register,
    build_admission_policy,
    build_evaluation_suite_manifest,
    build_exposure_history,
    build_policy_provenance,
    build_task_characteristics,
    build_visibility_policy,
    core_development_exposure_history,
    evaluate_access,
    evaluate_holdout_eligibility,
    load_admission_decision,
    load_admission_policy,
    load_exposure_history,
    load_holdout_eligibility,
    load_visibility_policy,
    record_allowed_access,
    reference_task_split,
    task_lineage_from_quality,
    validate_access_decision,
    validate_admission_decision,
    validate_exposure_history_extension,
)
from harnesslab.evaluation_suites.models import EvaluationSuiteManifest
from harnesslab.release.contracts import load_core_corpus
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.quality import (
    BenchmarkTier,
    QualificationCheck,
    QualificationEvidence,
    TaskProvenance,
    TaskQualification,
    TaskQualityMetadata,
    TaskSourceKind,
    qualify_task,
    unqualified_task,
)
from harnesslab.tasks.splits import (
    DevelopmentExposure,
    SplitRole,
    TaskSplitAssignment,
    TaskSplitFreeze,
    freeze_split,
)

ROOT = Path(__file__).resolve().parents[1]


def _digest(label: str) -> str:
    return canonical_digest({"m3-fixture": label})


def _quality(task_id: str, version: str = "1.0.0") -> TaskQualityMetadata:
    package = TaskPackage.load(ROOT / "tasks" / task_id / version)
    return TaskQualityMetadata.from_package(package)


def _qualification_evidence(tier: BenchmarkTier, prefix: str) -> tuple[QualificationEvidence, ...]:
    checks = {
        QualificationCheck.PACKAGE_VALID,
        QualificationCheck.BASELINE_FAILS,
        QualificationCheck.ORACLE_PASSES,
        QualificationCheck.DETERMINISTIC_HEALTH,
    }
    if tier is BenchmarkTier.TIER_B:
        checks |= {
            QualificationCheck.FROZEN_REPOSITORY_SNAPSHOT,
            QualificationCheck.WORKSPACE_ISOLATION,
            QualificationCheck.HIDDEN_ASSETS_ISOLATED,
            QualificationCheck.ROBUSTNESS_VARIANTS_FAIL,
            QualificationCheck.FAILURE_BOUNDARIES_VALID,
        }
    return tuple(
        QualificationEvidence(check=check, evidence_identity=_digest(f"{prefix}:{check.value}"))
        for check in sorted(checks, key=lambda item: item.value)
    )


def _qualify(quality: TaskQualityMetadata) -> TaskQualification:
    return qualify_task(
        quality,
        qualification_id=f"qualification-{quality.task.task_id}-{quality.task.task_version}",
        evidence=_qualification_evidence(quality.benchmark_tier, quality.task.task_id),
    )


def _provenance(label: str = "v1") -> PolicyProvenance:
    return build_policy_provenance(
        authority_identity=_digest("policy-authority"),
        source_revision_identity=_digest(f"policy-source:{label}"),
    )


def _discriminative_policy(*, version: str = "1.0.0") -> AdmissionPolicy:
    return build_admission_policy(
        policy_id="discriminative-admission",
        policy_version=version,
        namespace=GovernanceNamespace.OFFICIAL,
        suite_purpose=SuitePurpose.DISCRIMINATIVE,
        acceptance_criteria=DiscriminativeAcceptanceCriteria(
            minimum_configurations=3,
            minimum_repetitions_per_configuration=5,
            minimum_pairwise_effect_absolute=0.1,
            maximum_rank_instability=0.2,
        ),
        provenance=_provenance(version),
    )


def _stress_policy() -> AdmissionPolicy:
    return build_admission_policy(
        policy_id="stress-admission",
        policy_version="1.0.0",
        namespace=GovernanceNamespace.OFFICIAL,
        suite_purpose=SuitePurpose.STRESS,
        acceptance_criteria=StressAcceptanceCriteria(
            minimum_distinct_stress_dimensions=2,
            required_dimensions=(StressDimension.MULTI_FILE, StressDimension.REPAIR_LOOP),
        ),
        provenance=_provenance("stress"),
    )


def _suite(purpose: SuitePurpose) -> EvaluationSuiteManifest:
    return build_evaluation_suite_manifest(
        suite_id=f"fixture-{purpose.value.lower()}",
        suite_version="1.0.0",
        purpose=purpose,
    )


def _candidate(
    task_id: str = "core-python-deduplicate",
    *,
    qualified: bool = True,
    difficulty: DifficultyBand = DifficultyBand.UNASSESSED,
    stress_dimensions: tuple[StressDimension, ...] = (),
) -> tuple[TaskQualityMetadata, AdmissionCandidate]:
    quality = _quality(task_id)
    characteristics = build_task_characteristics(
        quality,
        difficulty=difficulty,
        stress_dimensions=stress_dimensions,
    )
    return (
        quality,
        build_admission_candidate(characteristics, _qualify(quality) if qualified else None),
    )


def _admission_evidence(
    candidate: AdmissionCandidate, kind: EvidenceKind, label: str | None = None
) -> AdmissionEvidenceReference:
    task = candidate.characteristics.task
    name = label or kind.value.lower()
    if kind is EvidenceKind.TASK_QUALIFICATION and candidate.task_qualification is not None:
        name = candidate.task_qualification.qualification_id
        digest = candidate.task_qualification.qualification_identity
    else:
        digest = _digest(name)
    return AdmissionEvidenceReference(
        kind=kind,
        reference=TaskArtifactReference(
            task=task,
            artifact=ImmutableArtifactReference(
                artifact_id=name,
                schema_version=1,
                artifact_digest=digest,
            ),
        ),
    )


def _complete_evidence(
    candidate: AdmissionCandidate, policy: AdmissionPolicy
) -> tuple[AdmissionEvidenceReference, ...]:
    return tuple(_admission_evidence(candidate, kind) for kind in policy.evidence_requirements)


def _split_fixture() -> tuple[
    TaskQualityMetadata,
    TaskQualification,
    TaskSplitReference,
    TaskQualityMetadata,
    TaskQualification,
    TaskSplitReference,
    TaskSplitFreeze,
]:
    development_quality = _quality("core-python-deduplicate")
    held_out_quality = _quality("core-python-feature-flag")
    development_qualification = _qualify(development_quality)
    held_out_qualification = _qualify(held_out_quality)
    development = TaskSplitAssignment(
        role=SplitRole.DEVELOPMENT,
        qualification=development_qualification,
        development_exposure=DevelopmentExposure.USED,
    )
    held_out = TaskSplitAssignment(
        role=SplitRole.HELD_OUT,
        qualification=held_out_qualification,
        development_exposure=DevelopmentExposure.NOT_USED,
    )
    split = freeze_split("m3-fixture-split", (held_out, development))
    return (
        development_quality,
        development_qualification,
        reference_task_split(development_quality.task, split, development),
        held_out_quality,
        held_out_qualification,
        reference_task_split(held_out_quality.task, split, held_out),
        split,
    )


def _sealed_policy(quality: TaskQualityMetadata) -> VisibilityPolicy:
    return build_visibility_policy(
        policy_id=f"sealed-{quality.task.task_id}",
        policy_version="1.0.0",
        namespace=GovernanceNamespace.OFFICIAL,
        task_lineage=task_lineage_from_quality(quality),
        visibility=AssetVisibility.SEALED_HOLDOUT,
        allowed_purposes=(AccessPurpose.HOLDOUT_EVALUATION,),
    )


def _history(
    ledger_id: str, coverage: ExposureCoverage = ExposureCoverage.COMPLETE
) -> ExposureHistory:
    return build_exposure_history(
        ledger_id,
        coverage=coverage,
        coverage_evidence_identity=(
            _digest(f"{ledger_id}:coverage") if coverage is ExposureCoverage.COMPLETE else None
        ),
    )


def test_deterministic_versioned_policy_identity_and_explicit_criteria() -> None:
    first = _discriminative_policy()
    second = _discriminative_policy()

    assert first == second
    assert first.policy_digest == canonical_digest(first.payload())
    assert first.candidate_requirements.configuration_neutral is True
    assert EvidenceKind.CONTROLLED_COMPARISON in first.evidence_requirements
    assert AdmissionReasonCode.NONCOMPARABLE_EVIDENCE in first.rejection_reason_codes


def test_policy_unknown_fields_and_favored_configuration_rules_fail_closed(
    tmp_path: Path,
) -> None:
    policy = _discriminative_policy()
    raw = policy.model_dump(mode="json")
    raw["favored_model"] = "chosen-model"
    raw["policy_digest"] = canonical_digest(
        {key: value for key, value in raw.items() if key != "policy_digest"}
    )
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(GovernanceArtifactError, match="invalid admission policy"):
        load_admission_policy(path)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        DiscriminativeAcceptanceCriteria(
            minimum_configurations=2,
            minimum_repetitions_per_configuration=2,
            minimum_pairwise_effect_absolute=0.1,
            maximum_rank_instability=0.2,
            favored_harness="chosen-harness",  # type: ignore[call-arg]
        )


def test_admission_requires_exact_policy_and_suite_identity() -> None:
    policy = _discriminative_policy()
    _, candidate = _candidate()
    suite = _suite(SuitePurpose.DISCRIMINATIVE)
    decision = build_admission_decision(
        decision_id="admit-task",
        status=AdmissionStatus.ADMITTED,
        candidate=candidate,
        target_suite=suite.as_reference(),
        policy=policy,
        evidence=_complete_evidence(candidate, policy),
        reason_codes=(AdmissionReasonCode.ACCEPTANCE_CRITERIA_SATISFIED,),
    )

    validate_admission_decision(decision, policy=policy, target_suite=suite.as_reference())
    stale = _discriminative_policy(version="1.0.1")
    with pytest.raises(AdmissionGovernanceError, match="stale or mismatched"):
        validate_admission_decision(decision, policy=stale, target_suite=suite.as_reference())
    other_suite = build_evaluation_suite_manifest(
        suite_id="other-discriminative",
        suite_version="1.0.0",
        purpose=SuitePurpose.DISCRIMINATIVE,
    )
    with pytest.raises(AdmissionGovernanceError, match="suite identity"):
        validate_admission_decision(
            decision, policy=policy, target_suite=other_suite.as_reference()
        )


def test_policy_supersession_is_explicit_and_cannot_rebind_another_policy() -> None:
    predecessor = _discriminative_policy(version="1.0.0")
    provenance = build_policy_provenance(
        authority_identity=_digest("policy-authority"),
        source_revision_identity=_digest("policy-source:1.1.0"),
        predecessor=predecessor.as_reference(),
    )
    successor = build_admission_policy(
        policy_id=predecessor.policy_id,
        policy_version="1.1.0",
        namespace=GovernanceNamespace.OFFICIAL,
        suite_purpose=SuitePurpose.DISCRIMINATIVE,
        acceptance_criteria=DiscriminativeAcceptanceCriteria(
            minimum_configurations=3,
            minimum_repetitions_per_configuration=5,
            minimum_pairwise_effect_absolute=0.1,
            maximum_rank_instability=0.2,
        ),
        provenance=provenance,
    )
    assert successor.provenance.predecessor == predecessor.as_reference()

    wrong_predecessor = predecessor.as_reference().model_copy(update={"policy_id": "other-policy"})
    with pytest.raises(AdmissionGovernanceError, match="same policy id"):
        build_admission_policy(
            policy_id=predecessor.policy_id,
            policy_version="1.1.0",
            namespace=GovernanceNamespace.OFFICIAL,
            suite_purpose=SuitePurpose.DISCRIMINATIVE,
            acceptance_criteria=DiscriminativeAcceptanceCriteria(
                minimum_configurations=3,
                minimum_repetitions_per_configuration=5,
                minimum_pairwise_effect_absolute=0.1,
                maximum_rank_instability=0.2,
            ),
            provenance=build_policy_provenance(
                authority_identity=_digest("policy-authority"),
                source_revision_identity=_digest("policy-source:wrong"),
                predecessor=wrong_predecessor,
            ),
        )


def test_decision_evidence_must_bind_the_same_exact_task() -> None:
    policy = _discriminative_policy()
    _, candidate = _candidate()
    other_quality, _ = _candidate("core-python-feature-flag")
    evidence = _admission_evidence(candidate, EvidenceKind.TASK_QUALIFICATION)
    mismatched = evidence.model_copy(
        update={
            "reference": TaskArtifactReference(
                task=other_quality.task,
                artifact=evidence.reference.artifact,
            )
        }
    )
    raw = {
        "schema_version": 1,
        "decision_id": "bad-binding",
        "namespace": GovernanceNamespace.OFFICIAL.value,
        "status": AdmissionStatus.CANDIDATE.value,
        "candidate": candidate.model_dump(mode="json"),
        "target_suite": _suite(SuitePurpose.DISCRIMINATIVE).as_reference().model_dump(mode="json"),
        "admission_policy": policy.as_reference().model_dump(mode="json"),
        "evidence": [mismatched.model_dump(mode="json")],
        "reason_codes": [],
    }
    raw["decision_digest"] = canonical_digest(raw)
    with pytest.raises(ValidationError, match="does not bind"):
        AdmissionDecision.model_validate(raw)


def test_admitted_task_qualification_evidence_must_match_candidate_digest() -> None:
    policy = _discriminative_policy()
    _, candidate = _candidate()
    evidence = list(_complete_evidence(candidate, policy))
    qualification_index = next(
        index for index, item in enumerate(evidence) if item.kind is EvidenceKind.TASK_QUALIFICATION
    )
    qualification_evidence = evidence[qualification_index]
    evidence[qualification_index] = qualification_evidence.model_copy(
        update={
            "reference": TaskArtifactReference(
                task=candidate.characteristics.task,
                artifact=qualification_evidence.reference.artifact.model_copy(
                    update={"artifact_digest": _digest("wrong-qualification")}
                ),
            )
        }
    )

    with pytest.raises(AdmissionGovernanceError, match="candidate qualification"):
        build_admission_decision(
            decision_id="wrong-qualification-evidence",
            status=AdmissionStatus.ADMITTED,
            candidate=candidate,
            target_suite=_suite(SuitePurpose.DISCRIMINATIVE).as_reference(),
            policy=policy,
            evidence=tuple(evidence),
            reason_codes=(AdmissionReasonCode.ACCEPTANCE_CRITERIA_SATISFIED,),
        )


@pytest.mark.parametrize(
    ("policy", "only_kind"),
    [
        (_stress_policy(), EvidenceKind.TIER_B_QUALIFICATION),
        (_discriminative_policy(), EvidenceKind.HISTORICAL_MATRIX_PARTICIPATION),
    ],
)
def test_legacy_qualification_or_participation_alone_cannot_admit(
    policy: AdmissionPolicy, only_kind: EvidenceKind
) -> None:
    task_id = (
        "repo-python-ledger-transfer"
        if only_kind is EvidenceKind.TIER_B_QUALIFICATION
        else "core-python-deduplicate"
    )
    _, candidate = _candidate(task_id)
    suite = _suite(policy.suite_purpose)

    with pytest.raises(AdmissionGovernanceError, match="admission evidence is missing"):
        build_admission_decision(
            decision_id="unsupported-admission",
            status=AdmissionStatus.ADMITTED,
            candidate=candidate,
            target_suite=suite.as_reference(),
            policy=policy,
            evidence=(_admission_evidence(candidate, only_kind),),
            reason_codes=(AdmissionReasonCode.ACCEPTANCE_CRITERIA_SATISFIED,),
        )


def test_candidates_admissions_and_rejections_remain_auditable() -> None:
    policy = _discriminative_policy()
    _, accepted_candidate = _candidate()
    _, rejected_candidate = _candidate("core-python-feature-flag")
    suite = _suite(SuitePurpose.DISCRIMINATIVE)
    candidate = build_admission_decision(
        decision_id="01-candidate",
        status=AdmissionStatus.CANDIDATE,
        candidate=accepted_candidate,
        target_suite=suite.as_reference(),
        policy=policy,
    )
    admitted = build_admission_decision(
        decision_id="02-admitted",
        status=AdmissionStatus.ADMITTED,
        candidate=accepted_candidate,
        target_suite=suite.as_reference(),
        policy=policy,
        evidence=_complete_evidence(accepted_candidate, policy),
        reason_codes=(AdmissionReasonCode.ACCEPTANCE_CRITERIA_SATISFIED,),
    )
    rejected = build_admission_decision(
        decision_id="03-rejected",
        status=AdmissionStatus.REJECTED,
        candidate=rejected_candidate,
        target_suite=suite.as_reference(),
        policy=policy,
        evidence=(_admission_evidence(rejected_candidate, EvidenceKind.POLICY_EVALUATION),),
        reason_codes=(AdmissionReasonCode.NONCOMPARABLE_EVIDENCE,),
    )

    register = build_admission_decision_register(
        "m3-admission-audit", (rejected, admitted, candidate)
    )

    assert tuple(item.status for item in register.decisions) == (
        AdmissionStatus.CANDIDATE,
        AdmissionStatus.ADMITTED,
        AdmissionStatus.REJECTED,
    )
    assert admitted.as_empirical_reference().task == accepted_candidate.characteristics.task
    governed_member = EvaluationSuiteMembership(
        task=accepted_candidate.characteristics.task,
        task_qualification=accepted_candidate.task_qualification,
        admission_policy=policy.as_reference(),
        empirical_qualification=admitted.as_empirical_reference(),
    )
    governed_manifest = build_evaluation_suite_manifest(
        suite_id="synthetic-admitted-fixture",
        suite_version="1.0.0",
        purpose=SuitePurpose.DISCRIMINATIVE,
        memberships=(governed_member,),
    )
    assert governed_manifest.memberships == (governed_member,)


def test_exposure_events_are_immutable_append_only_and_deterministic() -> None:
    quality = _quality("core-python-deduplicate")
    lineage = task_lineage_from_quality(quality)
    original = _history("exposure-ledger")
    first = append_exposure_event(
        original,
        task_lineage=lineage,
        exposure_type=ExposureType.DEVELOPMENT_TASK_ACCESS,
        purpose=AccessPurpose.DEVELOPMENT,
        actor_identity=_digest("developer"),
    )
    repeated = append_exposure_event(
        original,
        task_lineage=lineage,
        exposure_type=ExposureType.DEVELOPMENT_TASK_ACCESS,
        purpose=AccessPurpose.DEVELOPMENT,
        actor_identity=_digest("developer"),
    )

    assert first == repeated
    assert original.events == ()
    assert first.events[0].previous_event_identity is None
    validate_exposure_history_extension(original, first)
    with pytest.raises(ValidationError, match="frozen"):
        first.events[0].sequence = 2  # type: ignore[misc]


def test_complete_exposure_coverage_requires_immutable_evidence() -> None:
    with pytest.raises(ExposureGovernanceError, match="requires immutable evidence"):
        build_exposure_history("unsupported-complete", coverage=ExposureCoverage.COMPLETE)
    quality = _quality("core-python-deduplicate")
    with pytest.raises(ExposureGovernanceError, match="type and purpose are inconsistent"):
        append_exposure_event(
            _history("mislabeled-development"),
            task_lineage=task_lineage_from_quality(quality),
            exposure_type=ExposureType.HOLDOUT_EVALUATION,
            purpose=AccessPurpose.DEVELOPMENT,
            actor_identity=_digest("developer"),
        )


def test_exposed_history_cannot_transition_back_to_unexposed() -> None:
    quality = _quality("core-python-deduplicate")
    lineage = task_lineage_from_quality(quality)
    empty = _history("irreversible")
    exposed = append_exposure_event(
        empty,
        task_lineage=lineage,
        exposure_type=ExposureType.DEVELOPMENT_LINEAGE_USE,
        purpose=AccessPurpose.DEVELOPMENT,
        actor_identity=_digest("developer"),
    )
    later = append_exposure_event(
        exposed,
        task_lineage=lineage,
        exposure_type=ExposureType.QUALIFICATION_AUDIT,
        purpose=AccessPurpose.QUALIFICATION_AUDIT,
        actor_identity=_digest("auditor"),
    )

    assert assess_exposure(lineage, empty).state is ExposureState.NOT_EXPOSED
    assert assess_exposure(lineage, exposed).state is ExposureState.EXPOSED
    assert assess_exposure(lineage, later).state is ExposureState.EXPOSED
    validate_exposure_history_extension(exposed, later)
    with pytest.raises(ExposureGovernanceError, match="predecessor digest"):
        validate_exposure_history_extension(empty, later)


def test_unknown_exposure_blocks_untouched_holdout_eligibility() -> None:
    _, _, _, held_out_quality, held_out_qualification, held_out_ref, split = _split_fixture()
    result = evaluate_holdout_eligibility(
        evaluation_id="unknown-exposure",
        namespace=GovernanceNamespace.OFFICIAL,
        qualification=held_out_qualification,
        claim_id="formal-claim",
        claim_context=HoldoutClaimContext.FORMAL_COMPARISON,
        split_reference=held_out_ref,
        split_freeze=split,
        visibility_policy=_sealed_policy(held_out_quality),
        exposure_history=_history("unknown-history", ExposureCoverage.UNKNOWN),
    )

    assert result.status is HoldoutEligibilityStatus.UNKNOWN_BLOCKED
    assert result.reason_codes == (HoldoutReasonCode.EXPOSURE_UNKNOWN,)


def test_same_task_cannot_be_development_and_untouched_holdout() -> None:
    development_quality, development_qualification, development_ref, *_, split = _split_fixture()
    result = evaluate_holdout_eligibility(
        evaluation_id="development-not-holdout",
        namespace=GovernanceNamespace.OFFICIAL,
        qualification=development_qualification,
        claim_id="release-claim",
        claim_context=HoldoutClaimContext.RELEASE_CLAIM,
        split_reference=development_ref,
        split_freeze=split,
        visibility_policy=_sealed_policy(development_quality),
        exposure_history=_history("development-history"),
    )

    assert result.status is HoldoutEligibilityStatus.INELIGIBLE
    assert HoldoutReasonCode.DEVELOPMENT_ASSIGNMENT in result.reason_codes


def test_unverified_or_stale_split_reference_blocks_holdout() -> None:
    _, _, _, held_out_quality, held_out_qualification, held_out_ref, split = _split_fixture()
    unverified = evaluate_holdout_eligibility(
        evaluation_id="unverified-split",
        namespace=GovernanceNamespace.OFFICIAL,
        qualification=held_out_qualification,
        claim_id="formal-claim",
        claim_context=HoldoutClaimContext.FORMAL_COMPARISON,
        split_reference=held_out_ref,
        split_freeze=None,
        visibility_policy=_sealed_policy(held_out_quality),
        exposure_history=_history("unverified-split-history"),
    )
    assert unverified.status is HoldoutEligibilityStatus.UNKNOWN_BLOCKED
    assert unverified.reason_codes == (HoldoutReasonCode.SPLIT_EVIDENCE_UNVERIFIED,)

    stale = held_out_ref.model_copy(update={"split_identity": _digest("stale-split")})
    with pytest.raises(HoldoutGovernanceError, match="stale or mismatched"):
        evaluate_holdout_eligibility(
            evaluation_id="stale-split",
            namespace=GovernanceNamespace.OFFICIAL,
            qualification=held_out_qualification,
            claim_id="formal-claim",
            claim_context=HoldoutClaimContext.FORMAL_COMPARISON,
            split_reference=stale,
            split_freeze=split,
            visibility_policy=_sealed_policy(held_out_quality),
            exposure_history=_history("stale-split-history"),
        )


def test_lineage_overlap_blocks_holdout() -> None:
    (
        development_quality,
        _,
        _,
        original_held_out_quality,
        _,
        held_out_ref,
        split,
    ) = _split_fixture()
    shared = _digest("shared-lineage")
    development_quality = development_quality.model_copy(
        update={
            "provenance": TaskProvenance(
                source_kind=TaskSourceKind.HARNESSLAB,
                source_identity=_digest("development-source"),
                parent_identities=(shared,),
            )
        }
    )
    held_out_quality = original_held_out_quality.model_copy(
        update={
            "provenance": TaskProvenance(
                source_kind=TaskSourceKind.HARNESSLAB,
                source_identity=_digest("holdout-source"),
                parent_identities=(shared,),
            )
        }
    )
    history = _history("lineage-overlap")
    history = append_exposure_event(
        history,
        task_lineage=task_lineage_from_quality(development_quality),
        exposure_type=ExposureType.DEVELOPMENT_LINEAGE_USE,
        purpose=AccessPurpose.DEVELOPMENT,
        actor_identity=_digest("developer"),
    )

    result = evaluate_holdout_eligibility(
        evaluation_id="lineage-block",
        namespace=GovernanceNamespace.OFFICIAL,
        qualification=_qualify(held_out_quality),
        claim_id="formal-claim",
        claim_context=HoldoutClaimContext.FORMAL_COMPARISON,
        split_reference=held_out_ref,
        split_freeze=split,
        visibility_policy=_sealed_policy(held_out_quality),
        exposure_history=history,
    )

    assert result.status is HoldoutEligibilityStatus.INELIGIBLE
    assert HoldoutReasonCode.LINEAGE_EXPOSURE_CONFIRMED in result.reason_codes


def test_version_bump_cannot_erase_exposure_of_the_same_task_family() -> None:
    old = _quality("core-python-deduplicate", "1.0.0")
    new = _quality("core-python-deduplicate", "1.0.1")
    history = append_exposure_event(
        _history("version-family"),
        task_lineage=task_lineage_from_quality(old),
        exposure_type=ExposureType.DEVELOPMENT_TASK_ACCESS,
        purpose=AccessPurpose.DEVELOPMENT,
        actor_identity=_digest("developer"),
    )

    assessment = assess_exposure(task_lineage_from_quality(new), history)

    assert assessment.state is ExposureState.EXPOSED
    assert assessment.match_kinds[0].value == "EXACT_TASK_OR_VERSION_FAMILY"


def test_existing_core_tasks_resolve_as_exposed_development_not_holdout() -> None:
    corpus = load_core_corpus(ROOT / "release/core-corpus-v4.json")
    history = core_development_exposure_history(ROOT, corpus)

    assert len(history.events) == 18
    for event in history.events:
        assert event.exposure_type is ExposureType.HISTORICAL_CORE_DEVELOPMENT
        assert assess_exposure(event.task_lineage, history).state is ExposureState.EXPOSED

    first_quality = _quality(corpus.tasks[0].task_id, corpus.tasks[0].version)
    result = evaluate_holdout_eligibility(
        evaluation_id="core-is-development",
        namespace=GovernanceNamespace.OFFICIAL,
        qualification=_qualify(first_quality),
        claim_id="untouched-core-claim",
        claim_context=HoldoutClaimContext.RELEASE_CLAIM,
        split_reference=None,
        split_freeze=None,
        visibility_policy=build_visibility_policy(
            policy_id="core-development-visibility",
            policy_version="1.0.0",
            namespace=GovernanceNamespace.OFFICIAL,
            task_lineage=task_lineage_from_quality(first_quality),
            visibility=AssetVisibility.DEVELOPMENT,
            allowed_purposes=(AccessPurpose.DEVELOPMENT,),
        ),
        exposure_history=history,
    )
    assert result.status is HoldoutEligibilityStatus.INELIGIBLE
    assert HoldoutReasonCode.DEVELOPMENT_EXPOSURE_CONFIRMED in result.reason_codes


def test_no_tier_b_task_is_automatically_promoted_to_stress() -> None:
    policy = _stress_policy()
    quality, candidate = _candidate(
        "repo-python-ledger-transfer",
        difficulty=DifficultyBand.ADVANCED,
        stress_dimensions=(StressDimension.MULTI_FILE, StressDimension.REPAIR_LOOP),
    )
    manifest = _suite(SuitePurpose.STRESS)
    candidate_record = build_admission_decision(
        decision_id="tier-b-candidate-only",
        status=AdmissionStatus.CANDIDATE,
        candidate=candidate,
        target_suite=manifest.as_reference(),
        policy=policy,
    )

    assert quality.benchmark_tier is BenchmarkTier.TIER_B
    assert manifest.memberships == ()
    assert candidate_record.status is AdmissionStatus.CANDIDATE


def test_difficulty_quality_suite_and_exposure_are_independent_axes() -> None:
    quality, candidate = _candidate(
        difficulty=DifficultyBand.ADVANCED,
        stress_dimensions=(StressDimension.LONG_TRAJECTORY,),
    )
    history = _history("independent-axes", ExposureCoverage.UNKNOWN)
    decision = build_admission_decision(
        decision_id="independent-candidate",
        status=AdmissionStatus.CANDIDATE,
        candidate=candidate,
        target_suite=_suite(SuitePurpose.STRESS).as_reference(),
        policy=_stress_policy(),
    )

    assert quality.benchmark_tier is BenchmarkTier.TIER_A
    assert candidate.characteristics.difficulty is DifficultyBand.ADVANCED
    assert decision.target_suite.purpose is SuitePurpose.STRESS
    assert decision.status is AdmissionStatus.CANDIDATE
    assert (
        assess_exposure(task_lineage_from_quality(quality), history).state is ExposureState.UNKNOWN
    )


def test_malformed_and_stale_digest_references_fail_closed(tmp_path: Path) -> None:
    policy = _discriminative_policy()
    raw = policy.model_dump(mode="json")
    raw["candidate_requirements"]["configuration_neutral"] = False
    path = tmp_path / "tampered-policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(GovernanceArtifactError, match="invalid admission policy"):
        load_admission_policy(path)

    _, candidate = _candidate()
    suite = _suite(SuitePurpose.DISCRIMINATIVE)
    decision = build_admission_decision(
        decision_id="stale-policy-decision",
        status=AdmissionStatus.CANDIDATE,
        candidate=candidate,
        target_suite=suite.as_reference(),
        policy=policy,
    )
    fake_policy_reference = VersionedPolicyReference(
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        policy_digest=_digest("stale-policy"),
    )
    forged_payload = decision.payload()
    forged_payload["admission_policy"] = fake_policy_reference.model_dump(mode="json")
    forged_payload["decision_digest"] = canonical_digest(forged_payload)
    forged = AdmissionDecision.model_validate(forged_payload)
    with pytest.raises(AdmissionGovernanceError, match="policy identity"):
        validate_admission_decision(forged, policy=policy, target_suite=suite.as_reference())


def test_visibility_boundary_denies_development_and_records_allowed_access() -> None:
    _, _, _, held_out_quality, held_out_qualification, held_out_ref, split = _split_fixture()
    policy = _sealed_policy(held_out_quality)
    denied = evaluate_access(
        request_id="development-access",
        task=held_out_quality.task,
        purpose=AccessPurpose.DEVELOPMENT,
        actor_identity=_digest("developer"),
        policy=policy,
    )
    allowed = evaluate_access(
        request_id="holdout-access",
        task=held_out_quality.task,
        purpose=AccessPurpose.HOLDOUT_EVALUATION,
        actor_identity=_digest("holdout-runner"),
        policy=policy,
    )
    history = _history("access-ledger")

    assert denied.status is AccessStatus.DENIED
    assert allowed.status is AccessStatus.ALLOWED
    validate_access_decision(allowed, policy)
    forged_allowed = denied.model_copy(
        update={
            "status": AccessStatus.ALLOWED,
            "decision_digest": _digest("forged-access"),
        }
    )
    with pytest.raises(ExposureGovernanceError, match="stale or inconsistent"):
        validate_access_decision(forged_allowed, policy)
    with pytest.raises(ExposureGovernanceError, match="denied access"):
        record_allowed_access(history, decision=denied, policy=policy)
    recorded = record_allowed_access(history, decision=allowed, policy=policy)
    assert assess_exposure(task_lineage_from_quality(held_out_quality), recorded).state is (
        ExposureState.NOT_EXPOSED
    )
    eligible = evaluate_holdout_eligibility(
        evaluation_id="allowed-holdout",
        namespace=GovernanceNamespace.OFFICIAL,
        qualification=held_out_qualification,
        claim_id="formal-claim",
        claim_context=HoldoutClaimContext.FORMAL_COMPARISON,
        split_reference=held_out_ref,
        split_freeze=split,
        visibility_policy=policy,
        exposure_history=recorded,
    )
    assert eligible.status is HoldoutEligibilityStatus.ELIGIBLE


def test_official_custom_isolation_fails_closed() -> None:
    package = TaskPackage.load(ROOT / "tasks/core-python-deduplicate/1.0.0")
    custom_quality = TaskQualityMetadata.from_package(
        package,
        source_kind=TaskSourceKind.CUSTOM,
        source_identity=_digest("custom-source"),
    )
    characteristics = build_task_characteristics(custom_quality)
    candidate = build_admission_candidate(characteristics)
    policy = _discriminative_policy()
    suite = _suite(SuitePurpose.DISCRIMINATIVE)
    with pytest.raises(AdmissionGovernanceError, match="Custom/imported"):
        build_admission_decision(
            decision_id="custom-candidate",
            status=AdmissionStatus.CANDIDATE,
            candidate=candidate,
            target_suite=suite.as_reference(),
            policy=policy,
        )


def test_governance_artifacts_serialize_only_allowlisted_metadata() -> None:
    quality = _quality("core-python-deduplicate")
    lineage = task_lineage_from_quality(quality)
    history = append_exposure_event(
        _history("redacted-ledger"),
        task_lineage=lineage,
        exposure_type=ExposureType.HIDDEN_ASSET_ACCESS,
        purpose=AccessPurpose.DEVELOPMENT,
        actor_identity=_digest("actor"),
        source_identity=_digest("source"),
    )
    serialized = history.canonical_json()

    assert "gold solution body" not in serialized
    assert "api-key-secret" not in serialized
    assert "package_path" not in serialized
    assert "workspace_path" not in serialized
    assert "verifier/verify.py" not in serialized
    assert "HIDDEN_ASSET_ACCESS" in serialized


def test_governance_artifact_round_trips_preserve_exact_identities(tmp_path: Path) -> None:
    _, _, _, held_out_quality, held_out_qualification, held_out_ref, split = _split_fixture()
    policy = _discriminative_policy()
    _, candidate = _candidate()
    decision = build_admission_decision(
        decision_id="round-trip-candidate",
        status=AdmissionStatus.CANDIDATE,
        candidate=candidate,
        target_suite=_suite(SuitePurpose.DISCRIMINATIVE).as_reference(),
        policy=policy,
    )
    history = _history("round-trip-history")
    visibility = _sealed_policy(held_out_quality)
    eligibility = evaluate_holdout_eligibility(
        evaluation_id="round-trip-eligibility",
        namespace=GovernanceNamespace.OFFICIAL,
        qualification=held_out_qualification,
        claim_id="round-trip-claim",
        claim_context=HoldoutClaimContext.FORMAL_COMPARISON,
        split_reference=held_out_ref,
        split_freeze=split,
        visibility_policy=visibility,
        exposure_history=history,
    )
    artifacts = {
        "policy.json": (policy.canonical_json(), load_admission_policy, policy),
        "decision.json": (decision.canonical_json(), load_admission_decision, decision),
        "history.json": (history.canonical_json(), load_exposure_history, history),
        "visibility.json": (
            json.dumps(visibility.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
            load_visibility_policy,
            visibility,
        ),
        "eligibility.json": (
            eligibility.canonical_json(),
            load_holdout_eligibility,
            eligibility,
        ),
    }
    for filename, (serialized, loader, expected) in artifacts.items():
        path = tmp_path / filename
        path.write_text(serialized, encoding="utf-8")
        assert loader(path) == expected


def test_unqualified_task_is_ineligible_not_silently_promoted() -> None:
    _, _, _, held_out_quality, _, held_out_ref, split = _split_fixture()
    result = evaluate_holdout_eligibility(
        evaluation_id="unqualified-holdout",
        namespace=GovernanceNamespace.OFFICIAL,
        qualification=unqualified_task(held_out_quality),
        claim_id="formal-claim",
        claim_context=HoldoutClaimContext.FORMAL_COMPARISON,
        split_reference=held_out_ref,
        split_freeze=split,
        visibility_policy=_sealed_policy(held_out_quality),
        exposure_history=_history("unqualified-history"),
    )

    assert result.status is HoldoutEligibilityStatus.INELIGIBLE
    assert HoldoutReasonCode.TASK_UNQUALIFIED in result.reason_codes


def test_task_lineage_reference_rejects_duplicate_or_noncanonical_identity() -> None:
    quality = _quality("core-python-deduplicate")
    lineage = task_lineage_from_quality(quality)
    with pytest.raises(ValidationError, match="unique and canonical"):
        TaskLineageReference(
            task=lineage.task,
            quality_identity=lineage.quality_identity,
            source_kind=lineage.source_kind,
            lineage_identities=(lineage.lineage_identities[0], lineage.lineage_identities[0]),
        )
