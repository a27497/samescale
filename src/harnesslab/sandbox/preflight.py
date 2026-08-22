from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
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


def resolve_effective_endpoint(
    context_endpoint: str,
    environment: Mapping[str, str],
) -> str:
    """Resolve the endpoint with the same environment precedence as Docker CLI."""
    if environment.get("DOCKER_CONTEXT"):
        return context_endpoint
    if docker_host := environment.get("DOCKER_HOST"):
        return docker_host
    return context_endpoint


def context_selection_environment(environment: Mapping[str, str]) -> dict[str, str]:
    selected = dict(environment)
    if selected.get("DOCKER_CONTEXT"):
        selected.pop("DOCKER_HOST", None)
    return selected


def pin_local_docker_environment(
    environment: Mapping[str, str],
    endpoint: str,
) -> dict[str, str]:
    pinned = dict(environment)
    for name in (
        "DOCKER_CONTEXT",
        "DOCKER_HOST",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    ):
        pinned.pop(name, None)
    pinned["DOCKER_HOST"] = endpoint
    return pinned


async def _docker_runtime_preflight(
    environment: Mapping[str, str] | None = None,
) -> tuple[DockerPreflight, dict[str, str]]:
    executable = shutil.which("docker")
    if executable is None:
        raise DockerPreflightError("Docker CLI is not installed or not on PATH")
    source_environment = dict(environment) if environment is not None else os.environ.copy()
    selection_environment = context_selection_environment(source_environment)
    selection_cli = _DockerCLI(executable, environment=selection_environment)
    context_result = await selection_cli.run("context", "show")
    context = context_result.stdout.decode("utf-8", errors="replace").strip()
    endpoint_result = await selection_cli.run(
        "context", "inspect", context, "--format", "{{json .Endpoints.docker.Host}}"
    )
    context_endpoint = json.loads(endpoint_result.stdout.decode("utf-8"))
    endpoint = resolve_effective_endpoint(context_endpoint, source_environment)
    endpoint_scheme = validate_local_endpoint(endpoint)
    pinned_environment = pin_local_docker_environment(source_environment, endpoint)
    cli = _DockerCLI(executable, environment=pinned_environment)
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
    return (
        DockerPreflight(
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
        ),
        pinned_environment,
    )


async def _docker_preflight() -> DockerPreflight:
    preflight, _ = await _docker_runtime_preflight()
    return preflight


async def docker_preflight() -> DockerPreflight:
    return await run_on_subprocess_loop(_docker_preflight())
