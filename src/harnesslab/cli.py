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
from harnesslab.analyst.cli import analyst_app
from harnesslab.comparability.engine import ComparabilityEngine
from harnesslab.comparability.manifest import ComparabilityInputError, load_manifest_facts
from harnesslab.comparability.models import ComparabilityIntent
from harnesslab.core.config import Settings
from harnesslab.db.health import check_database
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
from harnesslab.release.smoke import (
    SmokeControlPlane,
    SmokeControlPlaneError,
    SmokeExecutionStatus,
    execute_real_smoke,
)
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
app.add_typer(task_app, name="task")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(model_app, name="model")
app.add_typer(harness_app, name="harness")
app.add_typer(compare_app, name="compare")
app.add_typer(experiment_app, name="experiment")
app.add_typer(run_app, name="run")
app.add_typer(report_app, name="report")
app.add_typer(judge_app, name="judge")
app.add_typer(analyst_app, name="analyst")
app.add_typer(release_app, name="release")
model_app.add_typer(model_profile_app, name="profile")
harness_app.add_typer(codex_harness_app, name="codex")
harness_app.add_typer(claude_harness_app, name="claude")
harness_app.add_typer(deepseek_harness_app, name="deepseek")
release_app.add_typer(release_smoke_app, name="smoke")


@release_smoke_app.command("preflight")
def preflight_release_smoke(
    repository_root: str = typer.Option(
        ".", "--repository-root", help="Repository containing the frozen release plans."
    ),
) -> None:
    """Validate the exact eight-call plan keylessly, without resolving secrets or networking."""

    try:
        control = SmokeControlPlane.load(Path(repository_root))
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
) -> None:
    """Execute the exact smoke plan; it is inert unless the explicit authorization flag is set."""

    try:
        receipt = asyncio.run(
            execute_real_smoke(
                Path(repository_root),
                allow_real_smoke=allow_real_smoke,
                artifact_root=Path(artifact_root) if artifact_root is not None else None,
            )
        )
    except SmokeControlPlaneError as exc:
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
    typer.echo("REAL_CODEX_SMOKE=NOT_RUN")


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
        f"protocol={profile.protocol.value} endpoint={profile.base_url}{profile.route}"
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
