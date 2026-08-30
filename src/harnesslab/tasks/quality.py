from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.tasks.package import TaskPackage


class TaskQualityError(ValueError):
    """Task quality metadata or qualification evidence is inconsistent."""


class TaskFamily(StrEnum):
    CORE = "CORE"
    REPO_ENGINEERING = "REPO_ENGINEERING"
    IMPORTED = "IMPORTED"
    CUSTOM = "CUSTOM"


class BenchmarkTier(StrEnum):
    TIER_A = "TIER_A"
    TIER_B = "TIER_B"
    UNASSIGNED = "UNASSIGNED"


class TaskSourceKind(StrEnum):
    HARNESSLAB = "HARNESSLAB"
    IMPORTED = "IMPORTED"
    CUSTOM = "CUSTOM"


class QualificationStatus(StrEnum):
    QUALIFIED = "QUALIFIED"
    NOT_QUALIFIED = "NOT_QUALIFIED"


class QualificationCheck(StrEnum):
    PACKAGE_VALID = "PACKAGE_VALID"
    BASELINE_FAILS = "BASELINE_FAILS"
    ORACLE_PASSES = "ORACLE_PASSES"
    DETERMINISTIC_HEALTH = "DETERMINISTIC_HEALTH"
    FROZEN_REPOSITORY_SNAPSHOT = "FROZEN_REPOSITORY_SNAPSHOT"
    WORKSPACE_ISOLATION = "WORKSPACE_ISOLATION"
    HIDDEN_ASSETS_ISOLATED = "HIDDEN_ASSETS_ISOLATED"
    ROBUSTNESS_VARIANTS_FAIL = "ROBUSTNESS_VARIANTS_FAIL"
    FAILURE_BOUNDARIES_VALID = "FAILURE_BOUNDARIES_VALID"


_TIER_A_CHECKS = frozenset(
    {
        QualificationCheck.PACKAGE_VALID,
        QualificationCheck.BASELINE_FAILS,
        QualificationCheck.ORACLE_PASSES,
        QualificationCheck.DETERMINISTIC_HEALTH,
    }
)
_TIER_B_CHECKS = _TIER_A_CHECKS | {
    QualificationCheck.FROZEN_REPOSITORY_SNAPSHOT,
    QualificationCheck.WORKSPACE_ISOLATION,
    QualificationCheck.HIDDEN_ASSETS_ISOLATED,
    QualificationCheck.ROBUSTNESS_VARIANTS_FAIL,
    QualificationCheck.FAILURE_BOUNDARIES_VALID,
}


class TaskIdentity(BaseModel):
    """The existing package identity, copied rather than reinterpreted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: Identifier
    task_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    task_digest: Sha256Digest
    workspace_digest: Sha256Digest
    verifier_digest: Sha256Digest

    @classmethod
    def from_package(cls, package: TaskPackage) -> TaskIdentity:
        return cls(
            task_id=package.definition.id,
            task_version=package.definition.version,
            task_digest=package.definition.content_digest,
            workspace_digest=package.definition.workspace.digest,
            verifier_digest=package.verifier_digest,
        )


class TaskProvenance(BaseModel):
    """Digest-bound source and derivation lineage used for leakage checks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_kind: TaskSourceKind
    source_identity: Sha256Digest
    source_revision: str | None = Field(default=None, min_length=1, max_length=300)
    parent_identities: tuple[Sha256Digest, ...] = ()

    @field_validator("parent_identities")
    @classmethod
    def parent_identities_are_canonical(
        cls, values: tuple[Sha256Digest, ...]
    ) -> tuple[Sha256Digest, ...]:
        if tuple(sorted(set(values))) != values:
            raise ValueError("parent identities must be unique and in canonical order")
        return values

    @property
    def lineage_identities(self) -> frozenset[str]:
        return frozenset((self.source_identity, *self.parent_identities))


class TaskQualityMetadata(BaseModel):
    """Quality category and provenance kept outside immutable task packages."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    task: TaskIdentity
    family: TaskFamily
    benchmark_tier: BenchmarkTier
    provenance: TaskProvenance

    @model_validator(mode="after")
    def category_is_coherent(self) -> TaskQualityMetadata:
        expected = {
            TaskFamily.CORE: (BenchmarkTier.TIER_A, TaskSourceKind.HARNESSLAB),
            TaskFamily.REPO_ENGINEERING: (
                BenchmarkTier.TIER_B,
                TaskSourceKind.HARNESSLAB,
            ),
            TaskFamily.IMPORTED: (BenchmarkTier.UNASSIGNED, TaskSourceKind.IMPORTED),
            TaskFamily.CUSTOM: (BenchmarkTier.UNASSIGNED, TaskSourceKind.CUSTOM),
        }[self.family]
        if (self.benchmark_tier, self.provenance.source_kind) != expected:
            raise ValueError("task family, benchmark tier, and source kind are inconsistent")
        return self

    @property
    def quality_identity(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))

    @classmethod
    def from_package(
        cls,
        package: TaskPackage,
        *,
        source_kind: TaskSourceKind = TaskSourceKind.HARNESSLAB,
        source_identity: str | None = None,
        source_revision: str | None = None,
        parent_identities: tuple[str, ...] = (),
    ) -> TaskQualityMetadata:
        if source_kind is TaskSourceKind.HARNESSLAB:
            family = (
                TaskFamily.REPO_ENGINEERING
                if package.manifest.repo_engineering is not None
                else TaskFamily.CORE
            )
            tier = (
                BenchmarkTier.TIER_B
                if family is TaskFamily.REPO_ENGINEERING
                else BenchmarkTier.TIER_A
            )
        elif source_kind is TaskSourceKind.IMPORTED:
            family = TaskFamily.IMPORTED
            tier = BenchmarkTier.UNASSIGNED
        else:
            family = TaskFamily.CUSTOM
            tier = BenchmarkTier.UNASSIGNED
        return cls(
            task=TaskIdentity.from_package(package),
            family=family,
            benchmark_tier=tier,
            provenance=TaskProvenance(
                source_kind=source_kind,
                source_identity=source_identity or package.definition.content_digest,
                source_revision=source_revision,
                parent_identities=parent_identities,
            ),
        )


class QualificationEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    check: QualificationCheck
    evidence_identity: Sha256Digest


class TaskQualification(BaseModel):
    """A categorical qualification claim; deliberately contains no invented score."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    quality: TaskQualityMetadata
    status: QualificationStatus
    qualification_id: Identifier | None = None
    evidence: tuple[QualificationEvidence, ...] = ()

    @field_validator("evidence")
    @classmethod
    def evidence_is_canonical(
        cls, values: tuple[QualificationEvidence, ...]
    ) -> tuple[QualificationEvidence, ...]:
        keys = tuple((item.check.value, item.evidence_identity) for item in values)
        if tuple(sorted(set(keys))) != keys:
            raise ValueError("qualification evidence must be unique and in canonical order")
        if len({item.check for item in values}) != len(values):
            raise ValueError("qualification checks may be evidenced only once")
        return values

    @model_validator(mode="after")
    def qualification_claim_is_supported(self) -> TaskQualification:
        if self.status is QualificationStatus.NOT_QUALIFIED:
            if self.qualification_id is not None or self.evidence:
                raise ValueError("unqualified tasks cannot carry qualification claims")
            return self
        if self.quality.benchmark_tier is BenchmarkTier.UNASSIGNED:
            raise ValueError("imported/custom tasks need an assigned governed tier first")
        if self.qualification_id is None:
            raise ValueError("qualified tasks require a qualification id")
        required = (
            _TIER_A_CHECKS
            if self.quality.benchmark_tier is BenchmarkTier.TIER_A
            else _TIER_B_CHECKS
        )
        actual = {item.check for item in self.evidence}
        missing = sorted(check.value for check in required - actual)
        if missing:
            raise ValueError(f"qualification evidence is missing checks: {', '.join(missing)}")
        return self

    @property
    def qualification_identity(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


def qualify_task(
    quality: TaskQualityMetadata,
    *,
    qualification_id: str,
    evidence: tuple[QualificationEvidence, ...],
) -> TaskQualification:
    """Create a supported categorical qualification or fail closed."""

    try:
        return TaskQualification(
            quality=quality,
            status=QualificationStatus.QUALIFIED,
            qualification_id=qualification_id,
            evidence=evidence,
        )
    except ValueError as exc:
        raise TaskQualityError(str(exc)) from exc


def unqualified_task(quality: TaskQualityMetadata) -> TaskQualification:
    return TaskQualification(quality=quality, status=QualificationStatus.NOT_QUALIFIED)
