from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from harnesslab import __version__
from harnesslab.analyst.cli import analyst_app
from harnesslab.comparability.engine import ComparabilityEngine
from harnesslab.comparability.manifest import ComparabilityInputError, load_manifest_facts
from harnesslab.comparability.models import ComparabilityIntent
from harnesslab.custom_eval.cli import custom_eval_app
from harnesslab.egress import EgressNetworkIsolationUnavailable
from harnesslab.experiment.cli import experiment_app, report_app, run_app
from harnesslab.harness_lane.profile import canonical_codex_profile
from harnesslab.harness_lane.runtime import CodexRuntime
from harnesslab.judgelab.cli import judge_app
from harnesslab.model_lane.models import DirectModelOutcome, ProviderFailureCategory
from harnesslab.model_lane.profiles import ModelProfileError, load_model_profile
from harnesslab.model_lane.runner import DirectModelRunError, DirectModelRunner
from harnesslab.multi_harness.models import DeepSeekSessionExtraction, HarnessKind
from harnesslab.multi_harness.profile import canonical_claude_profile, canonical_deepseek_profile
from harnesslab.multi_harness.runtime import MultiHarnessRuntime
from harnesslab.preflight.cli import budget_app, preflight_app
from harnesslab.productization.cli import (
    doctor_command,
    down_command,
    status_command,
    up_command,
)
from harnesslab.release.diagnostic import (
    ComponentDiagnosticError,
    execute_real_component_diagnostics,
    summarize_component_diagnostic_report,
)
from harnesslab.release.evidence import EvidenceSummaryError, summarize_smoke_evidence
from harnesslab.release.judge import (
    RealJudgeControlPlaneError,
    build_real_judge_plan,
    execute_real_judge_calibration,
)
from harnesslab.release.matrix import (
    MatrixControlPlane,
    MatrixControlPlaneError,
    execute_real_matrix,
    execute_real_matrix_canary,
)
from harnesslab.release.smoke import (
    SmokeControlPlane,
    SmokeControlPlaneError,
    SmokeExecutionStatus,
    execute_real_smoke,
    resolve_runtime_identities,
)
from harnesslab.release.telemetry import summarize_smoke_telemetry
from harnesslab.sandbox.preflight import DockerPreflightError, docker_preflight
from harnesslab.tasks.package import TaskPackageError
from harnesslab.tasks.validation import validate_task_package

app = typer.Typer(no_args_is_help=True, help="HarnessLab AI control CLI.")
task_app = typer.Typer(no_args_is_help=True, help="Inspect and validate versioned task packages.")
sandbox_app = typer.Typer(no_args_is_help=True, help="Inspect the Phase C Docker sandbox boundary.")
model_app = typer.Typer(no_args_is_help=True, help="Run Phase D direct-model evaluations.")
model_profile_app = typer.Typer(no_args_is_help=True, help="Validate direct-model profiles.")
harness_app = typer.Typer(no_args_is_help=True, help="Inspect pinned coding harness runtimes.")
codex_harness_app = typer.Typer(no_args_is_help=True, help="Inspect the pinned Codex harness.")
claude_harness_app = typer.Typer(no_args_is_help=True, help="Inspect the pinned Claude harness.")
deepseek_harness_app = typer.Typer(
    no_args_is_help=True, help="Inspect the pinned DeepSeek harness."
)
compare_app = typer.Typer(no_args_is_help=True, help="Assess evidence comparability.")
release_app = typer.Typer(no_args_is_help=True, help="Prepare bounded Core release operations.")
release_smoke_app = typer.Typer(
    no_args_is_help=True, help="Preflight or explicitly execute the exact K-B1 smoke plan."
)
release_component_smoke_app = typer.Typer(
    no_args_is_help=True, help="Diagnose only frozen calls not attempted by a release smoke."
)
release_matrix_app = typer.Typer(
    no_args_is_help=True, help="Preflight or explicitly execute the frozen Core real Matrix."
)
release_telemetry_app = typer.Typer(
    no_args_is_help=True, help="Summarize safe K-B2 smoke telemetry and cost inputs."
)
release_judge_app = typer.Typer(
    no_args_is_help=True, help="Preflight or execute the frozen real Judge campaign."
)
app.command("up")(up_command)
app.command("down")(down_command)
app.command("status")(status_command)
app.add_typer(task_app, name="task")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(model_app, name="model")
app.add_typer(harness_app, name="harness")
app.add_typer(compare_app, name="compare")
app.add_typer(custom_eval_app, name="custom-eval")
app.add_typer(experiment_app, name="experiment")
app.add_typer(run_app, name="run")
app.add_typer(report_app, name="report")
app.add_typer(judge_app, name="judge")
app.add_typer(analyst_app, name="analyst")
app.add_typer(release_app, name="release")
app.add_typer(preflight_app, name="preflight")
app.add_typer(budget_app, name="budget")
model_app.add_typer(model_profile_app, name="profile")
harness_app.add_typer(codex_harness_app, name="codex")
harness_app.add_typer(claude_harness_app, name="claude")
harness_app.add_typer(deepseek_harness_app, name="deepseek")
release_app.add_typer(release_smoke_app, name="smoke")
release_app.add_typer(release_component_smoke_app, name="component-smoke")
release_app.add_typer(release_matrix_app, name="matrix")
release_app.add_typer(release_telemetry_app, name="telemetry")
release_app.add_typer(release_judge_app, name="judge")


@release_smoke_app.command("preflight")
def preflight_release_smoke(
    repository_root: str = typer.Option(
        ".", "--repository-root", help="Repository containing the frozen release plans."
    ),
    plan_version: str = typer.Option("v2", "--plan-version", help="Frozen plan version."),
) -> None:
    """Validate the exact eight-call plan keylessly, without resolving secrets or networking."""

    try:
        control = SmokeControlPlane.load(Path(repository_root), plan_version=plan_version)
        receipt = control.preflight()
    except SmokeControlPlaneError as exc:
        typer.echo(f"FAIL smoke preflight: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo("SMOKE_PREFLIGHT=PASS")
    typer.echo(f"SMOKE_PLAN_DIGEST={receipt.smoke_plan_digest}")
    typer.echo(f"RELEASE_PLAN_DIGEST={receipt.release_plan_digest}")
    typer.echo(f"SMOKE_CALL_BINDINGS={len(control.bindings)}")
    typer.echo("REAL_EVALUATION_CALL_COUNT=0")


@release_smoke_app.command("execute")
def execute_release_smoke(
    allow_real_smoke: bool = typer.Option(
        False,
        "--allow-real-smoke",
        help="Explicitly authorize only the frozen eight-call provider smoke.",
    ),
    repository_root: str = typer.Option(
        ".", "--repository-root", help="Repository containing the frozen release plans."
    ),
    artifact_root: str | None = typer.Option(
        None, "--artifact-root", help="Safe immutable smoke evidence destination."
    ),
    plan_version: str = typer.Option("v2", "--plan-version", help="Frozen plan version."),
) -> None:
    """Execute the exact smoke plan; it is inert unless the explicit authorization flag is set."""

    try:
        receipt = asyncio.run(
            execute_real_smoke(
                Path(repository_root),
                allow_real_smoke=allow_real_smoke,
                artifact_root=Path(artifact_root) if artifact_root is not None else None,
                plan_version=plan_version,
            )
        )
    except (SmokeControlPlaneError, EgressNetworkIsolationUnavailable) as exc:
        typer.echo(f"FAIL smoke execution: {exc}")
        raise typer.Exit(code=2) from exc
    typer.echo(f"SMOKE_EXECUTION={receipt.status.value}")
    typer.echo(f"ATTEMPTED_TOP_LEVEL_LAUNCHES={receipt.attempted_top_level_launches}")
    if receipt.failing_call_id is not None:
        typer.echo(f"FAILING_CALL_ID={receipt.failing_call_id}")
        assert receipt.failure_category is not None
        typer.echo(f"FAILURE_CATEGORY={receipt.failure_category.value}")
    if receipt.status is SmokeExecutionStatus.ABORTED:
        raise typer.Exit(code=1)


@release_smoke_app.command("credential-preflight")
def preflight_release_smoke_credentials(
    plan_version: str = typer.Option("v2", "--plan-version", help="Frozen plan version."),
) -> None:
    """Report only presence of frozen runtime references; never print credential values."""

    from harnesslab.release.smoke import REQUIRED_CONFIGURATION_REFERENCES

    if plan_version not in {"v2", "v3", "v4"}:
        typer.echo("FAIL credential preflight: plan version must be v2, v3, or v4")
        raise typer.Exit(code=2)
    if plan_version != "v2":
        typer.echo(f"PLAN_VERSION={plan_version}")
    missing = False
    for reference in REQUIRED_CONFIGURATION_REFERENCES:
        present = bool(os.environ.get(reference, "").strip())
        typer.echo(f"{reference}={'SET' if present else 'MISSING'}")
        missing = missing or not present
    if missing:
        raise typer.Exit(code=2)


@release_smoke_app.command("evidence-summary")
def summarize_release_smoke_evidence(
    artifact_root: str = typer.Option(
        ..., "--artifact-root", help="Operator evidence root containing smoke-execution.json."
    ),
    candidate_history: bool = typer.Option(
        False, "--candidate-history", help="Emit a safe candidate history object."
    ),
) -> None:
    """Derive receipt and call-artifact digest domains without provider access or writes."""

    try:
        summary = summarize_smoke_evidence(Path(artifact_root))
    except EvidenceSummaryError as exc:
        typer.echo(f"FAIL smoke evidence summary: {exc}")
        raise typer.Exit(code=1) from exc
    content = (
        summary.candidate_history_summary()
        if candidate_history
        else summary.model_dump(mode="json")
    )
    typer.echo(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


@release_component_smoke_app.command("execute")
def execute_release_component_smoke(
    allow_real_diagnostic: bool = typer.Option(
        False,
        "--allow-real-diagnostic",
        help="Explicitly authorize only unattempted frozen diagnostic calls.",
    ),
    skip_attempted_from: str = typer.Option(
        ...,
        "--skip-attempted-from",
        help="Authoritative release smoke receipt whose attempted calls must never repeat.",
    ),
    artifact_root: str = typer.Option(
        ..., "--artifact-root", help="Unique DIAGNOSTIC_ONLY evidence destination."
    ),
    repository_root: str = typer.Option(
        ".", "--repository-root", help="Repository containing the frozen release plans."
    ),
    plan_version: str = typer.Option("v2", "--plan-version", help="Frozen plan version."),
) -> None:
    """Continue across independent unattempted components; never produce release evidence."""

    try:
        report = asyncio.run(
            execute_real_component_diagnostics(
                Path(repository_root),
                allow_real_diagnostic=allow_real_diagnostic,
                attempt_receipt_path=Path(skip_attempted_from),
                artifact_root=Path(artifact_root),
                plan_version=plan_version,
            )
        )
    except (ComponentDiagnosticError, EgressNetworkIsolationUnavailable) as exc:
        typer.echo(f"FAIL component diagnostic: {exc}")
        raise typer.Exit(code=2) from exc
    typer.echo("EVIDENCE_CLASS=DIAGNOSTIC_ONLY")
    typer.echo("RELEASE_PROMOTABLE=false")
    typer.echo(f"DIAGNOSTIC_TOP_LEVEL_LAUNCHES={report.diagnostic_top_level_launches}")
    typer.echo(f"DIAGNOSTIC_CALL_IDS={','.join(report.diagnostic_call_ids)}")


@release_component_smoke_app.command("evidence-summary")
def summarize_release_component_evidence(
    report: str = typer.Option(..., "--report", help="Component diagnostic report path."),
    source_commit: str = typer.Option(..., "--source-commit", help="Exact execution HEAD."),
) -> None:
    """Validate and emit a safe candidate DIAGNOSTIC_ONLY history object."""

    try:
        summary = summarize_component_diagnostic_report(Path(report))
    except ComponentDiagnosticError as exc:
        typer.echo(f"FAIL component evidence summary: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(
        json.dumps(
            summary.candidate_history_summary(source_commit),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


@release_matrix_app.command("preflight")
def preflight_release_matrix(
    repository_root: str = typer.Option(
        ".", "--repository-root", help="Repository containing the frozen release plans."
    ),
    plan_version: str = typer.Option("v2", "--plan-version", help="Frozen plan version."),
) -> None:
    """Inspect local runtime identities and validate the exact 630-slot plan keylessly."""

    try:
        runtime = asyncio.run(resolve_runtime_identities())
        receipt = MatrixControlPlane.load(
            Path(repository_root), plan_version=plan_version
        ).preflight(runtime)
    except MatrixControlPlaneError as exc:
        typer.echo(f"FAIL Matrix preflight: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo("MATRIX_PREFLIGHT=PASS")
    typer.echo(f"MATRIX_ID={receipt.matrix_id}")
    typer.echo(f"CELLS={receipt.cells}")
    typer.echo(f"TASKS={receipt.tasks}")
    typer.echo(f"REPEATS={receipt.repeats}")
    typer.echo(f"LOGICAL_RUNS={receipt.logical_runs}")
    typer.echo(f"EXPERIMENT_PLAN_DIGEST={receipt.experiment_plan_digest}")
    typer.echo("REAL_CALLS=0")


@release_matrix_app.command("execute")
def execute_release_matrix(
    allow_real_matrix: bool = typer.Option(
        False, "--allow-real-matrix", help="Explicitly authorize the frozen real Matrix plane."
    ),
    max_runs: int | None = typer.Option(
        None, "--max-runs", help="Required bound from 1 to 630; there is no launch default."
    ),
    concurrency: int = typer.Option(
        2, "--concurrency", min=1, max=4, help="Bounded worker concurrency (campaign max 4)."
    ),
    selection: str = typer.Option(
        "remaining",
        "--selection",
        help="v3 full-plan slot selection: canary, pilot, or remaining.",
    ),
    artifact_root: str = typer.Option(
        "artifacts/core-real-matrix-v2", "--artifact-root", help="Immutable Matrix artifacts."
    ),
    runtime_root: str = typer.Option(
        ".runtime/core-real-matrix-v2", "--runtime-root", help="Ephemeral Matrix runtime root."
    ),
    repository_root: str = typer.Option(
        ".", "--repository-root", help="Repository containing the frozen release plans."
    ),
    plan_version: str = typer.Option("v2", "--plan-version", help="Frozen plan version."),
) -> None:
    """Run a resumable bounded slice of the strict Matrix; inert without both explicit gates."""

    try:
        result = asyncio.run(
            execute_real_matrix(
                Path(repository_root),
                allow_real_matrix=allow_real_matrix,
                max_runs=max_runs,
                concurrency=concurrency,
                artifact_root=Path(artifact_root),
                runtime_root=Path(runtime_root),
                plan_version=plan_version,
                selection=selection,  # type: ignore[arg-type]
            )
        )
    except (MatrixControlPlaneError, EgressNetworkIsolationUnavailable, ValueError) as exc:
        typer.echo(f"FAIL Matrix execution: {exc}")
        raise typer.Exit(code=2) from exc
    typer.echo(f"MATRIX_ID={result.matrix_id}")
    typer.echo(f"PLAN_DIGEST={result.plan_digest}")
    typer.echo(f"LOGICAL_RUNS={result.logical_runs}")
    typer.echo(f"EXECUTED_RUNS={result.executed_runs}")
    typer.echo(f"CONCURRENCY={result.concurrency}")
    typer.echo(f"SELECTION={result.selection}")
    typer.echo(f"SELECTED_SLOTS={result.selected_slots}")
    typer.echo(f"TERMINAL_SELECTED_SLOTS={result.terminal_selected_slots}")
    typer.echo(f"PENDING_SELECTED_SLOTS={result.pending_selected_slots}")


@release_matrix_app.command("canary")
def execute_release_matrix_canary(
    allow_real_matrix_canary: bool = typer.Option(
        False,
        "--allow-real-matrix-canary",
        help="Explicitly authorize the exact seven-cell v3 Matrix canary.",
    ),
    concurrency: int = typer.Option(
        1, "--concurrency", min=1, max=7, help="Bounded canary worker concurrency."
    ),
    artifact_root: str = typer.Option(
        "artifacts/core-real-matrix-v3-canary",
        "--artifact-root",
        help="Immutable Matrix canary artifacts.",
    ),
    runtime_root: str = typer.Option(
        ".runtime/core-real-matrix-v3-canary",
        "--runtime-root",
        help="Ephemeral Matrix canary runtime root.",
    ),
    repository_root: str = typer.Option(
        ".", "--repository-root", help="Repository containing the frozen release plans."
    ),
) -> None:
    """Run one fixed task once through all seven v3 production bindings."""

    try:
        result = asyncio.run(
            execute_real_matrix_canary(
                Path(repository_root),
                allow_real_matrix_canary=allow_real_matrix_canary,
                concurrency=concurrency,
                artifact_root=Path(artifact_root),
                runtime_root=Path(runtime_root),
            )
        )
    except (MatrixControlPlaneError, EgressNetworkIsolationUnavailable, ValueError) as exc:
        typer.echo(f"FAIL Matrix canary execution: {exc}")
        raise typer.Exit(code=2) from exc
    typer.echo(f"MATRIX_ID={result.matrix_id}")
    typer.echo(f"PLAN_DIGEST={result.plan_digest}")
    typer.echo(f"LOGICAL_RUNS={result.logical_runs}")
    typer.echo(f"EXECUTED_RUNS={result.executed_runs}")
    typer.echo(f"REAL_MATRIX_PLANE_CANARY={'PASS' if result.technical_pass else 'FAIL'}")
    for item in result.results:
        typer.echo(
            "CANARY_RESULT="
            + json.dumps(
                {
                    "cell_id": item.cell_id,
                    "task_id": item.task_id,
                    "status": item.status,
                    "normalized_outcome": item.normalized_outcome,
                    "source_outcome": item.source_outcome,
                    "evidence_digest": item.evidence_digest,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    if not result.technical_pass:
        raise typer.Exit(code=1)


@release_judge_app.command("preflight")
def preflight_release_judge(
    repository_root: str = typer.Option(
        ".", "--repository-root", help="Repository containing the frozen release plans."
    ),
) -> None:
    """Resolve the existing v3 GLM profile and exact 63-slot suite without provider calls."""

    try:
        plan, _suite, _definitions = build_real_judge_plan(Path(repository_root))
    except (RealJudgeControlPlaneError, ValueError) as exc:
        typer.echo(f"FAIL real Judge preflight: {exc}")
        raise typer.Exit(code=2) from exc
    typer.echo("REAL_JUDGE_PREFLIGHT=PASS")
    typer.echo(f"CALIBRATION_ID={plan.calibration_id}")
    typer.echo(f"PLAN_DIGEST={plan.plan_digest}")
    typer.echo(f"EVALUATION_SLOTS={len(plan.slots)}")
    typer.echo("REAL_CALLS=0")


@release_judge_app.command("calibrate")
def calibrate_release_judge(
    allow_real_judge: bool = typer.Option(
        False, "--allow-real-judge", help="Explicitly authorize the exact 63-call campaign."
    ),
    artifact_root: str = typer.Option(
        "artifacts/core-real-judge-v3", "--artifact-root", help="Immutable Judge artifacts."
    ),
    repository_root: str = typer.Option(
        ".", "--repository-root", help="Repository containing the frozen release plans."
    ),
) -> None:
    """Resume the frozen real calibration; output/schema failures are terminal observations."""

    try:
        report = asyncio.run(
            execute_real_judge_calibration(
                Path(repository_root),
                allow_real_judge=allow_real_judge,
                artifact_root=Path(artifact_root),
            )
        )
    except (RealJudgeControlPlaneError, ValueError) as exc:
        typer.echo(f"FAIL real Judge calibration: {exc}")
        raise typer.Exit(code=2) from exc
    cell = report.cells[0]
    typer.echo(f"CALIBRATION_ID={report.calibration_id}")
    typer.echo(f"PLAN_DIGEST={report.plan_digest}")
    typer.echo(f"REPORT_DIGEST={report.report_digest}")
    qualification = (
        "QUALIFIED" if cell.qualification_status.value == "QUALIFIED_FOR_SUITE" else "NOT_QUALIFIED"
    )
    typer.echo(f"REAL_JUDGE_CALIBRATION={qualification}")


@release_telemetry_app.command("summarize")
def summarize_release_telemetry(
    artifact_root: str = typer.Option(..., "--artifact-root", help="Operator smoke evidence root."),
) -> None:
    """Aggregate only observed smoke telemetry; missing price input remains explicit."""

    try:
        summary = summarize_smoke_telemetry(Path(artifact_root))
    except EvidenceSummaryError as exc:
        typer.echo(f"FAIL telemetry summary: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(summary.canonical_json())


@compare_app.command("assess")
def assess_comparability(
    left: str = typer.Argument(help="Left M-Lane or H-Lane manifest.json."),
    right: str = typer.Argument(help="Right M-Lane or H-Lane manifest.json."),
    intent: str = typer.Option("general", "--intent", help="Comparison claim intent."),
    json_output: bool = typer.Option(False, "--json", help="Emit canonical JSON."),
) -> None:
    """Assess two immutable evidence manifests without guessing missing identities."""

    try:
        parsed_intent = ComparabilityIntent(intent.replace("-", "_").upper())
        report = ComparabilityEngine().assess(
            load_manifest_facts(Path(left)),
            load_manifest_facts(Path(right)),
            intent=parsed_intent,
        )
    except (ComparabilityInputError, ValueError) as exc:
        typer.echo(f"FAIL comparability input: {exc}")
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(report.canonical_json())
        return
    typer.echo(f"status={report.status.value}")
    typer.echo(f"intent={report.intent.value}")
    typer.echo(f"left_evidence={report.left_evidence_identity}")
    typer.echo(f"right_evidence={report.right_evidence_identity}")
    for reason in report.reasons:
        typer.echo(
            f"{reason.severity.value} {reason.code.value} field={reason.field}: {reason.detail}"
        )


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
def doctor(
    compose_file: Annotated[
        Path | None, typer.Option("--compose-file", help="Product Compose file.")
    ] = None,
    project_name: Annotated[
        str, typer.Option("--project-name", help="Compose project name.")
    ] = "harnesslab",
) -> None:
    """Check Docker, product configuration, and runtime readiness keylessly."""

    doctor_command(compose_file=compose_file, project_name=project_name)


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


@codex_harness_app.command("doctor")
def codex_harness_doctor() -> None:
    """Verify the pinned Codex image, CLI version, exec flags, and profile fingerprint."""

    try:
        result = asyncio.run(CodexRuntime().doctor())
        profile = canonical_codex_profile(result.image)
    except DockerPreflightError as exc:
        typer.echo(f"NOT_VERIFIED Codex Harness: {exc}")
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"FAIL Codex Harness: {type(exc).__name__}: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"PASS version={result.version}")
    typer.echo(f"PASS image={result.image.reference} id={result.image.image_id}")
    typer.echo(f"PASS exec_flags={','.join(result.required_flags)}")
    typer.echo(
        "PASS toolchain="
        + ",".join(f"{name}={version}" for name, version in result.tool_versions.items())
    )
    typer.echo(f"PASS profile_hash={profile.fingerprint}")
    typer.echo("CODEX_TRACE_COVERAGE=FULL_STREAM")
    typer.echo("REAL_CODEX_SMOKE=NOT_VERIFIED")


@claude_harness_app.command("doctor")
def claude_harness_doctor() -> None:
    """Verify Claude Code version, image, stream flags, toolchains, and fingerprint."""

    try:
        result = asyncio.run(MultiHarnessRuntime(HarnessKind.CLAUDE_CODE).doctor())
        profile = canonical_claude_profile(result.image)
    except DockerPreflightError as exc:
        typer.echo(f"NOT_VERIFIED Claude Code Harness: {exc}")
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"FAIL Claude Code Harness: {type(exc).__name__}: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"PASS version={result.version}")
    typer.echo(f"PASS image={result.image.reference} id={result.image.image_id}")
    typer.echo(f"PASS exec_flags={','.join(result.required_flags)}")
    typer.echo(
        "PASS toolchain="
        + ",".join(f"{name}={version}" for name, version in result.tool_versions.items())
    )
    typer.echo(f"PASS profile_hash={profile.fingerprint}")
    typer.echo("REAL_CLAUDE_SMOKE=NOT_RUN")


@deepseek_harness_app.command("doctor")
def deepseek_harness_doctor() -> None:
    """Verify the public DeepSeek headless/config contracts and pinned runtime."""

    try:
        result = asyncio.run(MultiHarnessRuntime(HarnessKind.DEEPSEEK).doctor())
        if result.config_digest is None:
            raise RuntimeError("effective config digest is missing")
        profile = canonical_deepseek_profile(result.image, result.config_digest)
    except DockerPreflightError as exc:
        typer.echo(f"NOT_VERIFIED DeepSeek Harness: {exc}")
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"FAIL DeepSeek Harness: {type(exc).__name__}: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"PASS version={result.version}")
    typer.echo(f"PASS image={result.image.reference} id={result.image.image_id}")
    typer.echo(f"PASS launcher_flags={','.join(result.required_flags)}")
    typer.echo(f"PASS default_config_digest={result.default_config_digest}")
    typer.echo(f"PASS effective_config_digest={result.config_digest}")
    typer.echo(
        "PASS toolchain="
        + ",".join(f"{name}={version}" for name, version in result.tool_versions.items())
    )
    typer.echo(f"PASS profile_hash={profile.fingerprint}")
    typer.echo(f"DEEPSEEK_E2={DeepSeekSessionExtraction.DEFERRED_NOT_VERIFIED.value}")
    typer.echo("REAL_DEEPSEEK_SMOKE=NOT_RUN")


@model_profile_app.command("validate")
def validate_model_profile(
    profile_path: str = typer.Argument(help="Path to a credential-reference-only model profile."),
) -> None:
    """Validate provider route identity without reading the referenced credential."""

    try:
        profile = load_model_profile(Path(profile_path))
    except ModelProfileError as exc:
        typer.echo(f"FAIL model profile: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"PASS provider={profile.provider} model={profile.requested_model} "
        f"protocol={profile.protocol.value} endpoint_identity={profile.provider_route_identity}"
    )
    typer.echo(f"credential_reference={profile.credential_reference or 'NOT_CONFIGURED'}")


@model_app.command("run")
def run_direct_model(
    task_path: str = typer.Argument(help="Path to an M-Lane versioned task package."),
    profile_path: str = typer.Option(..., "--profile", help="Path to a model profile YAML file."),
    artifact_root: str | None = typer.Option(
        None, "--artifact-root", help="Optional local Phase D evidence directory."
    ),
    allow_custom_endpoint: bool = typer.Option(
        False,
        "--allow-custom-endpoint",
        help="Explicitly trust a non-official endpoint to receive the referenced credential.",
    ),
) -> None:
    """Invoke one direct model attempt, apply its strict patch, and verify it in Docker."""

    try:
        profile = load_model_profile(Path(profile_path))
        runner = DirectModelRunner(
            artifact_root=Path(artifact_root) if artifact_root is not None else None,
            allow_custom_endpoint=allow_custom_endpoint,
        )
        result = asyncio.run(runner.run(Path(task_path), profile))
    except (ModelProfileError, DirectModelRunError, TaskPackageError, OSError) as exc:
        typer.echo(f"FAIL direct model run: {exc}")
        raise typer.Exit(code=1) from exc
    evidence = result.evidence
    typer.echo(f"outcome={evidence.outcome.value}")
    typer.echo(f"task={evidence.task_id}@{evidence.task_version}")
    typer.echo(f"requested_model={evidence.requested_model}")
    typer.echo(f"observed_model={evidence.observed_model or 'NOT_OBSERVED'}")
    typer.echo(f"artifact={result.artifact_directory}")
    if evidence.verifier_score is not None:
        typer.echo(f"score={evidence.verifier_score:.3f}")
    if evidence.outcome is DirectModelOutcome.VERIFIED_PASS:
        return
    if evidence.provider_failure is ProviderFailureCategory.CONFIGURATION:
        raise typer.Exit(code=2)
    raise typer.Exit(code=1)
