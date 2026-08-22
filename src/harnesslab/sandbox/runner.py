from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from harnesslab.sandbox.artifacts import (
    ArtifactError,
    ArtifactWriter,
    assert_managed_path,
    assert_tree_has_no_run_secrets,
    make_tree_writable,
    redact_exact,
)
from harnesslab.sandbox.docker_cli import (
    CommandResult,
    DockerCommandError,
    DockerCommandTimeout,
    _DockerCLI,
    docker_environment,
)
from harnesslab.sandbox.models import (
    FakeSubjectRequest,
    ImageIdentity,
    IsolatedVerifierResult,
    MountEvidence,
    SandboxRunResult,
    SandboxStatus,
    SecurityEvidence,
)
from harnesslab.sandbox.preflight import _docker_runtime_preflight
from harnesslab.sandbox.subprocess_loop import run_on_subprocess_loop
from harnesslab.tasks.models import VerifierReport
from harnesslab.tasks.package import TaskPackage, digest_tree

SANDBOX_IMAGE = "harnesslab-phase-c:0.1.0"
RUN_LABEL = "com.harnesslab.phase=C"
OUTPUT_LIMIT_BYTES = 65_536


class SandboxExecutionError(RuntimeError):
    """The trusted Docker lifecycle could not produce a run result."""


def _trusted_subject_script(request: FakeSubjectRequest) -> str:
    operations = [
        "import os, pathlib, sys, time",
        "workspace = pathlib.Path('/workspace')",
        "assert not pathlib.Path('/verifier').exists()",
        "assert not pathlib.Path('/oracle').exists()",
    ]
    if request.require_marker_absent:
        operations.append(
            "assert not (workspace / 'phase-c-marker.txt').exists(), 'workspace was reused'"
        )
    if request.solve_python_clamp:
        operations.append(
            "(workspace / 'calculator.py').write_text("
            '"def clamp(value: int, lower: int, upper: int) -> int:\\n"'
            '"    return max(lower, min(value, upper))\\n", encoding="utf-8")'
        )
    if request.write_marker:
        operations.append(
            "(workspace / 'phase-c-marker.txt').write_text('run marker', encoding='utf-8')"
        )
    if request.echo_secret_name is not None:
        operations.extend(
            (
                f"secret = os.environ[{request.echo_secret_name!r}]",
                "print('stdout-secret=' + secret)",
                "print('stderr-secret=' + secret, file=sys.stderr)",
            )
        )
        if request.write_secret_file:
            operations.append(
                "(workspace / 'subject-secret.txt').write_text(secret, encoding='utf-8')"
            )
        if request.write_secret_filename:
            operations.append("(workspace / secret).write_text('fixture', encoding='utf-8')")
    if request.create_unsafe_symlink:
        operations.append("os.symlink('/etc/passwd', workspace / 'unsafe-link')")
    if request.output_bytes:
        operations.append(f"print('x' * {request.output_bytes})")
    if request.sleep_seconds:
        operations.append(f"time.sleep({request.sleep_seconds!r})")
    operations.append("print('fake-subject-complete')")
    return "\n".join(operations)


class DockerSandbox:
    def __init__(
        self,
        *,
        runtime_root: Path | None = None,
        artifact_root: Path | None = None,
    ) -> None:
        base = Path(tempfile.gettempdir()) / "harnesslab-phase-c"
        self.runtime_root = (runtime_root or base / "runtime").resolve()
        self.artifact_root = (artifact_root or base / "artifacts").resolve()
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    async def ensure_image(self) -> ImageIdentity:
        return await run_on_subprocess_loop(self._ensure_image())

    async def _ensure_image(self) -> ImageIdentity:
        image, _ = await self._prepare_image()
        return image

    async def _prepare_image(self) -> tuple[ImageIdentity, dict[str, str]]:
        _, docker_cli_environment = await _docker_runtime_preflight()
        cli = _DockerCLI(
            output_limit=OUTPUT_LIMIT_BYTES,
            environment=docker_cli_environment,
        )
        inspected = await cli.run("image", "inspect", SANDBOX_IMAGE, check=False)
        if inspected.returncode != 0:
            repository_root = Path(__file__).resolve().parents[3]
            docker_context = repository_root / "docker" / "sandbox"
            await cli.run(
                "build",
                "--tag",
                SANDBOX_IMAGE,
                str(docker_context),
                timeout=300,
            )
        return await self._image_identity(cli), docker_cli_environment

    async def _image_identity(self, cli: _DockerCLI) -> ImageIdentity:
        result = await cli.run(
            "image",
            "inspect",
            SANDBOX_IMAGE,
            "--format",
            "{{json .Id}}|{{json .RepoDigests}}",
        )
        image_id_raw, repo_digests_raw = result.stdout.decode("utf-8").strip().split("|", 1)
        return ImageIdentity(
            reference=SANDBOX_IMAGE,
            image_id=json.loads(image_id_raw),
            repo_digests=tuple(json.loads(repo_digests_raw) or ()),
        )

    async def run_fake_subject(
        self,
        package: TaskPackage,
        request: FakeSubjectRequest,
        *,
        timeout_seconds: float = 15,
        run_id: str | None = None,
        secrets: Mapping[str, str] | None = None,
    ) -> SandboxRunResult:
        return await run_on_subprocess_loop(
            self._run_fake_subject(
                package,
                request,
                timeout_seconds=timeout_seconds,
                run_id=run_id or uuid4().hex,
                secrets=secrets or {},
            )
        )

    async def _run_fake_subject(
        self,
        package: TaskPackage,
        request: FakeSubjectRequest,
        *,
        timeout_seconds: float,
        run_id: str,
        secrets: Mapping[str, str],
    ) -> SandboxRunResult:
        run_root = self._reserve_run_root(run_id)
        materialized = None
        try:
            writer = ArtifactWriter(self.artifact_root, run_id)
            materialized = package.materialize(run_root)
            workspace = assert_managed_path(self.runtime_root, materialized.workspace)
            make_tree_writable(workspace)
            workspace_input_digest = digest_tree(workspace)
            subject_mounts: tuple[tuple[Path, str, bool], ...] = ()
            if materialized.context is not None:
                context = assert_managed_path(self.runtime_root, materialized.context)
                digest_tree(context)
                subject_mounts = ((context, "/context", True),)
            return await self._execute_container(
                package=package,
                role="subject",
                run_id=run_id,
                workspace=workspace,
                workspace_read_only=False,
                additional_mounts=subject_mounts,
                command=("-c", _trusted_subject_script(request)),
                timeout_seconds=timeout_seconds,
                secrets=secrets,
                workspace_input_digest=workspace_input_digest,
                writer=writer,
            )
        finally:
            if materialized is not None:
                materialized.cleanup()
            self._cleanup_run_root(run_root)

    async def run_hidden_verifier(
        self,
        package: TaskPackage,
        subject_run: SandboxRunResult,
        *,
        timeout_seconds: float = 15,
        run_id: str | None = None,
    ) -> IsolatedVerifierResult:
        return await run_on_subprocess_loop(
            self._run_hidden_verifier(
                package,
                subject_run,
                timeout_seconds=timeout_seconds,
                run_id=run_id or uuid4().hex,
            )
        )

    async def _run_hidden_verifier(
        self,
        package: TaskPackage,
        subject_run: SandboxRunResult,
        *,
        timeout_seconds: float,
        run_id: str,
    ) -> IsolatedVerifierResult:
        workspace = subject_run.artifact_directory / "workspace"
        assert_managed_path(self.artifact_root, workspace)
        if not workspace.is_dir():
            raise ArtifactError("subject workspace artifact is unavailable")
        return await self._run_hidden_verifier_workspace(
            package,
            workspace,
            timeout_seconds=timeout_seconds,
            run_id=run_id,
            secret_values=(),
        )

    async def run_hidden_verifier_workspace(
        self,
        package: TaskPackage,
        workspace: Path,
        *,
        timeout_seconds: float = 15,
        run_id: str | None = None,
        secret_values: tuple[str, ...] = (),
    ) -> IsolatedVerifierResult:
        """Verify a trusted-runner workspace through the existing isolated boundary."""

        return await run_on_subprocess_loop(
            self._run_hidden_verifier_workspace(
                package,
                workspace.resolve(),
                timeout_seconds=timeout_seconds,
                run_id=run_id or uuid4().hex,
                secret_values=secret_values,
            )
        )

    async def _run_hidden_verifier_workspace(
        self,
        package: TaskPackage,
        workspace: Path,
        *,
        timeout_seconds: float,
        run_id: str,
        secret_values: tuple[str, ...],
    ) -> IsolatedVerifierResult:
        if not workspace.is_dir() or workspace.is_symlink():
            raise ArtifactError("verifier workspace is unavailable or unsafe")
        assert_tree_has_no_run_secrets(workspace, secret_values)
        verifier_root = package.root / "verifier"
        entrypoint = package.verifier_entrypoint.relative_to(verifier_root).as_posix()
        writer = ArtifactWriter(self.artifact_root, run_id)
        workspace_input_digest = digest_tree(workspace)
        run = await self._execute_container(
            package=package,
            role="verifier",
            run_id=run_id,
            workspace=workspace,
            workspace_read_only=True,
            additional_mounts=((verifier_root, "/verifier", True),),
            command=(f"/verifier/{entrypoint}", "/workspace"),
            timeout_seconds=timeout_seconds,
            secrets={},
            workspace_input_digest=workspace_input_digest,
            writer=writer,
        )
        if run.manifest.status is not SandboxStatus.SUCCEEDED:
            raise SandboxExecutionError(
                f"isolated verifier sandbox did not succeed: {run.manifest.status.value}"
            )
        try:
            report = VerifierReport.model_validate_json(run.stdout)
        except ValidationError as exc:
            raise SandboxExecutionError("isolated verifier returned malformed output") from exc
        return IsolatedVerifierResult(run=run, passed=report.passed, score=report.score)

    async def _execute_container(
        self,
        *,
        package: TaskPackage,
        role: str,
        run_id: str,
        workspace: Path,
        workspace_read_only: bool,
        additional_mounts: tuple[tuple[Path, str, bool], ...],
        command: tuple[str, ...],
        timeout_seconds: float,
        secrets: Mapping[str, str],
        workspace_input_digest: str,
        writer: ArtifactWriter,
    ) -> SandboxRunResult:
        image, docker_cli_environment = await self._prepare_image()
        cli = _DockerCLI(
            output_limit=OUTPUT_LIMIT_BYTES,
            environment=docker_cli_environment,
        )
        try:
            create_environment = docker_environment(docker_cli_environment, secrets)
        except ValueError as exc:
            raise SandboxExecutionError(str(exc)) from exc
        container_name = f"harnesslab-{role}-{run_id}"
        security: SecurityEvidence | None = None
        stdout = b""
        stderr = b""
        empty_digest = (
            "sha256:" + "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        stdout_stream_digest = empty_digest
        stderr_stream_digest = empty_digest
        stdout_truncated = False
        stderr_truncated = False
        exit_code: int | None = None
        status = SandboxStatus.FAILED
        summary = "container did not start"
        timed_out = False
        cancelled = False
        cleanup_verified = False
        create_attempted = False
        started = time.monotonic()
        cancellation: asyncio.CancelledError | None = None
        try:
            create_arguments = self._create_arguments(
                role=role,
                run_id=run_id,
                container_name=container_name,
                workspace=workspace,
                workspace_read_only=workspace_read_only,
                additional_mounts=additional_mounts,
                secret_names=tuple(secrets),
                command=command,
            )
            create_attempted = True
            await cli.run(
                *create_arguments,
                environment=create_environment,
            )
            security = await self._inspect_security(cli, container_name)
            try:
                attached = await cli.run(
                    "start", "--attach", container_name, timeout=timeout_seconds, check=False
                )
                stdout, stderr = attached.stdout, attached.stderr
                stdout_stream_digest = attached.stdout_digest
                stderr_stream_digest = attached.stderr_digest
                stdout_truncated = attached.stdout_truncated
                stderr_truncated = attached.stderr_truncated
                exit_code = await self._container_exit_code(cli, container_name)
                status = SandboxStatus.SUCCEEDED if exit_code == 0 else SandboxStatus.FAILED
                summary = "container completed" if exit_code == 0 else "container exited non-zero"
            except DockerCommandTimeout as exc:
                stdout, stderr = exc.result.stdout, exc.result.stderr
                stdout_stream_digest = exc.result.stdout_digest
                stderr_stream_digest = exc.result.stderr_digest
                stdout_truncated = exc.result.stdout_truncated
                stderr_truncated = exc.result.stderr_truncated
                status = SandboxStatus.TIMEOUT
                timed_out = True
                summary = "container execution timed out"
            except asyncio.CancelledError as exc:
                status = SandboxStatus.CANCELLED
                cancelled = True
                summary = "container execution cancelled"
                cancellation = exc
        except DockerCommandError as exc:
            stdout, stderr = exc.result.stdout, exc.result.stderr
            stdout_stream_digest = exc.result.stdout_digest
            stderr_stream_digest = exc.result.stderr_digest
            stdout_truncated = exc.result.stdout_truncated
            stderr_truncated = exc.result.stderr_truncated
            summary = redact_exact(str(exc), secrets.values())
        except asyncio.CancelledError as exc:
            status = SandboxStatus.CANCELLED
            cancelled = True
            summary = "container execution cancelled"
            cancellation = exc
            if security is None and await self._is_owned_container(
                cli, container_name, run_id=run_id, role=role
            ):
                security = await self._inspect_security(cli, container_name)
        finally:
            if create_attempted:
                cleanup_verified = await self._remove_and_verify(
                    cli, container_name, run_id=run_id, role=role
                )

        if security is None:
            if cancellation is not None:
                if not cleanup_verified:
                    raise SandboxExecutionError(
                        "container cleanup could not be verified after cancellation"
                    )
                raise cancellation
            raise SandboxExecutionError(redact_exact(summary, secrets.values()))
        duration_ms = int((time.monotonic() - started) * 1000)
        result = writer.finalize(
            package=package,
            role=role,
            container_name=container_name,
            workspace=workspace,
            workspace_input_digest=workspace_input_digest,
            image=image,
            security=security,
            status=status,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out,
            cancelled=cancelled,
            cleanup_verified=cleanup_verified,
            stdout=stdout,
            stderr=stderr,
            stdout_stream_digest=stdout_stream_digest,
            stderr_stream_digest=stderr_stream_digest,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            summary=summary,
            secrets=secrets.values(),
        )
        if cancellation is not None:
            if not cleanup_verified:
                raise SandboxExecutionError(
                    "container cleanup could not be verified after cancellation"
                )
            raise cancellation
        return result

    def _create_arguments(
        self,
        *,
        role: str,
        run_id: str,
        container_name: str,
        workspace: Path,
        workspace_read_only: bool,
        additional_mounts: tuple[tuple[Path, str, bool], ...],
        secret_names: tuple[str, ...],
        command: tuple[str, ...],
    ) -> tuple[str, ...]:
        mount = f"type=bind,src={workspace},dst=/workspace"
        if workspace_read_only:
            mount += ",readonly"
        arguments = [
            "create",
            "--name",
            container_name,
            "--label",
            RUN_LABEL,
            "--label",
            f"com.harnesslab.run_id={run_id}",
            "--label",
            f"com.harnesslab.role={role}",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--memory",
            "128m",
            "--cpus",
            "0.5",
            "--pids-limit",
            "64",
            "--restart",
            "no",
            "--user",
            "10001:10001",
            "--workdir",
            "/workspace",
            "--mount",
            mount,
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size=16m",
        ]
        for source, destination, read_only in additional_mounts:
            mount_value = f"type=bind,src={source.resolve()},dst={destination}"
            if read_only:
                mount_value += ",readonly"
            arguments.extend(("--mount", mount_value))
        for name in secret_names:
            arguments.extend(("--env", name))
        arguments.extend((SANDBOX_IMAGE, *command))
        return tuple(arguments)

    async def _inspect_security(self, cli: _DockerCLI, container_name: str) -> SecurityEvidence:
        template = (
            "{{json .HostConfig.Privileged}}|{{json .HostConfig.ReadonlyRootfs}}|"
            "{{json .HostConfig.CapDrop}}|{{json .HostConfig.SecurityOpt}}|"
            "{{json .HostConfig.NetworkMode}}|{{json .HostConfig.Memory}}|"
            "{{json .HostConfig.NanoCpus}}|{{json .HostConfig.PidsLimit}}|"
            "{{json .HostConfig.RestartPolicy.Name}}|{{json .Config.User}}|"
            "{{json .HostConfig.PidMode}}|{{json .HostConfig.PortBindings}}|"
            "{{json .HostConfig.Devices}}|{{json .HostConfig.Tmpfs}}"
        )
        result = await cli.run("inspect", container_name, "--format", template)
        values = result.stdout.decode("utf-8").strip().split("|")
        if len(values) != 14:
            raise SandboxExecutionError("unexpected Docker security inspection output")
        decoded = [json.loads(value) for value in values]
        mount_result = await cli.run(
            "inspect",
            container_name,
            "--format",
            "{{range .Mounts}}{{json .Destination}}|{{json .RW}}|{{json .Type}}{{println}}{{end}}",
        )
        mounts = tuple(
            MountEvidence(
                destination=json.loads(parts[0]),
                read_write=json.loads(parts[1]),
                mount_type=json.loads(parts[2]),
            )
            for line in mount_result.stdout.decode("utf-8").splitlines()
            if (parts := line.split("|")) and len(parts) == 3
        )
        security_options = tuple(decoded[3] or ())
        return SecurityEvidence(
            privileged=decoded[0],
            read_only_rootfs=decoded[1],
            cap_drop=tuple(decoded[2] or ()),
            security_options=security_options,
            network_mode=decoded[4],
            memory_bytes=decoded[5],
            nano_cpus=decoded[6],
            pids_limit=decoded[7],
            restart_policy=decoded[8],
            user=decoded[9],
            pid_mode=decoded[10],
            published_ports=bool(decoded[11]),
            device_count=len(decoded[12] or ()),
            mounts=mounts,
            tmpfs_destinations=tuple(sorted((decoded[13] or {}).keys())),
            docker_socket_mounted=any(
                mount.destination in {"/var/run/docker.sock", "/run/docker.sock"}
                for mount in mounts
            ),
            seccomp_unconfined=any("seccomp=unconfined" in option for option in security_options),
        )

    async def _container_exit_code(self, cli: _DockerCLI, container_name: str) -> int:
        result = await cli.run("inspect", container_name, "--format", "{{json .State.ExitCode}}")
        return int(json.loads(result.stdout.decode("utf-8")))

    async def _is_owned_container(
        self,
        cli: _DockerCLI,
        container_name: str,
        *,
        run_id: str,
        role: str,
    ) -> bool:
        inspected = await cli.run(
            "inspect",
            container_name,
            "--format",
            "{{json .Config.Labels}}",
            check=False,
        )
        if inspected.returncode != 0:
            return False
        labels = json.loads(inspected.stdout.decode("utf-8")) or {}
        return (
            labels.get("com.harnesslab.phase") == "C"
            and labels.get("com.harnesslab.run_id") == run_id
            and labels.get("com.harnesslab.role") == role
        )

    async def _remove_and_verify(
        self,
        cli: _DockerCLI,
        container_name: str,
        *,
        run_id: str,
        role: str,
    ) -> bool:
        if not await self._is_owned_container(cli, container_name, run_id=run_id, role=role):
            return await self._container_absent(cli, container_name)
        await cli.run("kill", container_name, check=False)
        await cli.run("rm", "--force", container_name, check=False)
        return await self._container_absent(cli, container_name)

    async def _container_absent(self, cli: _DockerCLI, container_name: str) -> bool:
        listed = await cli.run(
            "ps",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            f"name=^/{container_name}$",
            check=False,
        )
        return listed.returncode == 0 and not listed.stdout.strip()

    def _reserve_run_root(self, run_id: str) -> Path:
        if not run_id or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in run_id
        ):
            raise ArtifactError("run_id must use lowercase ASCII letters, digits, or hyphens")
        run_root = self.runtime_root / run_id
        run_root.mkdir(exist_ok=False)
        return assert_managed_path(self.runtime_root, run_root)

    def _cleanup_run_root(self, run_root: Path) -> None:
        managed = assert_managed_path(self.runtime_root, run_root)
        if managed.exists():
            shutil.rmtree(managed)


async def no_harnesslab_containers() -> bool:
    async def check() -> bool:
        cli = _DockerCLI()
        result: CommandResult = await cli.run(
            "ps", "--all", "--quiet", "--filter", f"label={RUN_LABEL}"
        )
        return not result.stdout.strip()

    return await run_on_subprocess_loop(check())
