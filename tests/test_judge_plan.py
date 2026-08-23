from __future__ import annotations

from pathlib import Path

from harnesslab.judgelab.models import JudgeMode, OrderVariant
from harnesslab.judgelab.plan import build_calibration_plan, load_calibration_spec
from harnesslab.judgelab.suite import load_judge_suite

ROOT = Path(__file__).resolve().parents[1]
SUITE_ROOT = ROOT / "judge_suites/core-calibration/1.0.0"


def test_plan_is_timestamp_free_deterministic_and_explicitly_repeated() -> None:
    suite = load_judge_suite(SUITE_ROOT)
    spec = load_calibration_spec(SUITE_ROOT / "calibration.yaml")
    plan = build_calibration_plan(spec, suite)
    assert plan.canonical_json() == build_calibration_plan(spec, suite).canonical_json()
    assert plan.plan_digest == build_calibration_plan(spec, suite).plan_digest
    assert len(plan.slots) == 126
    assert len({slot.slot_id for slot in plan.slots}) == 126
    assert "timestamp" not in plan.canonical_json().casefold()
    label_slots = [slot for slot in plan.slots if slot.case_mode is JudgeMode.LABEL]
    assert {slot.repeat_index for slot in label_slots} == {0, 1, 2}
    assert {slot.order_variant for slot in label_slots} == {OrderVariant.NOT_APPLICABLE}


def test_pairwise_swap_is_one_logical_trial_with_two_order_variants() -> None:
    suite = load_judge_suite(SUITE_ROOT)
    spec = load_calibration_spec(SUITE_ROOT / "calibration.yaml")
    plan = build_calibration_plan(spec, suite)
    slots = [
        slot
        for slot in plan.slots
        if slot.judge_cell_id == "good-judge" and slot.case_id == "pair-a-wins"
    ]
    assert len(slots) == 6
    for repeat in range(3):
        assert {slot.order_variant for slot in slots if slot.repeat_index == repeat} == {
            OrderVariant.ORIGINAL,
            OrderVariant.SWAPPED,
        }


def test_definition_policy_can_explicitly_disable_pairwise_swap() -> None:
    suite = load_judge_suite(SUITE_ROOT)
    spec = load_calibration_spec(SUITE_ROOT / "calibration.yaml")
    disabled = spec.model_copy(
        update={
            "judge_cells": (
                spec.judge_cells[0].model_copy(update={"order_swap_policy": "DISABLED"}),
                spec.judge_cells[1],
            )
        }
    )
    plan = build_calibration_plan(disabled, suite)
    good_pair_slots = [
        slot
        for slot in plan.slots
        if slot.judge_cell_id == "good-judge" and slot.case_mode is JudgeMode.PAIRWISE
    ]
    assert len(plan.slots) == 108
    assert {slot.order_variant for slot in good_pair_slots} == {OrderVariant.ORIGINAL}


def test_plan_digest_changes_for_every_frozen_calibration_dimension() -> None:
    suite = load_judge_suite(SUITE_ROOT)
    spec = load_calibration_spec(SUITE_ROOT / "calibration.yaml")
    original = build_calibration_plan(spec, suite)
    changed_repeat = build_calibration_plan(spec.model_copy(update={"repeat_count": 4}), suite)
    changed_policy = build_calibration_plan(
        spec.model_copy(
            update={
                "qualification_policy": spec.qualification_policy.model_copy(
                    update={"minimum_coverage": 0.79}
                )
            }
        ),
        suite,
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
