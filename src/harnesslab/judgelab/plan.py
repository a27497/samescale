from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from harnesslab.judgelab.models import (
    JudgeCalibrationPlan,
    JudgeCalibrationSpec,
    JudgeEvaluationSlot,
    JudgeMode,
    JudgeSuite,
    OrderVariant,
    digest,
)
from harnesslab.judgelab.suite import JudgeSuiteError, load_judge_suite
from harnesslab.tasks.package import UniqueKeyLoader


class JudgePlanError(ValueError):
    """Calibration specification cannot resolve to its frozen dependencies."""


def load_calibration_spec(path: Path) -> JudgeCalibrationSpec:
    try:
        raw: Any = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise JudgePlanError(f"invalid calibration spec: {type(exc).__name__}") from exc
    if not isinstance(raw, dict):
        raise JudgePlanError("calibration spec must contain a mapping")
    try:
        return JudgeCalibrationSpec.model_validate(raw)
    except ValidationError as exc:
        raise JudgePlanError(f"invalid calibration spec: {exc}") from exc


def resolve_suite(spec: JudgeCalibrationSpec, repository_root: Path) -> JudgeSuite:
    candidate = (repository_root / spec.suite_reference).resolve()
    suites_root = (repository_root / "judge_suites").resolve()
    if suites_root not in candidate.parents:
        raise JudgePlanError("suite reference escapes judge_suites")
    try:
        suite = load_judge_suite(candidate)
    except JudgeSuiteError as exc:
        raise JudgePlanError(str(exc)) from exc
    if suite.suite_digest != spec.suite_digest:
        raise JudgePlanError("resolved suite digest does not match calibration spec")
    return suite


def build_calibration_plan(spec: JudgeCalibrationSpec, suite: JudgeSuite) -> JudgeCalibrationPlan:
    slots: list[JudgeEvaluationSlot] = []
    public_cases = sorted(suite.public.cases, key=lambda case: case.case_id)
    for cell in sorted(spec.judge_cells, key=lambda item: item.id):
        for case in public_cases:
            if case.mode is JudgeMode.PAIRWISE:
                variants = (
                    (OrderVariant.ORIGINAL, OrderVariant.SWAPPED)
                    if cell.order_swap_policy == "REQUIRED"
                    else (OrderVariant.ORIGINAL,)
                )
            else:
                variants = (OrderVariant.NOT_APPLICABLE,)
            for repeat_index in range(spec.repeat_count):
                for variant in variants:
                    identity = {
                        "calibration_id": spec.calibration_id,
                        "judge_cell_id": cell.id,
                        "suite_digest": suite.suite_digest,
                        "definition_digest": cell.definition_digest,
                        "profile_identity": cell.profile_identity,
                        "case_id": case.case_id,
                        "case_public_digest": case.public_digest,
                        "repeat_index": repeat_index,
                        "order_variant": variant.value,
                    }
                    slots.append(
                        JudgeEvaluationSlot(
                            slot_id=digest(identity),
                            slot_order=len(slots),
                            calibration_id=spec.calibration_id,
                            judge_cell_id=cell.id,
                            case_id=case.case_id,
                            case_mode=case.mode,
                            case_public_digest=case.public_digest,
                            repeat_index=repeat_index,
                            order_variant=variant,
                        )
                    )
    if len({slot.slot_id for slot in slots}) != len(slots):
        raise JudgePlanError("plan expansion produced duplicate logical Judge slots")
    return JudgeCalibrationPlan(
        calibration_id=spec.calibration_id,
        name=spec.name,
        suite_id=suite.public.suite_id,
        suite_version=suite.public.version,
        suite_digest=suite.suite_digest,
        public_digest=suite.public_digest,
        judge_cells=tuple(sorted(spec.judge_cells, key=lambda item: item.id)),
        repeat_count=spec.repeat_count,
        execution_seed=spec.execution_seed,
        qualification_policy=spec.qualification_policy,
        slots=tuple(slots),
    )
