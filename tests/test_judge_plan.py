from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from harnesslab.judgelab.models import (
    JudgeCalibrationSpec,
    JudgeCellSpec,
    JudgeDefinition,
    JudgeMode,
    JudgeSuite,
    OrderVariant,
)
from harnesslab.judgelab.plan import (
    JudgePlanError,
    build_calibration_plan,
    load_calibration_spec,
    validate_plan_definitions,
)
from harnesslab.judgelab.suite import load_judge_definition, load_judge_suite

ROOT = Path(__file__).resolve().parents[1]
SUITE_ROOT = ROOT / "judge_suites/core-calibration/1.0.0"


def _inputs() -> tuple[
    JudgeSuite, JudgeDefinition, JudgeCalibrationSpec, dict[str, JudgeDefinition]
]:
    suite = load_judge_suite(SUITE_ROOT)
    definition = load_judge_definition(SUITE_ROOT / "definition.yaml")
    spec = load_calibration_spec(SUITE_ROOT / "calibration.yaml")
    definitions = {cell.id: definition for cell in spec.judge_cells}
    return suite, definition, spec, definitions


def test_plan_is_timestamp_free_deterministic_and_explicitly_repeated() -> None:
    suite, _definition, spec, definitions = _inputs()
    plan = build_calibration_plan(spec, suite, definitions)
    assert (
        plan.canonical_json() == build_calibration_plan(spec, suite, definitions).canonical_json()
    )
    assert plan.plan_digest == build_calibration_plan(spec, suite, definitions).plan_digest
    assert len(plan.slots) == 126
    assert len({slot.slot_id for slot in plan.slots}) == 126
    assert "timestamp" not in plan.canonical_json().casefold()
    label_slots = [slot for slot in plan.slots if slot.case_mode is JudgeMode.LABEL]
    assert {slot.repeat_index for slot in label_slots} == {0, 1, 2}
    assert {slot.order_variant for slot in label_slots} == {OrderVariant.NOT_APPLICABLE}


def test_pairwise_swap_is_one_logical_trial_with_two_order_variants() -> None:
    suite, _definition, spec, definitions = _inputs()
    plan = build_calibration_plan(spec, suite, definitions)
    slots = [
        slot
        for slot in plan.slots
        if slot.judge_cell_id == "good-judge" and slot.case_id == "pair-arithmetic"
    ]
    assert len(slots) == 6
    for repeat in range(3):
        assert {slot.order_variant for slot in slots if slot.repeat_index == repeat} == {
            OrderVariant.ORIGINAL,
            OrderVariant.SWAPPED,
        }


def test_judge_definition_is_authoritative_pairwise_order_policy() -> None:
    suite, definition, spec, definitions = _inputs()
    disabled_definition = definition.model_copy(update={"order_swap_policy": "DISABLED"})
    disabled = spec.model_copy(
        update={
            "judge_cells": (
                spec.judge_cells[0].model_copy(
                    update={"definition_digest": disabled_definition.definition_digest}
                ),
                spec.judge_cells[1],
            )
        }
    )
    definitions[spec.judge_cells[0].id] = disabled_definition
    plan = build_calibration_plan(disabled, suite, definitions)
    good_pair_slots = [
        slot
        for slot in plan.slots
        if slot.judge_cell_id == "good-judge" and slot.case_mode is JudgeMode.PAIRWISE
    ]
    assert len(plan.slots) == 108
    assert {slot.order_variant for slot in good_pair_slots} == {OrderVariant.ORIGINAL}


def test_cell_cannot_override_order_policy_and_unsupported_modes_fail_before_enqueue() -> None:
    suite, definition, spec, _definitions = _inputs()
    with pytest.raises(ValidationError, match="extra_forbidden"):
        JudgeCellSpec.model_validate(
            {**spec.judge_cells[0].model_dump(mode="json"), "order_swap_policy": "DISABLED"}
        )
    label_only = definition.model_copy(update={"supported_modes": (JudgeMode.LABEL,)})
    changed_spec = spec.model_copy(
        update={
            "judge_cells": tuple(
                cell.model_copy(update={"definition_digest": label_only.definition_digest})
                for cell in spec.judge_cells
            )
        }
    )
    with pytest.raises(JudgePlanError, match="does not support cases"):
        build_calibration_plan(
            changed_spec,
            suite,
            {cell.id: label_only for cell in changed_spec.judge_cells},
        )
    valid_plan = build_calibration_plan(spec, suite, _definitions)
    tampered_plan = valid_plan.model_copy(
        update={
            "slots": tuple(
                slot
                for slot in valid_plan.slots
                if not (
                    slot.judge_cell_id == "good-judge"
                    and slot.case_id == "pair-arithmetic"
                    and slot.repeat_index == 0
                    and slot.order_variant is OrderVariant.SWAPPED
                )
            )
        }
    )
    with pytest.raises(JudgePlanError, match="order variants disagree"):
        validate_plan_definitions(tampered_plan, suite, _definitions)


def test_plan_digest_changes_for_every_frozen_calibration_dimension() -> None:
    suite, _definition, spec, definitions = _inputs()
    original = build_calibration_plan(spec, suite, definitions)
    changed_repeat = build_calibration_plan(
        spec.model_copy(update={"repeat_count": 4}), suite, definitions
    )
    changed_policy = build_calibration_plan(
        spec.model_copy(
            update={
                "qualification_policy": spec.qualification_policy.model_copy(
                    update={"minimum_coverage": 0.79}
                )
            }
        ),
        suite,
        definitions,
    )
    changed_profile = original.model_copy(
        update={
            "judge_cells": (
                original.judge_cells[0].model_copy(
                    update={"profile_identity": "sha256:" + "f" * 64}
                ),
                *original.judge_cells[1:],
            )
        }
    )
    assert (
        len(
            {
                original.plan_digest,
                changed_repeat.plan_digest,
                changed_policy.plan_digest,
                changed_profile.plan_digest,
            }
        )
        == 4
    )


def test_qualification_policy_is_versioned_all_required_checks_pass() -> None:
    _suite, _definition, spec, _definitions = _inputs()
    assert spec.qualification_policy.qualification_rule == "ALL_REQUIRED_CHECKS_PASS"
    raw = spec.qualification_policy.model_dump(mode="json")
    del raw["qualification_rule"]
    with pytest.raises(ValidationError, match="qualification_rule"):
        type(spec.qualification_policy).model_validate(raw)
