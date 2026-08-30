from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from harnesslab.budget import BudgetCeilingStatus, BudgetEstimateRequest, estimate_budget
from harnesslab.preflight.io import PreflightInputError, load_control_manifest
from harnesslab.preflight.models import PreflightSpecification, PreflightStatus
from harnesslab.preflight.service import run_preflight

preflight_app = typer.Typer(
    no_args_is_help=True,
    help="Run authoritative keyless checks before any experiment spend.",
)
budget_app = typer.Typer(
    no_args_is_help=True,
    help="Estimate deterministic experiment call, token, request, turn, and cost ceilings.",
)


@preflight_app.command("run")
def preflight_run(
    manifest: Annotated[Path, typer.Argument(help="Strict JSON preflight specification.")],
    repository_root: Annotated[
        Path,
        typer.Option(
            "--repository-root",
            help="Repository containing the referenced task packages.",
        ),
    ] = Path("."),
) -> None:
    """Collect host facts and emit one READY, READY_WITH_WARNINGS, or BLOCKED report."""

    try:
        specification = load_control_manifest(manifest, PreflightSpecification)
        report = asyncio.run(run_preflight(specification, repository_root))
    except PreflightInputError as exc:
        typer.echo(f"PREFLIGHT_INPUT_ERROR={exc}")
        raise typer.Exit(code=2) from exc
    typer.echo(report.model_dump_json())
    if report.status is PreflightStatus.BLOCKED:
        raise typer.Exit(code=2)


@budget_app.command("estimate")
def budget_estimate(
    manifest: Annotated[Path, typer.Argument(help="Strict JSON budget-estimate request.")],
) -> None:
    """Emit deterministic projections without provider or Judge execution."""

    try:
        request = load_control_manifest(manifest, BudgetEstimateRequest)
    except PreflightInputError as exc:
        typer.echo(f"BUDGET_INPUT_ERROR={exc}")
        raise typer.Exit(code=2) from exc
    estimate = estimate_budget(request)
    typer.echo(estimate.model_dump_json())
    if estimate.budget_ceiling_status in {
        BudgetCeilingStatus.EXCEEDS_CEILING,
        BudgetCeilingStatus.INDETERMINATE,
    }:
        raise typer.Exit(code=2)
