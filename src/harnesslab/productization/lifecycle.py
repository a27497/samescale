from __future__ import annotations

import asyncio
import hashlib
import http.client
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from harnesslab.sandbox.models import DockerPreflight
from harnesslab.sandbox.preflight import DockerPreflightError, docker_preflight

_PROJECT_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
EXPECTED_PRODUCT_SERVICES = frozenset({"postgres", "migrate", "api"})


class LifecycleError(RuntimeError):
    """A product lifecycle operation failed without exposing command output."""

    def __init__(
        self,
        action: str,
        detail: str,
        *,
        exit_code: int = 1,
        output_digest: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.action = action
        self.exit_code = exit_code
        self.output_digest = output_digest


class CheckState(StrEnum):
    PASS = "PASS"
    NOT_RUNNING = "NOT_RUNNING"
    FAIL = "FAIL"


@dataclass(frozen=True)
class LifecycleCheck:
    name: str
    state: CheckState
    detail: str


@dataclass(frozen=True)
class ServiceState:
    service: str
    container: str
    state: str
    health: str
    exit_code: int | None

    @property
    def ready(self) -> bool:
        state = self.state.lower()
        health = self.health.lower()
        if state == "running":
            return health not in {"starting", "unhealthy"}
        return state == "exited" and self.exit_code == 0

    @property
    def display_state(self) -> str:
        if self.state.lower() == "exited" and self.exit_code == 0:
            return "complete"
        return self.state.lower() or "unknown"


@dataclass(frozen=True)
class CommandOutput:
    returncode: int
    stdout: str
    stderr_digest: str


class CommandExecutor(Protocol):
    def run(self, arguments: Sequence[str], *, timeout: float) -> CommandOutput: ...


class EndpointKind(StrEnum):
    API = "api"
    WORKBENCH = "workbench"


class EndpointProber(Protocol):
    def probe(self, port: int, path: str, kind: EndpointKind, *, timeout: float) -> bool: ...


class LocalEndpointProber:
    """Probe fixed loopback product endpoints without following redirects or retaining bodies."""

    def probe(self, port: int, path: str, kind: EndpointKind, *, timeout: float) -> bool:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        try:
            connection.request("GET", path, headers={"Accept": "application/json,text/html"})
            response = connection.getresponse()
            body = response.read(65_537)
            if response.status != 200 or len(body) > 65_536:
                return False
            if kind is EndpointKind.API:
                payload: object = json.loads(body)
                return payload == {"status": "ok", "database": "ok"}
            content_type = response.getheader("Content-Type", "").lower()
            return "text/html" in content_type and b'id="app"' in body
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError, http.client.HTTPException):
            return False
        finally:
            connection.close()


class SubprocessExecutor:
    """Run argument-vector-only Docker commands and retain no stderr text."""

    def run(self, arguments: Sequence[str], *, timeout: float) -> CommandOutput:
        try:
            result = subprocess.run(
                list(arguments),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise LifecycleError("docker compose", type(exc).__name__) from None
        stderr_digest = "sha256:" + hashlib.sha256(result.stderr).hexdigest()
        return CommandOutput(
            returncode=result.returncode,
            stdout=result.stdout.decode("utf-8", errors="replace"),
            stderr_digest=stderr_digest,
        )


Preflight = Callable[[], DockerPreflight]


def _default_preflight() -> DockerPreflight:
    try:
        return asyncio.run(docker_preflight())
    except DockerPreflightError as exc:
        raise LifecycleError("docker preflight", str(exc), exit_code=2) from None
    except Exception as exc:
        raise LifecycleError("docker preflight", type(exc).__name__) from None


def resolve_compose_file(
    requested: Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path:
    env = os.environ if environment is None else environment
    if requested is not None:
        candidate = requested
    elif configured := env.get("HARNESSLAB_COMPOSE_FILE", "").strip():
        candidate = Path(configured)
    else:
        # Never execute a Compose file merely because it is present in an
        # operator-controlled working directory. The source distribution's
        # manifest is trusted; every external manifest requires explicit opt-in.
        source_manifest = Path(__file__).resolve().parents[3] / "docker-compose.yml"
        packaged_manifest = Path(__file__).resolve().parent / "distribution/docker-compose.yml"
        candidate = source_manifest if source_manifest.is_file() else packaged_manifest
    compose_file = candidate.expanduser().resolve()
    if not compose_file.is_file():
        raise LifecycleError(
            "compose discovery",
            "the HarnessLab Compose file does not exist; "
            "use --compose-file with a trusted distribution",
            exit_code=2,
        )
    return compose_file


class ProductLifecycle:
    """Orchestrate only the local product stack; no model or Judge path is imported."""

    def __init__(
        self,
        compose_file: Path | None = None,
        *,
        project_name: str = "harnesslab",
        executor: CommandExecutor | None = None,
        preflight: Preflight | None = None,
        endpoint_prober: EndpointProber | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if not _PROJECT_NAME.fullmatch(project_name):
            raise LifecycleError("configuration", "invalid Compose project name", exit_code=2)
        self.compose_file = resolve_compose_file(
            compose_file,
            environment=environment,
        )
        self.project_name = project_name
        self._executor = executor or SubprocessExecutor()
        self._preflight = preflight or _default_preflight
        self._endpoint_prober = endpoint_prober or LocalEndpointProber()
        self._environment = dict(os.environ if environment is None else environment)

    @property
    def _compose_prefix(self) -> tuple[str, ...]:
        return (
            "docker",
            "compose",
            "--project-name",
            self.project_name,
            "--file",
            str(self.compose_file),
            "--env-file",
            str(self._compose_env_file),
        )

    @property
    def _compose_env_file(self) -> Path:
        distribution_env = self.compose_file.parent / ".env"
        if distribution_env.is_file():
            return distribution_env
        return Path(__file__).resolve().parent / "default.env.example"

    def docker_preflight(self) -> DockerPreflight:
        return self._preflight()

    def validate(self) -> None:
        self._run("validate compose", "config", "--quiet", timeout=60)

    def up(self, *, wait_timeout: int = 180, build: bool | None = None) -> DockerPreflight:
        if wait_timeout < 1:
            raise LifecycleError("configuration", "wait timeout must be positive", exit_code=2)
        preflight = self.docker_preflight()
        self.validate()
        should_build = build
        if should_build is None:
            should_build = not bool(self._product_setting("HARNESSLAB_IMAGE", ""))
        build_option = "--build" if should_build else "--no-build"
        self._run(
            "start product stack",
            "up",
            "--detach",
            build_option,
            "--remove-orphans",
            "--wait",
            "--wait-timeout",
            str(wait_timeout),
            timeout=float(wait_timeout + 300),
        )
        services = self._status_without_preflight()
        observed = {service.service for service in services}
        if not EXPECTED_PRODUCT_SERVICES.issubset(observed):
            raise LifecycleError("readiness", "one or more required product services are missing")
        if not all(service.ready for service in services):
            raise LifecycleError("readiness", "one or more product services are not ready")
        if not all(check.state is CheckState.PASS for check in self.endpoint_checks()):
            raise LifecycleError("readiness", "API or bundled Workbench readiness failed")
        return preflight

    def down(self) -> DockerPreflight:
        preflight = self.docker_preflight()
        self.validate()
        self._run("stop product stack", "down", "--remove-orphans", timeout=180)
        return preflight

    def status(self) -> tuple[DockerPreflight, tuple[ServiceState, ...]]:
        preflight = self.docker_preflight()
        self.validate()
        return preflight, self._status_without_preflight()

    def doctor(self) -> tuple[LifecycleCheck, ...]:
        checks: list[LifecycleCheck] = []
        try:
            preflight = self.docker_preflight()
        except LifecycleError as exc:
            return (LifecycleCheck("docker", CheckState.FAIL, str(exc)),)
        checks.append(
            LifecycleCheck(
                "docker",
                CheckState.PASS,
                f"server={preflight.server_version} context={preflight.context}",
            )
        )
        try:
            self.validate()
        except LifecycleError as exc:
            checks.append(LifecycleCheck("compose", CheckState.FAIL, str(exc)))
            return tuple(checks)
        checks.append(
            LifecycleCheck(
                "compose", CheckState.PASS, f"project={self.project_name} configuration valid"
            )
        )
        try:
            services = self._status_without_preflight()
        except LifecycleError as exc:
            checks.append(LifecycleCheck("services", CheckState.FAIL, str(exc)))
            return tuple(checks)
        service_checks = self._service_checks(services)
        checks.extend(service_checks)
        if all(check.state is CheckState.PASS for check in service_checks):
            checks.extend(self.endpoint_checks())
        else:
            checks.extend(
                (
                    LifecycleCheck("api-health", CheckState.NOT_RUNNING, "services not ready"),
                    LifecycleCheck("workbench", CheckState.NOT_RUNNING, "services not ready"),
                )
            )
        checks.append(LifecycleCheck("provider-calls", CheckState.PASS, "disabled for lifecycle"))
        checks.append(LifecycleCheck("judge-calls", CheckState.PASS, "disabled for lifecycle"))
        return tuple(checks)

    def endpoint_checks(self) -> tuple[LifecycleCheck, LifecycleCheck]:
        try:
            port = self.product_port()
        except LifecycleError as exc:
            failure = LifecycleCheck("api-health", CheckState.FAIL, str(exc))
            return failure, LifecycleCheck("workbench", CheckState.FAIL, str(exc))
        api_ready = self._endpoint_prober.probe(port, "/api/health", EndpointKind.API, timeout=3)
        workbench_ready = self._endpoint_prober.probe(port, "/", EndpointKind.WORKBENCH, timeout=3)
        return (
            LifecycleCheck(
                "api-health",
                CheckState.PASS if api_ready else CheckState.FAIL,
                f"http://127.0.0.1:{port}/api/health",
            ),
            LifecycleCheck(
                "workbench",
                CheckState.PASS if workbench_ready else CheckState.FAIL,
                f"http://127.0.0.1:{port}/",
            ),
        )

    def _service_checks(self, services: tuple[ServiceState, ...]) -> tuple[LifecycleCheck, ...]:
        by_name = {service.service: service for service in services}
        checks: list[LifecycleCheck] = []
        for service_name, display_name in (
            ("postgres", "postgresql"),
            ("migrate", "migration"),
            ("api", "api-container"),
        ):
            service = by_name.get(service_name)
            if service is None:
                state = CheckState.NOT_RUNNING if not services else CheckState.FAIL
                detail = "NOT_CONFIGURED; run `harnesslab up`" if not services else "missing"
            elif service.ready:
                state = CheckState.PASS
                detail = service.display_state
                if service.health:
                    detail += f" health={service.health}"
            else:
                state = CheckState.FAIL
                detail = service.display_state
                if service.health:
                    detail += f" health={service.health}"
            checks.append(LifecycleCheck(display_name, state, detail))
        return tuple(checks)

    def product_port(self) -> int:
        raw = self._product_setting("HARNESSLAB_PORT", "8000")
        try:
            port = int(raw)
        except ValueError:
            raise LifecycleError("configuration", "HARNESSLAB_PORT must be an integer") from None
        if not 1 <= port <= 65_535:
            raise LifecycleError("configuration", "HARNESSLAB_PORT is outside the valid range")
        return port

    def _product_setting(self, name: str, default: str) -> str:
        if name in self._environment:
            configured = self._environment[name].strip()
            return configured or default
        dotenv = self._compose_env_file
        try:
            lines = dotenv.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return default
        except OSError:
            raise LifecycleError("configuration", "the product .env file is unreadable") from None
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line.removeprefix("export ").lstrip()
            key, separator, value = line.partition("=")
            if separator and key.strip() == name:
                normalized = value.strip()
                if (
                    len(normalized) >= 2
                    and normalized[0] == normalized[-1]
                    and normalized[0]
                    in {
                        "'",
                        '"',
                    }
                ):
                    normalized = normalized[1:-1]
                elif " #" in normalized:
                    normalized = normalized.split(" #", 1)[0].rstrip()
                return normalized or default
        return default

    def _status_without_preflight(self) -> tuple[ServiceState, ...]:
        output = self._run("inspect product stack", "ps", "--all", "--format", "json", timeout=60)
        return parse_compose_status(output.stdout)

    def _run(self, action: str, *arguments: str, timeout: float) -> CommandOutput:
        output = self._executor.run((*self._compose_prefix, *arguments), timeout=timeout)
        if output.returncode != 0:
            raise LifecycleError(
                action,
                f"{action} failed (exit {output.returncode})",
                output_digest=output.stderr_digest,
            )
        return output


def parse_compose_status(raw: str) -> tuple[ServiceState, ...]:
    text = raw.strip()
    if not text:
        return ()
    try:
        parsed: object = json.loads(text)
        records = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        records = []
        for line in text.splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                raise LifecycleError(
                    "inspect product stack", "Docker returned invalid status data"
                ) from None
    services: list[ServiceState] = []
    for record in records:
        if not isinstance(record, dict):
            raise LifecycleError("inspect product stack", "Docker returned invalid status data")
        exit_code: object = record.get("ExitCode")
        try:
            normalized_exit = (
                int(exit_code) if isinstance(exit_code, (int, str)) and exit_code != "" else None
            )
        except (TypeError, ValueError):
            normalized_exit = None
        services.append(
            ServiceState(
                service=str(record.get("Service") or "unknown"),
                container=str(record.get("Name") or record.get("ID") or "unknown"),
                state=str(record.get("State") or "unknown"),
                health=str(record.get("Health") or ""),
                exit_code=normalized_exit,
            )
        )
    return tuple(sorted(services, key=lambda service: (service.service, service.container)))
