from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from harnesslab.core.config import Settings
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.judgelab.calibration import execute_calibration
from harnesslab.judgelab.models import (
    JudgeCalibrationPlan,
    JudgeCellSpec,
    JudgeDefinition,
    JudgeSuite,
    digest,
)
from harnesslab.judgelab.plan import (
    build_calibration_plan,
    load_calibration_spec,
    resolve_definitions,
    resolve_suite,
)
from harnesslab.judgelab.report import JudgeCalibrationReport
from harnesslab.release.provider_config import configured_model_profile
from harnesslab.release.smoke import SmokeControlPlane, SmokeControlPlaneError

REAL_JUDGE_CALIBRATION_ID = "core-real-judge-v5"
REAL_JUDGE_CELL_ID = "judge-glm52-opencode-go-chat"
REAL_JUDGE_CALLS = 63


class RealJudgeControlPlaneError(SmokeControlPlaneError):
    """The frozen real Judge campaign cannot be planned or executed safely."""


def build_real_judge_plan(
    repository_root: Path,
    environment: Mapping[str, str] | None = None,
) -> tuple[JudgeCalibrationPlan, JudgeSuite, dict[str, JudgeDefinition]]:
    selected_environment = environment if environment is not None else os.environ
    control = SmokeControlPlane.load(repository_root, plan_version="v5")
    provider = next(
        (
            item
            for item in control.release_plan.selected_profiles
            if item.profile_id == REAL_JUDGE_CELL_ID
        ),
        None,
    )
    if provider is None:
        raise RealJudgeControlPlaneError("frozen GLM-5.2 Judge profile is unavailable")
    reference = provider.credential_reference
    if reference is None or not selected_environment.get(reference, "").strip():
        raise RealJudgeControlPlaneError("required Judge credential reference is missing")
    profile = configured_model_profile(provider, selected_environment)
    suite_root = repository_root / "judge_suites/core-calibration/1.0.0"
    base_spec = load_calibration_spec(suite_root / "calibration.yaml")
    suite = resolve_suite(base_spec, repository_root)
    base_definitions = resolve_definitions(base_spec, repository_root)
    source_cell = base_spec.judge_cells[0]
    definition = base_definitions[source_cell.id]
    cell = JudgeCellSpec(
        id=REAL_JUDGE_CELL_ID,
        definition_reference=source_cell.definition_reference,
        definition_digest=source_cell.definition_digest,
        model_profile=profile,
        profile_identity=digest(profile),
        runner_contract="provider-adapter-v1",
    )
    real_spec = base_spec.model_copy(
        update={
            "calibration_id": REAL_JUDGE_CALIBRATION_ID,
            "name": "HarnessLab Core Real GLM-5.2 Judge Calibration v5",
            "judge_cells": (cell,),
        }
    )
    plan = build_calibration_plan(real_spec, suite, {cell.id: definition})
    if len(plan.slots) != REAL_JUDGE_CALLS:
        raise RealJudgeControlPlaneError("real Judge plan is not exactly 63 evaluation slots")
    return plan, suite, {cell.id: definition}


async def execute_real_judge_calibration(
    repository_root: Path,
    *,
    allow_real_judge: bool,
    artifact_root: Path,
    environment: Mapping[str, str] | None = None,
) -> JudgeCalibrationReport:
    if not allow_real_judge:
        raise RealJudgeControlPlaneError("real Judge requires --allow-real-judge")
    plan, suite, definitions = build_real_judge_plan(repository_root, environment)
    engine = create_engine(Settings())
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            return await execute_calibration(
                session,
                plan=plan,
                suite=suite,
                definitions=definitions,
                artifact_root=artifact_root,
                allow_real_judge=True,
            )
    finally:
        await engine.dispose()
