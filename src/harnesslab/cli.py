from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import typer
import uvicorn
from pydantic import ValidationError

from harnesslab import __version__
from harnesslab.core.config import Settings
from harnesslab.db.health import check_database
from harnesslab.sandbox.preflight import DockerPreflightError, docker_preflight
from harnesslab.tasks.package import TaskPackageError
from harnesslab.tasks.validation import validate_task_package

app = typer.Typer(no_args_is_help=True, help="HarnessLab AI control CLI.")
task_app = typer.Typer(no_args_is_help=True, help="Inspect and validate versioned task packages.")
sandbox_app = typer.Typer(no_args_is_help=True, help="Inspect the Phase C Docker sandbox boundary.")
app.add_typer(task_app, name="task")
app.add_typer(sandbox_app, name="sandbox")


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_CONFIGURED = "NOT_CONFIGURED"


@dataclass(frozen=True)
class DoctorResult:
    name: str
    status: CheckStatus
    detail: str


async def run_doctor() -> list[DoctorResult]:
    results = [
        DoctorResult("package", CheckStatus.PASS, f"HarnessLab {__version__}"),
    ]
    if sys.version_info[:2] == (3, 12):
        results.append(DoctorResult("python", CheckStatus.PASS, sys.version.split()[0]))
    else:
        results.append(
            DoctorResult(
                "python", CheckStatus.FAIL, f"requires Python 3.12; found {sys.version.split()[0]}"
            )
        )

    try:
        settings = Settings()
    except ValidationError:
        results.append(
            DoctorResult(
                "configuration", CheckStatus.NOT_CONFIGURED, "DATABASE_URL is missing or invalid"
            )
        )
        results.append(
            DoctorResult("postgresql", CheckStatus.NOT_CONFIGURED, "configuration is unavailable")
        )
        return results

    results.append(
        DoctorResult("configuration", CheckStatus.PASS, f"environment={settings.environment}")
    )
    try:
        await check_database(settings)
    except Exception as exc:  # CLI boundary reports the error class without credentials.
        results.append(DoctorResult("postgresql", CheckStatus.FAIL, type(exc).__name__))
    else:
        results.append(DoctorResult("postgresql", CheckStatus.PASS, "SELECT 1 succeeded"))
    return results


def version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show the HarnessLab package version and exit.",
    ),
) -> None:
    """Manage and inspect the HarnessLab control plane."""


@app.command()
def doctor() -> None:
    """Check runtime, configuration, and PostgreSQL connectivity."""

    results = asyncio.run(run_doctor())
    for result in results:
        typer.echo(f"{result.status.value:<14} {result.name:<15} {result.detail}")
    if any(result.status is CheckStatus.FAIL for result in results):
        raise typer.Exit(code=1)
    if any(result.status is CheckStatus.NOT_CONFIGURED for result in results):
        raise typer.Exit(code=2)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Address to bind."),
    port: int = typer.Option(8000, min=1, max=65535, help="Port to bind."),
) -> None:
    """Start the FastAPI control API."""

    uvicorn.run(
        "harnesslab.api.app:app",
        host=host,
        port=port,
        loop="harnesslab.core.runtime:selector_loop_factory",
    )


@task_app.command("validate")
def validate_task(
    task_path: str = typer.Argument(help="Path to a versioned task package."),
) -> None:
    """Validate manifest, digest, hidden verifier, and baseline/oracle polarity."""

    try:
        result = validate_task_package(Path(task_path))
    except (TaskPackageError, OSError) as exc:
        typer.echo(f"FAIL task package: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"task: {result.task_id}@{result.task_version}")
    typer.echo(f"task digest: {result.task_digest}")
    typer.echo(
        f"baseline: passed={result.baseline.result.passed} score={result.baseline.result.score:.3f}"
    )
    typer.echo(
        f"oracle: passed={result.oracle.result.passed} score={result.oracle.result.score:.3f}"
    )
    if not result.valid:
        for error in result.errors:
            typer.echo(f"FAIL {error}")
        raise typer.Exit(code=1)
    typer.echo("validation: PASS")


@sandbox_app.command("doctor")
def sandbox_doctor() -> None:
    """Verify local Docker can provide the Linux-container sandbox boundary."""

    try:
        result = asyncio.run(docker_preflight())
    except DockerPreflightError as exc:
        typer.echo(f"NOT_VERIFIED docker sandbox: {exc}")
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"FAIL docker sandbox: {type(exc).__name__}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"PASS docker_cli={result.cli_path}")
    typer.echo(
        f"PASS context={result.context} endpoint={result.endpoint_scheme} "
        f"server={result.server_version} os={result.server_os}/{result.server_arch}"
    )
    typer.echo(f"PASS default_seccomp={result.default_seccomp}")
