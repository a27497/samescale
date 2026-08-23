from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from harnesslab.judgelab.models import (
    JudgeCalibrationPlan,
    JudgeCalibrationSpec,
    JudgeDefinition,
    JudgeEvaluationSlot,
    JudgeMode,
    JudgeSuite,
    OrderVariant,
    digest,
)
from harnesslab.judgelab.suite import JudgeSuiteError, load_judge_definition, load_judge_suite
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


def resolve_definitions(
    spec: JudgeCalibrationSpec, repository_root: Path
) -> dict[str, JudgeDefinition]:
    definitions: dict[str, JudgeDefinition] = {}
    suites_root = (repository_root / "judge_suites").resolve()
    for cell in spec.judge_cells:
        candidate = (repository_root / cell.definition_reference).resolve()
        if suites_root not in candidate.parents:
            raise JudgePlanError("definition reference escapes judge_suites")
        try:
            definition = load_judge_definition(candidate)
        except JudgeSuiteError as exc:
            raise JudgePlanError(str(exc)) from exc
        if definition.definition_digest != cell.definition_digest:
            raise JudgePlanError(f"definition digest mismatch for Judge cell {cell.id}")
        definitions[cell.id] = definition
    return definitions


def build_calibration_plan(
    spec: JudgeCalibrationSpec,
    suite: JudgeSuite,
    definitions: dict[str, JudgeDefinition],
) -> JudgeCalibrationPlan:
    slots: list[JudgeEvaluationSlot] = []
    public_cases = sorted(suite.public.cases, key=lambda case: case.case_id)
    for cell in sorted(spec.judge_cells, key=lambda item: item.id):
        definition = definitions.get(cell.id)
        if definition is None or definition.definition_digest != cell.definition_digest:
            raise JudgePlanError(f"resolved definition missing or mismatched for cell {cell.id}")
        unsupported = sorted(
            case.case_id for case in public_cases if case.mode not in definition.supported_modes
        )
        if unsupported:
            raise JudgePlanError(
                f"JudgeDefinition for cell {cell.id} does not support cases: "
                f"{','.join(unsupported)}"
            )
        for case in public_cases:
            if case.mode is JudgeMode.PAIRWISE:
                variants = (
                    (OrderVariant.ORIGINAL, OrderVariant.SWAPPED)
                    if definition.order_swap_policy == "REQUIRED"
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
    plan = JudgeCalibrationPlan(
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
    validate_plan_definitions(plan, suite, definitions)
    return plan


def validate_plan_definitions(
    plan: JudgeCalibrationPlan,
    suite: JudgeSuite,
    definitions: dict[str, JudgeDefinition],
) -> None:
    cases = {case.case_id: case for case in suite.public.cases}
    for cell in plan.judge_cells:
        definition = definitions.get(cell.id)
        if definition is None or definition.definition_digest != cell.definition_digest:
            raise JudgePlanError(f"resolved definition missing or mismatched for cell {cell.id}")
        unsupported = sorted(
            case.case_id for case in cases.values() if case.mode not in definition.supported_modes
        )
        if unsupported:
            raise JudgePlanError(
                f"JudgeDefinition for cell {cell.id} does not support cases: "
                f"{','.join(unsupported)}"
            )
        for case in cases.values():
            expected = (
                {OrderVariant.ORIGINAL, OrderVariant.SWAPPED}
                if case.mode is JudgeMode.PAIRWISE and definition.order_swap_policy == "REQUIRED"
                else {OrderVariant.ORIGINAL}
                if case.mode is JudgeMode.PAIRWISE
                else {OrderVariant.NOT_APPLICABLE}
            )
            for repeat_index in range(plan.repeat_count):
                actual = {
                    slot.order_variant
                    for slot in plan.slots
                    if slot.judge_cell_id == cell.id
                    and slot.case_id == case.case_id
                    and slot.repeat_index == repeat_index
                }
                if actual != expected:
                    raise JudgePlanError(
                        f"plan order variants disagree with JudgeDefinition for cell {cell.id}"
                    )
