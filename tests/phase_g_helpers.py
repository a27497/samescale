from __future__ import annotations

from pathlib import Path

from harnesslab.comparability.models import ComparabilityIntent, canonical_digest
from harnesslab.contracts.common import EvaluationLane
from harnesslab.experiment.spec import ExperimentCellSpec, ExperimentSpec
from harnesslab.tasks.package import TaskPackage

ROOT = Path(__file__).resolve().parents[1]
PYTHON_TASK_PATH = "tasks/micro-python-clamp/1.0.0"


def identity(label: str) -> str:
    return canonical_digest({"identity": label})


def task_budget_identity() -> str:
    package = TaskPackage.load(ROOT / PYTHON_TASK_PATH)
    return canonical_digest(package.definition.budget.model_dump(mode="json"))


def cell(
    cell_id: str,
    lane: EvaluationLane,
    *,
    requested_model: str = "fake-shared-model",
    provider_route: str = "fake-provider-route",
    harness: str | None = None,
    harness_version: str = "1.0",
    reasoning_effort: str | None = None,
    profile_identity: str | None = None,
    harness_config_identity: str | None = None,
    runner_contract: str | None = None,
) -> ExperimentCellSpec:
    return ExperimentCellSpec(
        id=cell_id,
        lane=lane,
        requested_model=requested_model,
        provider_route=provider_route,
        profile_reference=f"builtin:{cell_id}",
        profile_identity=profile_identity or identity(f"profile:{cell_id}"),
        harness=harness or ("direct-model" if lane is EvaluationLane.MODEL else "fake-harness"),
        harness_version=harness_version,
        harness_config_identity=harness_config_identity or identity(f"config:{cell_id}"),
        reasoning_effort=reasoning_effort,
        resource_budget_identity=task_budget_identity(),
        network_policy="deny",
        runner_contract=runner_contract
        or ("direct-model-v1" if lane is EvaluationLane.MODEL else "harness-v1"),
    )


def basic_spec(*, repeat_count: int = 5) -> ExperimentSpec:
    return ExperimentSpec(
        experiment_id="phase-g-test",
        name="Phase G deterministic test",
        task_packages=(PYTHON_TASK_PATH,),
        cells=(cell("model", EvaluationLane.MODEL), cell("harness", EvaluationLane.HARNESS)),
        repeat_count=repeat_count,
        execution_seed=42,
        comparison_intent=ComparabilityIntent.HARNESS_UPLIFT,
        paired_comparisons=(
            {
                "id": "model-vs-harness",
                "left_cell_id": "model",
                "right_cell_id": "harness",
            },
        ),
    )
