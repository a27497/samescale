from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

from harnesslab.budget import BudgetEstimate, BudgetEstimateRequest, estimate_budget
from harnesslab.preflight.models import (
    PreflightObservations,
    PreflightReport,
    PreflightSpecification,
)
from harnesslab.preflight.service import assess_preflight, run_preflight

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
router = APIRouter(prefix="/preflight", tags=["preflight"])


class PreflightAssessmentRequest(PreflightSpecification):
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
