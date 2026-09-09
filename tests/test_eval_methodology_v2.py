from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane
from harnesslab.contracts.run import RunStatus
from harnesslab.core.config import Settings
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.experiment.methodology import (
    BudgetContract,
    BudgetDimension,
    BudgetDimensionStatus,
    BudgetFairnessClass,
    BudgetScope,
    ComparisonType,
    EvaluationMode,
    FunnelStage,
    MethodologyError,
    MetricAvailability,
    MetricValue,
    ProviderAvailability,
    RecoveryEligibility,
    StageDecision,
    classify_budget_fairness,
    classify_comparison,
    load_evaluation_methodology,
    next_funnel_stage,
    project_default_portfolio,
    recovery_authorization,
    require_comparable_budgets,
    require_comparison_type,
    require_provider_identity,
)
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.plan import (
    ExperimentPlan,
    MethodologyV2ExperimentPlan,
    build_blocked_interleaved_schedule,
    build_experiment_plan,
    build_methodology_v2_plan,
    executable_block_slot_ids,
    load_experiment_plan_payload,
)
from harnesslab.experiment.queue import (
    ExperimentConflict,
    claim_next_run,
    enqueue_plan,
    requeue_failed_infra_after_repair,
)
from harnesslab.experiment.spec import ExperimentSpec, ExperimentSpecError
from harnesslab.experiment.statistics import EvidenceTier, aggregate_evidence_tier
from harnesslab.release.matrix import MATRIX_LOGICAL_RUNS, MatrixControlPlane
from harnesslab.tasks.health import TaskHealthError, validate_task_health
from harnesslab.tasks.validation import validate_task_package
from tests.phase_g_helpers import ROOT, basic_spec, cell

METHODOLOGY_PATH = ROOT / "release/evaluation-methodology-v2.json"


def budget_contract(*, wall_time: int = 60) -> BudgetContract:
    return BudgetContract(
        max_wall_time=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=wall_time,
            unit="seconds",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_output_tokens=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=2000,
            unit="tokens",
            scopes=(BudgetScope.PER_PROVIDER_REQUEST, BudgetScope.PER_LOGICAL_RUN),
        ),
        max_model_turns=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=1,
            unit="turns",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_tool_calls=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=0,
            unit="calls",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_provider_requests=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=1,
            unit="requests",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_cost=BudgetDimension(
            status=BudgetDimensionStatus.NOT_AVAILABLE,
            value=None,
            unit="USD",
            scopes=(BudgetScope.NOT_AVAILABLE,),
        ),
    )


def seven_cell_plan(*, repeats: int = 3) -> tuple[ExperimentSpec, ExperimentPlan]:
    cells = tuple(
        cell(
            f"cell-{index}",
            EvaluationLane.MODEL if index % 2 == 0 else EvaluationLane.HARNESS,
            provider_route=f"provider-{index % 3}",
        )
        for index in range(7)
    )
    spec = ExperimentSpec(
        experiment_id="methodology-v2-scheduling",
        name="Methodology v2 scheduling fixture",
        task_packages=("tasks/micro-python-clamp/1.0.0",),
        cells=cells,
        repeat_count=repeats,
        execution_seed=19,
    )
    return spec, build_experiment_plan(spec, ROOT)


def test_methodology_artifact_is_strict_complete_and_projects_216_runs() -> None:
    methodology = load_evaluation_methodology(METHODOLOGY_PATH)
    projection = project_default_portfolio(methodology.default_portfolio)

    assert methodology.methodology_id == "harnesslab-evaluation-methodology-v2"
    tier_a = next(item for item in methodology.task_tiers if item.tier.value.startswith("TIER_A"))
    assert len(tier_a.current_task_ids) == 18
    assert projection.breadth_subject_runs == 126
    assert projection.critical_comparison_memberships == 162
    assert projection.critical_unique_subject_runs == 135
    assert projection.breadth_overlap_subject_runs == 45
    assert projection.incremental_critical_subject_runs == 90
    assert projection.projected_unique_subject_runs == 216
    assert projection.reduction_subject_runs == 414
    assert projection.reduction_fraction == pytest.approx(414 / 630)

    raw = methodology.model_dump(mode="json")
    raw["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        type(methodology).model_validate(raw)


def test_same_seed_same_schedule_and_different_seed_preserves_slot_identity() -> None:
    _spec, plan = seven_cell_plan()
    blocks_a, slots_a = build_blocked_interleaved_schedule(plan, schedule_seed=7)
    blocks_b, slots_b = build_blocked_interleaved_schedule(plan, schedule_seed=7)
    blocks_c, slots_c = build_blocked_interleaved_schedule(plan, schedule_seed=29)

    assert blocks_a == blocks_b
    assert slots_a == slots_b
    assert tuple(block.cell_execution_order for block in blocks_a) != tuple(
        block.cell_execution_order for block in blocks_c
    )
    assert {slot.slot_id for slot in slots_a} == {slot.slot_id for slot in slots_c}
    assert [slot.slot_order for slot in slots_c] == list(range(len(slots_c)))


def test_scheduler_interleaves_cells_by_block_and_pauses_unavailable_provider() -> None:
    _spec, plan = seven_cell_plan(repeats=1)
    blocks, slots = build_blocked_interleaved_schedule(
        plan,
        schedule_seed=11,
        provider_availability={
            "provider-1": ProviderAvailability.PROVIDER_UNAVAILABLE,
        },
    )

    assert len(blocks) == 1
    block = blocks[0]
    assert len(block.cell_execution_order) == 7
    assert len(set(block.cell_execution_order)) == 7
    assert {slot.task.task_id for slot in slots[:7]} == {"micro-python-clamp"}
    assert {slot.repeat_index for slot in slots[:7]} == {0}
    assert block.provider_availability is ProviderAvailability.PROVIDER_UNAVAILABLE
    assert block.unavailable_provider_routes == ("provider-1",)
    assert executable_block_slot_ids(block) == ()


def test_capability_never_retries_and_infra_gets_exactly_one_new_identity() -> None:
    capability = recovery_authorization(
        slot_id="sha256:" + "1" * 64,
        original_attempt_identity="sha256:" + "2" * 64,
        outcome=StatisticalOutcome.CAPABILITY_FAIL,
        recovery_attempt_count=0,
    )
    first_infra = recovery_authorization(
        slot_id="sha256:" + "1" * 64,
        original_attempt_identity="sha256:" + "2" * 64,
        outcome=StatisticalOutcome.INFRA_FAILURE,
        recovery_attempt_count=0,
    )
    second_infra = recovery_authorization(
        slot_id="sha256:" + "1" * 64,
        original_attempt_identity="sha256:" + "2" * 64,
        outcome=StatisticalOutcome.INFRA_FAILURE,
        recovery_attempt_count=1,
    )

    assert capability.eligibility is RecoveryEligibility.CAPABILITY_TERMINAL_NO_RETRY
    assert capability.recovery_attempt_identity is None
    assert first_infra.eligibility is RecoveryEligibility.ELIGIBLE
    assert first_infra.recovery_attempt_identity not in {
        None,
        first_infra.original_attempt_identity,
    }
    assert second_infra.eligibility is RecoveryEligibility.INFRA_RECOVERY_EXHAUSTED
    assert second_infra.recovery_attempt_identity is None


def test_provider_substitution_changes_slot_identity_and_is_rejected() -> None:
    original_spec = basic_spec(repeat_count=1)
    original = original_spec.cells[0]
    substituted = original.model_copy(
        update={
            "provider_route": "substituted-provider-route",
            "profile_identity": canonical_digest({"profile": "substituted"}),
        }
    )
    changed_spec = original_spec.model_copy(update={"cells": (substituted, original_spec.cells[1])})
    original_plan = build_experiment_plan(original_spec, ROOT)
    changed_plan = build_experiment_plan(changed_spec, ROOT)

    original_slot = next(slot for slot in original_plan.run_slots if slot.cell_id == original.id)
    changed_slot = next(slot for slot in changed_plan.run_slots if slot.cell_id == original.id)
    assert original_slot.slot_id != changed_slot.slot_id
    with pytest.raises(MethodologyError, match="provider substitution"):
        require_provider_identity(original, substituted)


def test_modes_expand_n1_n3_n5_without_pooling_unrelated_tasks() -> None:
    for mode in EvaluationMode:
        plan = build_experiment_plan(basic_spec(repeat_count=mode.repeat_count), ROOT)
        assert plan.repeat_count == mode.repeat_count
        assert len(plan.run_slots) == 2 * mode.repeat_count

    assert aggregate_evidence_tier((1, 1, 1, 1, 1)) is EvidenceTier.SMOKE
    assert aggregate_evidence_tier((3, 3)) is EvidenceTier.INFORMAL
    assert aggregate_evidence_tier((5, 2)) is EvidenceTier.INSUFFICIENT


def test_comparison_classification_blocks_false_harness_uplift() -> None:
    direct = cell(
        "direct",
        EvaluationLane.MODEL,
        requested_model="shared-model",
        provider_route="shared-provider",
        harness="direct-model",
        runner_contract="direct-v1",
    )
    harness = cell(
        "harness",
        EvaluationLane.HARNESS,
        requested_model="shared-model",
        provider_route="shared-provider",
        harness="codex",
        runner_contract="codex-v1",
    )
    deepseek_flash = harness.model_copy(update={"requested_model": "deepseek-v4-flash"})
    deepseek_pro = direct.model_copy(update={"requested_model": "deepseek-v4-pro"})

    assert classify_comparison(direct, harness) is ComparisonType.HARNESS_UPLIFT
    assert (
        classify_comparison(deepseek_pro, deepseek_flash)
        is ComparisonType.END_TO_END_SYSTEM_COMPARISON
    )
    with pytest.raises(MethodologyError, match="not claimed HARNESS_UPLIFT"):
        require_comparison_type(
            deepseek_pro,
            deepseek_flash,
            ComparisonType.HARNESS_UPLIFT,
        )


def test_controlled_ablation_requires_exactly_one_declared_treatment() -> None:
    base = cell("medium", EvaluationLane.HARNESS, reasoning_effort="medium")
    high = base.model_copy(
        update={
            "id": "high",
            "reasoning_effort": "high",
            "profile_identity": canonical_digest({"profile": "high"}),
            "harness_config_identity": canonical_digest({"config": "high"}),
        }
    )
    drifted = high.model_copy(update={"provider_route": "different-provider"})

    assert (
        classify_comparison(base, high, declared_ablation_dimension="reasoning_effort")
        is ComparisonType.CONTROLLED_ABLATION
    )
    assert (
        classify_comparison(base, drifted, declared_ablation_dimension="reasoning_effort")
        is ComparisonType.END_TO_END_SYSTEM_COMPARISON
    )


def test_budget_contract_and_missing_metrics_are_explicit_and_comparable() -> None:
    budget = budget_contract()
    assert budget.max_wall_time.status is BudgetDimensionStatus.ENFORCED
    assert budget.max_model_turns.status is BudgetDimensionStatus.ENFORCED
    assert MetricValue(status=MetricAvailability.NOT_AVAILABLE).value is None
    require_comparable_budgets(budget, budget.model_copy())

    with pytest.raises(MethodologyError, match="not resource-normalized comparable"):
        require_comparable_budgets(budget, budget_contract(wall_time=90))
    with pytest.raises(ValidationError, match="cannot contain a value"):
        MetricValue(status=MetricAvailability.NOT_AVAILABLE, value=1)


def test_budget_scope_is_required_for_resource_normalized_comparison() -> None:
    scoped = budget_contract()
    legacy = BudgetContract.model_validate(
        {name: dimension.model_dump(mode="json", exclude={"scopes"}) for name, dimension in scoped}
    )

    assert (
        classify_budget_fairness(legacy, legacy)
        is BudgetFairnessClass.NATIVE_HARNESS_SYSTEM_COMPARISON
    )
    with pytest.raises(MethodologyError, match="not resource-normalized comparable"):
        require_comparable_budgets(legacy, legacy)


def test_per_request_scope_does_not_imply_per_logical_run_scope() -> None:
    per_request = budget_contract().model_copy(
        update={
            "max_output_tokens": BudgetDimension(
                status=BudgetDimensionStatus.ENFORCED,
                value=2000,
                unit="tokens",
                scopes=(BudgetScope.PER_PROVIDER_REQUEST,),
            )
        }
    )

    assert per_request.max_output_tokens.scopes is not None
    assert BudgetScope.PER_LOGICAL_RUN not in per_request.max_output_tokens.scopes
    assert (
        classify_budget_fairness(per_request, per_request)
        is BudgetFairnessClass.NATIVE_HARNESS_SYSTEM_COMPARISON
    )


def test_direct_single_request_contract_can_cover_request_and_run_scopes() -> None:
    direct = budget_contract()

    assert direct.max_provider_requests.value == 1
    assert direct.max_model_turns.value == 1
    assert direct.max_tool_calls.value == 0
    assert direct.max_output_tokens.scopes == (
        BudgetScope.PER_PROVIDER_REQUEST,
        BudgetScope.PER_LOGICAL_RUN,
    )
    assert (
        classify_budget_fairness(direct, direct)
        is BudgetFairnessClass.RESOURCE_NORMALIZED_COMPARISON
    )


def test_multi_turn_per_turn_cap_and_unknown_request_count_block_aggregate_claim() -> None:
    unavailable = BudgetDimension(
        status=BudgetDimensionStatus.NOT_AVAILABLE,
        value=None,
        unit="count",
        scopes=(BudgetScope.NOT_AVAILABLE,),
    )
    native = budget_contract().model_copy(
        update={
            "max_output_tokens": BudgetDimension(
                status=BudgetDimensionStatus.ENFORCED,
                value=2000,
                unit="tokens",
                scopes=(BudgetScope.PER_PROVIDER_REQUEST, BudgetScope.PER_MODEL_TURN),
            ),
            "max_model_turns": unavailable.model_copy(update={"unit": "turns"}),
            "max_provider_requests": unavailable.model_copy(update={"unit": "requests"}),
        }
    )

    assert native.max_provider_requests.status is BudgetDimensionStatus.NOT_AVAILABLE
    assert native.max_output_tokens.scopes is not None
    assert BudgetScope.PER_LOGICAL_RUN not in native.max_output_tokens.scopes
    assert (
        classify_budget_fairness(native, native)
        is BudgetFairnessClass.NATIVE_HARNESS_SYSTEM_COMPARISON
    )
    with pytest.raises(MethodologyError, match="not resource-normalized comparable"):
        require_comparable_budgets(native, native)


def test_same_numeric_token_value_does_not_override_scope_difference() -> None:
    direct = budget_contract()
    per_turn = direct.model_copy(
        update={
            "max_output_tokens": direct.max_output_tokens.model_copy(
                update={
                    "scopes": (
                        BudgetScope.PER_PROVIDER_REQUEST,
                        BudgetScope.PER_MODEL_TURN,
                    )
                }
            )
        }
    )

    assert direct.max_output_tokens.value == per_turn.max_output_tokens.value == 2000
    assert direct.identity != per_turn.identity
    assert (
        classify_budget_fairness(direct, per_turn)
        is BudgetFairnessClass.NATIVE_HARNESS_SYSTEM_COMPARISON
    )


def test_chat_4000_direct_budgets_are_symmetric_and_resource_normalized() -> None:
    qwen = budget_contract().model_copy(
        update={
            "max_output_tokens": budget_contract().max_output_tokens.model_copy(
                update={"value": 4000}
            )
        }
    )
    deepseek = qwen.model_copy()

    assert qwen.max_output_tokens.value == deepseek.max_output_tokens.value == 4000
    assert qwen.identity == deepseek.identity
    require_comparable_budgets(qwen, deepseek)


def test_legacy_unscoped_budget_identity_and_serialization_remain_stable() -> None:
    raw = {
        "max_wall_time": {"status": "ENFORCED", "value": 60, "unit": "seconds"},
        "max_output_tokens": {"status": "ENFORCED", "value": 2000, "unit": "tokens"},
        "max_model_turns": {"status": "NOT_AVAILABLE", "value": None, "unit": "turns"},
        "max_tool_calls": {"status": "NOT_AVAILABLE", "value": None, "unit": "calls"},
        "max_provider_requests": {
            "status": "NOT_AVAILABLE",
            "value": None,
            "unit": "requests",
        },
        "max_cost": {"status": "NOT_AVAILABLE", "value": None, "unit": "USD"},
    }
    loaded = BudgetContract.model_validate(raw)

    assert loaded.model_dump(mode="json") == raw
    assert loaded.identity == canonical_digest(raw)


def test_task_health_repeats_five_and_rejects_flaky_terminal_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_path = ROOT / "tasks/micro-python-clamp/1.0.0"
    attestation = validate_task_health(task_path, repeats=5)
    assert attestation.valid
    assert attestation.deterministic
    assert attestation.verifier_health_repeats == 5
    assert attestation.oracle_health_repeats == 5

    stable = validate_task_package(task_path)
    changed_result = stable.baseline.result.model_copy(update={"summary": "flaky terminal facts"})
    changed_baseline = stable.baseline.model_copy(update={"result": changed_result})
    changed = stable.model_copy(update={"baseline": changed_baseline})
    sequence = iter((stable, stable, changed, stable, stable))
    monkeypatch.setattr(
        "harnesslab.tasks.health.validate_task_package",
        lambda _path: next(sequence),
    )
    with pytest.raises(TaskHealthError, match="deterministic terminal health"):
        validate_task_health(task_path, repeats=5)


def test_v2_plan_persists_method_budget_health_mode_and_schedule() -> None:
    methodology = load_evaluation_methodology(METHODOLOGY_PATH)
    spec = basic_spec(repeat_count=1).model_copy(update={"experiment_id": "methodology-v2-plan"})
    plan = build_methodology_v2_plan(
        spec,
        ROOT,
        methodology=methodology,
        evaluation_mode=EvaluationMode.QUICK,
        funnel_stage=FunnelStage.BREADTH,
        schedule_seed=73,
        budget_contract=budget_contract(),
    )
    loaded = load_experiment_plan_payload(json.loads(plan.canonical_json()))

    assert isinstance(plan, MethodologyV2ExperimentPlan)
    assert isinstance(loaded, MethodologyV2ExperimentPlan)
    assert plan.schema_version == 2
    assert plan.methodology_digest == methodology.digest
    assert plan.budget_contract_identity == plan.budget_contract.identity
    assert plan.evaluation_mode is EvaluationMode.QUICK
    assert plan.repeat_count == 1
    assert plan.schedule_seed == 73
    assert len(plan.task_health_attestations) == 1
    assert plan.task_health_attestations[0].valid
    assert len(plan.schedule_blocks) == 1
    assert set(plan.schedule_blocks[0].slot_ids) == {slot.slot_id for slot in plan.run_slots}
    assert loaded.digest == plan.digest

    with pytest.raises(ExperimentSpecError, match="repeat count"):
        build_methodology_v2_plan(
            basic_spec(repeat_count=3),
            ROOT,
            methodology=methodology,
            evaluation_mode=EvaluationMode.QUICK,
            funnel_stage=FunnelStage.BREADTH,
            schedule_seed=73,
            budget_contract=budget_contract(),
        )


@pytest.mark.integration
async def test_v2_queue_pauses_unavailable_blocks_and_rejects_legacy_requeue(
    database_url: str,
) -> None:
    methodology = load_evaluation_methodology(METHODOLOGY_PATH)
    experiment_id = f"methodology-v2-queue-{uuid4().hex[:12]}"
    spec = basic_spec(repeat_count=1).model_copy(update={"experiment_id": experiment_id})
    plan = build_methodology_v2_plan(
        spec,
        ROOT,
        methodology=methodology,
        evaluation_mode=EvaluationMode.QUICK,
        funnel_stage=FunnelStage.BREADTH,
        schedule_seed=73,
        budget_contract=budget_contract(),
        provider_availability={
            "fake-provider-route": ProviderAvailability.PROVIDER_UNAVAILABLE,
        },
    )
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, plan)
        async with factory() as session, session.begin():
            claimed = await claim_next_run(
                session,
                experiment_id,
                "methodology-v2-worker",
                now=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
                ttl=timedelta(seconds=30),
            )
        assert claimed is None

        async with factory() as session, session.begin():
            run = await session.scalar(
                select(ExperimentRunRecord)
                .where(ExperimentRunRecord.experiment_id == experiment_id)
                .limit(1)
            )
            assert run is not None
            run.status = RunStatus.FAILED_INFRA.value
            run.normalized_outcome = StatisticalOutcome.INFRA_FAILURE.value
            run.source_outcome = "controlled-infra"
            run.failure_detail = "immutable-v2-fixture"
            run.attempt = 1
        async with factory() as session:
            with pytest.raises(ExperimentConflict, match="immutable new attempt evidence"):
                async with session.begin():
                    await requeue_failed_infra_after_repair(
                        session,
                        run.run_id,
                        expected_source_outcome="controlled-infra",
                        expected_failure_detail="immutable-v2-fixture",
                    )
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()


def test_funnel_requires_explicit_go_and_never_auto_promotes() -> None:
    assert next_funnel_stage(FunnelStage.PREFLIGHT, StageDecision.STOP) is None
    assert next_funnel_stage(FunnelStage.PREFLIGHT, StageDecision.GO) is FunnelStage.SMOKE


def test_legacy_v3_matrix_and_portfolio_remain_readable_and_unchanged() -> None:
    methodology = load_evaluation_methodology(METHODOLOGY_PATH)
    control = MatrixControlPlane.load(ROOT, plan_version="v3")
    corpus = json.loads((ROOT / "release/core-corpus.json").read_text())
    portfolio = json.loads((ROOT / "release/core-real-matrix-v3-portfolio-view.json").read_text())
    tier_a = next(
        item for item in methodology.task_tiers if item.tier.value == "TIER_A_MICRO_CONTRACT"
    )

    assert control.matrix_id == "core-real-matrix-v3"
    assert MATRIX_LOGICAL_RUNS == 630
    assert set(tier_a.current_task_ids) == {item["task_id"] for item in corpus["tasks"]}
    assert methodology.backward_compatibility.historical_plan_digest == (
        "sha256:5b91aea8c2cf812e911358b3a39f75d8d0eada153188c219eaf5176d3b3b107d"
    )
    assert portfolio["source_matrix_id"] == "core-real-matrix-v3"
    assert portfolio["logical_slot_count"] == 189
    assert portfolio["formal_matrix"] == {
        "cells": 7,
        "tasks": 18,
        "repeats": 5,
        "logical_slots": 630,
        "complete": False,
        "resumable": True,
    }


@pytest.mark.integration
async def test_block_dispatch_resume_reconciles_expired_cancellations_before_selection(
    database_url: str,
) -> None:
    from harnesslab.experiment.dispatch import BlockAwareDispatcher, DispatchProfile
    from harnesslab.experiment.executor import ExperimentRunExecutor
    from harnesslab.experiment.queue import request_run_cancellation

    experiment_id = f"closeout-cancel-{uuid4().hex[:12]}"
    base = basic_spec(repeat_count=1)
    spec = base.model_copy(
        update={
            "experiment_id": experiment_id,
            "cells": tuple(
                cell.model_copy(update={"provider_route": "fixture|local"}) for cell in base.cells
            ),
        }
    )
    plan = build_methodology_v2_plan(
        spec,
        ROOT,
        methodology=load_evaluation_methodology(METHODOLOGY_PATH),
        evaluation_mode=EvaluationMode.QUICK,
        funnel_stage=FunnelStage.BREADTH,
        schedule_seed=73,
        budget_contract=budget_contract(),
    )
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    started = datetime.now(UTC) - timedelta(minutes=2)
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, plan)
            for slot in plan.run_slots:
                claim = await claim_next_run(
                    session,
                    experiment_id,
                    "abandoned",
                    now=started,
                    ttl=timedelta(seconds=30),
                    slot_ids=(slot.slot_id,),
                )
                assert claim is not None
                await request_run_cancellation(
                    session, claim.run_id, now=started + timedelta(seconds=1)
                )
        executor = ExperimentRunExecutor(
            repository_root=ROOT, session_factory=factory, bindings={}, owner="resume"
        )
        dispatcher = BlockAwareDispatcher(
            executor=executor,
            plan=plan,
            profile=DispatchProfile(
                profile_id="local-test",
                global_concurrency=1,
                max_harness_concurrency=1,
                max_direct_concurrency=1,
                provider_concurrency={"fixture": 1},
            ),
        )
        result = await dispatcher.run(max_runs=1)
        assert result.completed == () and result.events == ()
        async with factory() as session:
            rows = (
                await session.scalars(
                    select(ExperimentRunRecord).where(
                        ExperimentRunRecord.experiment_id == experiment_id
                    )
                )
            ).all()
            assert len(rows) == len(plan.run_slots)
            assert all(row.status == "cancelled" and row.attempt == 1 for row in rows)
        assert await dispatcher.run(max_runs=1) == result
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()
