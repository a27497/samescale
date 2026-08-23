from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from harnesslab.core.config import Settings
from harnesslab.db.models.judgelab import JudgeCalibrationRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.judgelab.calibration import execute_calibration
from harnesslab.judgelab.models import JudgeCalibrationPlan
from harnesslab.judgelab.plan import (
    JudgePlanError,
    build_calibration_plan,
    load_calibration_spec,
    resolve_definitions,
    resolve_suite,
)
from harnesslab.judgelab.report import JudgeCalibrationReport
from harnesslab.judgelab.suite import (
    JudgeSuiteError,
    load_judge_suite,
)

judge_app = typer.Typer(no_args_is_help=True, help="Run Phase H JudgeLab calibration.")
judge_suite_app = typer.Typer(no_args_is_help=True, help="Validate versioned Judge suites.")
judge_app.add_typer(judge_suite_app, name="suite")


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _write_or_echo(content: str, output: str | None) -> None:
    if output is None:
        typer.echo(content)
    else:
        Path(output).write_text(content, encoding="utf-8")
        typer.echo(f"output={output}")


@judge_suite_app.command("validate")
def validate_suite(
    suite_path: str = typer.Argument(help="Versioned Judge suite directory."),
    json_output: bool = typer.Option(False, "--json", help="Emit canonical identities."),
) -> None:
    """Validate strict public cases, hidden gold, probes, and split digests."""

    try:
        suite = load_judge_suite(Path(suite_path))
    except JudgeSuiteError as exc:
        typer.echo(f"FAIL Judge suite: {exc}")
        raise typer.Exit(code=1) from exc
    result = {
        "suite_id": suite.public.suite_id,
        "suite_version": suite.public.version,
        "case_count": len(suite.public.cases),
        "public_digest": suite.public_digest,
        "gold_digest": suite.gold_digest,
        "suite_digest": suite.suite_digest,
    }
    if json_output:
        typer.echo(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        for key, value in result.items():
            typer.echo(f"{key}={value}")
        typer.echo("validation=PASS")


def _load_plan_and_dependencies(path: Path) -> tuple[JudgeCalibrationPlan, Any, dict[str, Any]]:
    spec = load_calibration_spec(path)
    suite = resolve_suite(spec, _repository_root())
    definitions = resolve_definitions(spec, _repository_root())
    plan = build_calibration_plan(spec, suite, definitions)
    return plan, suite, definitions


@judge_app.command("plan")
def plan_calibration(
    calibration_spec: str = typer.Argument(help="Strict JudgeCalibrationSpec YAML."),
    json_output: bool = typer.Option(False, "--json", help="Emit canonical plan JSON."),
    output: str | None = typer.Option(None, "--output", help="Write canonical plan JSON."),
) -> None:
    """Resolve and deterministically expand Judge evaluation slots."""

    try:
        plan, _suite, _definitions = _load_plan_and_dependencies(Path(calibration_spec))
    except (JudgePlanError, JudgeSuiteError) as exc:
        typer.echo(f"FAIL Judge plan: {exc}")
        raise typer.Exit(code=1) from exc
    if json_output or output:
        _write_or_echo(plan.canonical_json(), output)
        return
    typer.echo(f"calibration_id={plan.calibration_id}")
    typer.echo(f"suite_digest={plan.suite_digest}")
    typer.echo(f"plan_digest={plan.plan_digest}")
    typer.echo(f"judge_cells={len(plan.judge_cells)} evaluation_slots={len(plan.slots)}")


async def _calibrate(path: Path, artifact_root: Path) -> JudgeCalibrationReport:
    plan, suite, definitions = _load_plan_and_dependencies(path)
    settings = Settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            return await execute_calibration(
                session,
                plan=plan,
                suite=suite,
                definitions=definitions,
                artifact_root=artifact_root,
                allow_real_judge=os.environ.get("HARNESSLAB_ENABLE_REAL_JUDGE") == "1",
            )
    finally:
        await engine.dispose()


@judge_app.command("calibrate")
def calibrate(
    calibration_spec: str = typer.Argument(help="Strict JudgeCalibrationSpec YAML."),
    artifact_root: str = typer.Option(
        "harnesslab-artifacts/judgelab", "--artifact-root", help="Immutable Judge artifact root."
    ),
) -> None:
    """Persist, execute, reload, calibrate, qualify, and report Judge cells."""

    try:
        report = asyncio.run(_calibrate(Path(calibration_spec), Path(artifact_root)))
    except (JudgePlanError, JudgeSuiteError, ValidationError, ValueError) as exc:
        typer.echo(f"FAIL Judge calibration: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"calibration_id={report.calibration_id}")
    typer.echo(f"suite_digest={report.suite_digest}")
    typer.echo(f"plan_digest={report.plan_digest}")
    typer.echo(f"judge_cells={len(report.cells)}")
    typer.echo(f"evaluation_slots={sum(cell.run_counts['planned'] for cell in report.cells)}")
    typer.echo(
        "qualification="
        + ",".join(
            f"{cell.judge_cell_id}:{cell.qualification_status.value}" for cell in report.cells
        )
    )
    typer.echo(f"report_digest={report.report_digest}")
    typer.echo("REAL_JUDGE_SMOKE=NOT_RUN")


async def _load_report(calibration_id: str) -> JudgeCalibrationReport:
    settings = Settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            record = await session.get(JudgeCalibrationRecord, calibration_id)
            if record is None or record.report_json_path is None or record.report_digest is None:
                raise JudgePlanError("calibration report is unavailable")
            report = JudgeCalibrationReport.model_validate_json(
                Path(record.report_json_path).read_text(encoding="utf-8")
            )
            if report.report_digest != record.report_digest:
                raise JudgePlanError("persisted calibration report digest mismatch")
            return report
    finally:
        await engine.dispose()


@judge_app.command("report")
def report_calibration(
    calibration_id: str = typer.Argument(help="Persisted calibration id."),
    json_output: bool = typer.Option(False, "--json", help="Emit deterministic JSON."),
    output: str | None = typer.Option(None, "--output", help="Write report bytes."),
) -> None:
    """Reload a deterministic persisted JudgeCalibrationReport."""

    try:
        report = asyncio.run(_load_report(calibration_id))
    except (JudgePlanError, OSError, ValidationError) as exc:
        typer.echo(f"FAIL Judge report: {exc}")
        raise typer.Exit(code=1) from exc
    _write_or_echo(report.canonical_json() if json_output else report.markdown(), output)
