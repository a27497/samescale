from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

from harnesslab.budget import (
    BudgetEstimate,
    BudgetEstimateRequest,
    MatrixBudgetEstimate,
    MatrixBudgetEstimateRequest,
    estimate_budget,
    estimate_matrix_budget,
)
from harnesslab.preflight.models import (
    MatrixPreflightReport,
    MatrixPreflightSpecification,
    PreflightObservations,
    PreflightReport,
    PreflightSpecification,
)
from harnesslab.preflight.service import (
    assess_matrix_preflight,
    assess_preflight,
    run_matrix_preflight,
    run_preflight,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
router = APIRouter(prefix="/preflight", tags=["preflight"])


class PreflightAssessmentRequest(PreflightSpecification):
    observations: PreflightObservations


class MatrixPreflightAssessmentRequest(MatrixPreflightSpecification):
    observations: PreflightObservations


@router.post("/assess", response_model=PreflightReport)
async def assess(request: PreflightAssessmentRequest) -> PreflightReport:
    specification = PreflightSpecification.model_validate(
        request.model_dump(exclude={"observations"})
    )
    return assess_preflight(specification, request.observations)


@router.post("/run", response_model=PreflightReport)
async def run(specification: PreflightSpecification) -> PreflightReport:
    return await run_preflight(specification, REPOSITORY_ROOT, os.environ)


@router.post("/budget", response_model=BudgetEstimate)
async def budget(request: BudgetEstimateRequest) -> BudgetEstimate:
    return estimate_budget(request)


@router.post("/matrix/assess", response_model=MatrixPreflightReport)
async def assess_matrix(request: MatrixPreflightAssessmentRequest) -> MatrixPreflightReport:
    specification = MatrixPreflightSpecification.model_validate(
        request.model_dump(exclude={"observations"})
    )
    return assess_matrix_preflight(specification, request.observations)


@router.post("/matrix/run", response_model=MatrixPreflightReport)
async def run_matrix(specification: MatrixPreflightSpecification) -> MatrixPreflightReport:
    return await run_matrix_preflight(specification, REPOSITORY_ROOT, os.environ)


@router.post("/matrix/budget", response_model=MatrixBudgetEstimate)
async def matrix_budget(request: MatrixBudgetEstimateRequest) -> MatrixBudgetEstimate:
    return estimate_matrix_budget(request)
