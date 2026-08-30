from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from harnesslab.productization.lifecycle import CheckState, LifecycleError, ProductLifecycle


def _lifecycle(compose_file: Path | None, project_name: str) -> ProductLifecycle:
    try:
        return ProductLifecycle(compose_file, project_name=project_name)
    except LifecycleError as exc:
        _fail(exc)


def _fail(exc: LifecycleError) -> NoReturn:
    typer.echo(f"FAIL {exc.action}: {exc}")
    if exc.output_digest is not None:
        typer.echo(f"diagnostic_output={exc.output_digest}")
    raise typer.Exit(code=exc.exit_code) from exc


def up_command(
    compose_file: Annotated[
        Path | None,
        typer.Option(
            "--compose-file", help="Product Compose file; normally discovered automatically."
        ),
    ] = None,
    project_name: Annotated[
        str, typer.Option("--project-name", help="Compose project name.")
    ] = "harnesslab",
    wait_timeout: Annotated[
        int,
        typer.Option("--wait-timeout", min=1, help="Seconds allowed for service health checks."),
    ] = 180,
) -> None:
    """Build, migrate, start, and health-check the complete local product."""

    lifecycle = _lifecycle(compose_file, project_name)
    try:
        preflight = lifecycle.up(wait_timeout=wait_timeout)
    except LifecycleError as exc:
        _fail(exc)
    typer.echo(f"PASS docker server={preflight.server_version} context={preflight.context}")
    typer.echo(f"PASS product project={project_name} services ready")
    port = lifecycle.product_port()
    typer.echo(f"Workbench: http://localhost:{port}/")
    typer.echo(f"API health: http://localhost:{port}/api/health")
    typer.echo("PROVIDER_CALLS=0")
    typer.echo("JUDGE_CALLS=0")


def down_command(
    compose_file: Annotated[
        Path | None, typer.Option("--compose-file", help="Product Compose file.")
    ] = None,
    project_name: Annotated[
        str, typer.Option("--project-name", help="Compose project name.")
    ] = "harnesslab",
) -> None:
    """Stop the local product while preserving its database volume."""

    lifecycle = _lifecycle(compose_file, project_name)
    try:
        lifecycle.down()
    except LifecycleError as exc:
        _fail(exc)
    typer.echo(f"PASS product project={project_name} stopped")
    typer.echo("Data volumes preserved")


def status_command(
    compose_file: Annotated[
        Path | None, typer.Option("--compose-file", help="Product Compose file.")
    ] = None,
    project_name: Annotated[
        str, typer.Option("--project-name", help="Compose project name.")
    ] = "harnesslab",
) -> None:
    """Show health and state for every product service."""

    lifecycle = _lifecycle(compose_file, project_name)
    try:
        _preflight, services = lifecycle.status()
    except LifecycleError as exc:
        _fail(exc)
    if not services:
        typer.echo("NOT_RUNNING product stack; run `harnesslab up`")
        raise typer.Exit(code=2)
    typer.echo(f"{'SERVICE':<18} {'STATE':<12} {'HEALTH':<12} CONTAINER")
    for service in services:
        typer.echo(
            f"{service.service:<18} {service.display_state:<12} "
            f"{service.health or '-':<12} {service.container}"
        )
    required = {"postgres", "migrate", "api"}
    if not required.issubset({service.service for service in services}) or not all(
        service.ready for service in services
    ):
        raise typer.Exit(code=1)
    endpoint_checks = lifecycle.endpoint_checks()
    for check in endpoint_checks:
        typer.echo(f"{check.state.value:<12} {check.name:<15} {check.detail}")
    if any(check.state is CheckState.FAIL for check in endpoint_checks):
        raise typer.Exit(code=1)


def doctor_command(
    compose_file: Annotated[
        Path | None, typer.Option("--compose-file", help="Product Compose file.")
    ] = None,
    project_name: Annotated[
        str, typer.Option("--project-name", help="Compose project name.")
    ] = "harnesslab",
) -> None:
    """Check Docker, product configuration, and runtime readiness keylessly."""

    lifecycle = _lifecycle(compose_file, project_name)
    checks = lifecycle.doctor()
    for check in checks:
        typer.echo(f"{check.state.value:<12} {check.name:<15} {check.detail}")
    typer.echo("SECRETS=MASKED")
    if any(check.state is CheckState.FAIL for check in checks):
        raise typer.Exit(code=1)
    if any(check.state is CheckState.NOT_RUNNING for check in checks):
        raise typer.Exit(code=2)
