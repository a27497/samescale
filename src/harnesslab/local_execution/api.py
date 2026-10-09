from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.local_execution import service
from harnesslab.local_execution.models import AuthorizationRequest
from harnesslab.local_execution.policy import load_execution_policy
from harnesslab.local_plans.api import Catalog, Credentials, Private, Session

router = APIRouter(prefix="/local-execution", tags=["private-local-execution"])


@router.get("/status", dependencies=Private)
async def status() -> dict[str, object]:
    try:
        load_execution_policy()
        return {
            "enabled": True,
            "mode": "FAKE_CODEX",
            "real_execution_enabled": False,
            "reason_codes": ["REAL_COST_TOKEN_CAP_UNAVAILABLE"],
            "model_calls_allowed": 0,
        }
    except WorkbenchAPIError as exc:
        return {
            "enabled": False,
            "mode": "FAKE_CODEX",
            "real_execution_enabled": False,
            "reason_codes": [exc.code],
            "model_calls_allowed": 0,
        }


@router.post("/plans/{plan_id}/authorize", dependencies=Private)
async def authorize(
    plan_id: str,
    request: AuthorizationRequest,
    session: Session,
    catalog: Catalog,
    credentials: Credentials,
) -> dict[str, object]:
    return await service.authorize(session, plan_id, request, catalog, credentials)


@router.get("/plans/{plan_id}", dependencies=Private)
async def view(plan_id: str, session: Session) -> dict[str, object]:
    return await service.view(session, plan_id)


class Cancellation(BaseModel):
    action: Literal["CANCEL"]


@router.post("/plans/{plan_id}/cancel", dependencies=Private)
async def cancel(plan_id: str, request: Cancellation, session: Session) -> dict[str, object]:
    return await service.cancel(session, plan_id)
