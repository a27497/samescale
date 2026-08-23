from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane
from harnesslab.experiment.plan import build_experiment_plan
from harnesslab.experiment.spec import ExperimentSpec, ExperimentSpecError
from harnesslab.tasks.package import TaskPackage
from tests.phase_g_helpers import ROOT, basic_spec, cell, identity


def test_strict_experiment_spec_and_deterministic_matrix_plan() -> None:
    spec = basic_spec(repeat_count=5)
    first = build_experiment_plan(spec, ROOT)
    second = build_experiment_plan(spec, ROOT)

    assert len(first.run_slots) == 10
    assert first.canonical_json() == second.canonical_json()
    assert first.digest == second.digest
    assert len({slot.slot_id for slot in first.run_slots}) == 10
    assert [slot.slot_order for slot in first.run_slots] == list(range(10))
    assert all(slot.paired_slot_identity for slot in first.run_slots)
    assert "created_at" not in first.canonical_json()

    raw = spec.model_dump(mode="json")
    raw["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExperimentSpec.model_validate(raw)


def test_plan_digest_changes_with_resolved_control_identity() -> None:
    spec = basic_spec()
    changed_cell = spec.cells[0].model_copy(
        update={
            "profile_identity": identity("different-profile"),
            "harness_config_identity": identity("different-config"),
        }
    )
    changed = spec.model_copy(update={"cells": (changed_cell, spec.cells[1])})

    assert build_experiment_plan(spec, ROOT).digest != build_experiment_plan(changed, ROOT).digest


def test_spec_rejects_duplicates_unsafe_paths_and_unknown_pair_cells() -> None:
    raw = basic_spec().model_dump(mode="json")
    raw["cells"].append(raw["cells"][0])
    with pytest.raises(ValidationError, match="duplicate cell id"):
        ExperimentSpec.model_validate(raw)

    raw = basic_spec().model_dump(mode="json")
    raw["task_packages"] = ["../private-task"]
    with pytest.raises(ValidationError, match="path must not"):
        ExperimentSpec.model_validate(raw)

    raw = basic_spec().model_dump(mode="json")
    raw["paired_comparisons"][0]["right_cell_id"] = "missing"
    with pytest.raises(ValidationError, match="unknown cell"):
        ExperimentSpec.model_validate(raw)

    raw = basic_spec().model_dump(mode="json")
    raw["cells"][0]["profile_reference"] = "../private-profile.yaml"
    with pytest.raises(ValidationError, match="path must not"):
        ExperimentSpec.model_validate(raw)

    raw = basic_spec().model_dump(mode="json")
    raw["repeat_count"] = 0
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        ExperimentSpec.model_validate(raw)


def test_plan_rejects_unresolved_or_mutated_task_controls() -> None:
    raw = basic_spec().model_dump(mode="json")
    raw["task_packages"] = ["tasks/not-present/1.0.0"]
    spec = ExperimentSpec.model_validate(raw)
    with pytest.raises(ExperimentSpecError, match="cannot resolve"):
        build_experiment_plan(spec, ROOT)

    changed = (
        basic_spec()
        .cells[0]
        .model_copy(update={"resource_budget_identity": identity("wrong-budget")})
    )
    spec = basic_spec().model_copy(update={"cells": (changed, basic_spec().cells[1])})
    with pytest.raises(ExperimentSpecError, match="budget identity"):
        build_experiment_plan(spec, ROOT)


def test_controlled_ablation_accepts_one_treatment_and_rejects_hard_drift() -> None:
    base = cell(
        "low",
        EvaluationLane.HARNESS,
        reasoning_effort="low",
        profile_identity=identity("profile-low"),
        harness_config_identity=identity("config-low"),
    )
    variant = cell(
        "high",
        EvaluationLane.HARNESS,
        reasoning_effort="high",
        profile_identity=identity("profile-high"),
        harness_config_identity=identity("config-high"),
    ).model_copy(update={"profile_reference": base.profile_reference})
    spec = ExperimentSpec(
        experiment_id="ablation-test",
        name="Controlled ablation",
        task_packages=("tasks/micro-python-clamp/1.0.0",),
        cells=(base, variant),
        repeat_count=3,
        ablations=(
            {
                "id": "effort",
                "base_cell_id": "low",
                "variant_cell_id": "high",
                "changed_dimension": "reasoning_effort",
            },
        ),
    )
    assert spec.ablations[0].changed_dimension == "reasoning_effort"

    drifted = variant.model_copy(update={"provider_route": "different-route"})
    raw = spec.model_dump(mode="json")
    raw["cells"][1] = json.loads(drifted.model_dump_json())
    with pytest.raises(ValidationError, match="undeclared hard-control drift: provider_route"):
        ExperimentSpec.model_validate(raw)


def test_plan_rejects_cell_lane_unsupported_by_real_task() -> None:
    task_path = "tasks/micro-java-clamp/1.0.0"
    package = TaskPackage.load(ROOT / task_path)
    model_cell = cell("model", EvaluationLane.MODEL).model_copy(
        update={
            "resource_budget_identity": canonical_digest(
                package.definition.budget.model_dump(mode="json")
            ),
            "network_policy": package.definition.budget.network_policy,
        }
    )
    spec = ExperimentSpec(
        experiment_id="unsupported-lane",
        name="Reject unsupported task lane",
        task_packages=(task_path,),
        cells=(model_cell,),
    )

    with pytest.raises(ExperimentSpecError, match=r"does not support.*lane M"):
        build_experiment_plan(spec, ROOT)
