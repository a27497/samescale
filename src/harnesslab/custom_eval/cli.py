from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from pydantic import ValidationError

from harnesslab.custom_eval.builder import CustomTaskBuilder, CustomTaskBuilderError
from harnesslab.custom_eval.evaluation import (
    CustomEvaluationError,
    build_custom_plan,
    build_custom_report,
)
from harnesslab.custom_eval.models import (
    CustomEvaluationPlan,
    CustomPlanRequest,
    CustomRunEvidence,
    CustomTaskBuilderSpec,
    SourceType,
)
from harnesslab.custom_eval.store import ManagedTaskStore, ManagedTaskStoreError
from harnesslab.tasks.package import TaskPackageError, UniqueKeyLoader
from harnesslab.tasks.validation import validate_task_package

custom_eval_app = typer.Typer(
    no_args_is_help=True,
    help="Build and manage isolated, content-addressed custom evaluation tasks.",
)


def _store(path: str) -> ManagedTaskStore:
    return ManagedTaskStore(Path(path))


def _payload(path: str) -> Any:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
        if source.suffix.lower() in {".yaml", ".yml"}:
            return yaml.load(text, Loader=UniqueKeyLoader)
        return json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ManagedTaskStoreError("input artifact is unreadable or invalid") from exc


def _emit(value: object) -> None:
    typer.echo(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


@custom_eval_app.command("import")
def import_task(
    source_type: Annotated[SourceType, typer.Option("--source-type")],
    source: str = typer.Argument(help="Local path or exact git URL."),
    store_root: str = typer.Option(".runtime/custom-eval", "--store"),
    package_subpath: str | None = typer.Option(None, "--package-subpath"),
    commit: str | None = typer.Option(None, "--commit"),
    owner: str | None = typer.Option(None, "--owner"),
    category: str | None = typer.Option(None, "--category"),
    allow_remote_git: bool = typer.Option(False, "--allow-remote-git"),
) -> None:
    """Import a local folder/repository, exact git commit, or prepared task package."""

    try:
        store = _store(store_root)
        if source_type is SourceType.LOCAL_FOLDER:
            record = store.import_local_folder(Path(source), owner=owner, category=category)
        elif source_type is SourceType.PREPARED_PACKAGE:
            record = store.import_prepared_package(Path(source), owner=owner, category=category)
        elif source_type is SourceType.LOCAL_REPOSITORY:
            if package_subpath is None:
                raise ManagedTaskStoreError("local repository import requires --package-subpath")
            record = store.import_local_repository(
                Path(source), package_subpath, owner=owner, category=category
            )
        else:
            if package_subpath is None or commit is None:
                raise ManagedTaskStoreError("git import requires --commit and --package-subpath")
            record = store.import_git_exact_commit(
                source,
                commit,
                package_subpath,
                owner=owner,
                category=category,
                allow_remote_git=allow_remote_git,
            )
    except ManagedTaskStoreError as exc:
        typer.echo(f"FAIL custom import: {exc}")
        raise typer.Exit(code=1) from exc
    _emit(record.model_dump(mode="json"))


@custom_eval_app.command("list")
def list_tasks(store_root: str = typer.Option(".runtime/custom-eval", "--store")) -> None:
    """List frozen custom task identities."""

    try:
        records = _store(store_root).list()
    except ManagedTaskStoreError as exc:
        typer.echo(f"FAIL custom list: {exc}")
        raise typer.Exit(code=1) from exc
    _emit([record.model_dump(mode="json") for record in records])


@custom_eval_app.command("inspect")
def inspect_task(
    reference: str = typer.Argument(help="Custom task reference as <id>@<version>."),
    store_root: str = typer.Option(".runtime/custom-eval", "--store"),
) -> None:
    """Inspect provenance and verify immutable snapshot identity."""

    try:
        record = _store(store_root).inspect(reference)
    except (ManagedTaskStoreError, ValueError) as exc:
        typer.echo(f"FAIL custom inspect: {exc}")
        raise typer.Exit(code=1) from exc
    _emit(record.model_dump(mode="json"))


@custom_eval_app.command("build")
def build_task(
    spec_path: str = typer.Argument(help="JSON or YAML custom task builder spec."),
    destination: str = typer.Option(..., "--destination"),
) -> None:
    """Build and structurally validate a prepared custom task package."""

    try:
        spec = CustomTaskBuilderSpec.model_validate(_payload(spec_path))
        built = CustomTaskBuilder().build(spec, Path(destination))
    except (ValidationError, ManagedTaskStoreError, CustomTaskBuilderError) as exc:
        typer.echo(f"FAIL custom build: {type(exc).__name__}")
        raise typer.Exit(code=1) from exc
    _emit(
        {
            "path": str(built.path),
            "task_identity": built.task_identity,
            "verifier_identity": built.verifier_identity,
            "structurally_validated": built.structurally_validated,
        }
    )


@custom_eval_app.command("validate")
def validate_task(
    reference: str = typer.Argument(help="Custom task reference as <id>@<version>."),
    store_root: str = typer.Option(".runtime/custom-eval", "--store"),
    execute_verifier: bool = typer.Option(False, "--execute-verifier"),
) -> None:
    """Verify snapshot structure, or explicitly run baseline/oracle verifier validation."""

    try:
        store = _store(store_root)
        record, package = store.load_package(reference)
        output: dict[str, object] = {
            "reference": record.reference,
            "snapshot_integrity": "PASS",
            "behavioral_validation": "NOT_RUN",
            "provider_calls": 0,
            "judge_calls": 0,
        }
        if execute_verifier:
            result = validate_task_package(package.root)
            output["behavioral_validation"] = "PASS" if result.valid else "FAIL"
            output["validation"] = result.model_dump(mode="json")
            if not result.valid:
                _emit(output)
                raise typer.Exit(code=1)
    except (ManagedTaskStoreError, TaskPackageError, OSError) as exc:
        typer.echo(f"FAIL custom validate: {exc}")
        raise typer.Exit(code=1) from exc
    _emit(output)


@custom_eval_app.command("plan")
def plan_evaluation(
    request_path: str = typer.Argument(help="JSON or YAML custom plan request."),
    store_root: str = typer.Option(".runtime/custom-eval", "--store"),
) -> None:
    """Freeze a keyless custom plan using canonical Quick/Compare/Formal repeats."""

    try:
        request = CustomPlanRequest.model_validate(_payload(request_path))
        plan = build_custom_plan(request, _store(store_root))
    except (ValidationError, ManagedTaskStoreError, CustomEvaluationError) as exc:
        typer.echo(f"FAIL custom plan: {type(exc).__name__}")
        raise typer.Exit(code=1) from exc
    output = plan.model_dump(mode="json")
    output["plan_digest"] = plan.digest
    _emit(output)


@custom_eval_app.command("report")
def report_evaluation(
    plan_path: str = typer.Argument(help="Frozen custom plan JSON."),
    evidence_path: str = typer.Argument(help="Custom run evidence JSON list."),
) -> None:
    """Generate a custom-only report without provider or Judge execution."""

    try:
        raw_plan = _payload(plan_path)
        if isinstance(raw_plan, dict):
            raw_plan.pop("plan_digest", None)
        plan = CustomEvaluationPlan.model_validate(raw_plan)
        raw_evidence = _payload(evidence_path)
        if not isinstance(raw_evidence, list):
            raise CustomEvaluationError("custom report evidence must contain a list")
        evidence = tuple(CustomRunEvidence.model_validate(item) for item in raw_evidence)
        report = build_custom_report(plan, evidence)
    except (ValidationError, ManagedTaskStoreError, CustomEvaluationError) as exc:
        typer.echo(f"FAIL custom report: {type(exc).__name__}")
        raise typer.Exit(code=1) from exc
    _emit(report.model_dump(mode="json"))


__all__ = ["custom_eval_app"]
