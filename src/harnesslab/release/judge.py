from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.provider import ThinkingMode, ThinkingTransport
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
from harnesslab.registry.alibaba import configured_alibaba_bailian_profile
from harnesslab.release.smoke import SmokeControlPlaneError

REAL_JUDGE_CALIBRATION_ID = "core-real-judge-v6-j1"
REAL_JUDGE_CELL_ID = "judge-glm52-alibaba-bailian-messages"
REAL_JUDGE_CALLS = 63
REAL_JUDGE_SAFE_PARALLELISM = 1
REAL_JUDGE_PREDECESSOR_PLAN_DIGEST = (
    "sha256:0cf4222bc7a9fc896029a406eb81605c83c63ecacd681567a487189d1d6ecd06"
)
REAL_JUDGE_PLAN_DIGEST = "sha256:542e114402b1faff63baf4c993a4a6d1d265df5f0c953e62a57345e4dcf29f86"


class RealJudgeControlPlaneError(SmokeControlPlaneError):
    """The frozen real Judge campaign cannot be planned or executed safely."""


def build_real_judge_plan(
    repository_root: Path,
    environment: Mapping[str, str] | None = None,
) -> tuple[JudgeCalibrationPlan, JudgeSuite, dict[str, JudgeDefinition]]:
    del environment  # Plan construction is keyless; execution resolves the references.
    profile = configured_alibaba_bailian_profile(
        "glm-5.2",
        Protocol.MESSAGES,
        max_output_tokens=256,
        thinking_mode=ThinkingMode.DISABLED,
        thinking_transport=ThinkingTransport.ANTHROPIC_MESSAGES_THINKING_OBJECT,
    ).model_copy(update={"request_timeout_seconds": 90})
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
            "name": "HarnessLab Core Real GLM-5.2 Judge Qualification V6 J1",
            "judge_cells": (cell,),
        }
    )
    plan = build_calibration_plan(real_spec, suite, {cell.id: definition})
    if len(plan.slots) != REAL_JUDGE_CALLS:
        raise RealJudgeControlPlaneError("real Judge plan is not exactly 63 evaluation slots")
    if plan.plan_digest != REAL_JUDGE_PLAN_DIGEST:
        raise RealJudgeControlPlaneError("V6 J1 Judge plan differs from the frozen digest")
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
