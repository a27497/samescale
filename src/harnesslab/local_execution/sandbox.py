from __future__ import annotations

from pathlib import Path
from typing import Any

from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.models import ImageIdentity, IsolatedVerifierResult, SecurityEvidence
from harnesslab.sandbox.preflight import _docker_runtime_preflight
from harnesslab.sandbox.runner import SANDBOX_IMAGE, DockerSandbox, SandboxExecutionError
from harnesslab.tasks.package import TaskPackage


class PinnedVerifierSandbox(DockerSandbox):
    """Existing verifier runner, with no build/pull path and exact content-ID selection."""

    def __init__(
        self,
        *,
        image_id: str,
        run_id: str,
        runtime_root: Path,
        artifact_root: Path,
        force_timeout: bool = False,
    ) -> None:
        super().__init__(runtime_root=runtime_root, artifact_root=artifact_root)
        self.image_id = image_id
        self.verifier_run_id = run_id + "-verifier"
        self.force_timeout = force_timeout

    async def _prepare_image(self) -> tuple[ImageIdentity, dict[str, str]]:
        _, environment = await _docker_runtime_preflight()
        cli = _DockerCLI(environment=environment)
        inspected = await cli.run("image", "inspect", self.image_id, "--format", "{{.Id}}")
        if inspected.stdout.decode().strip() != self.image_id:
            raise SandboxExecutionError("Verifier image identity changed")
        return ImageIdentity(reference=SANDBOX_IMAGE, image_id=self.image_id), environment

    def _create_arguments(self, **kwargs: Any) -> tuple[str, ...]:
        argv = list(super()._create_arguments(**kwargs))
        argv[1:1] = ["--pull", "never"]
        argv[argv.index(SANDBOX_IMAGE)] = self.image_id
        if self.force_timeout:
            index = argv.index(self.image_id)
            argv[index + 1 :] = ["-c", "import time; time.sleep(30)"]
        return tuple(argv)

    async def run_hidden_verifier_workspace(
        self,
        package: TaskPackage,
        workspace: Path,
        *,
        timeout_seconds: float = 15,
        run_id: str | None = None,
        secret_values: tuple[str, ...] = (),
    ) -> IsolatedVerifierResult:
        return await super().run_hidden_verifier_workspace(
            package,
            workspace,
            timeout_seconds=min(timeout_seconds, 1) if self.force_timeout else timeout_seconds,
            run_id=self.verifier_run_id,
            secret_values=secret_values,
        )

    async def _inspect_security(self, cli: _DockerCLI, container_name: str) -> SecurityEvidence:
        security = await super()._inspect_security(cli, container_name)
        allowed = {"/workspace", "/verifier"}
        binds = [m for m in security.mounts if m.mount_type == "bind"]
        if (
            set(m.destination for m in binds) != allowed
            or any(m.read_write for m in binds)
            or security.privileged
            or not security.read_only_rootfs
            or security.docker_socket_mounted
            or security.network_mode != "none"
            or security.memory_bytes != 134217728
            or security.nano_cpus != 500000000
            or security.pids_limit != 64
            or security.user != "10001:10001"
            or security.published_ports
            or security.device_count
            or security.pid_mode
            or "ALL" not in security.cap_drop
            or "no-new-privileges=true" not in security.security_options
        ):
            raise SandboxExecutionError("Verifier mount/resource/security attestation failed")
        return security
