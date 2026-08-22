from __future__ import annotations

from pathlib import Path

from harnesslab.tasks.models import (
    EvidenceAsset,
    EvidenceManifest,
    OutcomeCategory,
    TaskValidationResult,
    VerifierExecutionResult,
)
from harnesslab.tasks.package import MaterializedTask, TaskPackage, digest_tree
from harnesslab.tasks.verifier import execute_verifier


def _evidence(
    package: TaskPackage,
    materialized: MaterializedTask,
    result: VerifierExecutionResult,
    run_kind: str,
) -> EvidenceManifest:
    return EvidenceManifest(
        task_id=package.definition.id,
        task_version=package.definition.version,
        task_digest=package.definition.content_digest,
        workspace_digest=package.workspace_digest(materialized),
        verifier=EvidenceAsset(
            kind="hidden_verifier",
            path=package.manifest.verifier.entrypoint,
            digest=package.verifier_digest,
        ),
        result=result,
        run_kind=run_kind,
    )


def _trusted_assets_are_hidden(materialized: MaterializedTask) -> bool:
    exposed_names = {path.name for path in materialized.root.iterdir()}
    return "verifier" not in exposed_names and "oracle" not in exposed_names


def validate_task_package(path: Path) -> TaskValidationResult:
    package = TaskPackage.load(path)
    errors: list[str] = []
    if digest_tree(package.root) != package.definition.content_digest:
        errors.append("task digest is not reproducible")

    baseline_workspace = package.materialize()
    oracle_workspace = package.materialize()
    try:
        if not _trusted_assets_are_hidden(baseline_workspace):
            errors.append("trusted verifier/oracle assets leaked into the subject materialization")
        baseline_result = execute_verifier(package, baseline_workspace)
        package.apply_oracle(oracle_workspace)
        oracle_result = execute_verifier(package, oracle_workspace)

        if baseline_result.category is not OutcomeCategory.SUBJECT_RESULT:
            errors.append(f"baseline verifier invalid: {baseline_result.category.value}")
        elif baseline_result.passed:
            errors.append("untouched baseline unexpectedly passed")
        if oracle_result.category is not OutcomeCategory.SUBJECT_RESULT:
            errors.append(f"oracle verifier invalid: {oracle_result.category.value}")
        elif not oracle_result.passed:
            errors.append("oracle overlay did not pass")

        baseline_evidence = _evidence(
            package, baseline_workspace, baseline_result, run_kind="baseline"
        )
        oracle_evidence = _evidence(package, oracle_workspace, oracle_result, run_kind="oracle")
    finally:
        baseline_workspace.cleanup()
        oracle_workspace.cleanup()

    return TaskValidationResult(
        valid=not errors,
        task_id=package.definition.id,
        task_version=package.definition.version,
        task_digest=package.definition.content_digest,
        baseline=baseline_evidence,
        oracle=oracle_evidence,
        errors=tuple(errors),
    )
