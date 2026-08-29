from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

import harnesslab.sandbox.preflight as preflight_module
from harnesslab.sandbox.artifacts import (
    ArtifactError,
    assert_managed_path,
    assert_tree_has_no_run_secrets,
    make_tree_readable,
    sha256_file,
)
from harnesslab.sandbox.docker_cli import CommandResult, _DockerCLI, docker_environment
from harnesslab.sandbox.models import (
    FakeSubjectRequest,
    SandboxArtifactManifest,
    SandboxStatus,
    SecurityEvidence,
    VerifierFailureSubtype,
    VerifierLifecycleStage,
    VerifierLifecycleStageEvidence,
    VerifierLifecycleStageStatus,
)
from harnesslab.sandbox.preflight import (
    DockerPreflightError,
    _docker_preflight,
    _docker_runtime_preflight,
    docker_preflight,
    resolve_effective_endpoint,
    validate_local_endpoint,
)
from harnesslab.sandbox.runner import DockerSandbox, SandboxExecutionError, no_harnesslab_containers
from harnesslab.sandbox.subprocess_loop import run_on_subprocess_loop
from harnesslab.tasks.package import TaskPackage, digest_tree

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON_TASK = REPOSITORY_ROOT / "tasks" / "micro-python-clamp" / "1.0.0"
TYPESCRIPT_TASK = REPOSITORY_ROOT / "tasks" / "micro-typescript-clamp" / "1.0.0"
TIER_B_TASKS = (
    REPOSITORY_ROOT / "tasks" / "repo-python-ledger-transfer" / "1.0.0",
    REPOSITORY_ROOT / "tasks" / "repo-java-widget-update" / "1.0.0",
    REPOSITORY_ROOT / "tasks" / "repo-typescript-resilient-client" / "1.0.0",
)


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


def tree_modes(root: Path) -> dict[str, int]:
    return {
        path.relative_to(root).as_posix() or ".": stat.S_IMODE(path.stat().st_mode)
        for path in (root, *root.rglob("*"))
    }


def make_tree_restrictive(root: Path) -> None:
    for path in (root, *root.rglob("*")):
        path.chmod(0o700 if path.is_dir() else 0o600)


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


def test_effective_docker_endpoint_precedence_rejects_remote_overrides() -> None:
    local_unix = "unix:///var/run/docker.sock"
    local_npipe = "npipe:////./pipe/docker_engine"

    assert resolve_effective_endpoint(local_unix, {}) == local_unix
    assert validate_local_endpoint(resolve_effective_endpoint(local_unix, {})) == "unix"
    assert (
        validate_local_endpoint(
            resolve_effective_endpoint(local_npipe, {"DOCKER_HOST": local_npipe})
        )
        == "npipe"
    )
    with pytest.raises(DockerPreflightError, match="local unix/npipe required"):
        validate_local_endpoint(
            resolve_effective_endpoint(local_unix, {"DOCKER_HOST": "ssh://remote-builder"})
        )
    with pytest.raises(DockerPreflightError, match="local unix/npipe required"):
        validate_local_endpoint(
            resolve_effective_endpoint(local_unix, {"DOCKER_HOST": "tcp://192.0.2.10:2376"})
        )

    explicit_context = {
        "DOCKER_CONTEXT": "local-explicit",
        "DOCKER_HOST": "ssh://ignored-by-docker-context",
    }
    assert resolve_effective_endpoint(local_unix, explicit_context) == local_unix
    assert validate_local_endpoint(resolve_effective_endpoint(local_unix, explicit_context)) == (
        "unix"
    )


async def test_docker_preflight_rejects_remote_host_before_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    empty_digest = "sha256:" + hashlib.sha256(b"").hexdigest()

    class FakeDockerCLI:
        def __init__(
            self,
            executable: str,
            *,
            environment: Mapping[str, str] | None = None,
        ) -> None:
            assert executable == "docker"
            assert environment is not None

        async def run(self, *arguments: str) -> CommandResult:
            calls.append(arguments)
            if arguments == ("context", "show"):
                stdout = b"local-current\n"
            elif arguments[:3] == ("context", "inspect", "local-current"):
                stdout = b'"unix:///var/run/docker.sock"\n'
            else:
                pytest.fail(f"preflight attempted a daemon connection: {arguments[0]}")
            return CommandResult(0, stdout, b"", empty_digest, empty_digest, False, False)

    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _: "docker")
    monkeypatch.setattr(preflight_module, "_DockerCLI", FakeDockerCLI)

    for remote_host in ("ssh://remote-builder", "tcp://192.0.2.10:2376"):
        calls.clear()
        monkeypatch.setenv("DOCKER_HOST", remote_host)
        with pytest.raises(DockerPreflightError, match="local unix/npipe required"):
            await _docker_preflight()
        assert calls == [
            ("context", "show"),
            (
                "context",
                "inspect",
                "local-current",
                "--format",
                "{{json .Endpoints.docker.Host}}",
            ),
        ]


async def test_explicit_local_context_is_pinned_over_remote_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environments: list[dict[str, str]] = []
    empty_digest = "sha256:" + hashlib.sha256(b"").hexdigest()

    class FakeDockerCLI:
        def __init__(
            self,
            executable: str,
            *,
            environment: Mapping[str, str] | None = None,
        ) -> None:
            assert executable == "docker"
            environments.append(dict(environment or {}))

        async def run(self, *arguments: str) -> CommandResult:
            if arguments == ("context", "show"):
                stdout = b"local-explicit\n"
            elif arguments[:3] == ("context", "inspect", "local-explicit"):
                stdout = b'"unix:///var/run/docker.sock"\n'
            elif arguments[:2] == ("version", "--format"):
                stdout = b'{"Client":{"Version":"test"},"Server":{"Version":"test","Os":"linux"}}'
            elif arguments[:2] == ("info", "--format"):
                stdout = b'"Docker Test"|"linux"|"amd64"|["name=seccomp,profile=default"]'
            else:
                pytest.fail(f"unexpected Docker command: {arguments}")
            return CommandResult(0, stdout, b"", empty_digest, empty_digest, False, False)

    monkeypatch.setattr(shutil, "which", lambda _: "docker")
    monkeypatch.setattr(preflight_module, "_DockerCLI", FakeDockerCLI)
    preflight, pinned = await _docker_runtime_preflight(
        {
            "PATH": "fixture",
            "DOCKER_CONTEXT": "local-explicit",
            "DOCKER_HOST": "ssh://remote-builder",
        }
    )

    assert preflight.context == "local-explicit"
    assert preflight.endpoint_scheme == "unix"
    assert environments[0]["DOCKER_CONTEXT"] == "local-explicit"
    assert "DOCKER_HOST" not in environments[0]
    assert pinned["DOCKER_HOST"] == "unix:///var/run/docker.sock"
    assert "DOCKER_CONTEXT" not in pinned
    assert environments[1] == pinned
    for secret_name in (
        "DOCKER_HOST",
        "docker_host",
        "Docker_Context",
        "DOCKER_API_VERSION",
    ):
        with pytest.raises(ValueError, match="must not control Docker CLI transport"):
            docker_environment(pinned, {secret_name: "fake-run-secret"})


async def test_docker_cli_subprocess_uses_pinned_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pinned = dict(os.environ)
    pinned["DOCKER_HOST"] = "unix:///pinned-local.sock"
    monkeypatch.setenv("DOCKER_HOST", "ssh://ambient-remote")
    cli = _DockerCLI(executable=sys.executable, environment=pinned)

    result = await run_on_subprocess_loop(
        cli.run(
            "-c",
            "import os; print(os.environ['DOCKER_HOST'])",
        )
    )
    assert result.stdout.decode("utf-8").strip() == "unix:///pinned-local.sock"


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


def test_make_tree_readable_preserves_digest_and_execute_bits(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    nested = root / "nested"
    nested.mkdir(parents=True)
    regular = nested / "regular.txt"
    executable = nested / "script.py"
    regular.write_text("regular", encoding="utf-8")
    executable.write_text("print('safe')\n", encoding="utf-8")
    root.chmod(0o700)
    nested.chmod(0o700)
    regular.chmod(0o600)
    executable.chmod(0o700)
    before = digest_tree(root)

    assert make_tree_readable(root) == before

    assert digest_tree(root) == before
    assert stat.S_IMODE(root.stat().st_mode) == 0o755
    assert stat.S_IMODE(nested.stat().st_mode) == 0o755
    assert stat.S_IMODE(regular.stat().st_mode) == 0o644
    assert stat.S_IMODE(executable.stat().st_mode) == 0o744


def test_make_tree_readable_does_not_chmod_an_already_portable_foreign_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "foreign-workspace"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    source = root / "events.py"
    source.write_text("value = 1\n", encoding="utf-8")
    source.chmod(0o644)
    before = digest_tree(root)
    original_chmod = Path.chmod

    def reject_workspace_chmod(path: Path, mode: int, *, follow_symlinks: bool = True) -> None:
        if path == root or root in path.parents:
            raise PermissionError("synthetic foreign ownership")
        original_chmod(path, mode, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "chmod", reject_workspace_chmod)

    assert make_tree_readable(root) == before
    assert digest_tree(root) == before


@pytest.mark.integration
async def test_restrictive_task_permissions_are_portable_to_non_root_hidden_verifier(
    tmp_path: Path,
) -> None:
    copied_task = tmp_path / "restricted" / "micro-python-clamp" / "1.0.0"
    shutil.copytree(PYTHON_TASK, copied_task)
    make_tree_restrictive(copied_task)
    source_modes_before = tree_modes(copied_task)
    package = TaskPackage.load(copied_task)
    source_verifier_digest = package.verifier_digest
    managed = package.materialize(tmp_path / "materialized")
    runner = sandbox(tmp_path)
    try:
        package.apply_oracle(managed)
        make_tree_restrictive(managed.workspace)
        workspace_digest = digest_tree(managed.workspace)
        result = await runner.run_hidden_verifier_workspace(
            package,
            managed.workspace,
            run_id="restrictive-permission-portability",
        )
        workspace_digest_after = digest_tree(managed.workspace)
    finally:
        managed.cleanup()

    security = result.run.manifest.security
    mounts = {mount.destination: mount for mount in security.mounts}
    assert result.passed
    assert result.score == 1.0
    assert result.run.manifest.status is SandboxStatus.SUCCEEDED
    assert result.run.manifest.workspace_input_digest == workspace_digest
    assert workspace_digest_after == workspace_digest
    assert (
        source_verifier_digest == package.verifier_digest == digest_tree(copied_task / "verifier")
    )
    assert tree_modes(copied_task) == source_modes_before
    assert stat.S_IMODE((copied_task / "verifier").stat().st_mode) == 0o700
    assert stat.S_IMODE((copied_task / "verifier" / "verify.py").stat().st_mode) == 0o600
    assert security.user == "10001:10001"
    assert security.network_mode == "none"
    assert not security.privileged
    assert security.read_only_rootfs
    assert "ALL" in security.cap_drop
    assert "no-new-privileges=true" in security.security_options
    assert not security.docker_socket_mounted
    assert not security.published_ports
    assert not mounts["/workspace"].read_write
    assert not mounts["/verifier"].read_write
    assert result.run.manifest.cleanup_verified
    assert result.lifecycle is not None
    assert result.lifecycle.failure_subtype is None
    assert {item.stage for item in result.lifecycle.stages} == set(VerifierLifecycleStage)
    assert all(
        item.status is VerifierLifecycleStageStatus.COMPLETED for item in result.lifecycle.stages
    )
    assert not runner.runtime_root.joinpath("restrictive-permission-portability").exists()
    assert not container_exists(result.run.container_name)
    assert await no_harnesslab_containers()


@pytest.mark.integration
async def test_tier_b_oracles_pass_in_networkless_isolated_sandbox(tmp_path: Path) -> None:
    runner = sandbox(tmp_path)
    for task_path in TIER_B_TASKS:
        package = TaskPackage.load(task_path)
        managed = package.materialize(tmp_path / f"materialized-{package.definition.id}")
        try:
            package.apply_oracle(managed)
            result = await runner.run_hidden_verifier_workspace(
                package,
                managed.workspace,
                timeout_seconds=60,
                run_id=f"tier-b-oracle-{package.definition.id}",
            )
        finally:
            managed.cleanup()

        assert result.passed
        assert result.score == 1.0
        assert result.run.manifest.status is SandboxStatus.SUCCEEDED
        assert result.run.manifest.security.network_mode == "none"
        assert result.run.manifest.security.read_only_rootfs
        assert result.run.manifest.cleanup_verified
        assert result.lifecycle is not None
        assert result.lifecycle.failure_subtype is None
    assert await no_harnesslab_containers()


@pytest.mark.integration
async def test_verifier_staging_cleanup_failure_cannot_return_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = TaskPackage.load(PYTHON_TASK)
    managed = package.materialize(tmp_path / "materialized")
    runner = sandbox(tmp_path)
    original_cleanup = runner._cleanup_run_root

    def cleanup_then_fail(run_root: Path) -> None:
        original_cleanup(run_root)
        raise OSError("synthetic staging cleanup failure")

    monkeypatch.setattr(runner, "_cleanup_run_root", cleanup_then_fail)
    try:
        package.apply_oracle(managed)
        with pytest.raises(
            SandboxExecutionError, match="verifier staging cleanup could not be verified"
        ):
            await runner.run_hidden_verifier_workspace(
                package,
                managed.workspace,
                run_id="staging-cleanup-failure",
            )
    finally:
        managed.cleanup()

    assert not runner.runtime_root.joinpath("staging-cleanup-failure").exists()
    assert await no_harnesslab_containers()


@pytest.mark.asyncio
async def test_verifier_staging_rejects_source_digest_drift_before_container(
    tmp_path: Path,
) -> None:
    copied_task = tmp_path / "drifted" / "micro-python-clamp" / "1.0.0"
    shutil.copytree(PYTHON_TASK, copied_task)
    package = TaskPackage.load(copied_task)
    managed = package.materialize(tmp_path / "materialized")
    runner = sandbox(tmp_path)
    (copied_task / "verifier" / "verify.py").write_text(
        "raise RuntimeError('drifted')\n", encoding="utf-8"
    )
    try:
        with pytest.raises(
            SandboxExecutionError, match="permission-portable verifier staging failed"
        ):
            await runner.run_hidden_verifier_workspace(
                package,
                managed.workspace,
                run_id="source-verifier-drift",
            )
    finally:
        managed.cleanup()

    assert not (runner.artifact_root / "source-verifier-drift").exists()
    assert not runner.runtime_root.joinpath("source-verifier-drift").exists()
    assert await no_harnesslab_containers()


@pytest.mark.asyncio
async def test_verifier_permission_handoff_failure_has_bounded_safe_subtype(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = TaskPackage.load(PYTHON_TASK)
    managed = package.materialize(tmp_path / "materialized")
    runner = sandbox(tmp_path)

    def deny_permission_normalization(root: Path) -> str:
        raise PermissionError("synthetic foreign ownership")

    monkeypatch.setattr(
        "harnesslab.sandbox.runner.make_tree_readable", deny_permission_normalization
    )
    try:
        with pytest.raises(SandboxExecutionError) as captured:
            await runner.run_hidden_verifier_workspace(
                package,
                managed.workspace,
                run_id="permission-handoff-failure",
            )
    finally:
        managed.cleanup()

    diagnostics = captured.value.diagnostics
    assert diagnostics is not None
    assert diagnostics.failure_subtype is VerifierFailureSubtype.WORKSPACE_PERMISSION_HANDOFF_FAILED
    failed = next(
        item for item in diagnostics.stages if item.status is VerifierLifecycleStageStatus.FAILED
    )
    assert failed == VerifierLifecycleStageEvidence(
        stage=VerifierLifecycleStage.WORKSPACE_PREPARE,
        status=VerifierLifecycleStageStatus.FAILED,
        duration_ms=failed.duration_ms,
        exception_class="PermissionError",
        reason_code="VERIFIER_WORKSPACE_PERMISSION_NORMALIZATION_DENIED",
    )
    serialized = json.dumps(diagnostics.model_dump(mode="json"), sort_keys=True)
    assert "command" not in serialized
    assert "path" not in serialized
    assert "stderr" not in serialized
    assert "environment" not in serialized


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
async def test_workspace_secret_content_and_filename_are_withheld(tmp_path: Path) -> None:
    package = TaskPackage.load(PYTHON_TASK)
    runner = sandbox(tmp_path)
    cases = (
        ("phase-c-fake-workspace-credential-12345", True, False),
        ("phase-c-fake-filename-credential-67890", False, True),
    )

    for fake_secret, write_file, write_filename in cases:
        result = await runner.run_fake_subject(
            package,
            FakeSubjectRequest(
                echo_secret_name="FAKE_CREDENTIAL",
                write_secret_file=write_file,
                write_secret_filename=write_filename,
            ),
            run_id=f"workspace-secret-{uuid4().hex}",
            secrets={"FAKE_CREDENTIAL": fake_secret},
        )

        assert result.manifest.status is SandboxStatus.ARTIFACT_ERROR
        assert result.manifest.workspace_output_digest is None
        assert result.manifest.workspace_snapshot is None
        assert result.manifest.cleanup_verified
        assert not container_exists(result.container_name)
        for persisted in result.artifact_directory.rglob("*"):
            relative = persisted.relative_to(result.artifact_directory).as_posix()
            assert fake_secret not in relative
            if persisted.is_file() and not persisted.is_symlink():
                assert fake_secret.encode("utf-8") not in persisted.read_bytes()
    assert await no_harnesslab_containers()


@pytest.mark.integration
async def test_cleanup_verification_failure_cannot_report_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = TaskPackage.load(PYTHON_TASK)
    runner = sandbox(tmp_path)
    original_cleanup = runner._remove_and_verify

    async def cleanup_but_report_unverified(
        cli: _DockerCLI,
        container_name: str,
        *,
        run_id: str,
        role: str,
    ) -> bool:
        assert await original_cleanup(cli, container_name, run_id=run_id, role=role)
        return False

    monkeypatch.setattr(runner, "_remove_and_verify", cleanup_but_report_unverified)
    result = await runner.run_fake_subject(
        package,
        FakeSubjectRequest(),
        run_id=f"cleanup-unverified-{uuid4().hex}",
    )

    assert result.manifest.status is SandboxStatus.CLEANUP_ERROR
    assert not result.manifest.cleanup_verified
    assert result.manifest.workspace_output_digest is None
    assert result.manifest.workspace_snapshot is None
    assert not container_exists(result.container_name)
    invalid = result.manifest.model_dump(mode="json")
    invalid["status"] = SandboxStatus.SUCCEEDED
    with pytest.raises(ValidationError, match="success is forbidden"):
        SandboxArtifactManifest.model_validate(invalid)
    assert await no_harnesslab_containers()


async def test_cleanup_daemon_error_is_not_verified(tmp_path: Path) -> None:
    empty_digest = "sha256:" + hashlib.sha256(b"").hexdigest()

    class UnreachableDockerCLI(_DockerCLI):
        async def run(
            self,
            *arguments: str,
            timeout: float = 60,
            environment: Mapping[str, str] | None = None,
            check: bool = True,
        ) -> CommandResult:
            return CommandResult(
                1,
                b"",
                b"Cannot connect to the Docker daemon",
                empty_digest,
                empty_digest,
                False,
                False,
            )

    verified = await sandbox(tmp_path)._remove_and_verify(
        UnreachableDockerCLI(),
        "harnesslab-subject-unreachable",
        run_id="unreachable",
        role="subject",
    )
    assert not verified


@pytest.mark.integration
async def test_verifier_cleanup_failure_cannot_return_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = TaskPackage.load(PYTHON_TASK)
    runner = sandbox(tmp_path)
    subject = await runner.run_fake_subject(
        package,
        FakeSubjectRequest(),
        run_id=f"verifier-cleanup-subject-{uuid4().hex}",
    )
    original_cleanup = runner._remove_and_verify

    async def cleanup_but_report_unverified(
        cli: _DockerCLI,
        container_name: str,
        *,
        run_id: str,
        role: str,
    ) -> bool:
        assert await original_cleanup(cli, container_name, run_id=run_id, role=role)
        return False

    monkeypatch.setattr(runner, "_remove_and_verify", cleanup_but_report_unverified)
    verifier_run_id = f"verifier-cleanup-{uuid4().hex}"
    with pytest.raises(SandboxExecutionError, match="cleanup_error"):
        await runner.run_hidden_verifier(package, subject, run_id=verifier_run_id)

    manifest = json.loads(
        (runner.artifact_root / verifier_run_id / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "cleanup_error"
    assert not manifest["cleanup_verified"]
    assert manifest["workspace_snapshot"] is None
    assert await no_harnesslab_containers()


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


def test_workspace_secret_scan_detects_chunk_boundary_match(tmp_path: Path) -> None:
    fake_secret = "phase-c-fake-boundary-credential"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "large.bin").write_bytes(
        b"x" * (65_536 - 3) + fake_secret.encode("utf-8") + b"suffix"
    )

    with pytest.raises(ArtifactError, match="regular file contains an exact run secret"):
        assert_tree_has_no_run_secrets(workspace, (fake_secret,))
