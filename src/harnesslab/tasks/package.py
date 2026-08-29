from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import ValidationError
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

from harnesslab.contracts.task import (
    ContextBundleReference,
    OracleReference,
    TaskDefinition,
    VerifierReference,
    WorkspaceReference,
)
from harnesslab.tasks.models import TaskPackageManifest, validate_relative_path


class TaskPackageError(ValueError):
    """Raised when a task package is malformed or unsafe to materialize."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def sha256_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def is_link_like(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (is_junction is not None and is_junction())


def _package_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise TaskPackageError(f"directory does not exist: {root}")
    files: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in [*directory_names, *file_names]:
            candidate = current_path / name
            if is_link_like(candidate):
                raise TaskPackageError(
                    f"links and junctions are not allowed: {candidate.relative_to(root)}"
                )
        for name in file_names:
            files.append(current_path / name)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def digest_tree(root: Path) -> str:
    """Hash relative paths and bytes in deterministic POSIX path order."""

    digest = hashlib.sha256()
    for path in _package_files(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def resolve_package_path(root: Path, relative: str) -> Path:
    safe = validate_relative_path(relative)
    candidate = root.joinpath(*PurePosixPath(safe).parts)
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise TaskPackageError(f"path escapes task package: {relative}")
    return candidate


@dataclass(frozen=True)
class MaterializedTask:
    root: Path
    workspace: Path
    context: Path | None
    protected_digests: tuple[tuple[str, str], ...]

    def cleanup(self) -> None:
        shutil.rmtree(self.root)


@dataclass(frozen=True)
class TaskPackage:
    root: Path
    manifest: TaskPackageManifest
    definition: TaskDefinition
    verifier_digest: str
    oracle_digest: str

    @property
    def verifier_entrypoint(self) -> Path:
        return resolve_package_path(self.root, self.manifest.verifier.entrypoint)

    @property
    def oracle_path(self) -> Path:
        return resolve_package_path(self.root, self.manifest.oracle.path)

    @property
    def robustness_path(self) -> Path | None:
        definition = self.manifest.repo_engineering
        if definition is None:
            return None
        return resolve_package_path(self.root, definition.robustness_path)

    @property
    def robustness_variants(self) -> tuple[Path, ...]:
        root = self.robustness_path
        if root is None:
            return ()
        return tuple(
            sorted((path for path in root.iterdir() if path.is_dir()), key=lambda p: p.name)
        )

    @classmethod
    def load(cls, root: Path) -> TaskPackage:
        root = root.resolve()
        _package_files(root)
        manifest_path = root / "task.yaml"
        if not manifest_path.is_file():
            raise TaskPackageError("task.yaml is required")
        try:
            raw = yaml.load(manifest_path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        except (yaml.YAMLError, UnicodeDecodeError) as exc:
            raise TaskPackageError(f"invalid task.yaml: {exc}") from exc
        if not isinstance(raw, dict):
            raise TaskPackageError("task.yaml must contain a mapping")
        try:
            manifest = TaskPackageManifest.model_validate(raw)
        except ValidationError as exc:
            raise TaskPackageError(f"invalid task manifest: {exc}") from exc

        if root.name != manifest.version or root.parent.name != manifest.id:
            raise TaskPackageError("task directory must end with <task-id>/<version>")
        cls._validate_layout(root, manifest)

        instruction_path = resolve_package_path(root, manifest.instruction_path)
        workspace_path = resolve_package_path(root, manifest.workspace_path)
        context_path = (
            resolve_package_path(root, manifest.context_path) if manifest.context_path else None
        )
        oracle_path = resolve_package_path(root, manifest.oracle.path)

        workspace_digest = digest_tree(workspace_path)
        verifier_digest = digest_tree(root / "verifier")
        oracle_digest = digest_tree(oracle_path)
        context_reference = (
            ContextBundleReference(uri=manifest.context_path, digest=digest_tree(context_path))
            if context_path is not None and manifest.context_path is not None
            else None
        )
        definition = TaskDefinition(
            id=manifest.id,
            version=manifest.version,
            domain=manifest.domain,
            lane_support=manifest.lane_support,
            instruction=instruction_path.read_text(encoding="utf-8"),
            workspace=WorkspaceReference(uri=manifest.workspace_path, digest=workspace_digest),
            context_bundle=context_reference,
            verifier=VerifierReference(
                kind=manifest.verifier.kind,
                version=manifest.verifier.version,
                entrypoint=manifest.verifier.entrypoint,
                digest=verifier_digest,
            ),
            oracle=OracleReference(uri=manifest.oracle.path, digest=oracle_digest),
            budget=manifest.budget,
            expected_tools=manifest.expected_tools,
            metadata=manifest.metadata,
            content_digest=digest_tree(root),
        )
        return cls(
            root=root,
            manifest=manifest,
            definition=definition,
            verifier_digest=verifier_digest,
            oracle_digest=oracle_digest,
        )

    @staticmethod
    def _validate_layout(root: Path, manifest: TaskPackageManifest) -> None:
        paths = {
            "instruction": (manifest.instruction_path, "file", "instruction.md"),
            "workspace": (manifest.workspace_path, "directory", "workspace"),
            "verifier": (manifest.verifier.entrypoint, "file", "verifier"),
            "oracle": (manifest.oracle.path, "directory", "oracle"),
        }
        if manifest.context_path is not None:
            paths["context"] = (manifest.context_path, "directory", "context")
        if manifest.repo_engineering is not None:
            paths["robustness"] = (
                manifest.repo_engineering.robustness_path,
                "directory",
                "robustness",
            )
        for label, (relative, expected_kind, expected_top_level) in paths.items():
            if PurePosixPath(relative).parts[0] != expected_top_level:
                raise TaskPackageError(f"{label} must be under {expected_top_level}/")
            path = resolve_package_path(root, relative)
            if expected_kind == "file" and not path.is_file():
                raise TaskPackageError(f"{label} file does not exist: {relative}")
            if expected_kind == "directory" and not path.is_dir():
                raise TaskPackageError(f"{label} directory does not exist: {relative}")
        workspace = resolve_package_path(root, manifest.workspace_path)
        for protected in manifest.protected_paths:
            path = resolve_package_path(workspace, protected)
            if not path.is_file():
                raise TaskPackageError(f"protected file does not exist: {protected}")
        repo_engineering = manifest.repo_engineering
        if repo_engineering is not None:
            oracle = resolve_package_path(root, manifest.oracle.path)
            oracle_files = _package_files(oracle)
            if len(oracle_files) < repo_engineering.minimum_oracle_files:
                raise TaskPackageError(
                    "Tier-B oracle does not meet the declared multi-file minimum"
                )
            robustness = resolve_package_path(root, repo_engineering.robustness_path)
            variants = tuple(path for path in robustness.iterdir() if path.is_dir())
            if len(variants) < repo_engineering.minimum_robustness_variants:
                raise TaskPackageError(
                    "Tier-B package does not meet the declared robustness-variant minimum"
                )
            if any(not _package_files(variant) for variant in variants):
                raise TaskPackageError("Tier-B robustness variants must contain an overlay")

    def materialize(self, parent: Path | None = None) -> MaterializedTask:
        if parent is not None:
            parent.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="harnesslab-task-", dir=parent))
        workspace = root / "workspace"
        shutil.copytree(resolve_package_path(self.root, self.manifest.workspace_path), workspace)
        context: Path | None = None
        if self.manifest.context_path is not None:
            context = root / "context"
            shutil.copytree(resolve_package_path(self.root, self.manifest.context_path), context)
        protected = tuple(
            (relative, sha256_bytes(resolve_package_path(workspace, relative).read_bytes()))
            for relative in self.manifest.protected_paths
        )
        return MaterializedTask(
            root=root,
            workspace=workspace,
            context=context,
            protected_digests=protected,
        )

    def apply_oracle(self, materialized: MaterializedTask) -> None:
        self.apply_overlay(materialized, self.oracle_path)

    def apply_overlay(self, materialized: MaterializedTask, overlay: Path) -> None:
        resolved_overlay = overlay.resolve()
        resolved_root = self.root.resolve()
        if resolved_root not in resolved_overlay.parents:
            raise TaskPackageError("overlay must be contained by the task package")
        for source in _package_files(resolved_overlay):
            relative = source.relative_to(resolved_overlay)
            target = materialized.workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def workspace_digest(self, materialized: MaterializedTask) -> str:
        return digest_tree(materialized.workspace)
