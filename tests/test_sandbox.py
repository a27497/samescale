from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from harnesslab.sandbox.artifacts import ArtifactError, assert_managed_path, sha256_file
from harnesslab.sandbox.docker_cli import CommandResult, _DockerCLI
from harnesslab.sandbox.models import FakeSubjectRequest, SandboxStatus, SecurityEvidence
from harnesslab.sandbox.preflight import (
    DockerPreflightError,
    docker_preflight,
    validate_local_endpoint,
)
from harnesslab.sandbox.runner import DockerSandbox, no_harnesslab_containers
from harnesslab.tasks.package import TaskPackage, digest_tree

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON_TASK = REPOSITORY_ROOT / "tasks" / "micro-python-clamp" / "1.0.0"
TYPESCRIPT_TASK = REPOSITORY_ROOT / "tasks" / "micro-typescript-clamp" / "1.0.0"


def sandbox(tmp_path: Path) -> DockerSandbox:
    return DockerSandbox(
        runtime_root=tmp_path / "managed-runtime",
        artifact_root=tmp_path / "managed-artifacts",
    )


def container_exists(name: str) -> bool:
    completed = subprocess.run(
        ["docker", "inspect", name],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def test_security_model_rejects_privileged_inspect_mutation() -> None:
    effective = {
        "privileged": False,
        "read_only_rootfs": True,
        "cap_drop": ["ALL"],
        "security_options": ["no-new-privileges=true"],
        "network_mode": "none",
        "memory_bytes": 128 * 1024 * 1024,
        "nano_cpus": 500_000_000,
        "pids_limit": 64,
        "restart_policy": "no",
        "user": "10001:10001",
        "pid_mode": "",
        "published_ports": False,
        "device_count": 0,
        "mounts": [],
        "tmpfs_destinations": ["/tmp"],
        "docker_socket_mounted": False,
        "seccomp_unconfined": False,
    }
    SecurityEvidence.model_validate(effective)
    effective["privileged"] = True

    with pytest.raises(ValidationError, match="effective Docker configuration is not hardened"):
        SecurityEvidence.model_validate(effective)


@pytest.mark.integration
async def test_docker_preflight_rejects_remote_and_records_immutable_image(tmp_path: Path) -> None:
    with pytest.raises(DockerPreflightError, match="local unix/npipe required"):
        validate_local_endpoint("ssh://remote-builder")
    with pytest.raises(DockerPreflightError, match="local unix/npipe required"):
        validate_local_endpoint("tcp://192.0.2.10:2376")

    preflight = await docker_preflight()
    image = await sandbox(tmp_path).ensure_image()

    assert preflight.ready
    assert preflight.server_os == "linux"
    assert preflight.endpoint_scheme in {"unix", "npipe"}
    assert preflight.default_seccomp
    assert image.image_id.startswith("sha256:")
    assert len(image.image_id) == 71


@pytest.mark.integration
async def test_effective_inspect_profile_and_isolated_verifier_e2e(tmp_path: Path) -> None:
    package = TaskPackage.load(PYTHON_TASK)
    runner = sandbox(tmp_path)
    subject = await runner.run_fake_subject(
        package, FakeSubjectRequest(), run_id=f"subject-{uuid4().hex}"
    )

    security = subject.manifest.security
    assert subject.manifest.status is SandboxStatus.SUCCEEDED
    assert subject.manifest.cleanup_verified
    assert not security.privileged
    assert security.read_only_rootfs
    assert security.cap_drop == ("ALL",)
    assert "no-new-privileges=true" in security.security_options
    assert security.network_mode == "none"
    assert security.memory_bytes == 128 * 1024 * 1024
    assert security.nano_cpus == 500_000_000
    assert security.pids_limit == 64
    assert security.user == "10001:10001"
    assert not security.docker_socket_mounted
    assert security.device_count == 0
    assert security.tmpfs_destinations == ("/tmp",)
    assert not security.published_ports
    assert not container_exists(subject.container_name)
    assert not (subject.artifact_directory / "workspace" / "verifier").exists()
    assert not (subject.artifact_directory / "workspace" / "oracle").exists()

    verifier = await runner.run_hidden_verifier(package, subject, run_id=f"verifier-{uuid4().hex}")
    verifier_mounts = {mount.destination: mount for mount in verifier.run.manifest.security.mounts}
    assert verifier.run.container_name != subject.container_name
    assert verifier.passed
    assert verifier.score == 1.0
    assert not verifier_mounts["/workspace"].read_write
    assert not verifier_mounts["/verifier"].read_write
    assert verifier.run.manifest.cleanup_verified
    assert not container_exists(verifier.run.container_name)
    assert await no_harnesslab_containers()


@pytest.mark.integration
async def test_fresh_workspace_isolation_uses_same_task_definition(tmp_path: Path) -> None:
    package = TaskPackage.load(PYTHON_TASK)
    runner = sandbox(tmp_path)
    first = await runner.run_fake_subject(
        package,
        FakeSubjectRequest(write_marker=True),
        run_id=f"fresh-a-{uuid4().hex}",
    )
    second = await runner.run_fake_subject(
        package,
        FakeSubjectRequest(require_marker_absent=True),
        run_id=f"fresh-b-{uuid4().hex}",
    )

    assert first.manifest.task_digest == second.manifest.task_digest
    assert first.manifest.workspace_input_digest == second.manifest.workspace_input_digest
    assert first.artifact_directory != second.artifact_directory
    assert (first.artifact_directory / "workspace" / "phase-c-marker.txt").is_file()
    assert not (second.artifact_directory / "workspace" / "phase-c-marker.txt").exists()
    assert first.manifest.status is SandboxStatus.SUCCEEDED
    assert second.manifest.status is SandboxStatus.SUCCEEDED
    assert await no_harnesslab_containers()


@pytest.mark.integration
async def test_declared_context_is_subject_visible_read_only(tmp_path: Path) -> None:
    package = TaskPackage.load(TYPESCRIPT_TASK)
    result = await sandbox(tmp_path).run_fake_subject(
        package,
        FakeSubjectRequest(solve_python_clamp=False),
        run_id=f"context-{uuid4().hex}",
    )
    mounts = {mount.destination: mount for mount in result.manifest.security.mounts}

    assert result.manifest.status is SandboxStatus.SUCCEEDED
    assert "/context" in mounts
    assert not mounts["/context"].read_write
    assert not (result.artifact_directory / "workspace" / "context").exists()


@pytest.mark.integration
async def test_timeout_kills_and_removes_container(tmp_path: Path) -> None:
    package = TaskPackage.load(PYTHON_TASK)
    run_id = f"timeout-{uuid4().hex}"
    result = await sandbox(tmp_path).run_fake_subject(
        package,
        FakeSubjectRequest(sleep_seconds=10),
        timeout_seconds=0.5,
        run_id=run_id,
    )

    assert result.manifest.status is SandboxStatus.TIMEOUT
    assert result.manifest.timed_out
    assert result.manifest.cleanup_verified
    assert not container_exists(result.container_name)
    assert await no_harnesslab_containers()


@pytest.mark.integration
async def test_explicit_cancellation_kills_and_removes_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = TaskPackage.load(PYTHON_TASK)
    runner = sandbox(tmp_path)
    run_id = f"cancel-{uuid4().hex}"
    container_name = f"harnesslab-subject-{run_id}"
    create_completed = asyncio.Event()
    original_run = _DockerCLI.run

    async def pause_after_create(
        self: _DockerCLI,
        *arguments: str,
        timeout: float = 60,
        environment: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> CommandResult:
        result = await original_run(
            self,
            *arguments,
            timeout=timeout,
            environment=environment,
            check=check,
        )
        if arguments[0] == "create":
            create_completed.set()
            await asyncio.sleep(30)
        return result

    monkeypatch.setattr(_DockerCLI, "run", pause_after_create)
    task = asyncio.create_task(
        runner.run_fake_subject(
            package,
            FakeSubjectRequest(sleep_seconds=30),
            timeout_seconds=60,
            run_id=run_id,
        )
    )
    await asyncio.wait_for(create_completed.wait(), timeout=10)
    assert container_exists(container_name)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    manifest_path = runner.artifact_root / run_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "cancelled"
    assert manifest["cancelled"]
    assert manifest["cleanup_verified"]
    assert not container_exists(container_name)
    assert await no_harnesslab_containers()


@pytest.mark.integration
async def test_fake_secret_is_redacted_and_artifacts_are_consistent(tmp_path: Path) -> None:
    package = TaskPackage.load(PYTHON_TASK)
    runner = sandbox(tmp_path)
    fake_secret = "phase-c-fake-credential-12345"
    run_id = f"secret-{uuid4().hex}"
    result = await runner.run_fake_subject(
        package,
        FakeSubjectRequest(echo_secret_name="FAKE_CREDENTIAL"),
        run_id=run_id,
        secrets={"FAKE_CREDENTIAL": fake_secret},
    )

    manifest_path = result.artifact_directory / "manifest.json"
    stdout_path = result.artifact_directory / "stdout.txt"
    stderr_path = result.artifact_directory / "stderr.txt"
    persisted = (
        manifest_path.read_text(encoding="utf-8")
        + stdout_path.read_text(encoding="utf-8")
        + stderr_path.read_text(encoding="utf-8")
    )
    assert fake_secret not in persisted
    assert "[REDACTED]" in persisted
    assert result.manifest.stdout.digest == sha256_file(stdout_path)
    assert result.manifest.stderr.digest == sha256_file(stderr_path)
    assert result.manifest.workspace_output_digest == digest_tree(
        result.artifact_directory / "workspace"
    )
    with pytest.raises(FileExistsError):
        await runner.run_fake_subject(package, FakeSubjectRequest(), run_id=run_id)
    assert not (runner.runtime_root / run_id).exists()


@pytest.mark.integration
async def test_container_output_capture_is_bounded(tmp_path: Path) -> None:
    package = TaskPackage.load(PYTHON_TASK)
    result = await sandbox(tmp_path).run_fake_subject(
        package,
        FakeSubjectRequest(output_bytes=100_000),
        run_id=f"output-{uuid4().hex}",
    )

    stdout_path = result.artifact_directory / "stdout.txt"
    assert result.manifest.stdout_truncated
    assert not result.manifest.stderr_truncated
    assert stdout_path.stat().st_size <= 65_536
    assert result.manifest.stdout.digest == sha256_file(stdout_path)


@pytest.mark.integration
async def test_host_escape_and_subject_symlink_artifact_are_rejected(tmp_path: Path) -> None:
    managed = tmp_path / "managed"
    managed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ArtifactError, match="outside the managed root"):
        assert_managed_path(managed, outside)

    package = TaskPackage.load(PYTHON_TASK)
    result = await sandbox(tmp_path).run_fake_subject(
        package,
        FakeSubjectRequest(create_unsafe_symlink=True),
        run_id=f"symlink-{uuid4().hex}",
    )
    assert result.manifest.status is SandboxStatus.ARTIFACT_ERROR
    assert result.manifest.workspace_output_digest is None
    assert result.manifest.workspace_snapshot is None
    assert result.manifest.cleanup_verified
    assert not container_exists(result.container_name)
    assert await no_harnesslab_containers()


def test_artifact_digest_function_is_sensitive(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("before", encoding="utf-8")
    before = sha256_file(artifact)
    artifact.write_text("after", encoding="utf-8")
    after = sha256_file(artifact)

    assert before != after
    assert before == "sha256:" + hashlib.sha256(b"before").hexdigest()
