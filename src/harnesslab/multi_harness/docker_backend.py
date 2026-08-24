from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from uuid import uuid4

from harnesslab.contracts.provider import validate_provider_base_url
from harnesslab.egress import ProviderScopedDockerBoundary
from harnesslab.harness_lane.adapter import HarnessAdapterError
from harnesslab.multi_harness.adapter import HarnessExecutionPlan
from harnesslab.multi_harness.models import HarnessKind, HarnessProcessCapture
from harnesslab.multi_harness.profile import CLAUDE_IMAGE, DEEPSEEK_IMAGE
from harnesslab.sandbox.docker_cli import _DockerCLI, docker_environment
from harnesslab.sandbox.preflight import _docker_runtime_preflight
from harnesslab.sandbox.subprocess_loop import run_on_subprocess_loop

OUTER_RUN_LABEL = "com.harnesslab.phase=F"
MAX_CAPTURE_BYTES = 4_000_000
MAX_LINE_BYTES = 1_000_000


class DockerMultiHarnessBackend:
    """Optional real Phase F process inside a hardened, ephemeral outer container."""

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

    @property
    def artifact_secret_values(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(value for value in self.credentials.values() if value))

    def create_argv(self, plan: HarnessExecutionPlan, container_name: str) -> tuple[str, ...]:
        image = CLAUDE_IMAGE if plan.harness is HarnessKind.CLAUDE_CODE else DEEPSEEK_IMAGE
        arguments = [
            "create",
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
            f"type=bind,src={plan.workspace.resolve()},dst=/workspace",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=128m",
        ]
        if plan.context is not None:
            arguments.extend(
                ("--mount", f"type=bind,src={plan.context.resolve()},dst=/context,readonly")
            )
        translated_sources = {source for _, source in plan.environment_references}
        for name in sorted(set(self.credentials) - translated_sources):
            arguments.extend(("--env", name))
        for name, _ in sorted((*plan.environment_references, *plan.environment_literals)):
            arguments.extend(("--env", name))
        if self.egress_boundary is not None:
            for name, value in sorted(self.egress_boundary.subject_proxy_environment().items()):
                arguments.extend(("--env", f"{name}={value}"))
        arguments.extend(("--entrypoint", plan.argv[0], image, *plan.argv[1:]))
        return tuple(arguments)

    async def run(self, plan: HarnessExecutionPlan) -> HarnessProcessCapture:
        if not self.explicitly_enabled:
            raise HarnessAdapterError(
                "real Phase F execution requires explicit opt-in; Gate F uses deterministic fakes"
            )
        return await run_on_subprocess_loop(self._run(plan))

    async def _run(self, plan: HarnessExecutionPlan) -> HarnessProcessCapture:
        preflight, environment = await _docker_runtime_preflight()
        cli = _DockerCLI(output_limit=1_000_000, environment=environment)
        name = f"harnesslab-phase-f-{uuid4().hex}"
        container_environment = dict(self.credentials)
        for target, source in plan.environment_references:
            if source not in self.credentials:
                raise HarnessAdapterError(f"missing configured credential/reference: {source}")
            value = self.credentials[source]
            if target == "ANTHROPIC_BASE_URL":
                value = validate_provider_base_url(value)
            container_environment[target] = value
        container_environment.update(plan.environment_literals)
        create_environment = docker_environment(environment, container_environment)
        started = time.monotonic()
        lines: list[str] = []
        stderr_parts: list[bytes] = []
        timed_out = False
        cancelled = False
        exit_code: int | None = None
        create_attempted = False
        try:
            if self.egress_boundary is not None:
                await self.egress_boundary.provision(cli)
            create_attempted = True
            await cli.run(*self.create_argv(plan, name), environment=create_environment)
            await self._verify_effective_security(cli, name)
            process = await asyncio.create_subprocess_exec(
                preflight.cli_path,
                "start",
                "--attach",
                name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=environment,
                limit=MAX_LINE_BYTES + 1,
            )
            assert process.stdout is not None
            assert process.stderr is not None
            stdout = process.stdout
            stderr = process.stderr

            async def read_stdout() -> None:
                total = 0
                while raw := await stdout.readline():
                    total += len(raw)
                    if len(raw) > MAX_LINE_BYTES or total > MAX_CAPTURE_BYTES:
                        process.kill()
                        return
                    try:
                        lines.append(raw.decode(errors="strict").rstrip("\r\n"))
                    except UnicodeDecodeError:
                        process.kill()
                        return

            async def read_stderr() -> None:
                total = 0
                while chunk := await stderr.read(65_536):
                    total += len(chunk)
                    if total > MAX_CAPTURE_BYTES:
                        process.kill()
                        return
                    stderr_parts.append(chunk)

            try:
                async with asyncio.timeout(plan.timeout_seconds):
                    await asyncio.gather(read_stdout(), read_stderr(), process.wait())
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
                exit_code = int(json.loads(state.stdout.decode()))
        finally:
            if create_attempted:
                await self._cleanup(cli, name)
            if self.egress_boundary is not None:
                await self.egress_boundary.cleanup(cli)
        try:
            stderr_text = b"".join(stderr_parts).decode(errors="strict")
        except UnicodeDecodeError:
            stderr_text = ""
        return HarnessProcessCapture(
            tuple(lines),
            stderr_text,
            exit_code,
            int((time.monotonic() - started) * 1000),
            timed_out,
            cancelled,
        )

    async def _cleanup(self, cli: _DockerCLI, name: str) -> None:
        await cli.run("kill", name, check=False)
        await cli.run("rm", "--force", name, check=False)
        absent = await cli.run("ps", "--all", "--quiet", "--filter", f"name=^/{name}$", check=False)
        if absent.returncode != 0 or absent.stdout.strip():
            raise HarnessAdapterError("Phase F outer-container cleanup was not verified")

    async def _verify_effective_security(self, cli: _DockerCLI, name: str) -> None:
        template = (
            "{{json .HostConfig.Privileged}}|{{json .HostConfig.ReadonlyRootfs}}|"
            "{{json .HostConfig.NetworkMode}}|{{json .Config.User}}|"
            "{{json .HostConfig.CapDrop}}|{{json .HostConfig.SecurityOpt}}"
        )
        result = await cli.run("inspect", name, "--format", template)
        values = [json.loads(value) for value in result.stdout.decode().strip().split("|")]
        if len(values) != 6:
            raise HarnessAdapterError("unexpected Phase F container inspection output")
        privileged, read_only, network, user, cap_drop, security_options = values
        if not all(
            (
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
        ):
            raise HarnessAdapterError("Phase F outer-container security profile is not effective")
