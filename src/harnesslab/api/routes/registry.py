from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.api.workbench_dependencies import workbench_session
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.db.models.registry import RegistryExperimentSnapshotRecord
from harnesslab.experiment.methodology import EvaluationMode, load_evaluation_methodology
from harnesslab.experiment.spec import ExperimentSpecError
from harnesslab.registry.models import (
    CapabilityRegistryResponse,
    ExperimentBuilderRequest,
    ExperimentPreflight,
    ExperimentSnapshot,
    HarnessRegistryResponse,
    MethodologyRegistryItem,
    MethodologyRegistryResponse,
    ModelRegistryResponse,
    ProviderRegistryResponse,
    RegistryCatalog,
    RegistryError,
    RegistrySettings,
    TaskRegistryResponse,
)
from harnesslab.registry.service import (
    all_capabilities,
    build_experiment_snapshot,
    preflight_experiment,
    registry_catalog,
    registry_settings,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
Session = Annotated[AsyncSession, Depends(workbench_session)]
registry_router = APIRouter(prefix="/registry", tags=["registry-lite"])
experiment_router = APIRouter(prefix="/experiments", tags=["registry-lite-experiments"])


def _catalog() -> RegistryCatalog:
    return registry_catalog(REPOSITORY_ROOT, os.environ)


@registry_router.get("/providers", response_model=ProviderRegistryResponse)
async def providers() -> ProviderRegistryResponse:
    catalog = _catalog()
    return ProviderRegistryResponse(
        registry_id=catalog.registry_id,
        registry_digest=catalog.digest,
        items=catalog.providers,
    )


@registry_router.get("/models", response_model=ModelRegistryResponse)
async def models() -> ModelRegistryResponse:
    catalog = _catalog()
    return ModelRegistryResponse(
        registry_id=catalog.registry_id,
        registry_digest=catalog.digest,
        models=catalog.models,
        provider_profiles=catalog.provider_model_profiles,
    )


@registry_router.get("/harnesses", response_model=HarnessRegistryResponse)
async def harnesses() -> HarnessRegistryResponse:
    catalog = _catalog()
    return HarnessRegistryResponse(
        registry_id=catalog.registry_id,
        registry_digest=catalog.digest,
        items=catalog.harnesses,
    )


@registry_router.get("/capabilities", response_model=CapabilityRegistryResponse)
async def capabilities() -> CapabilityRegistryResponse:
    catalog = _catalog()
    return CapabilityRegistryResponse(
        registry_id=catalog.registry_id,
        registry_digest=catalog.digest,
        items=all_capabilities(catalog),
    )


@registry_router.get("/settings", response_model=RegistrySettings)
async def settings() -> RegistrySettings:
    catalog = _catalog()
    return registry_settings(catalog, os.environ)


@registry_router.get("/tasks", response_model=TaskRegistryResponse)
async def tasks() -> TaskRegistryResponse:
    catalog = _catalog()
    return TaskRegistryResponse(
        registry_id=catalog.registry_id,
        registry_digest=catalog.digest,
        items=catalog.tasks,
    )


@registry_router.get("/methodologies", response_model=MethodologyRegistryResponse)
async def methodologies() -> MethodologyRegistryResponse:
    methodology = load_evaluation_methodology(
        REPOSITORY_ROOT / "release/evaluation-methodology-v2.json"
    )
    return MethodologyRegistryResponse(
        items=(
            MethodologyRegistryItem(
                methodology_id=methodology.methodology_id,
                methodology_digest=methodology.digest,
                active=methodology.active,
                evaluation_modes=tuple(EvaluationMode),
                repeat_counts={mode: mode.repeat_count for mode in EvaluationMode},
                scheduling_policy=methodology.scheduling.id,
            ),
        )
    )


@experiment_router.post("/preflight", response_model=ExperimentPreflight)
async def preflight(request: ExperimentBuilderRequest) -> ExperimentPreflight:
    return preflight_experiment(request, REPOSITORY_ROOT, os.environ)


@experiment_router.post("/snapshot", response_model=ExperimentSnapshot)
async def snapshot(request: ExperimentBuilderRequest, session: Session) -> ExperimentSnapshot:
    try:
        frozen = build_experiment_snapshot(request, REPOSITORY_ROOT, os.environ)
    except (RegistryError, ExperimentSpecError, ValueError) as exc:
        raise WorkbenchAPIError(
            422,
            "INVALID_REGISTRY_SELECTION",
            "snapshot selection failed backend validation",
        ) from exc
    existing = await session.get(RegistryExperimentSnapshotRecord, frozen.snapshot_id)
    if existing is not None:
        # The ID binds treatment/runtime identities. Volatile provider status may
        # change a new preflight result, but it never mutates the frozen snapshot.
        return ExperimentSnapshot.model_validate(existing.snapshot_json)
    session.add(
        RegistryExperimentSnapshotRecord(
            id=frozen.snapshot_id,
            snapshot_digest=frozen.snapshot_digest,
            methodology_id=frozen.methodology_id,
            methodology_digest=frozen.methodology_digest,
            preflight_status=frozen.preflight.status.value,
            snapshot_json=frozen.model_dump(mode="json"),
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise WorkbenchAPIError(
            409, "IMMUTABLE_SNAPSHOT_CONFLICT", "snapshot identity already exists"
        ) from exc
    return frozen


@experiment_router.get("/snapshots/{snapshot_id}", response_model=ExperimentSnapshot)
async def get_snapshot(snapshot_id: str, session: Session) -> ExperimentSnapshot:
    record = await session.get(RegistryExperimentSnapshotRecord, snapshot_id)
    if record is None:
        raise WorkbenchAPIError(404, "NOT_FOUND", "experiment snapshot does not exist")
    try:
        return ExperimentSnapshot.model_validate(record.snapshot_json)
    except ValueError as exc:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "experiment snapshot is invalid"
        ) from exc
