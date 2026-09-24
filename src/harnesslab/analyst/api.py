from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from harnesslab.analyst.api_models import (
    AnalystSessionList,
    AnalystSessionView,
    AnalystSmokePreflight,
)
from harnesslab.analyst.comparison_showcase import ComparisonExample, comparison_example
from harnesslab.analyst.evidence import AnalystEvidenceError
from harnesslab.analyst.models import ProposedRegressionPlan, StrictModel
from harnesslab.analyst.sessions import AnalystSessions, ApprovalRequest, CreateInvestigation
from harnesslab.analyst.showcase import InvestigationExample, historical_example, offline_demo
from harnesslab.api.local_configuration import configuration_enabled
from harnesslab.api.workbench_dependencies import workspace_settings
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.db.session import create_engine
from harnesslab.evidence.reader import EvidenceReadError
from harnesslab.productization.assets import distribution_root
from harnesslab.registry.vault import CredentialVault

router = APIRouter(prefix="/workbench/analyst", tags=["analyst"])
ROOT = Path(__file__).resolve().parents[3]


async def analyst_service(request: Request) -> AsyncIterator[AnalystSessions]:
    settings = workspace_settings()
    engine = create_engine(settings)
    try:
        yield AnalystSessions(
            engine,
            repository_root=ROOT,
            artifact_roots=settings.workbench_artifact_roots,
            environment=os.environ,
            real_enabled=os.environ.get("HARNESSLAB_ANALYST_REAL_ENABLED") == "1",
            local_models_enabled=configuration_enabled(request),
            vault=CredentialVault.from_environment(),
        )
    except (ValueError, AnalystEvidenceError, EvidenceReadError) as exc:
        raise WorkbenchAPIError(
            409,
            "ANALYST_REQUEST_REJECTED",
            "Analyst scope, profile, approval or session state could not be validated.",
        ) from exc
    finally:
        await engine.dispose()


Service = Annotated[AnalystSessions, Depends(analyst_service)]


class ResumeRequest(StrictModel):
    confirm_real: bool = False


@router.get("/sessions", response_model=AnalystSessionList)
async def list_sessions(
    service: Service, experiment_id: str = Query(min_length=1, max_length=100)
) -> dict[str, object]:
    return {"items": [value.public_view() for value in await service.list(experiment_id)]}


@router.post("/sessions", status_code=201, response_model=AnalystSessionView)
async def create_session(request: CreateInvestigation, service: Service) -> dict[str, object]:
    return (await service.create(request)).public_view()


@router.get("/sessions/{session_id}", response_model=AnalystSessionView)
async def get_session(session_id: str, service: Service) -> dict[str, object]:
    return (await service.get(session_id)).public_view()


@router.get("/sessions/{session_id}/preflight", response_model=AnalystSmokePreflight)
async def smoke_preflight(session_id: str, service: Service) -> dict[str, object]:
    return await service.preflight(session_id)


@router.post("/sessions/{session_id}/resume", response_model=AnalystSessionView)
async def resume_session(
    session_id: str, request: ResumeRequest, service: Service
) -> dict[str, object]:
    return (await service.resume(session_id, confirm_real=request.confirm_real)).public_view()


@router.put("/sessions/{session_id}/proposal", response_model=AnalystSessionView)
async def propose(
    session_id: str, request: ProposedRegressionPlan, service: Service
) -> dict[str, object]:
    return (await service.propose(session_id, request)).public_view()


@router.post("/sessions/{session_id}/approval", response_model=AnalystSessionView)
async def approve(session_id: str, request: ApprovalRequest, service: Service) -> dict[str, object]:
    return (await service.approve(session_id, request)).public_view()


@router.post("/examples/offline", response_model=InvestigationExample)
async def run_offline_example() -> InvestigationExample:
    try:
        return await offline_demo()
    except ValueError as exc:
        raise WorkbenchAPIError(
            409, "OFFLINE_DEMO_REJECTED", "Offline demo did not produce validated evidence."
        ) from exc


@router.get("/examples/historical", response_model=InvestigationExample)
async def read_historical_example() -> InvestigationExample:
    try:
        return historical_example(ROOT)
    except (OSError, ValueError) as exc:
        raise WorkbenchAPIError(
            409,
            "HISTORICAL_EVIDENCE_UNAVAILABLE",
            "Frozen historical evidence is missing or failed digest validation.",
        ) from exc


@router.get("/examples/comparison", response_model=ComparisonExample)
async def read_comparison_example() -> ComparisonExample:
    try:
        return comparison_example(distribution_root())
    except (OSError, ValueError) as exc:
        raise WorkbenchAPIError(
            409,
            "COMPARISON_EVIDENCE_UNAVAILABLE",
            "Frozen comparison evidence is unavailable or invalid.",
        ) from exc
