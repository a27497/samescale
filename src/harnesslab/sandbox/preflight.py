from __future__ import annotations

import json
import shutil
from urllib.parse import urlparse

from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.models import DockerPreflight
from harnesslab.sandbox.subprocess_loop import run_on_subprocess_loop


class DockerPreflightError(RuntimeError):
    """Docker cannot provide the supported local Linux-container boundary."""


def validate_local_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    scheme = parsed.scheme.lower()
    if scheme not in {"unix", "npipe"}:
        raise DockerPreflightError(
            f"unsupported Docker endpoint scheme {scheme or 'unknown'}; local unix/npipe required"
        )
    return scheme


async def _docker_preflight() -> DockerPreflight:
    executable = shutil.which("docker")
    if executable is None:
        raise DockerPreflightError("Docker CLI is not installed or not on PATH")
    cli = _DockerCLI(executable)
    context_result = await cli.run("context", "show")
    context = context_result.stdout.decode("utf-8", errors="replace").strip()
    endpoint_result = await cli.run(
        "context", "inspect", context, "--format", "{{json .Endpoints.docker.Host}}"
    )
    endpoint = json.loads(endpoint_result.stdout.decode("utf-8"))
    endpoint_scheme = validate_local_endpoint(endpoint)
    version_result = await cli.run("version", "--format", "{{json .}}")
    version = json.loads(version_result.stdout.decode("utf-8"))
    server = version.get("Server")
    if not isinstance(server, dict):
        raise DockerPreflightError("Docker daemon is unreachable")
    if server.get("Os") != "linux":
        raise DockerPreflightError("Docker daemon must run Linux containers")
    info_result = await cli.run(
        "info",
        "--format",
        "{{json .OperatingSystem}}|{{json .OSType}}|{{json .Architecture}}|"
        "{{json .SecurityOptions}}",
    )
    operating_system_raw, os_type_raw, architecture_raw, security_options_raw = (
        info_result.stdout.decode("utf-8").strip().split("|", 3)
    )
    operating_system = json.loads(operating_system_raw)
    os_type = json.loads(os_type_raw)
    architecture = json.loads(architecture_raw)
    security_options = json.loads(security_options_raw) or []
    default_seccomp = any("seccomp" in option for option in security_options)
    if not default_seccomp:
        raise DockerPreflightError("Docker daemon does not report the default seccomp boundary")
    client = version.get("Client") or {}
    return DockerPreflight(
        ready=True,
        cli_path=executable,
        client_version=str(client.get("Version", "unknown")),
        server_version=str(server.get("Version", "unknown")),
        context=context,
        endpoint_scheme=endpoint_scheme,
        server_os=str(os_type),
        server_arch=str(architecture),
        operating_system=str(operating_system),
        default_seccomp=default_seccomp,
    )


async def docker_preflight() -> DockerPreflight:
    return await run_on_subprocess_loop(_docker_preflight())
