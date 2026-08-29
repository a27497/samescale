from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.core.config import Settings
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.experiment.executor import (
    CodexHarnessBinding,
    DirectModelBinding,
    ExperimentLaneBinding,
    ExperimentRunExecutor,
    resolved_comparison_profile_identity,
)
from harnesslab.experiment.methodology import (
    MethodologyError,
    load_evaluation_methodology,
    project_default_portfolio,
)
from harnesslab.experiment.model_comparison import (
    ModelComparisonAnalysisError,
    analyze_model_comparison,
)
from harnesslab.experiment.plan import (
    AnyExperimentPlan,
    build_experiment_plan,
    load_experiment_plan_payload,
)
from harnesslab.experiment.queue import ExperimentConflict, enqueue_plan, inspect_run
from harnesslab.experiment.report import (
    ExperimentReportError,
    build_experiment_report,
    load_verified_experiment_evidence,
)
from harnesslab.experiment.spec import ExperimentSpecError, load_experiment_spec
from harnesslab.harness_lane.fake import FakeCodexBackend
from harnesslab.harness_lane.profile import canonical_codex_profile
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.model_lane.fake import FakeDirectProvider
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.sandbox.models import ImageIdentity

experiment_app = typer.Typer(no_args_is_help=True, help="Plan and execute Phase G experiments.")
run_app = typer.Typer(no_args_is_help=True, help="Inspect durable experiment runs.")
report_app = typer.Typer(no_args_is_help=True, help="Build deterministic experiment reports.")

FAKE_PATCH = (
    '{"version":1,"operations":[{"op":"write","path":"calculator.py",'
    '"content":"def clamp(value: int, lower: int, upper: int) -> int:\\n'
    '    return max(lower, min(value, upper))\\n"}]}'
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _write_or_echo(content: str, output: Path | None) -> None:
    if output is None:
        typer.echo(content)
        return
    output.write_text(content, encoding="utf-8")
    typer.echo(f"output={output}")


def _load_plan(path: Path) -> AnyExperimentPlan:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        spec = load_experiment_spec(path)
        return build_experiment_plan(spec, _repository_root())
    except (OSError, UnicodeDecodeError) as exc:
        raise ExperimentSpecError(f"cannot read experiment input: {type(exc).__name__}") from exc
    if isinstance(raw, dict) and "run_slots" in raw:
        try:
            return load_experiment_plan_payload(raw)
        except (ValidationError, ExperimentSpecError) as exc:
            raise ExperimentSpecError(f"invalid experiment plan: {exc}") from exc
    spec = load_experiment_spec(path)
    return build_experiment_plan(spec, _repository_root())


@experiment_app.command("plan")
def plan_experiment(
    spec: str = typer.Argument(help="Strict ExperimentSpec YAML/JSON."),
    json_output: bool = typer.Option(False, "--json", help="Emit canonical plan JSON."),
    output: str | None = typer.Option(None, "--output", help="Write canonical plan JSON."),
) -> None:
    """Validate and deterministically expand an ExperimentSpec."""

    try:
        plan = build_experiment_plan(load_experiment_spec(Path(spec)), _repository_root())
    except ExperimentSpecError as exc:
        typer.echo(f"FAIL experiment plan: {exc}")
        raise typer.Exit(code=1) from exc
    if json_output or output is not None:
        _write_or_echo(plan.canonical_json(), Path(output) if output else None)
        return
    typer.echo(f"experiment_id={plan.experiment_id}")
    typer.echo(f"plan_digest={plan.digest}")
    typer.echo(f"cells={len(plan.cells)} tasks={len(plan.tasks)} runs={len(plan.run_slots)}")


@experiment_app.command("methodology-v2")
def methodology_v2_projection(
    methodology_path: str = typer.Option(
        "release/evaluation-methodology-v2.json",
        "--methodology",
        help="Strict methodology-v2 JSON artifact.",
    ),
) -> None:
    """Validate methodology v2 and print its planning-only portfolio projection."""

    try:
        methodology = load_evaluation_methodology(_repository_root() / methodology_path)
        projection = project_default_portfolio(methodology.default_portfolio)
    except MethodologyError as exc:
        typer.echo(f"FAIL evaluation methodology: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"methodology_id={methodology.methodology_id}")
    typer.echo(f"methodology_digest={methodology.digest}")
    typer.echo(f"breadth_subject_runs={projection.breadth_subject_runs}")
    typer.echo(f"incremental_critical_subject_runs={projection.incremental_critical_subject_runs}")
    typer.echo(f"projected_subject_runs={projection.projected_unique_subject_runs}")
    typer.echo(f"formal_exhaustive_subject_runs={projection.formal_exhaustive_subject_runs}")
    typer.echo(f"reduction_subject_runs={projection.reduction_subject_runs}")
    typer.echo("real_calls=0")


def _phase_g_fake_image() -> ImageIdentity:
    return ImageIdentity(
        reference="phase-g-keyless-codex:1",
        image_id="sha256:" + "7" * 64,
    )


def _keyless_bindings(
    plan: AnyExperimentPlan, artifact_root: Path, runtime_root: Path
) -> dict[str, ExperimentLaneBinding]:
    bindings: dict[str, ExperimentLaneBinding] = {}
    for cell in plan.cells:
        if cell.runner_contract == "phase-g-fake-direct-v1":
            direct_profile = ModelProfile(
                requested_model=cell.requested_model,
                provider="phase-g-fake",
                base_url="https://phase-g-fake.invalid/v1",
                route="/responses",
                protocol=Protocol.RESPONSES,
                reasoning=ReasoningProfile(effort=cell.reasoning_effort),
            )
            identity = resolved_comparison_profile_identity(direct_profile)
            expected_route = "phase-g-fake|responses|https://phase-g-fake.invalid/v1/responses"
            if cell.profile_identity != identity or cell.provider_route != expected_route:
                raise ExperimentSpecError(
                    f"cell {cell.id} does not match its resolved keyless direct profile"
                )
            if cell.harness_config_identity != canonical_digest(
                direct_profile.model_dump(mode="json")
            ):
                raise ExperimentSpecError(
                    f"cell {cell.id} has the wrong keyless direct configuration identity"
                )
            bindings[cell.id] = DirectModelBinding(
                DirectModelRunner(
                    artifact_root=artifact_root,
                    runtime_root=runtime_root / cell.id,
                    allow_custom_endpoint=True,
                ),
                direct_profile,
                FakeDirectProvider(FAKE_PATCH, observed_model=cell.requested_model),
            )
        elif cell.runner_contract == "phase-g-fake-codex-v1":
            codex_profile = canonical_codex_profile(
                _phase_g_fake_image(),
                requested_model=cell.requested_model,
                reasoning_effort=cell.reasoning_effort or "high",
            )
            if (
                cell.profile_identity != resolved_comparison_profile_identity(codex_profile)
                or cell.provider_route != codex_profile.provider_route
                or cell.harness_config_identity != codex_profile.fingerprint
            ):
                raise ExperimentSpecError(
                    f"cell {cell.id} does not match its resolved keyless Codex profile"
                )
            bindings[cell.id] = CodexHarnessBinding(
                CodexHarnessRunner(
                    artifact_root=artifact_root,
                    runtime_root=runtime_root / cell.id,
                ),
                codex_profile,
                FakeCodexBackend(),
            )
        else:
            raise ExperimentSpecError(
                f"cell {cell.id} has no configured local runner binding; use --enqueue-only"
            )
    return bindings


async def _run_experiment(
    plan: AnyExperimentPlan,
    *,
    execute: bool,
    artifact_root: Path,
    runtime_root: Path,
) -> tuple[int, int]:
    settings = Settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        bindings = _keyless_bindings(plan, artifact_root, runtime_root) if execute else {}
        async with factory() as session, session.begin():
            enqueued = await enqueue_plan(session, plan)
        executed = 0
        if execute:
            worker = ExperimentRunExecutor(
                repository_root=_repository_root(),
                session_factory=factory,
                bindings=bindings,
                owner="harnesslab-local-worker",
            )
            executed = len(await worker.run_until_idle(plan.experiment_id))
        return enqueued.logical_run_count, executed
    finally:
        await engine.dispose()


@experiment_app.command("run")
def run_experiment(
    plan_or_spec: str = typer.Argument(help="ExperimentSpec or canonical ExperimentPlan."),
    execute: bool = typer.Option(
        True,
        "--execute/--enqueue-only",
        help="Execute configured keyless local bindings or only persist the queue.",
    ),
    artifact_root: str = typer.Option(
        "artifacts/experiments", "--artifact-root", help="Lane artifact root."
    ),
    runtime_root: str = typer.Option(
        ".runtime/experiments", "--runtime-root", help="Ephemeral runtime root."
    ),
) -> None:
    """Persist idempotent slots and run the bounded in-process worker when configured."""

    try:
        plan = _load_plan(Path(plan_or_spec))
        logical, executed = asyncio.run(
            _run_experiment(
                plan,
                execute=execute,
                artifact_root=Path(artifact_root),
                runtime_root=Path(runtime_root),
            )
        )
    except (ExperimentConflict, ExperimentSpecError, ValidationError, ValueError) as exc:
        typer.echo(f"FAIL experiment run: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"experiment_id={plan.experiment_id}")
    typer.echo(f"plan_digest={plan.digest}")
    typer.echo(f"logical_runs={logical} executed={executed}")


async def _inspect(run_id: str) -> dict[str, Any]:
    settings = Settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            return asdict(await inspect_run(session, run_id))
    finally:
        await engine.dispose()


@run_app.command("inspect")
def inspect_experiment_run(
    run_id: str = typer.Argument(help="Durable experiment run id."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Show lifecycle, logical slot, artifact reference, and normalized outcome."""

    try:
        result = asyncio.run(_inspect(run_id))
    except ExperimentConflict as exc:
        typer.echo(f"FAIL run inspect: {exc}")
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(result, sort_keys=True, separators=(",", ":"), default=str))
        return
    typer.echo(f"run_id={result['run_id']} status={result['status']}")
    typer.echo(
        f"experiment_id={result['experiment_id']} cell_id={result['cell_id']} "
        f"attempt={result['attempt']}"
    )
    typer.echo(f"manifest={result['artifact_manifest_path'] or 'NOT_AVAILABLE'}")
    typer.echo(f"outcome={result['normalized_outcome'] or 'NOT_AVAILABLE'}")


async def _report(experiment_id: str) -> Any:
    settings = Settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            return await build_experiment_report(session, experiment_id)
    finally:
        await engine.dispose()


@report_app.command("compare")
def compare_experiment(
    experiment_id: str = typer.Argument(help="Persisted experiment id."),
    json_output: bool = typer.Option(False, "--json", help="Emit canonical JSON."),
    output: str | None = typer.Option(None, "--output", help="Write report bytes."),
) -> None:
    """Build a deterministic, Comparability-aware Phase G report."""

    try:
        report = asyncio.run(_report(experiment_id))
    except ExperimentReportError as exc:
        typer.echo(f"FAIL report compare: {exc}")
        raise typer.Exit(code=1) from exc
    content = report.canonical_json() if json_output else report.markdown()
    _write_or_echo(content, Path(output) if output else None)


async def _model_comparison_closeout(experiment_id: str) -> Any:
    settings = Settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            evidence = await load_verified_experiment_evidence(session, experiment_id)
            return analyze_model_comparison(evidence, repository_root=_repository_root())
    finally:
        await engine.dispose()


@report_app.command("model-comparison")
def model_comparison_closeout(
    experiment_id: str = typer.Argument(help="Persisted MODEL_COMPARISON experiment id."),
    output: str | None = typer.Option(None, "--output", help="Write canonical closeout JSON."),
) -> None:
    """Generate a deterministic machine-readable closeout without executing any run."""

    try:
        closeout = asyncio.run(_model_comparison_closeout(experiment_id))
    except (ExperimentReportError, ModelComparisonAnalysisError) as exc:
        typer.echo(f"FAIL report model-comparison: {exc}")
        raise typer.Exit(code=1) from exc
    _write_or_echo(closeout.canonical_json(), Path(output) if output else None)
