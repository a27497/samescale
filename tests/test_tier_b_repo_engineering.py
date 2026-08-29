from __future__ import annotations

from pathlib import Path

import pytest

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane
from harnesslab.experiment.methodology import (
    BudgetContract,
    BudgetDimension,
    BudgetDimensionStatus,
    BudgetScope,
    EvaluationMode,
    FunnelStage,
    TaskTier,
    load_evaluation_methodology,
)
from harnesslab.experiment.plan import build_methodology_v2_plan
from harnesslab.experiment.spec import ExperimentCellSpec, ExperimentSpec, ExperimentSpecError
from harnesslab.tasks.models import OutcomeCategory
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.tier_b import (
    discover_tier_b_packages,
    load_tier_b_qualification,
    validate_tier_b_qualification,
)
from harnesslab.tasks.validation import validate_task_package
from harnesslab.tasks.verifier import execute_verifier

ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = ROOT / "release/tier-b-qualification-v1.json"
METHODOLOGY = ROOT / "release/evaluation-methodology-v2.json"


def budget_contract() -> BudgetContract:
    def enforced(value: int, unit: str) -> BudgetDimension:
        return BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=value,
            unit=unit,
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        )

    return BudgetContract(
        max_wall_time=enforced(600, "seconds"),
        max_output_tokens=enforced(8000, "tokens"),
        max_model_turns=enforced(20, "turns"),
        max_tool_calls=enforced(100, "calls"),
        max_provider_requests=enforced(20, "requests"),
        max_cost=BudgetDimension(
            status=BudgetDimensionStatus.NOT_AVAILABLE,
            value=None,
            unit="USD",
            scopes=(BudgetScope.NOT_AVAILABLE,),
        ),
    )


def tier_b_spec(package: TaskPackage) -> ExperimentSpec:
    def identity(label: str) -> str:
        return canonical_digest({"identity": label})

    task_budget = canonical_digest(package.definition.budget.model_dump(mode="json"))
    return ExperimentSpec(
        experiment_id="tier-b-planner-contract",
        name="Tier-B planner contract",
        task_packages=(package.root.relative_to(ROOT).as_posix(),),
        cells=(
            ExperimentCellSpec(
                id="keyless-fixture",
                lane=EvaluationLane.MODEL,
                requested_model="fake-model",
                provider_route="fake-provider",
                profile_reference="builtin:tier-b-fixture",
                profile_identity=identity("profile"),
                harness="direct-model",
                harness_version="1",
                harness_config_identity=identity("config"),
                resource_budget_identity=task_budget,
                network_policy="deny",
                runner_contract="direct-model-v1",
            ),
        ),
        repeat_count=1,
    )


def test_frozen_tier_b_inventory_and_qualification_identities_match() -> None:
    packages = discover_tier_b_packages(ROOT)
    artifact = load_tier_b_qualification(QUALIFICATION)
    validate_tier_b_qualification(ROOT, artifact)

    assert artifact.task_count == 3
    assert artifact.real_provider_calls == 0
    assert artifact.hidden_test_leakage == "NONE"
    assert {task.language for task in artifact.tasks} == {"python", "java", "typescript"}
    assert {package.definition.id for package in packages} == {
        task.task_id for task in artifact.tasks
    }
    assert all(len(task.oracle_changed_files) >= 2 for task in artifact.tasks)
    assert all(len(task.robustness_variants) >= 2 for task in artifact.tasks)


@pytest.mark.parametrize(
    "task_id",
    (
        "repo-python-ledger-transfer",
        "repo-java-widget-update",
        "repo-typescript-resilient-client",
    ),
)
def test_tier_b_baseline_fails_and_multifile_oracle_passes(task_id: str) -> None:
    path = ROOT / "tasks" / task_id / "1.0.0"
    package = TaskPackage.load(path)
    result = validate_task_package(path)

    assert package.manifest.repo_engineering is not None
    assert result.valid
    assert result.baseline.result.category is OutcomeCategory.SUBJECT_RESULT
    assert not result.baseline.result.passed
    assert result.oracle.result.category is OutcomeCategory.SUBJECT_RESULT
    assert result.oracle.result.passed
    assert result.oracle.result.score == 1.0


def test_partial_repo_fixes_remain_capability_failures_and_assets_stay_hidden() -> None:
    for package in discover_tier_b_packages(ROOT):
        for variant in package.robustness_variants:
            materialized = package.materialize()
            try:
                package.apply_overlay(materialized, variant)
                result = execute_verifier(package, materialized)
                assert not (
                    {"verifier", "oracle", "robustness"}
                    & {path.name for path in materialized.root.iterdir()}
                )
            finally:
                materialized.cleanup()
            assert result.category is OutcomeCategory.SUBJECT_RESULT
            assert not result.passed


def test_methodology_plan_requires_and_binds_tier_b_qualification() -> None:
    package = discover_tier_b_packages(ROOT)[0]
    spec = tier_b_spec(package)
    methodology = load_evaluation_methodology(METHODOLOGY)

    with pytest.raises(ExperimentSpecError, match="qualification artifact"):
        build_methodology_v2_plan(
            spec,
            ROOT,
            methodology=methodology,
            evaluation_mode=EvaluationMode.QUICK,
            funnel_stage=FunnelStage.BREADTH,
            schedule_seed=7,
            budget_contract=budget_contract(),
        )

    plan = build_methodology_v2_plan(
        spec,
        ROOT,
        methodology=methodology,
        evaluation_mode=EvaluationMode.QUICK,
        funnel_stage=FunnelStage.BREADTH,
        schedule_seed=7,
        budget_contract=budget_contract(),
        tier_b_qualification_path=QUALIFICATION,
    )

    artifact = load_tier_b_qualification(QUALIFICATION)
    assert plan.benchmark_tier is TaskTier.TIER_B_REPO_ENGINEERING
    assert plan.tier_b_qualification_id == artifact.qualification_id
    assert plan.tier_b_qualification_digest == artifact.qualification_digest
    assert plan.task_health_attestations[0].valid
