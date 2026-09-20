from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from uuid import uuid4

from harnesslab.contracts.provider import validate_provider_base_url
from harnesslab.egress import ProviderScopedDockerBoundary, ProxySecurityAttestation
from harnesslab.harness_lane.adapter import CodexExecutionPlan, HarnessAdapterError
from harnesslab.harness_lane.models import (
    CodexBackendFailureEvidence,
    CodexBackendFailurePhase,
    CodexCleanupFailure,
    CodexCleanupFailureScope,
    CodexProcessCapture,
    CodexStreamDiagnosticCategory,
)
from harnesslab.sandbox.docker_cli import _DockerCLI, docker_environment
from harnesslab.sandbox.preflight import _docker_runtime_preflight
from harnesslab.sandbox.subprocess_loop import run_on_subprocess_loop

OUTER_RUN_LABEL = "com.harnesslab.phase=E"
MAX_CAPTURE_BYTES = 4_000_000
MAX_LINE_BYTES = 1_000_000


class CodexBackendExecutionError(HarnessAdapterError):
    """Typed safe backend failure whose string form never includes process output."""

    def __init__(self, evidence: CodexBackendFailureEvidence) -> None:
        self.evidence = evidence
        cleanup = "+CLEANUP" if evidence.cleanup_failures else ""
        if evidence.phase is CodexBackendFailurePhase.CLEANUP:
            message = "real Codex cleanup was not verified: CLEANUP"
        else:
            message = f"Codex backend execution failed: {evidence.phase.value}{cleanup}"
        super().__init__(message)

    def with_cleanup_failures(
        self, failures: tuple[CodexCleanupFailure, ...]
    ) -> CodexBackendExecutionError:
        return CodexBackendExecutionError(
            self.evidence.model_copy(
                update={"cleanup_failures": self.evidence.cleanup_failures + failures}
            )
        )


@dataclass
class _StreamCapture:
    lines: list[str] = field(default_factory=list)
    stdout: bytearray = field(default_factory=bytearray)
    stderr: bytearray = field(default_factory=bytearray)
    stdout_category: CodexStreamDiagnosticCategory = CodexStreamDiagnosticCategory.EMPTY
    stderr_category: CodexStreamDiagnosticCategory = CodexStreamDiagnosticCategory.EMPTY

    def evidence(
        self,
        phase: CodexBackendFailurePhase,
        *,
        started: float,
        exit_code: int | None = None,
        timed_out: bool = False,
        cancelled: bool = False,
        cleanup_failures: tuple[CodexCleanupFailure, ...] = (),
    ) -> CodexBackendFailureEvidence:
        return CodexBackendFailureEvidence(
            phase=phase,
            exit_code=exit_code,
            timed_out=timed_out,
            cancelled=cancelled,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            stdout_category=self.stdout_category,
            stdout_digest="sha256:" + hashlib.sha256(self.stdout).hexdigest(),
            stderr_category=self.stderr_category,
            stderr_digest="sha256:" + hashlib.sha256(self.stderr).hexdigest(),
            cleanup_failures=cleanup_failures,
        )


class _AttachedProcessFailure(Exception):
    def __init__(self, phase: CodexBackendFailurePhase) -> None:
        self.phase = phase
        super().__init__(phase.value)


class DockerCodexBackend:
    """Optional real Codex process backend inside the HarnessLab outer Docker boundary.

    Gate E never selects it for provider execution. Production callers must explicitly supply the
    provider-scoped proxy boundary; otherwise the outer network remains ``none``.
    """

    def __init__(
        self,
        *,
        explicitly_enabled: bool = False,
        credentials: Mapping[str, str] | None = None,
        egress_boundary: ProviderScopedDockerBoundary | None = None,
    ) -> None:
        self.explicitly_enabled = explicitly_enabled
        self.credentials = dict(credentials or {})
        self.egress_boundary = egress_boundary
        self.egress_attestation: ProxySecurityAttestation | None = None

    @property
    def artifact_secret_values(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(value for value in self.credentials.values() if value))

    def create_argv(self, plan: CodexExecutionPlan, container_name: str) -> tuple[str, ...]:
        workspace_mount = f"type=bind,src={plan.workspace.resolve()},dst=/workspace"
        arguments = [
            "create",
            "--interactive",
            "--name",
            container_name,
            "--label",
            OUTER_RUN_LABEL,
            "--label",
            f"com.harnesslab.run_id={container_name}",
            "--network",
            (
                self.egress_boundary.subject_network_mode
                if self.egress_boundary is not None
                else "none"
            ),
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--memory",
            "1g",
            "--cpus",
            "2",
            "--pids-limit",
            "256",
            "--restart",
            "no",
            "--user",
            "10001:10001",
            "--workdir",
            "/workspace",
            "--mount",
            workspace_mount,
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=64m",
        ]
        if plan.context is not None:
            arguments.extend(
                (
                    "--mount",
                    f"type=bind,src={plan.context.resolve()},dst=/context,readonly",
                )
            )
        translated_sources = {source for _, source in plan.environment_references}
        for name in sorted(set(self.credentials) - translated_sources):
            arguments.extend(("--env", name))
        for name, _ in sorted(plan.environment_references):
            arguments.extend(("--env", name))
        if self.egress_boundary is not None:
            for name, value in sorted(self.egress_boundary.subject_proxy_environment().items()):
                arguments.extend(("--env", f"{name}={value}"))
        arguments.extend(
            (
                "--entrypoint",
                "/usr/local/bin/harnesslab-codex-runtime",
                plan.image_reference,
                *plan.argv[1:],
            )
        )
        return tuple(arguments)

    async def run(self, plan: CodexExecutionPlan) -> CodexProcessCapture:
        if not self.explicitly_enabled:
            raise HarnessAdapterError(
                "real Codex execution requires explicit operator opt-in and auth configuration"
            )
        return await run_on_subprocess_loop(self._run(plan))

    async def _run(self, plan: CodexExecutionPlan) -> CodexProcessCapture:
        started = time.monotonic()
        try:
            preflight, environment = await _docker_runtime_preflight()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            raise self._failure(CodexBackendFailurePhase.UNKNOWN, started=started) from exc
        cli = _DockerCLI(output_limit=1_000_000, environment=environment)
        name = f"harnesslab-codex-{uuid4().hex}"
        container_environment = dict(self.credentials)
        for target, source in plan.environment_references:
            if source not in self.credentials:
                raise self._failure(CodexBackendFailurePhase.CONTAINER_CREATE, started=started)
            value = self.credentials[source]
            if target in {"HARNESSLAB_GPT56_RELAY_BASE_URL", "HARNESSLAB_CODEX_RELAY_BASE_URL"}:
                try:
                    value = validate_provider_base_url(value)
                except ValueError as exc:
                    raise self._failure(
                        CodexBackendFailurePhase.CONTAINER_CREATE, started=started
                    ) from exc
            container_environment[target] = value
        create_environment = docker_environment(environment, container_environment)
        create_attempted = False
        capture: CodexProcessCapture | None = None
        primary_failure: CodexBackendExecutionError | None = None
        cancellation: asyncio.CancelledError | None = None
        try:
            try:
                if self.egress_boundary is not None:
                    try:
                        self.egress_attestation = await self.egress_boundary.provision(cli)
                    except asyncio.CancelledError:
                        raise
                    except BaseException as exc:
                        raise self._failure(
                            CodexBackendFailurePhase.EGRESS_PROVISION, started=started
                        ) from exc
                create_attempted = True
                try:
                    await cli.run(*self.create_argv(plan, name), environment=create_environment)
                except asyncio.CancelledError:
                    raise
                except BaseException as exc:
                    raise self._failure(
                        CodexBackendFailurePhase.CONTAINER_CREATE, started=started
                    ) from exc
                try:
                    await self._verify_effective_security(cli, name)
                except asyncio.CancelledError:
                    raise
                except BaseException as exc:
                    raise self._failure(
                        CodexBackendFailurePhase.SECURITY_ATTEST, started=started
                    ) from exc
                capture = await self._execute_attached_process(
                    preflight.cli_path,
                    name,
                    plan,
                    environment,
                    started=started,
                )
                if capture.timed_out or capture.cancelled:
                    capture = CodexProcessCapture(
                        lines=capture.lines,
                        exit_code=None,
                        duration_ms=capture.duration_ms,
                        timed_out=capture.timed_out,
                        cancelled=capture.cancelled,
                    )
                else:
                    try:
                        state = await cli.run(
                            "inspect", name, "--format", "{{json .State.ExitCode}}", check=False
                        )
                        if state.returncode != 0:
                            raise ValueError("container exit state unavailable")
                        exit_code = int(json.loads(state.stdout.decode("utf-8")))
                        capture = CodexProcessCapture(
                            lines=capture.lines,
                            exit_code=exit_code,
                            duration_ms=capture.duration_ms,
                            timed_out=capture.timed_out,
                            cancelled=capture.cancelled,
                        )
                    except asyncio.CancelledError:
                        raise
                    except BaseException as exc:
                        raise self._failure(
                            CodexBackendFailurePhase.PROCESS_EXIT,
                            started=started,
                            capture=capture,
                        ) from exc
            except CodexBackendExecutionError as exc:
                primary_failure = exc
            except asyncio.CancelledError as exc:
                cancellation = exc
            except BaseException:
                primary_failure = self._failure(CodexBackendFailurePhase.UNKNOWN, started=started)
        finally:
            cleanup_failures = await self._collect_cleanup_failures(
                cli, name, create_attempted=create_attempted
            )
        if primary_failure is not None:
            if cleanup_failures:
                primary_failure = primary_failure.with_cleanup_failures(cleanup_failures)
            raise primary_failure
        if cancellation is not None:
            if cleanup_failures:
                raise self._failure(
                    CodexBackendFailurePhase.CLEANUP,
                    started=started,
                    cancelled=True,
                    cleanup_failures=cleanup_failures,
                ) from cancellation
            raise cancellation
        if cleanup_failures:
            raise self._failure(
                CodexBackendFailurePhase.CLEANUP,
                started=started,
                capture=capture,
                cleanup_failures=cleanup_failures,
            )
        if capture is None:
            raise self._failure(CodexBackendFailurePhase.UNKNOWN, started=started)
        return capture

    async def _execute_attached_process(
        self,
        cli_path: str,
        name: str,
        plan: CodexExecutionPlan,
        environment: Mapping[str, str],
        *,
        started: float | None = None,
    ) -> CodexProcessCapture:
        """Start and capture docker attach without retaining raw stderr."""

        effective_started = time.monotonic() if started is None else started
        streams = _StreamCapture()
        try:
            process = await asyncio.create_subprocess_exec(
                cli_path,
                "start",
                "--attach",
                "--interactive",
                name,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=environment,
                limit=MAX_LINE_BYTES + 1,
            )
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            raise CodexBackendExecutionError(
                streams.evidence(
                    CodexBackendFailurePhase.CONTAINER_START,
                    started=effective_started,
                )
            ) from exc
        if process.stdin is None or process.stdout is None or process.stderr is None:
            self._kill_process(process)
            raise CodexBackendExecutionError(
                streams.evidence(
                    CodexBackendFailurePhase.CONTAINER_START,
                    started=effective_started,
                )
            )
        stdin = process.stdin
        stdout = process.stdout
        stderr = process.stderr

        async def read_stdout() -> None:
            try:
                while raw := await stdout.readline():
                    streams.stdout.extend(raw)
                    streams.stdout_category = CodexStreamDiagnosticCategory.PRESENT
                    if len(raw) > MAX_LINE_BYTES or len(streams.stdout) > MAX_CAPTURE_BYTES:
                        streams.stdout_category = CodexStreamDiagnosticCategory.TRUNCATED
                        streams.lines.append("{malformed-capture-limit")
                        self._kill_process(process)
                        return
                    try:
                        streams.lines.append(raw.decode("utf-8", errors="strict").rstrip("\r\n"))
                    except UnicodeDecodeError:
                        streams.lines.append("{malformed-utf8")
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                streams.stdout_category = CodexStreamDiagnosticCategory.READ_FAILED
                raise _AttachedProcessFailure(CodexBackendFailurePhase.STDOUT_READ) from exc

        async def read_stderr() -> None:
            try:
                while chunk := await stderr.read(65_536):
                    remaining = MAX_CAPTURE_BYTES - len(streams.stderr)
                    if remaining > 0:
                        streams.stderr.extend(chunk[:remaining])
                    streams.stderr_category = CodexStreamDiagnosticCategory.PRESENT
                    if len(chunk) > remaining:
                        streams.stderr_category = CodexStreamDiagnosticCategory.TRUNCATED
                        self._kill_process(process)
                        return
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                streams.stderr_category = CodexStreamDiagnosticCategory.READ_FAILED
                raise _AttachedProcessFailure(CodexBackendFailurePhase.STDERR_READ) from exc

        async def wait_process() -> None:
            try:
                await process.wait()
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                raise _AttachedProcessFailure(CodexBackendFailurePhase.PROCESS_WAIT) from exc

        tasks = (
            asyncio.create_task(read_stdout()),
            asyncio.create_task(read_stderr()),
            asyncio.create_task(wait_process()),
        )
        timed_out = False
        cancelled = False
        failure: _AttachedProcessFailure | None = None
        try:
            async with asyncio.timeout(plan.timeout_seconds):
                try:
                    stdin.write(plan.prompt.encode("utf-8"))
                    await stdin.drain()
                    stdin.close()
                except asyncio.CancelledError:
                    raise
                except BaseException as exc:
                    raise _AttachedProcessFailure(CodexBackendFailurePhase.STDIN_WRITE) from exc
                await asyncio.gather(*tasks)
        except TimeoutError:
            timed_out = True
        except asyncio.CancelledError:
            cancelled = True
        except _AttachedProcessFailure as exc:
            failure = exc
        finally:
            if timed_out or cancelled or failure is not None:
                self._kill_process(process)
            with suppress(BaseException):
                stdin.close()
            await asyncio.gather(*tasks, return_exceptions=True)
        duration_ms = max(0, int((time.monotonic() - effective_started) * 1000))
        if failure is not None:
            raise CodexBackendExecutionError(
                streams.evidence(
                    failure.phase,
                    started=effective_started,
                    exit_code=process.returncode,
                )
            ) from failure
        return CodexProcessCapture(
            lines=tuple(streams.lines),
            exit_code=None if timed_out or cancelled else process.returncode,
            duration_ms=duration_ms,
            timed_out=timed_out,
            cancelled=cancelled,
        )

    @staticmethod
    def _kill_process(process: asyncio.subprocess.Process) -> None:
        with suppress(ProcessLookupError, RuntimeError):
            process.kill()

    @staticmethod
    def _failure(
        phase: CodexBackendFailurePhase,
        *,
        started: float,
        capture: CodexProcessCapture | None = None,
        cancelled: bool = False,
        cleanup_failures: tuple[CodexCleanupFailure, ...] = (),
    ) -> CodexBackendExecutionError:
        return CodexBackendExecutionError(
            CodexBackendFailureEvidence(
                phase=phase,
                exit_code=None if capture is None else capture.exit_code,
                timed_out=False if capture is None else capture.timed_out,
                cancelled=cancelled or (False if capture is None else capture.cancelled),
                duration_ms=max(0, int((time.monotonic() - started) * 1000)),
                cleanup_failures=cleanup_failures,
            )
        )

    async def _cleanup_execution(
        self, cli: _DockerCLI, name: str, *, create_attempted: bool
    ) -> None:
        """Attempt every cleanup layer even when an earlier layer raises."""

        failures = await self._collect_cleanup_failures(
            cli, name, create_attempted=create_attempted
        )
        if failures:
            raise CodexBackendExecutionError(
                CodexBackendFailureEvidence(
                    phase=CodexBackendFailurePhase.CLEANUP,
                    duration_ms=0,
                    cleanup_failures=failures,
                )
            )

    async def _collect_cleanup_failures(
        self, cli: _DockerCLI, name: str, *, create_attempted: bool
    ) -> tuple[CodexCleanupFailure, ...]:
        """Attempt every cleanup layer and return only bounded, non-message facts."""

        cleanup_failures: list[CodexCleanupFailure] = []
        if create_attempted:
            try:
                await self._cleanup_outer_container(cli, name)
            except BaseException as exc:
                cleanup_failures.append(
                    CodexCleanupFailure(
                        scope=CodexCleanupFailureScope.SUBJECT,
                        error_type=type(exc).__name__,
                    )
                )
        if self.egress_boundary is not None:
            try:
                await self.egress_boundary.cleanup(cli)
            except BaseException as exc:
                cleanup_failures.append(
                    CodexCleanupFailure(
                        scope=CodexCleanupFailureScope.EGRESS,
                        error_type=type(exc).__name__,
                    )
                )
        return tuple(cleanup_failures)

    async def _cleanup_outer_container(self, cli: _DockerCLI, name: str) -> None:
        await cli.run("kill", name, check=False)
        await cli.run("rm", "--force", name, check=False)
        absent = await cli.run(
            "ps",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            f"name=^/{name}$",
            check=False,
        )
        if absent.returncode != 0 or absent.stdout.strip():
            raise HarnessAdapterError("real Codex outer container cleanup was not verified")

    async def _verify_effective_security(self, cli: _DockerCLI, name: str) -> None:
        template = (
            "{{json .HostConfig.Privileged}}|{{json .HostConfig.ReadonlyRootfs}}|"
            "{{json .HostConfig.NetworkMode}}|{{json .Config.User}}|"
            "{{json .HostConfig.CapDrop}}|{{json .HostConfig.SecurityOpt}}"
        )
        inspected = await cli.run("inspect", name, "--format", template)
        values = [
            json.loads(value) for value in inspected.stdout.decode("utf-8").strip().split("|")
        ]
        if len(values) != 6:
            raise HarnessAdapterError("unexpected Codex outer-container inspection output")
        privileged, read_only, network, user, cap_drop, security_options = values
        required = (
            not privileged,
            read_only,
            network
            == (
                self.egress_boundary.subject_network_mode
                if self.egress_boundary is not None
                else "none"
            ),
            user == "10001:10001",
            "ALL" in (cap_drop or ()),
            "no-new-privileges=true" in (security_options or ()),
        )
        if not all(required):
            raise HarnessAdapterError("Codex outer-container security profile is not effective")

        mounts = await cli.run(
            "inspect",
            name,
            "--format",
            "{{range .Mounts}}{{json .Destination}}{{println}}{{end}}",
        )
        destinations = {
            json.loads(line) for line in mounts.stdout.decode("utf-8").splitlines() if line
        }
        if not destinations.issubset({"/workspace", "/context"}):
            raise HarnessAdapterError("Codex outer container received an undeclared host mount")


async def cleanup_phase_e_containers() -> None:
    """Best-effort test helper for a cancelled backend construction path."""

    with suppress(Exception):
        _, environment = await _docker_runtime_preflight()
        cli = _DockerCLI(output_limit=1_000_000, environment=environment)
        listed = await cli.run(
            "ps", "--all", "--quiet", "--filter", f"label={OUTER_RUN_LABEL}", check=False
        )
        for container_id in listed.stdout.decode("utf-8").split():
            await cli.run("rm", "--force", container_id, check=False)
