from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, model_validator

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.custom_eval.builder import CustomTaskBuilder, CustomTaskBuilderError
from harnesslab.custom_eval.evaluation import (
    CustomEvaluationError,
    build_custom_plan,
    build_custom_report,
)
from harnesslab.custom_eval.models import (
    CustomEvaluationPlan,
    CustomEvaluationReport,
    CustomPlanRequest,
    CustomRunEvidence,
    CustomTaskBuilderSpec,
    ManagedTaskRecord,
    SourceType,
)
from harnesslab.custom_eval.store import ManagedTaskStore, ManagedTaskStoreError

router = APIRouter(prefix="/custom-eval", tags=["custom-evaluation"])


def custom_task_store() -> ManagedTaskStore:
    root = Path(os.environ.get("HARNESSLAB_CUSTOM_EVAL_STORE", ".runtime/custom-eval"))
    return ManagedTaskStore(root)


Store = Annotated[ManagedTaskStore, Depends(custom_task_store)]


class CustomImportRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: SourceType
    source: str
    package_subpath: str | None = None
    commit: str | None = None
    owner: str | None = None
    category: str | None = None
    allow_remote_git: bool = False

    @model_validator(mode="after")
    def source_contract_is_complete(self) -> CustomImportRequest:
        if (
            self.source_type in {SourceType.LOCAL_REPOSITORY, SourceType.GIT_EXACT_COMMIT}
            and self.package_subpath is None
        ):
            raise ValueError("repository imports require package_subpath")
        if self.source_type is SourceType.GIT_EXACT_COMMIT and self.commit is None:
            raise ValueError("git imports require an exact commit")
        return self


class CustomBuildRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec: CustomTaskBuilderSpec


class CustomValidationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: str
    snapshot_integrity: str
    behavioral_validation: str
    provider_calls: int
    judge_calls: int


class CustomReportRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan: CustomEvaluationPlan
    evidence: tuple[CustomRunEvidence, ...]


def _invalid(exc: Exception, operation: str) -> WorkbenchAPIError:
    return WorkbenchAPIError(
        422,
        "INVALID_CUSTOM_EVALUATION",
        f"custom evaluation {operation} failed backend validation",
    )


@router.post("/imports", response_model=ManagedTaskRecord)
async def import_task(request: CustomImportRequest, store: Store) -> ManagedTaskRecord:
    try:
        if request.source_type is SourceType.LOCAL_FOLDER:
            return store.import_local_folder(
                Path(request.source), owner=request.owner, category=request.category
            )
        if request.source_type is SourceType.PREPARED_PACKAGE:
            return store.import_prepared_package(
                Path(request.source), owner=request.owner, category=request.category
            )
        assert request.package_subpath is not None
        if request.source_type is SourceType.LOCAL_REPOSITORY:
            return store.import_local_repository(
                Path(request.source),
                request.package_subpath,
                owner=request.owner,
                category=request.category,
            )
        assert request.commit is not None
        return store.import_git_exact_commit(
            request.source,
            request.commit,
            request.package_subpath,
            owner=request.owner,
            category=request.category,
            allow_remote_git=request.allow_remote_git,
        )
    except ManagedTaskStoreError as exc:
        raise _invalid(exc, "import") from exc


@router.get("/tasks", response_model=tuple[ManagedTaskRecord, ...])
async def list_tasks(store: Store) -> tuple[ManagedTaskRecord, ...]:
    return store.list()


@router.get("/tasks/{task_id}/{version}", response_model=ManagedTaskRecord)
async def inspect_task(task_id: str, version: str, store: Store) -> ManagedTaskRecord:
    try:
        return store.inspect(f"{task_id}@{version}")
    except (ManagedTaskStoreError, ValueError) as exc:
        raise WorkbenchAPIError(404, "CUSTOM_TASK_NOT_FOUND", "custom task does not exist") from exc


@router.post("/build", response_model=ManagedTaskRecord)
async def build_task(request: CustomBuildRequest, store: Store) -> ManagedTaskRecord:
    try:
        with tempfile.TemporaryDirectory(prefix="harnesslab-custom-build-") as temporary:
            built = CustomTaskBuilder().build(request.spec, Path(temporary))
            return store.import_prepared_package(built.path)
    except (CustomTaskBuilderError, ManagedTaskStoreError) as exc:
        raise _invalid(exc, "build") from exc


@router.post("/validate/{task_id}/{version}", response_model=CustomValidationResponse)
async def validate_task(task_id: str, version: str, store: Store) -> CustomValidationResponse:
    """Perform safe structural/integrity validation; verifier execution stays explicit in CLI."""

    try:
        record, _package = store.load_package(f"{task_id}@{version}")
    except (ManagedTaskStoreError, ValueError) as exc:
        raise _invalid(exc, "validation") from exc
    return CustomValidationResponse(
        reference=record.reference,
        snapshot_integrity="PASS",
        behavioral_validation="NOT_RUN",
        provider_calls=0,
        judge_calls=0,
    )


@router.post("/plan", response_model=CustomEvaluationPlan)
async def plan_evaluation(request: CustomPlanRequest, store: Store) -> CustomEvaluationPlan:
    try:
        return build_custom_plan(request, store)
    except (ManagedTaskStoreError, CustomEvaluationError) as exc:
        raise _invalid(exc, "planning") from exc


@router.post("/report", response_model=CustomEvaluationReport)
async def report_evaluation(request: CustomReportRequest) -> CustomEvaluationReport:
    try:
        return build_custom_report(request.plan, request.evidence)
    except CustomEvaluationError as exc:
        raise _invalid(exc, "reporting") from exc


__all__ = ["custom_task_store", "router"]
