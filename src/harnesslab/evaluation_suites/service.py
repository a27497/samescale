from __future__ import annotations

from collections.abc import Iterable

from harnesslab.comparability.models import canonical_digest
from harnesslab.evaluation_suites.models import (
    EvaluationSuiteManifest,
    EvaluationSuiteMembership,
    ImmutableArtifactReference,
    SuiteManifestReference,
    SuitePurpose,
    TaskArtifactReference,
    TaskQualificationReference,
    TaskSplitReference,
)
from harnesslab.release.models import CoreCorpusManifest
from harnesslab.tasks.quality import QualificationStatus, TaskIdentity, TaskQualification
from harnesslab.tasks.splits import TaskSplitAssignment, TaskSplitFreeze


class EvaluationSuiteError(ValueError):
    """A suite manifest or one of its immutable references is inconsistent."""


def build_evaluation_suite_manifest(
    *,
    suite_id: str,
    suite_version: str,
    purpose: SuitePurpose,
    memberships: Iterable[EvaluationSuiteMembership] = (),
    supersedes: SuiteManifestReference | None = None,
) -> EvaluationSuiteManifest:
    """Build the canonical semantic manifest for explicitly supplied memberships only."""

    ordered = tuple(
        sorted(
            memberships,
            key=lambda item: (
                item.task.task_id,
                item.task.task_version,
                item.task.task_digest,
            ),
        )
    )
    payload = {
        "schema_version": 1,
        "suite_id": suite_id,
        "suite_version": suite_version,
        "purpose": purpose.value,
        "memberships": [item.model_dump(mode="json") for item in ordered],
        "supersedes": None if supersedes is None else supersedes.model_dump(mode="json"),
    }
    payload["manifest_digest"] = canonical_digest(payload)
    try:
        return EvaluationSuiteManifest.model_validate(payload)
    except ValueError as exc:
        raise EvaluationSuiteError(str(exc)) from exc


def reference_task_qualification(
    task: TaskIdentity, qualification: TaskQualification
) -> TaskQualificationReference:
    """Validate and reduce an existing task qualification to its immutable reference."""

    if qualification.status is not QualificationStatus.QUALIFIED:
        raise EvaluationSuiteError("suite references require a qualified task qualification")
    if qualification.quality.task != task:
        raise EvaluationSuiteError("task qualification does not match the member task")
    if qualification.qualification_id is None:  # Defensive against unvalidated construction.
        raise EvaluationSuiteError("qualified task qualification is missing its id")
    return TaskQualificationReference(
        task=task,
        qualification_id=qualification.qualification_id,
        qualification_identity=qualification.qualification_identity,
        quality_identity=qualification.quality.quality_identity,
    )


def reference_task_split(
    task: TaskIdentity,
    split: TaskSplitFreeze,
    assignment: TaskSplitAssignment,
) -> TaskSplitReference:
    """Reference an exact assignment proven to be present in a valid split freeze."""

    if assignment.qualification.quality.task != task:
        raise EvaluationSuiteError("split assignment does not match the member task")
    if assignment not in split.assignments:
        raise EvaluationSuiteError("split assignment is not present in the referenced split")
    return TaskSplitReference(
        task=task,
        split_id=split.split_id,
        split_identity=split.split_identity,
        methodology_id=split.methodology_id,
        role=assignment.role,
        development_exposure=assignment.development_exposure,
        assignment_identity=canonical_digest(assignment.model_dump(mode="json")),
    )


def memberships_from_core_corpus(
    corpus: CoreCorpusManifest,
) -> tuple[EvaluationSuiteMembership, ...]:
    """Adapt historical Core identities without changing or reinterpreting that artifact."""

    source_artifact = ImmutableArtifactReference(
        artifact_id=corpus.corpus_id,
        schema_version=corpus.schema_version,
        artifact_digest=corpus.digest,
    )
    memberships: list[EvaluationSuiteMembership] = []
    for item in corpus.tasks:
        task = TaskIdentity(
            task_id=item.task_id,
            task_version=item.version,
            task_digest=item.task_digest,
            workspace_digest=item.workspace_input_identity,
            verifier_digest=item.verifier_identity,
        )
        memberships.append(
            EvaluationSuiteMembership(
                task=task,
                source=TaskArtifactReference(task=task, artifact=source_artifact),
            )
        )
    return tuple(memberships)


def validate_supersession(
    manifest: EvaluationSuiteManifest, predecessor: EvaluationSuiteManifest
) -> None:
    """Verify an explicit supersession reference when both immutable manifests are available."""

    if manifest.supersedes is None:
        raise EvaluationSuiteError("suite manifest has no explicit supersession reference")
    if manifest.supersedes != predecessor.as_reference():
        raise EvaluationSuiteError("supersession reference does not match the predecessor manifest")
