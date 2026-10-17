from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import ValidationError
from starlette.requests import ClientDisconnect

from harnesslab.acceptance_plans import service
from harnesslab.acceptance_plans.models import ChangePlan, CreatePlan
from harnesslab.api.local_configuration import configuration_enabled
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.code_snapshots import service as snapshots
from harnesslab.external_evidence import service as evidence
from harnesslab.local_plans.api import Private
from harnesslab.local_plans.tasks import fail

router = APIRouter(prefix="/acceptance-plans", tags=["private-acceptance-scope"])


async def body[Model: (CreatePlan, ChangePlan)](request: Request, model: type[Model]) -> Model:
    data = bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(data) + len(chunk) > 96_000:
                    raise fail("ACCEPTANCE_SIZE_LIMIT", "Scope request is too large.", 413)
                data.extend(chunk)
        return model.model_validate_json(data)
    except (ValidationError, ValueError, ClientDisconnect, TimeoutError):
        raise fail("INVALID_REQUEST", "Request failed strict schema validation.", 422) from None


def guarded(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return call()
    except WorkbenchAPIError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise fail(
            "ACCEPTANCE_INVALID_INPUT", "Scope input or private storage failed validation.", 409
        ) from None


@router.get("/status")
def status(request: Request, response: Response) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "enabled": configuration_enabled(request)
        and bool(os.environ.get("HARNESSLAB_ACCEPTANCE_PLAN_STORE"))
        and bool(os.environ.get("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY")),
        "execution_enabled": False,
    }


@router.get("/snapshots", dependencies=Private)
def available_snapshots() -> dict[str, Any]:
    def load() -> dict[str, Any]:
        policy = evidence.load_policy()
        root = snapshots.storage(policy)
        items = []
        for folder in sorted(root.iterdir()) if root.exists() else []:
            if folder.name.startswith("."):
                continue
            try:
                snapshot = service.checked_snapshot(folder.name)
                items.append(
                    {
                        "identity": folder.name,
                        "status": "INTACT",
                        "content_digest": snapshot["manifest"]["content_digest"],
                        "file_count": len(snapshot["manifest"]["included"]),
                    }
                )
            except WorkbenchAPIError:
                items.append({"identity": folder.name, "status": "UNAVAILABLE_OR_CHANGED"})
        return {"items": items}

    return guarded(load)


@router.get("", dependencies=Private)
def plans() -> dict[str, Any]:
    return guarded(service.listing)


@router.post("", dependencies=Private)
async def create(request: Request) -> dict[str, Any]:
    value = await body(request, CreatePlan)
    return await asyncio.to_thread(guarded, lambda: service.create(value))


@router.get("/{plan_id}", dependencies=Private)
def detail(plan_id: str) -> dict[str, Any]:
    return guarded(lambda: service.read(plan_id))


@router.post("/{plan_id}/changes", dependencies=Private)
async def change(plan_id: str, request: Request) -> dict[str, Any]:
    value = await body(request, ChangePlan)
    return await asyncio.to_thread(guarded, lambda: service.change(plan_id, value))


@router.post("/{plan_id}/execute", dependencies=Private)
def disabled(plan_id: str) -> None:
    raise fail(
        "ACCEPTANCE_EXECUTION_DISABLED", "Scope confirmation never authorizes execution.", 403
    )
