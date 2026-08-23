from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.api.workbench_dependencies import workbench_session
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.api.workbench_models import (
    CoreReadinessResponse,
    ExperimentDetail,
    ExperimentListResponse,
    ExperimentReportResponse,
    ExperimentStatusResponse,
    JudgeCalibrationDetail,
    JudgeCalibrationListResponse,
    MatrixResponse,
    RegressionCompareRequest,
    RegressionCompareResponse,
    RunDetail,
    RunListResponse,
    TraceResponse,
)
from harnesslab.api.workbench_service import (
    core_readiness,
    experiment_detail,
    experiment_report,
    experiment_status,
    judge_calibration_detail,
    list_experiments,
    list_judge_calibrations,
    list_runs,
    matrix,
    regression_compare,
    run_detail,
    trace_detail,
)

router = APIRouter(prefix="/workbench", tags=["workbench"])
Session = Annotated[AsyncSession, Depends(workbench_session)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0, le=100_000)]


@router.get("/experiments", response_model=ExperimentListResponse)
async def experiments(
    session: Session,
    limit: PageLimit = 25,
    offset: PageOffset = 0,
    status: str | None = Query(default=None, max_length=30),
    search: str | None = Query(default=None, max_length=200),
) -> ExperimentListResponse:
    return await list_experiments(
        session,
        limit=limit,
        offset=offset,
        status_filter=status,
        search=search,
    )


@router.get("/experiments/{experiment_id}", response_model=ExperimentDetail)
async def get_experiment(experiment_id: str, session: Session) -> ExperimentDetail:
    return await experiment_detail(session, experiment_id)


@router.get("/experiments/{experiment_id}/matrix", response_model=MatrixResponse)
async def get_matrix(experiment_id: str, session: Session) -> MatrixResponse:
    return await matrix(session, experiment_id)


@router.get("/experiments/{experiment_id}/runs", response_model=RunListResponse)
async def runs(
    experiment_id: str,
    session: Session,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    cell: str | None = Query(default=None, max_length=100),
    task: str | None = Query(default=None, max_length=100),
    lane: str | None = Query(default=None, max_length=1),
    status: str | None = Query(default=None, max_length=30),
    outcome: str | None = Query(default=None, max_length=30),
) -> RunListResponse:
    return await list_runs(
        session,
        experiment_id,
        limit=limit,
        offset=offset,
        cell=cell,
        task=task,
        lane=lane,
        status_filter=status,
        outcome=outcome,
    )


@router.get("/experiments/{experiment_id}/report", response_model=ExperimentReportResponse)
async def get_report(experiment_id: str, session: Session) -> ExperimentReportResponse:
    return await experiment_report(session, experiment_id)


@router.get("/experiments/{experiment_id}/status", response_model=ExperimentStatusResponse)
async def get_status(experiment_id: str, session: Session) -> ExperimentStatusResponse:
    return await experiment_status(session, experiment_id)


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, session: Session) -> RunDetail:
    return await run_detail(session, run_id)


@router.get("/runs/{run_id}/trace", response_model=TraceResponse)
async def get_trace(
    run_id: str,
    session: Session,
    path: str | None = Query(default=None, include_in_schema=False),
) -> TraceResponse:
    if path is not None:
        raise WorkbenchAPIError(
            422, "INVALID_ARTIFACT_REFERENCE", "artifact paths are not accepted"
        )
    return await trace_detail(session, run_id)


@router.get("/judgelab/calibrations", response_model=JudgeCalibrationListResponse)
async def calibrations(
    session: Session, limit: PageLimit = 25, offset: PageOffset = 0
) -> JudgeCalibrationListResponse:
    return await list_judge_calibrations(session, limit=limit, offset=offset)


@router.get("/judgelab/calibrations/{calibration_id}", response_model=JudgeCalibrationDetail)
async def get_calibration(calibration_id: str, session: Session) -> JudgeCalibrationDetail:
    return await judge_calibration_detail(session, calibration_id)


@router.post("/regression/compare", response_model=RegressionCompareResponse)
async def compare(request: RegressionCompareRequest, session: Session) -> RegressionCompareResponse:
    return await regression_compare(session, request)


@router.get("/core-readiness", response_model=CoreReadinessResponse)
async def readiness(session: Session) -> CoreReadinessResponse:
    return await core_readiness(session)
