"""Frozen Codex executable against a private, network-none protocol double.

This is FAKE_CODEX synthetic evidence, never subscription inference. The controller
has a separate PID/mount namespace; Subject sees only a loopback HTTP/SSE endpoint.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from harnesslab.harness_lane.adapter import CodexExecutionPlan, HarnessAdapterError
from harnesslab.harness_lane.docker_backend import DockerCodexBackend
from harnesslab.harness_lane.models import CodexProcessCapture
from harnesslab.local_execution.models import ExecutionPolicy
from harnesslab.local_plans.tasks import no_links
from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.preflight import _docker_runtime_preflight
from harnesslab.sandbox.subprocess_loop import run_on_subprocess_loop


class OfflineProtocolCodexBackend(DockerCodexBackend):
    def __init__(self, policy: ExecutionPolicy, run_id: str, authorization_digest: str) -> None:
        if not policy.protocol_stub or policy.protocol_limits is None:
            raise HarnessAdapterError("Offline protocol policy and limits required")
        super().__init__(explicitly_enabled=True, credentials={})
        self.policy = policy
        self.run_id = run_id
        self.authorization_digest = authorization_digest
        self.controller_name = "harnesslab-subscription-stub-" + run_id
        self.controller_id: str | None = None
        self.workspace: Path | None = None

    def container_name(self, plan: CodexExecutionPlan) -> str:
        return "harnesslab-local-" + self.run_id

    def create_argv(self, plan: CodexExecutionPlan, container_name: str) -> tuple[str, ...]:
        argv = list(super().create_argv(plan, container_name))
        argv[1:1] = ["--pull", "never"]
        if self.controller_id is None:
            raise HarnessAdapterError("Isolated offline controller must precede Subject")
        argv[argv.index("--network") + 1] = "container:" + self.controller_id
        argv[argv.index("--entrypoint") :] = [
            "--entrypoint",
            "python3",
            self.policy.subject_image_identity,
            "-c",
            "import os,pathlib,sys; pathlib.Path('/tmp/codex-home').mkdir(mode=0o700); "
            "pathlib.Path('/tmp/home').mkdir(mode=0o700); "
            "os.execvp('codex',['codex',*sys.argv[1:]])",
            *plan.argv[1:],
        ]
        return tuple(argv)

    async def run(self, plan: CodexExecutionPlan) -> CodexProcessCapture:
        if plan.task_id != "micro-python-clamp" or plan.context is not None:
            raise HarnessAdapterError("Protocol double supports only the trusted clamp fixture")
        self.workspace = plan.workspace.resolve()
        limits = self.policy.protocol_limits
        assert limits is not None
        model = plan.argv[plan.argv.index("--model") + 1]
        argv = (
            *plan.argv,
            "-c",
            'model_provider="samescale_offline_stub"',
            "-c",
            'model_providers.samescale_offline_stub.name="Offline protocol double"',
            "-c",
            'model_providers.samescale_offline_stub.base_url="http://127.0.0.1:8765/v1"',
            "-c",
            'model_providers.samescale_offline_stub.wire_api="responses"',
            "-c",
            "model_providers.samescale_offline_stub.requires_openai_auth=false",
            "-c",
            "model_providers.samescale_offline_stub.supports_websockets=false",
            "-c",
            "model_providers.samescale_offline_stub.request_max_retries=0",
            "-c",
            "model_providers.samescale_offline_stub.stream_max_retries=0",
        )
        selected = replace(
            plan, argv=argv, timeout_seconds=min(plan.timeout_seconds, limits.wall_time_seconds)
        )
        return await run_on_subprocess_loop(self._protocol_run(selected, model))

    async def _protocol_run(self, plan: CodexExecutionPlan, model: str) -> CodexProcessCapture:
        _, environment = await _docker_runtime_preflight()
        cli = _DockerCLI(environment=environment)
        root = self.policy.runtime_root / (self.run_id + "-controller")
        no_links(root)
        root.mkdir(mode=0o700)
        control, receipts = root / "control", root / "receipts"
        control.mkdir(mode=0o755)
        receipts.mkdir(mode=0o777)
        receipts.chmod(0o777)  # Only this container receives the scoped receipt directory.
        script = control / "broker.py"
        script.write_bytes(Path(__file__).with_name("subscription_protocol.py").read_bytes())
        script.chmod(0o644)
        limits = self.policy.protocol_limits
        assert limits is not None
        spec = {
            "run_id": self.run_id,
            "authorization_digest": self.authorization_digest,
            "model": model,
            "max_requests": limits.max_requests,
            "wall_time_seconds": min(plan.timeout_seconds, limits.wall_time_seconds),
            "scenario": self.policy.protocol_scenario,
        }
        (control / "policy.json").write_text(json.dumps(spec))
        (control / "policy.json").chmod(0o644)
        try:
            created = await cli.run(
                "create",
                "--pull",
                "never",
                "--name",
                self.controller_name,
                "--label",
                "com.harnesslab.phase=E",
                "--label",
                "com.harnesslab.role=offline-subscription-controller",
                "--label",
                "com.harnesslab.run_id=" + self.controller_name,
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
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=32m",
                "--mount",
                f"type=bind,src={control},dst=/control,readonly",
                "--mount",
                f"type=bind,src={receipts},dst=/receipts",
                "--entrypoint",
                "python3",
                self.policy.verifier_image_identity,
                "/control/broker.py",
            )
            self.controller_id = created.stdout.decode().strip()
            await self._attest_controller(cli, control, receipts)
            await cli.run("start", self.controller_name)
            # Private loopback health check, inside the controller's network-none namespace.
            for _ in range(20):
                ready = await cli.run(
                    "exec",
                    self.controller_name,
                    "python3",
                    "-c",
                    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health').close()",
                    check=False,
                )
                if ready.returncode == 0:
                    break
                await asyncio.sleep(0.05)
            else:
                raise HarnessAdapterError("Offline controller did not become ready")
            return await self._run(plan)
        finally:
            # No cancellation receipt until both Subject and controller are absent.
            await self._cleanup_controller(cli)
            journal = receipts / "controller.json"
            if journal.is_file():
                no_links(journal)
                target = self.policy.artifact_root / (self.run_id + ".protocol.json")
                no_links(target)
                with target.open("xb") as stream:
                    stream.write(journal.read_bytes())

    async def _cleanup_controller(self, cli: _DockerCLI) -> None:
        inspected = await cli.run("inspect", self.controller_name, check=False)
        if inspected.returncode == 0:
            d = json.loads(inspected.stdout)[0]
            labels = d["Config"].get("Labels", {})
            if (
                labels.get("com.harnesslab.run_id") != self.controller_name
                or labels.get("com.harnesslab.role") != "offline-subscription-controller"
                or labels.get("com.harnesslab.phase") != "E"
                or (self.controller_id is not None and d["Id"] != self.controller_id)
            ):
                raise HarnessAdapterError("Refuse cleanup of an unowned controller")
            await self._cleanup_outer_container(cli, self.controller_name)
        else:
            absent = await cli.run(
                "ps", "--all", "--quiet", "--filter", f"name=^/{self.controller_name}$"
            )
            if absent.stdout.strip():
                raise HarnessAdapterError("Controller absence could not be established")

    async def _attest_controller(self, cli: _DockerCLI, control: Path, receipts: Path) -> None:
        observed = json.loads((await cli.run("inspect", self.controller_name)).stdout)[0]
        self._security(
            observed, "none", self.policy.verifier_image_identity, 134217728, 500000000, 64
        )
        binds = [m for m in observed["Mounts"] if m["Type"] == "bind"]
        if len(binds) != 2 or {(m["Source"], m["Destination"], m["RW"]) for m in binds} != {
            (str(control), "/control", False),
            (str(receipts), "/receipts", True),
        }:
            raise HarnessAdapterError("Controller mount attestation failed")

    @staticmethod
    def _security(
        d: dict[str, Any], network: str, image: str, memory: int, cpus: int, pids: int
    ) -> None:
        host, config = d["HostConfig"], d["Config"]
        if (
            d["Image"] != image
            or host["NetworkMode"] != network
            or host["Privileged"]
            or not host["ReadonlyRootfs"]
            or config["User"] != "10001:10001"
            or host["Memory"] != memory
            or host["NanoCpus"] != cpus
            or host["PidsLimit"] != pids
            or host["RestartPolicy"]["Name"] != "no"
            or host.get("PidMode")
            or host.get("Devices")
            or host.get("PortBindings")
            or "ALL" not in host["CapDrop"]
            or "no-new-privileges=true" not in host["SecurityOpt"]
            or any(
                any(x in e.split("=", 1)[0] for x in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
                for e in config.get("Env", [])
            )
        ):
            raise HarnessAdapterError("Offline controller/Subject isolation attestation failed")

    async def _verify_effective_security(self, cli: _DockerCLI, name: str) -> None:
        d = json.loads((await cli.run("inspect", name)).stdout)[0]
        self._security(
            d,
            "container:" + str(self.controller_id),
            self.policy.subject_image_identity,
            1073741824,
            2000000000,
            256,
        )
        binds = [m for m in d["Mounts"] if m["Type"] == "bind"]
        if (
            len(binds) != 1
            or binds[0]["Source"] != str(self.workspace)
            or binds[0]["Destination"] != "/workspace"
            or not binds[0]["RW"]
        ):
            raise HarnessAdapterError("Subject has undeclared mounts")
