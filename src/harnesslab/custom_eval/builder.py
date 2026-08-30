from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from harnesslab.custom_eval.models import CustomEvaluationDefinition, CustomTaskBuilderSpec
from harnesslab.tasks.models import validate_relative_path
from harnesslab.tasks.package import TaskPackage, TaskPackageError, is_link_like


class CustomTaskBuilderError(ValueError):
    """A builder input cannot safely produce a runnable custom task package."""


@dataclass(frozen=True)
class BuiltTaskPackage:
    path: Path
    task_identity: str
    verifier_identity: str
    structurally_validated: bool = True


def _reject_links(root: Path) -> None:
    if is_link_like(root):
        raise CustomTaskBuilderError("builder sources cannot be links or junctions")
    if root.is_dir():
        for current, directories, files in os.walk(root, followlinks=False):
            for name in (*directories, *files):
                candidate = Path(current) / name
                if is_link_like(candidate):
                    raise CustomTaskBuilderError(
                        "builder sources cannot contain links or junctions"
                    )


def _copy_file(source: Path, destination: Path) -> None:
    _reject_links(source)
    if not source.is_file():
        raise CustomTaskBuilderError(f"builder file source does not exist: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _copy_directory(source: Path, destination: Path) -> None:
    _reject_links(source)
    if not source.is_dir():
        raise CustomTaskBuilderError(f"builder directory source does not exist: {source}")
    shutil.copytree(source, destination)


class CustomTaskBuilder:
    """Build a standard HarnessLab task package plus frozen custom criteria."""

    def build(self, spec: CustomTaskBuilderSpec, destination_root: Path) -> BuiltTaskPackage:
        package_root = destination_root.resolve() / spec.task_id / spec.version
        if package_root.exists():
            raise CustomTaskBuilderError("builder destination already exists")
        try:
            entrypoint = validate_relative_path(spec.verifier_entrypoint)
            protected_paths = tuple(validate_relative_path(path) for path in spec.protected_paths)
        except ValueError as exc:
            raise CustomTaskBuilderError("builder package path is unsafe") from exc
        if PurePosixPath(entrypoint).parts[0] != "verifier":
            raise CustomTaskBuilderError("verifier entrypoint must be below verifier/")

        package_root.mkdir(parents=True)
        try:
            _copy_file(Path(spec.instruction_source), package_root / "instruction.md")
            _copy_directory(Path(spec.workspace_source), package_root / "workspace")
            verifier_source = Path(spec.verifier_source)
            if verifier_source.is_dir():
                _copy_directory(verifier_source, package_root / "verifier")
            else:
                _copy_file(verifier_source, package_root.joinpath(*PurePosixPath(entrypoint).parts))
            _copy_directory(Path(spec.oracle_source), package_root / "oracle")

            manifest = {
                "schema_version": 1,
                "id": spec.task_id,
                "version": spec.version,
                "domain": spec.domain,
                "lane_support": sorted(lane.value for lane in spec.lane_support),
                "instruction_path": "instruction.md",
                "workspace_path": "workspace",
                "verifier": {
                    "kind": "python",
                    "version": spec.verifier_version,
                    "entrypoint": entrypoint,
                    "timeout_seconds": spec.verifier_timeout_seconds,
                },
                "oracle": {"path": "oracle"},
                "budget": {
                    "timeout_seconds": spec.timeout_seconds,
                    "max_output_tokens": spec.max_output_tokens,
                    "network_policy": "deny",
                },
                "protected_paths": list(protected_paths),
                "metadata": spec.metadata,
            }
            (package_root / "task.yaml").write_text(
                yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
            )
            custom_definition = CustomEvaluationDefinition(
                owner=spec.owner,
                category=spec.category,
                criteria=spec.criteria,
            )
            (package_root / "custom-eval.yaml").write_text(
                yaml.safe_dump(
                    custom_definition.model_dump(mode="json"),
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            package = TaskPackage.load(package_root)
        except TaskPackageError as exc:
            shutil.rmtree(package_root, ignore_errors=True)
            raise CustomTaskBuilderError("built task package failed structural validation") from exc
        except (OSError, CustomTaskBuilderError):
            shutil.rmtree(package_root, ignore_errors=True)
            raise
        return BuiltTaskPackage(
            path=package_root,
            task_identity=package.definition.content_digest,
            verifier_identity=package.verifier_digest,
        )


__all__ = ["BuiltTaskPackage", "CustomTaskBuilder", "CustomTaskBuilderError"]
