from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.api.local_configuration import (
    configuration_enabled,
    configured_credentials,
    local_operator,
    workspace_catalog,
)
from harnesslab.api.workbench_dependencies import workbench_session
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.db.models.local_plan import LocalTaskPlanRecord
from harnesslab.local_plans import service
from harnesslab.local_plans.models import (
    PlanConfirmation,
    PlanRequest,
    PreflightReceipt,
    SavedPlan,
    TaskInspection,
)
from harnesslab.local_plans.tasks import (
    LocalImport,
    fail,
    import_task,
    inspect_task,
    load_policy,
    task_store,
)
from harnesslab.registry.models import RegistryCatalog

router = APIRouter(prefix="/local-plans", tags=["private-local-planning"])
Session = Annotated[AsyncSession, Depends(workbench_session)]
Catalog = Annotated[RegistryCatalog, Depends(workspace_catalog)]
Credentials = Annotated[frozenset[str], Depends(configured_credentials)]


async def private_planning(request: Request, response: Response) -> None:
    await local_operator(request)
    response.headers["Cache-Control"] = "no-store"


Private = [Depends(private_planning)]


@router.get("/status")
async def status(request: Request, response: Response) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "enabled": configuration_enabled(request)
        and bool(os.environ.get("HARNESSLAB_LOCAL_TASK_POLICY")),
        "execution_enabled": False,
    }


@router.get("/sources", dependencies=Private)
async def sources() -> dict[str, object]:
    policy = load_policy()
    candidates = []
    for key, root in policy.source_roots.items():
        # Discovery returns names only. Import performs bounded structural validation.
        for path in sorted(root.glob("*/*/task.yaml"))[:100]:
            if (
                not path.is_symlink()
                and not path.parent.is_symlink()
                and not path.parent.parent.is_symlink()
            ):
                candidates.append(
                    {"root_id": key, "relative_path": path.parent.relative_to(root).as_posix()}
                )
    return {"root_ids": sorted(policy.source_roots), "candidates": candidates}


@router.post("/tasks/import", dependencies=Private, response_model=TaskInspection)
async def ingest(request: LocalImport) -> TaskInspection:
    try:
        return import_task(load_policy(), request)
    except (OSError, ValueError):
        raise fail(
            "TASK_IMPORT_INVALID", "Task import failed its path, identity or structural contract."
        ) from None


@router.get("/tasks", dependencies=Private)
async def tasks() -> dict[str, object]:
    policy = load_policy()
    try:
        records = task_store(policy).list()
        return {"items": [inspect_task(policy, r.reference)[0] for r in records]}
    except (OSError, ValueError):
        raise fail(
            "TASK_INTEGRITY_ERROR",
            "Managed task integrity failed. Inspect the local source before continuing.",
            409,
        ) from None


@router.get("/tasks/{reference}", dependencies=Private, response_model=TaskInspection)
async def inspect(reference: str) -> TaskInspection:
    try:
        return inspect_task(load_policy(), reference)[0]
    except (OSError, ValueError):
        raise fail("TASK_INTEGRITY_ERROR", "Managed task is missing or invalid.", 409) from None


@router.get("/configurations", dependencies=Private)
async def configurations(catalog: Catalog) -> dict[str, object]:
    return {
        "items": [
            {
                "provider_profile_id": model.profile_id,
                "harness_profile_id": profile.profile_id,
                "requested_model": model.requested_model,
                "reasoning_effort": profile.reasoning_effort,
                "runtime_version": harness.version,
                "image_reference": harness.image_reference,
                "enabled": model.enabled and profile.enabled,
                "configuration_label": (
                    f"{model.requested_model} · Codex {harness.version}"
                    f" · {profile.reasoning_effort}"
                ),
            }
            for harness in catalog.harnesses
            if harness.harness_id == "codex"
            for profile in harness.profiles
            for model in catalog.provider_model_profiles
            if model.profile_id in profile.supported_provider_profile_ids
            and model.purpose == "SUBJECT"
        ]
    }


@router.post("/preflight", dependencies=Private)
async def preflight(
    request: PlanRequest, session: Session, catalog: Catalog, credentials: Credentials
) -> PreflightReceipt:
    return await service.preflight(session, request, catalog, credentials)


@router.post("/plans", dependencies=Private, response_model=SavedPlan)
async def save(
    request: PlanConfirmation, session: Session, catalog: Catalog, credentials: Credentials
) -> SavedPlan:
    return await service.confirm(session, request, catalog, credentials)


@router.get("/plans", dependencies=Private)
async def plans(
    session: Session,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    records = await session.scalars(
        select(LocalTaskPlanRecord)
        .order_by(LocalTaskPlanRecord.created_at.desc(), LocalTaskPlanRecord.id)
        .limit(limit)
        .offset(offset)
    )
    items = []
    for row in records:
        plan = service.validated_plan(row)
        assert plan.preflight.material is not None
        material = plan.preflight.material
        items.append(
            {
                "plan_id": plan.plan_id,
                "name": material.request.name,
                "task_reference": material.task.reference,
                "created_at": plan.created_at,
                "status": plan.status,
                "execution_authorized": False,
            }
        )
    total = await session.scalar(select(func.count()).select_from(LocalTaskPlanRecord))
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


@router.get("/plans/{plan_id}", dependencies=Private)
async def get_plan(
    plan_id: str, session: Session, catalog: Catalog, credentials: Credentials
) -> dict[str, object]:
    row = await session.get(LocalTaskPlanRecord, plan_id)
    if row is None:
        raise fail("PLAN_NOT_FOUND", "Saved plan does not exist.", 404)
    plan = service.validated_plan(row)
    assert plan.preflight.material is not None
    current, checks = service.assess(plan.preflight.material.request, catalog, credentials)
    unchanged = (
        current is not None and current.material_digest == plan.preflight.material.material_digest
    )
    return {
        "plan": plan,
        "current_status": "UNCHANGED_RECHECK_REQUIRED" if unchanged else "STALE",
        "checks": checks,
        "execution_enabled": False,
    }


@router.post("/plans/{plan_id}/execute", dependencies=Private)
async def execution_disabled(plan_id: str) -> None:
    raise WorkbenchAPIError(
        403,
        "PHASE1_EXECUTION_DISABLED",
        "This phase saves plans only. Execution requires separate authorization "
        "and an independent worker.",
    )
