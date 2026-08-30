from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml
from pydantic import ValidationError

from harnesslab.custom_eval.models import (
    CriterionKind,
    CustomEvaluationDefinition,
    EvaluationCriterion,
    ManagedTaskRecord,
    SourceProvenance,
    SourceType,
    TaskNamespace,
    canonical_digest,
    parse_task_reference,
)
from harnesslab.tasks.models import validate_relative_path
from harnesslab.tasks.package import TaskPackage, TaskPackageError, UniqueKeyLoader, digest_tree


class ManagedTaskStoreError(ValueError):
    """A managed custom task operation is unsafe, invalid, or conflicts with frozen state."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _definition_for_package(
    package_root: Path,
    *,
    owner: str | None,
    category: str | None,
) -> CustomEvaluationDefinition:
    definition_path = package_root / "custom-eval.yaml"
    if definition_path.is_file():
        try:
            raw = yaml.load(definition_path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
            definition = CustomEvaluationDefinition.model_validate(raw)
        except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as exc:
            raise ManagedTaskStoreError("invalid custom-eval.yaml") from exc
        if owner is not None and owner != definition.owner:
            raise ManagedTaskStoreError("import owner disagrees with prepared package ownership")
        if category is not None and category != definition.category:
            raise ManagedTaskStoreError("import category disagrees with prepared package category")
        return definition
    return CustomEvaluationDefinition(
        owner=owner or "unspecified-owner",
        category=category or "uncategorized",
        criteria=(
            EvaluationCriterion(
                id="hidden-verifier",
                kind=CriterionKind.HIDDEN_TEST,
                description="The package's deterministic hidden verifier must pass.",
            ),
        ),
    )


def load_custom_definition(package_root: Path) -> CustomEvaluationDefinition:
    """Load frozen criteria from a managed package, including legacy package defaults."""

    return _definition_for_package(package_root, owner=None, category=None)


class ManagedTaskStore:
    """Content-addressed custom task storage with an isolated mutable index."""

    def __init__(self, root: Path, *, repository_root: Path | None = None) -> None:
        self.root = root.resolve()
        official_root = (repository_root or _repository_root()).resolve()
        protected = tuple((official_root / name).resolve() for name in ("tasks", "release"))
        if any(self.root == path or path in self.root.parents for path in protected):
            raise ManagedTaskStoreError("custom task storage cannot live in an Official namespace")
        self.snapshots_root = self.root / "snapshots"
        self.index_root = self.root / "index"
        self.snapshots_root.mkdir(parents=True, exist_ok=True)
        self.index_root.mkdir(parents=True, exist_ok=True)

    def import_local_folder(
        self,
        package_path: Path,
        *,
        owner: str | None = None,
        category: str | None = None,
    ) -> ManagedTaskRecord:
        return self._import(
            package_path,
            source_type=SourceType.LOCAL_FOLDER,
            source_reference=str(package_path.resolve()),
            source_commit=None,
            owner=owner,
            category=category,
        )

    def import_prepared_package(
        self,
        package_path: Path,
        *,
        owner: str | None = None,
        category: str | None = None,
    ) -> ManagedTaskRecord:
        return self._import(
            package_path,
            source_type=SourceType.PREPARED_PACKAGE,
            source_reference=str(package_path.resolve()),
            source_commit=None,
            owner=owner,
            category=category,
        )

    def import_local_repository(
        self,
        repository: Path,
        package_subpath: str,
        *,
        owner: str | None = None,
        category: str | None = None,
    ) -> ManagedTaskRecord:
        repository = repository.resolve()
        if not (repository / ".git").exists():
            raise ManagedTaskStoreError("local repository source is not a git worktree")
        candidate = self._contained_subpath(repository, package_subpath)
        commit = self._git_output(repository, "rev-parse", "HEAD")
        if len(commit) != 40:
            raise ManagedTaskStoreError("local repository HEAD is not an exact commit")
        return self._import(
            candidate,
            source_type=SourceType.LOCAL_REPOSITORY,
            source_reference=f"{repository}#{package_subpath}",
            source_commit=commit,
            owner=owner,
            category=category,
        )

    def import_git_exact_commit(
        self,
        git_url: str,
        commit: str,
        package_subpath: str,
        *,
        owner: str | None = None,
        category: str | None = None,
        allow_remote_git: bool = False,
    ) -> ManagedTaskRecord:
        if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
            raise ManagedTaskStoreError(
                "git imports require an exact lowercase 40-character commit"
            )
        clone_source = self._safe_git_source(git_url, allow_remote_git=allow_remote_git)
        with tempfile.TemporaryDirectory(prefix="harnesslab-custom-git-") as temporary:
            clone = Path(temporary) / "repository"
            self._run_git(
                Path(temporary),
                "clone",
                "--quiet",
                "--no-checkout",
                clone_source,
                str(clone),
            )
            resolved_commit = self._git_output(
                clone, "rev-parse", "--verify", f"{commit}^{{commit}}"
            )
            if resolved_commit != commit:
                raise ManagedTaskStoreError("requested git commit did not resolve exactly")
            self._run_git(clone, "checkout", "--quiet", "--detach", commit)
            candidate = self._contained_subpath(clone, package_subpath)
            return self._import(
                candidate,
                source_type=SourceType.GIT_EXACT_COMMIT,
                source_reference=f"{self._git_reference(git_url)}#{package_subpath}",
                source_commit=commit,
                owner=owner,
                category=category,
            )

    def list(self) -> tuple[ManagedTaskRecord, ...]:
        records = tuple(self._load_record(path) for path in self.index_root.glob("*/*.json"))
        for record in records:
            self._verify_snapshot(record)
        return tuple(sorted(records, key=lambda item: (item.task_id, item.task_version)))

    def inspect(self, reference: str) -> ManagedTaskRecord:
        task_id, version = parse_task_reference(reference)
        index_path = self._index_path(task_id, version)
        if not index_path.is_file():
            raise ManagedTaskStoreError("managed custom task does not exist")
        record = self._load_record(index_path)
        self._verify_snapshot(record)
        return record

    def package_path(self, record: ManagedTaskRecord) -> Path:
        return (
            self.snapshots_root
            / record.managed_snapshot_identity.removeprefix("sha256:")
            / "package"
            / record.task_id
            / record.task_version
        )

    def load_package(self, reference: str) -> tuple[ManagedTaskRecord, TaskPackage]:
        record = self.inspect(reference)
        try:
            package = TaskPackage.load(self.package_path(record))
        except TaskPackageError as exc:
            raise ManagedTaskStoreError("managed snapshot package is invalid") from exc
        return record, package

    def _import(
        self,
        package_path: Path,
        *,
        source_type: SourceType,
        source_reference: str,
        source_commit: str | None,
        owner: str | None,
        category: str | None,
    ) -> ManagedTaskRecord:
        try:
            package = TaskPackage.load(package_path)
        except TaskPackageError as exc:
            raise ManagedTaskStoreError(f"invalid task package: {exc}") from exc
        definition = _definition_for_package(package.root, owner=owner, category=category)
        criteria_identity = canonical_digest(definition.model_dump(mode="json"))
        managed_identity = canonical_digest(
            {
                "namespace": TaskNamespace.CUSTOM.value,
                "task_identity": package.definition.content_digest,
                "owner": definition.owner,
                "category": definition.category,
                "criteria_identity": criteria_identity,
            }
        )
        record = ManagedTaskRecord(
            task_id=package.definition.id,
            task_version=package.definition.version,
            task_owner=definition.owner,
            task_category=definition.category,
            task_identity=package.definition.content_digest,
            workspace_identity=package.definition.workspace.digest,
            verifier_identity=package.verifier_digest,
            criteria=definition.criteria,
            criteria_identity=criteria_identity,
            managed_snapshot_identity=managed_identity,
            provenance=SourceProvenance(
                source_type=source_type,
                source_reference=source_reference,
                source_commit=source_commit,
                source_content_identity=digest_tree(package.root),
                imported_at=datetime.now(UTC),
            ),
        )
        index_path = self._index_path(record.task_id, record.task_version)
        if index_path.is_file():
            existing = self._load_record(index_path)
            if existing.managed_snapshot_identity != record.managed_snapshot_identity:
                raise ManagedTaskStoreError(
                    "custom task id/version is already bound to a different immutable snapshot"
                )
            self._verify_snapshot(existing)
            return existing

        snapshot_root = self.snapshots_root / managed_identity.removeprefix("sha256:")
        if not snapshot_root.exists():
            staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=self.snapshots_root))
            try:
                destination = staging / "package" / record.task_id / record.task_version
                destination.parent.mkdir(parents=True)
                shutil.copytree(package.root, destination)
                copied = TaskPackage.load(destination)
                if copied.definition.content_digest != record.task_identity:
                    raise ManagedTaskStoreError("managed snapshot changed while being copied")
                _write_json(staging / "record.json", record.model_dump(mode="json"))
                staging.rename(snapshot_root)
            except Exception:
                if staging.exists():
                    shutil.rmtree(staging, ignore_errors=True)
                raise
        index_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(index_path, record.model_dump(mode="json"))
        self._verify_snapshot(record)
        return record

    def _verify_snapshot(self, record: ManagedTaskRecord) -> None:
        package_path = self.package_path(record)
        record_path = package_path.parents[2] / "record.json"
        if not record_path.is_file():
            raise ManagedTaskStoreError("managed snapshot metadata is missing")
        frozen = self._load_record(record_path)
        if frozen != record:
            raise ManagedTaskStoreError("managed snapshot metadata disagrees with its index")
        try:
            package = TaskPackage.load(package_path)
        except TaskPackageError as exc:
            raise ManagedTaskStoreError("managed snapshot integrity validation failed") from exc
        if (
            package.definition.content_digest != record.task_identity
            or package.definition.workspace.digest != record.workspace_identity
            or package.verifier_digest != record.verifier_identity
        ):
            raise ManagedTaskStoreError("managed snapshot content identity changed")
        definition = CustomEvaluationDefinition(
            owner=record.task_owner,
            category=record.task_category,
            criteria=record.criteria,
        )
        if canonical_digest(definition.model_dump(mode="json")) != record.criteria_identity:
            raise ManagedTaskStoreError("managed snapshot criteria identity changed")

    @staticmethod
    def _load_record(path: Path) -> ManagedTaskRecord:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return ManagedTaskRecord.model_validate(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            raise ManagedTaskStoreError("managed task metadata is invalid") from exc

    def _index_path(self, task_id: str, version: str) -> Path:
        safe_id = validate_relative_path(task_id)
        safe_version = validate_relative_path(version)
        if "/" in safe_id or "/" in safe_version:
            raise ManagedTaskStoreError("invalid custom task identity")
        return self.index_root / safe_id / f"{safe_version}.json"

    @staticmethod
    def _contained_subpath(root: Path, subpath: str) -> Path:
        try:
            safe = validate_relative_path(subpath)
        except ValueError as exc:
            raise ManagedTaskStoreError("package subpath is unsafe") from exc
        candidate = (root / safe).resolve()
        if root.resolve() not in candidate.parents:
            raise ManagedTaskStoreError("package subpath escapes its source")
        return candidate

    @staticmethod
    def _safe_git_source(git_url: str, *, allow_remote_git: bool) -> str:
        parsed = urlparse(git_url)
        if parsed.scheme == "file":
            return str(Path(unquote(parsed.path)).resolve())
        if not parsed.scheme and "://" not in git_url:
            return str(Path(git_url).resolve())
        if not allow_remote_git:
            raise ManagedTaskStoreError(
                "remote git fetch is disabled; explicitly authorize it outside CI"
            )
        if os.environ.get("CI"):
            raise ManagedTaskStoreError("remote git fetch is disabled in CI")
        if parsed.scheme not in {"https", "ssh"}:
            raise ManagedTaskStoreError("unsupported git URL scheme")
        return git_url

    @staticmethod
    def _git_reference(git_url: str) -> str:
        parsed = urlparse(git_url)
        if not parsed.scheme:
            return str(Path(git_url).resolve())
        if parsed.scheme == "file":
            return f"file://{Path(unquote(parsed.path)).resolve()}"
        hostname = parsed.hostname or "redacted-host"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return parsed._replace(netloc=f"{hostname}{port}", query="", fragment="").geturl()

    @staticmethod
    def _run_git(workdir: Path, *arguments: str) -> None:
        try:
            subprocess.run(
                ("git", *arguments),
                cwd=workdir,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ManagedTaskStoreError("git import operation failed") from exc

    @classmethod
    def _git_output(cls, workdir: Path, *arguments: str) -> str:
        try:
            result = subprocess.run(
                ("git", *arguments),
                cwd=workdir,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ManagedTaskStoreError("git provenance lookup failed") from exc
        return result.stdout.strip()


__all__ = [
    "ManagedTaskStore",
    "ManagedTaskStoreError",
    "load_custom_definition",
]
