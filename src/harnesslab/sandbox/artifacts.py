from __future__ import annotations

import hashlib
import os
import shutil
import stat
from collections.abc import Iterable
from pathlib import Path

from harnesslab.sandbox.models import (
    ArtifactDigest,
    ImageIdentity,
    SandboxArtifactManifest,
    SandboxRunResult,
    SandboxStatus,
    SecurityEvidence,
)
from harnesslab.tasks.package import TaskPackage, TaskPackageError, digest_tree


class ArtifactError(RuntimeError):
    """A run artifact cannot be collected without crossing a safety boundary."""


def assert_managed_path(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    if resolved_candidate == resolved_root or resolved_root not in resolved_candidate.parents:
        raise ArtifactError(f"path is outside the managed root: {candidate}")
    return resolved_candidate


def redact_exact(text: str, secrets: Iterable[str]) -> str:
    redacted = text
    for value in sorted({secret for secret in secrets if secret}, key=len, reverse=True):
        redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65_536):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def assert_tree_has_no_run_secrets(root: Path, secrets: Iterable[str]) -> None:
    secret_text = tuple({value for value in secrets if value})
    if not secret_text:
        return
    secret_bytes = tuple(value.encode("utf-8") for value in secret_text)
    longest = max(len(value) for value in secret_bytes)
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in (*directory_names, *file_names):
            relative = (directory_path / name).relative_to(root).as_posix()
            if any(value in relative for value in secret_text):
                raise ArtifactError("workspace relative path contains an exact run secret")
        for name in file_names:
            path = directory_path / name
            if path.is_symlink() or not path.is_file():
                continue
            tail = b""
            with path.open("rb") as stream:
                while chunk := stream.read(65_536):
                    candidate = tail + chunk
                    if any(value in candidate for value in secret_bytes):
                        raise ArtifactError("workspace regular file contains an exact run secret")
                    tail = candidate[-(longest - 1) :] if longest > 1 else b""


def make_tree_writable(root: Path) -> None:
    digest_tree(root)
    if os.name == "nt":
        return
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        directory_path.chmod(0o777)
        for name in directory_names:
            (directory_path / name).chmod(0o777)
        for name in file_names:
            (directory_path / name).chmod(0o666)


def make_tree_readable(root: Path) -> str:
    """Make a safe managed tree readable by a non-root container without changing identity."""

    before_digest = digest_tree(root)
    if os.name != "nt":
        for directory, _, file_names in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            directory_mode = stat.S_IMODE(directory_path.stat(follow_symlinks=False).st_mode)
            directory_path.chmod(directory_mode | 0o555, follow_symlinks=False)
            for name in file_names:
                path = directory_path / name
                file_mode = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
                path.chmod(file_mode | 0o444, follow_symlinks=False)
    after_digest = digest_tree(root)
    if after_digest != before_digest:
        raise ArtifactError("permission normalization changed tree identity")
    return before_digest


class ArtifactWriter:
    def __init__(self, artifact_root: Path, run_id: str) -> None:
        self.artifact_root = artifact_root.resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.directory = self.artifact_root / run_id
        self.directory.mkdir(exist_ok=False)
        assert_managed_path(self.artifact_root, self.directory)

    def finalize(
        self,
        *,
        package: TaskPackage,
        role: str,
        container_name: str,
        workspace: Path,
        workspace_input_digest: str,
        image: ImageIdentity,
        security: SecurityEvidence,
        status: SandboxStatus,
        exit_code: int | None,
        duration_ms: int,
        timed_out: bool,
        cancelled: bool,
        cleanup_verified: bool,
        stdout: bytes,
        stderr: bytes,
        stdout_stream_digest: str,
        stderr_stream_digest: str,
        stdout_truncated: bool,
        stderr_truncated: bool,
        summary: str,
        secrets: Iterable[str],
    ) -> SandboxRunResult:
        secret_values = tuple(secrets)
        stdout_text = redact_exact(stdout.decode("utf-8", errors="replace"), secret_values)
        stderr_text = redact_exact(stderr.decode("utf-8", errors="replace"), secret_values)
        safe_summary = redact_exact(summary, secret_values)
        stdout_path = self.directory / "stdout.txt"
        stderr_path = self.directory / "stderr.txt"
        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")

        workspace_output_digest: str | None = None
        workspace_artifact: ArtifactDigest | None = None
        snapshot = self.directory / "workspace"
        if not cleanup_verified:
            status = SandboxStatus.CLEANUP_ERROR
            safe_summary = "container cleanup could not be verified"
        else:
            try:
                assert_tree_has_no_run_secrets(workspace, secret_values)
                workspace_output_digest = digest_tree(workspace)
                shutil.copytree(workspace, snapshot)
                copied_digest = digest_tree(snapshot)
                if copied_digest != workspace_output_digest:
                    raise ArtifactError("workspace snapshot digest changed during collection")
                workspace_artifact = ArtifactDigest(path="workspace", digest=copied_digest)
            except (TaskPackageError, ArtifactError, OSError) as exc:
                status = SandboxStatus.ARTIFACT_ERROR
                safe_summary = redact_exact(
                    f"unsafe workspace artifact: {type(exc).__name__}", secret_values
                )
                if snapshot.exists():
                    shutil.rmtree(snapshot)

        manifest = SandboxArtifactManifest(
            run_id=self.directory.name,
            role=role,
            task_id=package.definition.id,
            task_version=package.definition.version,
            task_digest=package.definition.content_digest,
            workspace_input_digest=workspace_input_digest,
            workspace_output_digest=workspace_output_digest,
            image=image,
            security=security,
            status=status,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out,
            cancelled=cancelled,
            cleanup_verified=cleanup_verified,
            stdout_stream_digest=stdout_stream_digest,
            stderr_stream_digest=stderr_stream_digest,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            stdout=ArtifactDigest(path="stdout.txt", digest=sha256_file(stdout_path)),
            stderr=ArtifactDigest(path="stderr.txt", digest=sha256_file(stderr_path)),
            workspace_snapshot=workspace_artifact,
            summary=safe_summary,
        )
        manifest_path = self.directory / "manifest.json"
        manifest_path.write_text(manifest.canonical_json(), encoding="utf-8")
        return SandboxRunResult(
            run_id=self.directory.name,
            container_name=container_name,
            artifact_directory=self.directory,
            manifest=manifest,
            stdout=stdout_text,
            stderr=stderr_text,
        )
