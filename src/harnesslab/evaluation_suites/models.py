from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.tasks.quality import TaskIdentity
from harnesslab.tasks.splits import DevelopmentExposure, SplitRole


class SuitePurpose(StrEnum):
    CORE = "CORE"
    DISCRIMINATIVE = "DISCRIMINATIVE"
    STRESS = "STRESS"


class ImmutableArtifactReference(BaseModel):
    """An opaque immutable artifact identity; it carries no qualification semantics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: Identifier
    schema_version: int = Field(ge=1)
    artifact_digest: Sha256Digest


class VersionedPolicyReference(BaseModel):
    """Reference slot for a future admission policy without implementing that policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: Identifier
    policy_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    policy_digest: Sha256Digest


class TaskArtifactReference(BaseModel):
    """Bind an immutable source or evidence artifact to one exact task identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: TaskIdentity
    artifact: ImmutableArtifactReference


class TaskQualificationReference(BaseModel):
    """Digest-bound reference derived from an existing qualified TaskQualification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: TaskIdentity
    qualification_id: Identifier
    qualification_identity: Sha256Digest
    quality_identity: Sha256Digest


class TaskSplitReference(BaseModel):
    """Exact assignment reference derived from an existing valid TaskSplitFreeze."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: TaskIdentity
    split_id: Identifier
    split_identity: Sha256Digest
    methodology_id: Identifier
    role: SplitRole
    development_exposure: DevelopmentExposure
    assignment_identity: Sha256Digest


class EvaluationSuiteMembership(BaseModel):
    """One explicitly declared suite member and its immutable sidecar references.

    Task qualification is the existing package-quality qualification. It is not
    Discriminative or Stress admission evidence. Likewise, membership by itself
    never claims empirical qualification; that claim requires the dedicated
    ``empirical_qualification`` reference and an admission policy reference.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: TaskIdentity
    source: TaskArtifactReference | None = None
    task_qualification: TaskQualificationReference | None = None
    split: TaskSplitReference | None = None
    admission_policy: VersionedPolicyReference | None = None
    empirical_qualification: TaskArtifactReference | None = None

    @model_validator(mode="after")
    def references_bind_the_same_task(self) -> EvaluationSuiteMembership:
        if self.source is not None and self.source.task != self.task:
            raise ValueError("source reference does not bind the member task")
        if self.task_qualification is not None and self.task_qualification.task != self.task:
            raise ValueError("task qualification reference does not bind the member task")
        if self.split is not None and self.split.task != self.task:
            raise ValueError("split reference does not bind the member task")
        if (
            self.empirical_qualification is not None
            and self.empirical_qualification.task != self.task
        ):
            raise ValueError("empirical qualification reference does not bind the member task")
        if self.empirical_qualification is not None and self.admission_policy is None:
            raise ValueError("empirical qualification requires an admission policy reference")
        return self

    @property
    def membership_identity(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class SuiteManifestReference(BaseModel):
    """The complete immutable identity needed to supersede a suite manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suite_id: Identifier
    suite_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    purpose: SuitePurpose
    manifest_digest: Sha256Digest


def _version_key(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def _membership_key(membership: EvaluationSuiteMembership) -> tuple[str, str, str]:
    task = membership.task
    return task.task_id, task.task_version, task.task_digest


class EvaluationSuiteManifest(BaseModel):
    """Canonical, timestamp-free sidecar describing one versioned suite population."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    suite_id: Identifier
    suite_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    purpose: SuitePurpose
    memberships: tuple[EvaluationSuiteMembership, ...] = ()
    supersedes: SuiteManifestReference | None = None
    manifest_digest: Sha256Digest

    @model_validator(mode="after")
    def manifest_is_canonical_and_self_consistent(self) -> EvaluationSuiteManifest:
        ordered = tuple(sorted(self.memberships, key=_membership_key))
        if self.memberships != ordered:
            raise ValueError("suite memberships must use canonical task identity order")

        seen: dict[str, EvaluationSuiteMembership] = {}
        for membership in self.memberships:
            existing = seen.get(membership.task.task_id)
            if existing is None:
                seen[membership.task.task_id] = membership
            elif existing == membership:
                raise ValueError("duplicate exact suite membership")
            else:
                raise ValueError("conflicting suite membership for the same task id")

        if self.purpose is SuitePurpose.CORE and any(
            membership.empirical_qualification is not None for membership in self.memberships
        ):
            raise ValueError("Core membership cannot claim empirical suite qualification")

        if self.supersedes is not None:
            if self.supersedes.suite_id != self.suite_id:
                raise ValueError("superseded manifest must have the same suite id")
            if self.supersedes.purpose is not self.purpose:
                raise ValueError("superseded manifest must have the same suite purpose")
            if _version_key(self.supersedes.suite_version) >= _version_key(self.suite_version):
                raise ValueError("superseded manifest version must precede the new version")
            if self.supersedes.manifest_digest == self.manifest_digest:
                raise ValueError("a suite manifest cannot supersede its own identity")

        if self.manifest_digest != canonical_digest(self.payload()):
            raise ValueError("suite manifest digest does not match its canonical payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"manifest_digest"})

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def identity(self) -> str:
        return self.manifest_digest

    def as_reference(self) -> SuiteManifestReference:
        return SuiteManifestReference(
            suite_id=self.suite_id,
            suite_version=self.suite_version,
            purpose=self.purpose,
            manifest_digest=self.manifest_digest,
        )
