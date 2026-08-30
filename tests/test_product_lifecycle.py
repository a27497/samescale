from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harnesslab.cli import app
from harnesslab.productization.lifecycle import (
    CheckState,
    CommandOutput,
    EndpointKind,
    LifecycleError,
    ProductLifecycle,
    parse_compose_status,
    resolve_compose_file,
)
from harnesslab.sandbox.models import DockerPreflight


class FakeExecutor:
    def __init__(self, status: str = "[]") -> None:
        self.status = status
        self.calls: list[tuple[tuple[str, ...], float]] = []
        self.failure: tuple[str, str] | None = None

    def run(self, arguments: Sequence[str], *, timeout: float) -> CommandOutput:
        args = tuple(arguments)
        self.calls.append((args, timeout))
        if self.failure is not None and self.failure[0] in args:
            secret = self.failure[1]
            digest = hashlib.sha256(secret.encode()).hexdigest()
            return CommandOutput(17, "", "sha256:" + digest)
        stdout = self.status if "ps" in args else ""
        return CommandOutput(0, stdout, "sha256:empty")


class FakeEndpointProber:
    def __init__(self, *, api: bool = True, workbench: bool = True) -> None:
        self.results = {EndpointKind.API: api, EndpointKind.WORKBENCH: workbench}
        self.calls: list[tuple[int, str, EndpointKind, float]] = []

    def probe(self, port: int, path: str, kind: EndpointKind, *, timeout: float) -> bool:
        self.calls.append((port, path, kind, timeout))
        return self.results[kind]


def docker_ready() -> DockerPreflight:
    return DockerPreflight(
        ready=True,
        cli_path="/usr/bin/docker",
        client_version="28.0.0",
        server_version="28.0.0",
        context="default",
        endpoint_scheme="unix",
        server_os="linux",
        server_arch="amd64",
        operating_system="Docker",
        default_seccomp=True,
    )


@pytest.fixture
def compose_file(tmp_path: Path) -> Path:
    path = tmp_path / "compose.yaml"
    path.write_text("services: {}\n", encoding="utf-8")
    return path


def running_status() -> str:
    return json.dumps(
        [
            {
                "Service": "api",
                "Name": "harnesslab-api-1",
                "State": "running",
                "Health": "healthy",
                "ExitCode": 0,
            },
            {
                "Service": "migrate",
                "Name": "harnesslab-migrate-1",
                "State": "exited",
                "Health": "",
                "ExitCode": 0,
            },
            {
                "Service": "postgres",
                "Name": "harnesslab-postgres-1",
                "State": "running",
                "Health": "healthy",
                "ExitCode": 0,
            },
        ]
    )


def test_up_preflights_validates_waits_and_checks_readiness(compose_file: Path) -> None:
    executor = FakeExecutor(running_status())
    endpoints = FakeEndpointProber()
    lifecycle = ProductLifecycle(
        compose_file, executor=executor, preflight=docker_ready, endpoint_prober=endpoints
    )

    lifecycle.up(wait_timeout=45)

    calls = [call for call, _timeout in executor.calls]
    assert calls[0][-2:] == ("config", "--quiet")
    assert calls[1][-7:] == (
        "up",
        "--detach",
        "--build",
        "--remove-orphans",
        "--wait",
        "--wait-timeout",
        "45",
    )
    assert calls[2][-4:] == ("ps", "--all", "--format", "json")
    assert all(
        "provider" not in argument and "judge" not in argument
        for call in calls
        for argument in call
    )
    assert [(port, path, kind) for port, path, kind, _ in endpoints.calls] == [
        (8000, "/api/health", EndpointKind.API),
        (8000, "/", EndpointKind.WORKBENCH),
    ]


def test_up_is_idempotent_compose_up_without_destructive_volume_flags(compose_file: Path) -> None:
    executor = FakeExecutor(running_status())
    lifecycle = ProductLifecycle(
        compose_file,
        executor=executor,
        preflight=docker_ready,
        endpoint_prober=FakeEndpointProber(),
    )

    lifecycle.up()
    lifecycle.up()

    up_calls = [call for call, _ in executor.calls if "up" in call]
    assert len(up_calls) == 2
    assert all(
        "--force-recreate" not in call and "--renew-anon-volumes" not in call for call in up_calls
    )


def test_prebuilt_image_disables_source_build(compose_file: Path) -> None:
    executor = FakeExecutor(running_status())
    lifecycle = ProductLifecycle(
        compose_file,
        executor=executor,
        preflight=docker_ready,
        endpoint_prober=FakeEndpointProber(),
        environment={"HARNESSLAB_IMAGE": "registry.example/harnesslab@sha256:" + "1" * 64},
    )

    lifecycle.up()

    up_call = next(call for call, _ in executor.calls if "up" in call)
    assert "--no-build" in up_call
    assert "--build" not in up_call


def test_down_preserves_volumes_and_is_repeatable(compose_file: Path) -> None:
    executor = FakeExecutor()
    lifecycle = ProductLifecycle(compose_file, executor=executor, preflight=docker_ready)

    lifecycle.down()
    lifecycle.down()

    down_calls = [call for call, _ in executor.calls if "down" in call]
    assert len(down_calls) == 2
    assert all(call[-2:] == ("down", "--remove-orphans") for call in down_calls)
    assert all("--volumes" not in call for call in down_calls)


def test_status_supports_compose_json_lines_and_one_shot_migration() -> None:
    raw = "\n".join(
        [
            json.dumps(
                {"Service": "postgres", "Name": "db", "State": "running", "Health": "healthy"}
            ),
            json.dumps(
                {"Service": "migrate", "Name": "migration", "State": "exited", "ExitCode": 0}
            ),
        ]
    )

    services = parse_compose_status(raw)

    assert [service.service for service in services] == ["migrate", "postgres"]
    assert all(service.ready for service in services)
    assert services[0].display_state == "complete"


def test_doctor_distinguishes_not_running_from_invalid_or_unhealthy(compose_file: Path) -> None:
    executor = FakeExecutor()
    lifecycle = ProductLifecycle(compose_file, executor=executor, preflight=docker_ready)

    checks = lifecycle.doctor()

    assert [(check.name, check.state) for check in checks] == [
        ("docker", CheckState.PASS),
        ("compose", CheckState.PASS),
        ("postgresql", CheckState.NOT_RUNNING),
        ("migration", CheckState.NOT_RUNNING),
        ("api-container", CheckState.NOT_RUNNING),
        ("api-health", CheckState.NOT_RUNNING),
        ("workbench", CheckState.NOT_RUNNING),
        ("provider-calls", CheckState.PASS),
        ("judge-calls", CheckState.PASS),
    ]


def test_doctor_probes_api_and_bundled_workbench_without_echoing_bodies(
    compose_file: Path,
) -> None:
    secret_body = "private-response-body"
    endpoints = FakeEndpointProber(workbench=False)
    lifecycle = ProductLifecycle(
        compose_file,
        executor=FakeExecutor(running_status()),
        preflight=docker_ready,
        endpoint_prober=endpoints,
        environment={"HARNESSLAB_PORT": "8123"},
    )

    checks = lifecycle.doctor()

    assert [(check.name, check.state) for check in checks[2:7]] == [
        ("postgresql", CheckState.PASS),
        ("migration", CheckState.PASS),
        ("api-container", CheckState.PASS),
        ("api-health", CheckState.PASS),
        ("workbench", CheckState.FAIL),
    ]
    assert [(port, path) for port, path, _kind, _timeout in endpoints.calls] == [
        (8123, "/api/health"),
        (8123, "/"),
    ]
    assert secret_body not in " ".join(check.detail for check in checks)


def test_product_port_uses_compose_dotenv_when_process_environment_is_unset(
    compose_file: Path,
) -> None:
    (compose_file.parent / ".env").write_text("HARNESSLAB_PORT='8124'\n", encoding="utf-8")
    endpoints = FakeEndpointProber()
    lifecycle = ProductLifecycle(
        compose_file,
        executor=FakeExecutor(running_status()),
        preflight=docker_ready,
        endpoint_prober=endpoints,
        environment={},
    )

    checks = lifecycle.endpoint_checks()

    assert all(check.state is CheckState.PASS for check in checks)
    assert {port for port, _path, _kind, _timeout in endpoints.calls} == {8124}


def test_command_failure_never_exposes_stderr_or_secret(compose_file: Path) -> None:
    literal_secret = "private-token-must-never-appear"
    executor = FakeExecutor()
    executor.failure = ("up", literal_secret)
    lifecycle = ProductLifecycle(compose_file, executor=executor, preflight=docker_ready)

    with pytest.raises(LifecycleError) as captured:
        lifecycle.up()

    assert literal_secret not in str(captured.value)
    assert literal_secret not in (captured.value.output_digest or "")


def test_compose_discovery_honors_explicit_environment_without_printing_it(tmp_path: Path) -> None:
    selected = tmp_path / "private-name-compose.yaml"
    selected.write_text("services: {}\n", encoding="utf-8")

    resolved = resolve_compose_file(environment={"HARNESSLAB_COMPOSE_FILE": str(selected)})

    assert resolved == selected.resolve()


def test_compose_discovery_ignores_untrusted_working_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    untrusted = tmp_path / "docker-compose.yml"
    untrusted.write_text("services:\n  attacker:\n    privileged: true\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "HARNESSLAB_PORT=61234\nHARNESSLAB_IMAGE=attacker.invalid/image:latest\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    resolved = resolve_compose_file(environment={})
    executor = FakeExecutor(running_status())
    lifecycle = ProductLifecycle(
        executor=executor,
        preflight=docker_ready,
        endpoint_prober=FakeEndpointProber(),
        environment={},
    )
    lifecycle.up()
    up_call = next(call for call, _ in executor.calls if "up" in call)

    assert resolved == Path(__file__).resolve().parents[1] / "docker-compose.yml"
    assert resolved != untrusted
    assert lifecycle.product_port() == 8000
    assert "--build" in up_call
    assert "attacker.invalid" not in " ".join(up_call)


def test_root_help_exposes_product_lifecycle_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("up", "down", "status", "doctor"):
        assert command in result.stdout
