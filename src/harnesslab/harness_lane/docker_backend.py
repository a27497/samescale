from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from contextlib import suppress
from uuid import uuid4

from harnesslab.harness_lane.adapter import CodexExecutionPlan, HarnessAdapterError
from harnesslab.harness_lane.models import CodexProcessCapture
from harnesslab.harness_lane.profile import CODEX_IMAGE
from harnesslab.sandbox.docker_cli import _DockerCLI, docker_environment
from harnesslab.sandbox.preflight import _docker_runtime_preflight
from harnesslab.sandbox.subprocess_loop import run_on_subprocess_loop

OUTER_RUN_LABEL = "com.harnesslab.phase=E"
MAX_CAPTURE_BYTES = 4_000_000
MAX_LINE_BYTES = 1_000_000


class DockerCodexBackend:
    """Optional real Codex process backend inside the HarnessLab outer Docker boundary.

    It is deliberately not selected by Gate E. The outer network remains ``none`` because Phase E
    cannot yet prove control-plane-only network separation for the pinned Codex sandbox.
    """

    def __init__(
        self,
        *,
        explicitly_enabled: bool = False,
        credentials: Mapping[str, str] | None = None,
    ) -> None:
        self.explicitly_enabled = explicitly_enabled
        self.credentials = dict(credentials or {})

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
            "none",
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
        for name in sorted(self.credentials):
            arguments.extend(("--env", name))
        arguments.extend(("--entrypoint", "codex", CODEX_IMAGE, *plan.argv[1:]))
        return tuple(arguments)

    async def run(self, plan: CodexExecutionPlan) -> CodexProcessCapture:
        if not self.explicitly_enabled:
            raise HarnessAdapterError(
                "real Codex execution requires explicit operator opt-in and auth configuration"
            )
        return await run_on_subprocess_loop(self._run(plan))

    async def _run(self, plan: CodexExecutionPlan) -> CodexProcessCapture:
        preflight, environment = await _docker_runtime_preflight()
        cli = _DockerCLI(output_limit=1_000_000, environment=environment)
        name = f"harnesslab-codex-{uuid4().hex}"
        create_environment = docker_environment(environment, self.credentials)
        create_attempted = False
        started = time.monotonic()
        lines: list[str] = []
        timed_out = False
        cancelled = False
        exit_code: int | None = None
        try:
            create_attempted = True
            await cli.run(*self.create_argv(plan, name), environment=create_environment)
            await self._verify_effective_security(cli, name)
            process = await asyncio.create_subprocess_exec(
                preflight.cli_path,
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
            assert process.stdin is not None
            assert process.stdout is not None
            assert process.stderr is not None
            stdout = process.stdout
            stderr = process.stderr
            process.stdin.write(plan.prompt.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()

            async def read_stdout() -> None:
                total = 0
                while raw := await stdout.readline():
                    total += len(raw)
                    if len(raw) > MAX_LINE_BYTES or total > MAX_CAPTURE_BYTES:
                        lines.append("{malformed-capture-limit")
                        process.kill()
                        return
                    try:
                        lines.append(raw.decode("utf-8", errors="strict").rstrip("\r\n"))
                    except UnicodeDecodeError:
                        lines.append("{malformed-utf8")

            async def drain_stderr() -> None:
                total = 0
                while chunk := await stderr.read(65_536):
                    total += len(chunk)
                    if total > MAX_CAPTURE_BYTES:
                        process.kill()
                        return

            try:
                async with asyncio.timeout(plan.timeout_seconds):
                    await asyncio.gather(read_stdout(), drain_stderr(), process.wait())
            except TimeoutError:
                timed_out = True
                process.kill()
                await process.wait()
            except asyncio.CancelledError:
                cancelled = True
                process.kill()
                await process.wait()
            state = await cli.run(
                "inspect", name, "--format", "{{json .State.ExitCode}}", check=False
            )
            if state.returncode == 0:
                exit_code = int(json.loads(state.stdout.decode("utf-8")))
        finally:
            if create_attempted:
                await self._cleanup_outer_container(cli, name)
        return CodexProcessCapture(
            lines=tuple(lines),
            exit_code=exit_code,
            duration_ms=int((time.monotonic() - started) * 1000),
            timed_out=timed_out,
            cancelled=cancelled,
        )

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
            network == "none",
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
