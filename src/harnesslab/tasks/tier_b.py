from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Sha256Digest
from harnesslab.tasks.health import validate_task_health
from harnesslab.tasks.models import OutcomeCategory, VerifierExecutionResult
from harnesslab.tasks.package import TaskPackage, digest_tree
from harnesslab.tasks.verifier import execute_verifier


class TierBQualificationError(ValueError):
    """A Tier-B corpus or its qualification evidence is incomplete or inconsistent."""


class RobustnessVariantQualification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,99}$")
    overlay_identity: Sha256Digest
    expected: Literal["FAIL"] = "FAIL"
    repeats: Literal[5] = 5
    terminal_identity: Sha256Digest


class TierBTaskQualification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    package_path: str
    task_id: str
    task_version: str
    language: Literal["python", "java", "typescript"]
    engineering_shape: str
    task_identity: Sha256Digest
    repository_snapshot_identity: Sha256Digest
    verifier_identity: Sha256Digest
    oracle_identity: Sha256Digest
    oracle_changed_files: tuple[str, ...] = Field(min_length=2)
    baseline_expected: Literal["FAIL"] = "FAIL"
    oracle_expected: Literal["PASS"] = "PASS"
    health_repeats: Literal[5] = 5
    baseline_terminal_identity: Sha256Digest
    oracle_terminal_identity: Sha256Digest
    robustness_variants: tuple[RobustnessVariantQualification, ...] = Field(min_length=2)


class TierBQualificationArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    qualification_id: Literal["tier-b-repo-engineering-v1"] = "tier-b-repo-engineering-v1"
    benchmark_tier: Literal["TIER_B_REPO_ENGINEERING"] = "TIER_B_REPO_ENGINEERING"
    repository_snapshot_model: Literal["task-package-frozen-workspace-v1"] = (
        "task-package-frozen-workspace-v1"
    )
    verifier_model: Literal["hidden-repository-contract-v1"] = "hidden-repository-contract-v1"
    task_count: int = Field(ge=3, le=5)
    tasks: tuple[TierBTaskQualification, ...] = Field(min_length=3, max_length=5)
    baseline_health: Literal["PASS"] = "PASS"
    oracle_health: Literal["PASS"] = "PASS"
    robustness: Literal["PASS"] = "PASS"
    workspace_isolation: Literal["PASS"] = "PASS"
    deterministic_digest: Literal["PASS"] = "PASS"
    hidden_test_leakage: Literal["NONE"] = "NONE"
    real_provider_calls: Literal[0] = 0
    qualification_digest: Sha256Digest

    @model_validator(mode="after")
    def task_inventory_is_coherent(self) -> TierBQualificationArtifact:
        if self.task_count != len(self.tasks):
            raise ValueError("Tier-B task_count does not match the inventory")
        if len({task.task_id for task in self.tasks}) != len(self.tasks):
            raise ValueError("Tier-B task identities must be unique")
        if tuple(task.task_id for task in self.tasks) != tuple(
            sorted(task.task_id for task in self.tasks)
        ):
            raise ValueError("Tier-B task inventory must use canonical task-id order")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"qualification_digest"})

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


def _terminal_identity(result: VerifierExecutionResult, workspace_digest: str) -> str:
    return canonical_digest(
        {
            "workspace_digest": workspace_digest,
            "result": result.model_dump(mode="json", exclude={"duration_ms"}),
        }
    )


def discover_tier_b_packages(repository_root: Path) -> tuple[TaskPackage, ...]:
    packages: list[TaskPackage] = []
    for manifest in sorted((repository_root / "tasks").glob("*/*/task.yaml")):
        package = TaskPackage.load(manifest.parent)
        if package.manifest.repo_engineering is not None:
            packages.append(package)
    if not 3 <= len(packages) <= 5:
        raise TierBQualificationError("Tier-B corpus must contain between three and five tasks")
    return tuple(sorted(packages, key=lambda package: package.definition.id))


def _qualify_variant(
    package: TaskPackage, variant: Path, *, repeats: int
) -> RobustnessVariantQualification:
    if repeats != 5:
        raise TierBQualificationError("Tier-B qualification requires exactly five repeats")
    identities: list[str] = []
    for _ in range(repeats):
        materialized = package.materialize()
        try:
            package.apply_overlay(materialized, variant)
            workspace_digest = package.workspace_digest(materialized)
            result = execute_verifier(package, materialized)
        finally:
            materialized.cleanup()
        if result.category is not OutcomeCategory.SUBJECT_RESULT or result.passed:
            raise TierBQualificationError(
                f"{package.definition.id}:{variant.name} is not a deterministic subject failure"
            )
        identities.append(_terminal_identity(result, workspace_digest))
    if len(set(identities)) != 1:
        raise TierBQualificationError(
            f"{package.definition.id}:{variant.name} terminal evidence is nondeterministic"
        )
    return RobustnessVariantQualification(
        name=variant.name,
        overlay_identity=digest_tree(variant),
        terminal_identity=identities[0],
    )


def _verify_workspace_boundaries(package: TaskPackage) -> None:
    first = package.materialize()
    second = package.materialize()
    try:
        forbidden = {"verifier", "oracle", "robustness"}
        if forbidden & {path.name for path in first.root.iterdir()}:
            raise TierBQualificationError(
                "hidden Tier-B assets leaked into subject materialization"
            )
        baseline_digest = package.definition.workspace.digest
        if package.workspace_digest(first) != baseline_digest:
            raise TierBQualificationError("Tier-B snapshot identity drifted during materialization")
        target = next(path for path in first.workspace.rglob("*") if path.is_file())
        target.write_bytes(target.read_bytes() + b"\nqualification mutation\n")
        if package.workspace_digest(second) != baseline_digest:
            raise TierBQualificationError("fresh Tier-B workspaces are not isolated")
    finally:
        first.cleanup()
        second.cleanup()


def _verify_failure_boundary(package: TaskPackage) -> None:
    if not package.manifest.protected_paths:
        raise TierBQualificationError("Tier-B tasks require at least one protected public contract")
    protected = package.materialize()
    try:
        target = protected.workspace / package.manifest.protected_paths[0]
        target.write_bytes(target.read_bytes() + b"\nmutation\n")
        result = execute_verifier(package, protected)
    finally:
        protected.cleanup()
    if result.category is not OutcomeCategory.PROTECTED_FILE_VIOLATION:
        raise TierBQualificationError("protected-file mutation did not fail closed")

    with tempfile.TemporaryDirectory(prefix="harnesslab-tier-b-infra-") as temporary:
        task_path = Path(temporary) / package.definition.id / package.definition.version
        task_path.parent.mkdir(parents=True)
        shutil.copytree(package.root, task_path)
        broken_entrypoint = task_path / package.manifest.verifier.entrypoint
        broken_entrypoint.write_text(
            'raise RuntimeError("verifier-owned fault")\n', encoding="utf-8"
        )
        broken = TaskPackage.load(task_path)
        materialized = broken.materialize()
        try:
            result = execute_verifier(broken, materialized)
        finally:
            materialized.cleanup()
    if result.category is not OutcomeCategory.VERIFIER_ERROR:
        raise TierBQualificationError("verifier-owned fault was not classified as infrastructure")


def build_tier_b_qualification(
    repository_root: Path, *, repeats: int = 5
) -> TierBQualificationArtifact:
    if repeats != 5:
        raise TierBQualificationError("Tier-B qualification requires exactly five repeats")
    tasks: list[TierBTaskQualification] = []
    for package in discover_tier_b_packages(repository_root):
        health = validate_task_health(package.root, repeats=repeats)
        _verify_workspace_boundaries(package)
        _verify_failure_boundary(package)
        variants = tuple(
            _qualify_variant(package, variant, repeats=repeats)
            for variant in package.robustness_variants
        )
        metadata = package.definition.metadata
        try:
            language = metadata["language"]
            engineering_shape = metadata["engineering_shape"]
        except KeyError as exc:
            raise TierBQualificationError(
                f"{package.definition.id} is missing Tier-B portfolio metadata"
            ) from exc
        oracle_files = tuple(
            path.relative_to(package.oracle_path).as_posix()
            for path in sorted(package.oracle_path.rglob("*"))
            if path.is_file()
        )
        tasks.append(
            TierBTaskQualification(
                package_path=package.root.relative_to(repository_root).as_posix(),
                task_id=package.definition.id,
                task_version=package.definition.version,
                language=language,
                engineering_shape=engineering_shape,
                task_identity=package.definition.content_digest,
                repository_snapshot_identity=package.definition.workspace.digest,
                verifier_identity=package.verifier_digest,
                oracle_identity=package.oracle_digest,
                oracle_changed_files=oracle_files,
                baseline_terminal_identity=health.baseline_terminal_identity,
                oracle_terminal_identity=health.oracle_terminal_identity,
                robustness_variants=variants,
            )
        )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "qualification_id": "tier-b-repo-engineering-v1",
        "benchmark_tier": "TIER_B_REPO_ENGINEERING",
        "repository_snapshot_model": "task-package-frozen-workspace-v1",
        "verifier_model": "hidden-repository-contract-v1",
        "task_count": len(tasks),
        "tasks": [task.model_dump(mode="json") for task in tasks],
        "baseline_health": "PASS",
        "oracle_health": "PASS",
        "robustness": "PASS",
        "workspace_isolation": "PASS",
        "deterministic_digest": "PASS",
        "hidden_test_leakage": "NONE",
        "real_provider_calls": 0,
    }
    payload["qualification_digest"] = canonical_digest(payload)
    return TierBQualificationArtifact.model_validate(payload)


def load_tier_b_qualification(path: Path) -> TierBQualificationArtifact:
    try:
        artifact = TierBQualificationArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TierBQualificationError(
            f"invalid Tier-B qualification: {type(exc).__name__}"
        ) from exc
    if artifact.qualification_digest != canonical_digest(artifact.payload()):
        raise TierBQualificationError("Tier-B qualification digest does not match its payload")
    return artifact


def validate_tier_b_qualification(
    repository_root: Path, artifact: TierBQualificationArtifact
) -> None:
    current = discover_tier_b_packages(repository_root)
    by_id = {package.definition.id: package for package in current}
    if set(by_id) != {task.task_id for task in artifact.tasks}:
        raise TierBQualificationError(
            "Tier-B qualification inventory does not match the repository"
        )
    for task in artifact.tasks:
        package = by_id[task.task_id]
        facts = (
            package.definition.version,
            package.definition.content_digest,
            package.definition.workspace.digest,
            package.verifier_digest,
            package.oracle_digest,
        )
        expected = (
            task.task_version,
            task.task_identity,
            task.repository_snapshot_identity,
            task.verifier_identity,
            task.oracle_identity,
        )
        if facts != expected:
            raise TierBQualificationError(f"Tier-B identity drift for {task.task_id}")
