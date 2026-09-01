from __future__ import annotations

from pathlib import Path

from harnesslab.judgelab.models import (
    JudgeCalibrationPlan,
    JudgeCalibrationSpec,
    JudgeCellSpec,
    digest,
)
from harnesslab.judgelab.plan import build_calibration_plan
from harnesslab.judgelab.suite import load_judge_definition, load_judge_suite
from harnesslab.release.judge_j3 import configured_j3_profile
from harnesslab.release.judge_methodology_v2 import OBJECTIVE_SUITE_REFERENCE, objective_v2_policy

J4_CALIBRATION_ID = "core-real-judge-v7-j4"
J4_CELL_ID = "judge-grok46-aiwanwu-objective-v2"
J4_CALLS = 63
J4_REPEAT_COUNT = 3
J4_SAFE_PARALLELISM = 1
J4_APPLICATION_RETRY_COUNT = 0
J4_COST_CEILING = "1.000000"
J4_RELAY_MODEL_ALIASES = ("grok-4.6", "grok-4.6-build")


def build_j4_plan(repository_root: Path) -> JudgeCalibrationPlan:
    suite_root = repository_root / OBJECTIVE_SUITE_REFERENCE
    suite = load_judge_suite(suite_root)
    definition = load_judge_definition(suite_root / "definition.yaml")
    profile = configured_j3_profile()
    cell = JudgeCellSpec(
        id=J4_CELL_ID,
        definition_reference=f"{OBJECTIVE_SUITE_REFERENCE}/definition.yaml",
        definition_digest=definition.definition_digest,
        model_profile=profile,
        profile_identity=digest(profile),
        runner_contract="provider-adapter-v1",
    )
    spec = JudgeCalibrationSpec(
        calibration_id=J4_CALIBRATION_ID,
        name="Grok 4.6 aiwanwu objective Judge qualification v2",
        suite_reference=OBJECTIVE_SUITE_REFERENCE,
        suite_digest=suite.suite_digest,
        judge_cells=(cell,),
        repeat_count=J4_REPEAT_COUNT,
        execution_seed=20260901,
        qualification_policy=objective_v2_policy(),
    )
    plan = build_calibration_plan(spec, suite, {cell.id: definition})
    if len(plan.slots) != J4_CALLS:
        raise ValueError("J4 objective qualification must contain exactly 63 slots")
    return plan
