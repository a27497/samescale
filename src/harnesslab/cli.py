from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from enum import StrEnum

import typer
import uvicorn
from pydantic import ValidationError

from harnesslab import __version__
from harnesslab.core.config import Settings
from harnesslab.db.health import check_database

app = typer.Typer(no_args_is_help=True, help="HarnessLab AI control CLI.")


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
