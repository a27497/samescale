from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from harnesslab.comparability.models import canonical_digest
from harnesslab.evaluation_suites import (
    EvaluationSuiteError,
    EvaluationSuiteManifest,
    EvaluationSuiteMembership,
    ImmutableArtifactReference,
    SuitePurpose,
    TaskArtifactReference,
    VersionedPolicyReference,
    build_evaluation_suite_manifest,
    load_evaluation_suite_manifest,
    memberships_from_core_corpus,
    reference_task_qualification,
    reference_task_split,
    validate_supersession,
)
from harnesslab.release.contracts import load_core_corpus
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.quality import (
    BenchmarkTier,
    QualificationCheck,
    QualificationEvidence,
    TaskIdentity,
    TaskQualification,
    TaskQualityMetadata,
    qualify_task,
    unqualified_task,
)
from harnesslab.tasks.splits import (
    DevelopmentExposure,
    SplitRole,
    TaskSplitAssignment,
    freeze_split,
)
from harnesslab.tasks.tier_b import load_tier_b_qualification

ROOT = Path(__file__).resolve().parents[1]


def _digest(label: str) -> str:
    return canonical_digest({"evaluation-suite-test": label})


def _task(task_id: str, version: str = "1.0.0", *, variant: str = "original") -> TaskIdentity:
    return TaskIdentity(
        task_id=task_id,
        task_version=version,
        task_digest=_digest(f"{task_id}:{version}:{variant}:task"),
        workspace_digest=_digest(f"{task_id}:{version}:{variant}:workspace"),
        verifier_digest=_digest(f"{task_id}:{version}:{variant}:verifier"),
    )


def _membership(task_id: str, *, variant: str = "original") -> EvaluationSuiteMembership:
    return EvaluationSuiteMembership(task=_task(task_id, variant=variant))


def _manifest(
    *,
    suite_version: str = "1.0.0",
    purpose: SuitePurpose = SuitePurpose.CORE,
    memberships: tuple[EvaluationSuiteMembership, ...] | None = None,
    supersedes: EvaluationSuiteManifest | None = None,
) -> EvaluationSuiteManifest:
    return build_evaluation_suite_manifest(
        suite_id="test-suite",
        suite_version=suite_version,
        purpose=purpose,
        memberships=memberships if memberships is not None else (_membership("task-a"),),
        supersedes=None if supersedes is None else supersedes.as_reference(),
    )


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


def _qualified_package(task_id: str) -> tuple[TaskQualityMetadata, TaskQualification]:
    package = TaskPackage.load(ROOT / "tasks" / task_id / "1.0.0")
    quality = TaskQualityMetadata.from_package(package)
    qualification = qualify_task(
        quality,
        qualification_id=f"qualification-{task_id}",
        evidence=_qualification_evidence(quality.benchmark_tier, task_id),
    )
    return quality, qualification


def test_valid_manifest_construction_and_canonical_digest_stability() -> None:
    first = _manifest()
    second = _manifest()

    assert first == second
    assert first.identity == first.manifest_digest == canonical_digest(first.payload())
    assert first.purpose is SuitePurpose.CORE
    assert first.schema_version == 1


def test_serialize_load_round_trip_preserves_identity(tmp_path: Path) -> None:
    manifest = _manifest()
    path = tmp_path / "suite.json"
    path.write_text(manifest.canonical_json(), encoding="utf-8")

    loaded = load_evaluation_suite_manifest(path)

    assert loaded == manifest
    assert loaded.identity == manifest.identity
    assert loaded.canonical_json() == manifest.canonical_json()


def test_reordered_input_has_the_same_semantic_manifest() -> None:
    task_a = _membership("task-a")
    task_b = _membership("task-b")

    first = _manifest(memberships=(task_b, task_a))
    second = _manifest(memberships=(task_a, task_b))

    assert first == second
    assert tuple(item.task.task_id for item in first.memberships) == ("task-a", "task-b")

    noncanonical = first.payload()
    noncanonical["memberships"] = list(reversed(noncanonical["memberships"]))
    noncanonical["manifest_digest"] = canonical_digest(noncanonical)
    with pytest.raises(ValidationError, match="canonical task identity order"):
        EvaluationSuiteManifest.model_validate(noncanonical)


def test_duplicate_exact_membership_is_rejected() -> None:
    member = _membership("task-a")

    with pytest.raises(EvaluationSuiteError, match="duplicate exact"):
        _manifest(memberships=(member, member))


def test_conflicting_membership_is_rejected() -> None:
    first = _membership("task-a")
    conflicting = _membership("task-a", variant="different-content")

    with pytest.raises(EvaluationSuiteError, match="conflicting"):
        _manifest(memberships=(first, conflicting))


def test_malformed_identities_are_rejected() -> None:
    with pytest.raises(ValidationError, match="task_digest"):
        TaskIdentity(
            task_id="task-a",
            task_version="1.0.0",
            task_digest="not-a-digest",
            workspace_digest=_digest("workspace"),
            verifier_digest=_digest("verifier"),
        )
    with pytest.raises(EvaluationSuiteError, match="suite_version"):
        build_evaluation_suite_manifest(
            suite_id="test-suite",
            suite_version="latest",
            purpose=SuitePurpose.CORE,
        )


def test_unknown_fields_are_rejected_at_every_loaded_level(tmp_path: Path) -> None:
    raw = json.loads(_manifest().canonical_json())
    raw["memberships"][0]["task"]["historical_participation"] = True
    raw["manifest_digest"] = canonical_digest(
        {key: value for key, value in raw.items() if key != "manifest_digest"}
    )
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(EvaluationSuiteError, match="invalid evaluation suite manifest"):
        load_evaluation_suite_manifest(path)


def test_supersession_is_explicit_digest_bound_and_immutable() -> None:
    predecessor = _manifest(suite_version="1.0.0")
    successor = _manifest(suite_version="1.1.0", supersedes=predecessor)

    assert successor.supersedes == predecessor.as_reference()
    validate_supersession(successor, predecessor)
    with pytest.raises(ValidationError, match="frozen"):
        successor.suite_version = "2.0.0"  # type: ignore[misc]


def test_invalid_supersession_and_reference_states_are_rejected() -> None:
    predecessor = _manifest(suite_version="1.0.0")
    other = build_evaluation_suite_manifest(
        suite_id="other-suite",
        suite_version="0.9.0",
        purpose=SuitePurpose.CORE,
    )
    with pytest.raises(EvaluationSuiteError, match="same suite id"):
        build_evaluation_suite_manifest(
            suite_id="test-suite",
            suite_version="1.1.0",
            purpose=SuitePurpose.CORE,
            supersedes=other.as_reference(),
        )
    with pytest.raises(EvaluationSuiteError, match="must precede"):
        build_evaluation_suite_manifest(
            suite_id="test-suite",
            suite_version="1.0.0",
            purpose=SuitePurpose.CORE,
            supersedes=predecessor.as_reference(),
        )

    unrelated_predecessor = _manifest(suite_version="0.9.0", memberships=())
    with pytest.raises(EvaluationSuiteError, match="does not match"):
        validate_supersession(
            _manifest(suite_version="1.1.0", supersedes=predecessor),
            unrelated_predecessor,
        )


def test_existing_qualification_and_split_validators_are_reused() -> None:
    development_quality, development_qualification = _qualified_package("core-python-deduplicate")
    held_out_quality, held_out_qualification = _qualified_package("core-python-feature-flag")
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
    split = freeze_split("suite-fixture-split", (held_out, development))
    task = development_quality.task

    qualification_ref = reference_task_qualification(task, development_qualification)
    split_ref = reference_task_split(task, split, development)
    member = EvaluationSuiteMembership(
        task=task,
        task_qualification=qualification_ref,
        split=split_ref,
    )

    assert member.task_qualification is not None
    assert member.split is not None
    with pytest.raises(EvaluationSuiteError, match="qualified task qualification"):
        reference_task_qualification(task, unqualified_task(held_out_quality))
    with pytest.raises(ValidationError, match="does not bind"):
        EvaluationSuiteMembership(task=held_out_quality.task, split=split_ref)


def test_current_core_identities_are_referenced_without_rewriting_corpus() -> None:
    corpus_path = ROOT / "release/core-corpus-v4.json"
    before = corpus_path.read_bytes()
    corpus = load_core_corpus(corpus_path)

    memberships = memberships_from_core_corpus(corpus)
    manifest = build_evaluation_suite_manifest(
        suite_id="harnesslab-core-evaluation-suite",
        suite_version="1.0.0",
        purpose=SuitePurpose.CORE,
        memberships=reversed(memberships),
    )

    assert len(manifest.memberships) == 18
    assert {item.task.task_id for item in manifest.memberships} == {
        item.task_id for item in corpus.tasks
    }
    assert all(item.source is not None for item in manifest.memberships)
    assert all(item.task_qualification is None for item in manifest.memberships)
    assert corpus_path.read_bytes() == before


def test_tier_b_qualification_does_not_automatically_create_stress_membership() -> None:
    qualification = load_tier_b_qualification(ROOT / "release/tier-b-qualification-v1.json")

    manifest = build_evaluation_suite_manifest(
        suite_id="harnesslab-stress-suite",
        suite_version="1.0.0",
        purpose=SuitePurpose.STRESS,
    )

    assert qualification.task_count > 0
    assert manifest.memberships == ()


def test_historical_matrix_evidence_does_not_create_discriminative_membership() -> None:
    matrix = json.loads((ROOT / "release/core-real-matrix-v6-final-analysis.json").read_text())

    manifest = build_evaluation_suite_manifest(
        suite_id="harnesslab-discriminative-suite",
        suite_version="1.0.0",
        purpose=SuitePurpose.DISCRIMINATIVE,
    )

    assert matrix
    assert manifest.memberships == ()


@pytest.mark.parametrize("purpose", [SuitePurpose.DISCRIMINATIVE, SuitePurpose.STRESS])
def test_synthetic_membership_does_not_imply_empirical_qualification(
    purpose: SuitePurpose,
) -> None:
    member = _membership("synthetic-task")
    manifest = _manifest(purpose=purpose, memberships=(member,))

    assert manifest.memberships[0].empirical_qualification is None
    assert manifest.memberships[0].admission_policy is None

    evidence = TaskArtifactReference(
        task=member.task,
        artifact=ImmutableArtifactReference(
            artifact_id="empirical-evidence",
            schema_version=1,
            artifact_digest=_digest("empirical-evidence"),
        ),
    )
    with pytest.raises(ValidationError, match="requires an admission policy"):
        EvaluationSuiteMembership.model_validate(
            {**member.model_dump(mode="json"), "empirical_qualification": evidence}
        )


def test_empirical_reference_requires_explicit_versioned_policy() -> None:
    task = _task("qualified-task")
    evidence = TaskArtifactReference(
        task=task,
        artifact=ImmutableArtifactReference(
            artifact_id="suite-qualification",
            schema_version=1,
            artifact_digest=_digest("suite-qualification"),
        ),
    )
    policy = VersionedPolicyReference(
        policy_id="discriminative-admission-policy",
        policy_version="1.0.0",
        policy_digest=_digest("admission-policy"),
    )

    member = EvaluationSuiteMembership(
        task=task,
        admission_policy=policy,
        empirical_qualification=evidence,
    )

    assert member.empirical_qualification == evidence
    assert member.admission_policy == policy
    with pytest.raises(ValidationError, match="does not bind"):
        EvaluationSuiteMembership(
            task=_task("different-task"),
            admission_policy=policy,
            empirical_qualification=evidence,
        )


def test_frozen_release_artifacts_remain_byte_identical() -> None:
    expected = {
        "release/core-corpus-v4.json": (
            "8fdf26537cb897603af0bae98092fb29d4927bc0f9a0dfb45cea86760f90642d"
        ),
        "release/tier-b-qualification-v1.json": (
            "7536ca2e7d0d93665c540d05233e63149aabcfb7291b4521d2fe42763b38daf7"
        ),
        "release/core-real-matrix-v6-final-analysis.json": (
            "59b4e083c54d2d4a3bb1dfd2ad59129c45db81543f5cc5ae51de18a927590252"
        ),
    }

    assert {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in expected
    } == expected
