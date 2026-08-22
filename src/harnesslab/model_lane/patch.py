from __future__ import annotations

import json
import shutil
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harnesslab.tasks.package import TaskPackageError, digest_tree, is_link_like, sha256_bytes

MAX_PATCH_OPERATIONS = 64
MAX_FILE_CONTENT_BYTES = 256_000
MAX_TOTAL_CONTENT_BYTES = 1_000_000
MAX_PATCH_PATH_BYTES = 1_024
MAX_PATH_COMPONENT_BYTES = 255
_WINDOWS_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class DirectPatchError(ValueError):
    """Model public output violates direct-patch-v1 or workspace safety."""


class DirectPatchInfrastructureError(DirectPatchError):
    """Trusted workspace staging or mutation failed independently of model output."""


def _validate_patch_path(value: str) -> str:
    if (
        not value
        or len(value.encode("utf-8")) > MAX_PATCH_PATH_BYTES
        or "\\" in value
        or "\x00" in value
    ):
        raise ValueError("path must be a bounded POSIX workspace-relative path")
    if value.startswith("/") or value.endswith("/"):
        raise ValueError("path must name a workspace-relative file")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("path must not contain empty, '.' or '..' components")
    if any(len(part.encode("utf-8")) > MAX_PATH_COMPONENT_BYTES for part in raw_parts):
        raise ValueError("path component exceeds the portable byte limit")
    if any(part.endswith((" ", ".")) for part in raw_parts):
        raise ValueError("path component has a Windows-ambiguous suffix")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("path must use NFC Unicode normalization")
    if any(":" in part for part in raw_parts):
        raise ValueError("path must not contain a drive or URI component")
    if any(part.split(".", 1)[0].upper() in _WINDOWS_DEVICE_NAMES for part in raw_parts):
        raise ValueError("path uses a reserved device name")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError("path must be relative")
    return path.as_posix()


class WriteOperation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    op: Literal["write"]
    path: str
    content: str

    _path_is_safe = field_validator("path")(_validate_patch_path)

    @field_validator("content")
    @classmethod
    def content_is_bounded(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_FILE_CONTENT_BYTES:
            raise ValueError("write content exceeds the per-file limit")
        return value


class DeleteOperation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    op: Literal["delete"]
    path: str

    _path_is_safe = field_validator("path")(_validate_patch_path)


PatchOperation = Annotated[WriteOperation | DeleteOperation, Field(discriminator="op")]


class DirectPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    operations: tuple[PatchOperation, ...] = Field(min_length=1, max_length=MAX_PATCH_OPERATIONS)

    @model_validator(mode="after")
    def operations_are_unambiguous_and_bounded(self) -> DirectPatch:
        paths = [operation.path for operation in self.operations]
        canonical_paths = [unicodedata.normalize("NFC", path).casefold() for path in paths]
        if len(canonical_paths) != len(set(canonical_paths)):
            raise ValueError("each path may appear at most once")
        for index, path in enumerate(canonical_paths):
            if any(
                other.startswith(f"{path}/") or path.startswith(f"{other}/")
                for other in canonical_paths[index + 1 :]
            ):
                raise ValueError("operation paths must not overlap as parent and child")
        total = sum(
            len(operation.content.encode("utf-8"))
            for operation in self.operations
            if isinstance(operation, WriteOperation)
        )
        if total > MAX_TOTAL_CONTENT_BYTES:
            raise ValueError("patch content exceeds the total limit")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )


def parse_direct_patch(public_output: str) -> DirectPatch:
    if not public_output or public_output != public_output.strip():
        raise DirectPatchError("direct patch must be one strict JSON object without wrapping text")

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise DirectPatchError("direct patch JSON contains a duplicate object key")
            result[key] = value
        return result

    try:
        raw = json.loads(public_output, object_pairs_hook=reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise DirectPatchError("direct patch is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise DirectPatchError("direct patch must be a JSON object")
    try:
        return DirectPatch.model_validate(raw)
    except Exception as exc:
        raise DirectPatchError("direct patch does not match direct-patch-v1") from exc


def _target(root: Path, relative: str) -> Path:
    root_resolved = root.resolve()
    target = root.joinpath(*PurePosixPath(relative).parts)
    resolved = target.resolve(strict=False)
    if resolved == root_resolved or root_resolved not in resolved.parents:
        raise DirectPatchError("patch path escapes the workspace")
    return target


def _assert_no_symlink_path(root: Path, target: Path) -> None:
    relative = target.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if is_link_like(current):
            raise DirectPatchError("patch path traverses a link or junction")


def _apply_direct_patch_in_place(
    workspace: Path,
    patch: DirectPatch,
    *,
    protected_digests: tuple[tuple[str, str], ...],
) -> str:
    if not workspace.is_dir() or is_link_like(workspace):
        raise DirectPatchError("workspace is unavailable or unsafe")
    protected = {path.casefold() for path, _ in protected_digests}
    planned: list[tuple[PatchOperation, Path]] = []
    for operation in patch.operations:
        if operation.path.casefold() in protected:
            raise DirectPatchError("direct patch targets a protected task file")
        target = _target(workspace, operation.path)
        _assert_no_symlink_path(workspace, target)
        if isinstance(operation, DeleteOperation):
            if not target.exists() or not target.is_file():
                raise DirectPatchError("delete operation must target an existing regular file")
        elif target.exists() and not target.is_file():
            raise DirectPatchError("write operation cannot replace a non-file")
        elif isinstance(operation, WriteOperation):
            parent = target.parent
            while parent != workspace:
                if parent.exists() and not parent.is_dir():
                    raise DirectPatchError("write path has a non-directory parent")
                parent = parent.parent
        planned.append((operation, target))

    for operation, target in planned:
        if isinstance(operation, WriteOperation):
            target.parent.mkdir(parents=True, exist_ok=True)
            _assert_no_symlink_path(workspace, target)
            target.write_text(operation.content, encoding="utf-8", newline="")
        else:
            target.unlink()

    for relative, expected_digest in protected_digests:
        protected_path = _target(workspace, relative)
        if (
            not protected_path.is_file()
            or sha256_bytes(protected_path.read_bytes()) != expected_digest
        ):
            raise DirectPatchInfrastructureError("protected task file identity changed")
    return digest_tree(workspace)


def _make_staging_root(workspace: Path) -> Path:
    try:
        return Path(
            tempfile.mkdtemp(prefix=f".{workspace.name}-direct-patch-", dir=workspace.parent)
        )
    except OSError as exc:
        raise DirectPatchInfrastructureError(
            "direct patch staging directory is unavailable"
        ) from exc


def apply_direct_patch(
    workspace: Path,
    patch: DirectPatch,
    *,
    protected_digests: tuple[tuple[str, str], ...],
    expected_input_digest: str | None = None,
) -> str:
    if not workspace.is_dir() or is_link_like(workspace):
        raise DirectPatchInfrastructureError("workspace is unavailable or unsafe")
    staging_root = _make_staging_root(workspace)
    candidate = staging_root / "candidate"
    original = staging_root / "original"
    cleanup_staging = True
    try:
        source_digest = digest_tree(workspace)
        if expected_input_digest is not None and source_digest != expected_input_digest:
            raise DirectPatchInfrastructureError(
                "workspace identity differs from the rendered prompt"
            )
        shutil.copytree(workspace, candidate)
        if digest_tree(candidate) != source_digest or digest_tree(workspace) != source_digest:
            raise DirectPatchInfrastructureError(
                "workspace identity changed while staging direct patch"
            )
        output_digest = _apply_direct_patch_in_place(
            candidate,
            patch,
            protected_digests=protected_digests,
        )
        workspace.replace(original)
        try:
            candidate.replace(workspace)
        except OSError as commit_error:
            try:
                original.replace(workspace)
            except OSError as rollback_error:
                cleanup_staging = False
                raise DirectPatchInfrastructureError(
                    f"direct patch rollback failed; original preserved at {original}"
                ) from rollback_error
            raise commit_error
        return output_digest
    except DirectPatchError:
        raise
    except (OSError, TaskPackageError) as exc:
        raise DirectPatchInfrastructureError(
            "direct patch could not be applied atomically"
        ) from exc
    finally:
        if cleanup_staging:
            shutil.rmtree(staging_root, ignore_errors=True)


def copy_workspace_snapshot(source: Path, destination: Path) -> str:
    if destination.exists():
        raise DirectPatchError("workspace snapshot destination already exists")
    shutil.copytree(source, destination)
    copied = digest_tree(destination)
    source_digest = digest_tree(source)
    if copied != source_digest:
        shutil.rmtree(destination)
        raise DirectPatchError("workspace snapshot identity changed during collection")
    return copied
