from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from harnesslab.core.config import Settings
from harnesslab.db.base import Base
from harnesslab.db.models.experiment import ExperimentRunRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.experiment.methodology import (
    EvaluationMode,
    FunnelStage,
    load_evaluation_methodology,
)
from harnesslab.experiment.model_comparison import analyze_model_comparison
from harnesslab.experiment.plan import (
    build_methodology_v2_plan,
    load_experiment_plan_payload,
)
from harnesslab.experiment.queue import enqueue_plan
from harnesslab.experiment.report import VerifiedExperimentEvidence
from harnesslab.experiment.spec import ExperimentCellSpec, ExperimentSpec, ExperimentSpecError
from harnesslab.registry.models import ExperimentSnapshot, PreflightStatus
from harnesslab.registry.runtime import direct_harness_control_identity
from harnesslab.registry.service import validate_frozen_runtime_contract
from harnesslab.registry.tier_b_smoke import (
    TIER_B_SMOKE_EXPERIMENT_ID,
    TIER_B_SMOKE_PLAN_DIGEST,
    TIER_B_SMOKE_SCHEDULE_SEED,
    tier_b_smoke_budget,
)
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.tier_b import load_tier_b_qualification

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "release/tier-b-smoke-keyless-plan.json"
PREREGISTRATION_PATH = ROOT / "release/tier-b-smoke-preregistration.json"
QUALIFICATION_PATH = ROOT / "release/tier-b-qualification-v1.json"
METHODOLOGY_PATH = ROOT / "release/evaluation-methodology-v2.json"
EXPECTED_TASK_IDS = {
    "repo-python-ledger-transfer",
    "repo-java-widget-update",
    "repo-typescript-resilient-client",
}


@asynccontextmanager
async def _isolated_queue_database(
    database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    schema = f"tier_b_smoke_{uuid4().hex}"
    administrative = create_engine(Settings.without_dotenv(database_url=database_url))
    try:
        async with administrative.begin() as connection:
            await connection.execute(CreateSchema(schema))
    finally:
        await administrative.dispose()

    engine = create_engine(Settings.without_dotenv(database_url=database_url)).execution_options(
        schema_translate_map={None: schema}
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield create_session_factory(engine)
    finally:
        await engine.dispose()
        cleanup = create_engine(Settings.without_dotenv(database_url=database_url))
        try:
            async with cleanup.begin() as connection:
                await connection.execute(DropSchema(schema, cascade=True))
        finally:
            await cleanup.dispose()


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _snapshot() -> tuple[ExperimentSnapshot, dict[str, object]]:
    payload = _json(PLAN_PATH)
    freeze = payload.pop("freeze")
    assert isinstance(freeze, dict)
    return ExperimentSnapshot.model_validate(payload), freeze


def test_tier_b_smoke_plan_round_trip_and_symmetric_direct_contract() -> None:
    snapshot, freeze = _snapshot()
    plan = snapshot.plan
    profiles = validate_frozen_runtime_contract(plan, snapshot.provider_selections)

    assert plan.experiment_id == TIER_B_SMOKE_EXPERIMENT_ID
    assert plan.digest == TIER_B_SMOKE_PLAN_DIGEST
    assert plan.schedule_seed == TIER_B_SMOKE_SCHEDULE_SEED
    assert plan.evaluation_mode is EvaluationMode.QUICK
    assert plan.repeat_count == 1
    assert plan.comparison_intent == "MODEL_COMPARISON"
    assert plan.scheduling_policy == "BLOCKED_INTERLEAVED_SCHEDULING"
    assert len(plan.tasks) == len(plan.schedule_blocks) == 3
    assert len(plan.run_slots) == len({slot.slot_id for slot in plan.run_slots}) == 6
    assert all(len(block.slot_ids) == 2 for block in plan.schedule_blocks)
    assert all(set(block.cell_execution_order) == {"Q", "D"} for block in plan.schedule_blocks)

    cells = {cell.id: cell for cell in plan.cells}
    assert set(cells) == set(profiles) == {"Q", "D"}
    assert cells["Q"].resource_envelope_identity == cells["D"].resource_envelope_identity
    assert cells["Q"].profile_identity == cells["D"].profile_identity
    assert cells["Q"].harness_config_identity == cells["D"].harness_config_identity
    assert cells["Q"].harness_config_identity == direct_harness_control_identity()
    assert all(profile.protocol.value == "chat_completions" for profile in profiles.values())
    assert all(profile.request_timeout_seconds == 180 for profile in profiles.values())
    assert all(profile.reasoning.max_output_tokens == 4000 for profile in profiles.values())

    budget = plan.budget_contract
    assert budget.max_provider_requests.value == 1
    assert budget.max_model_turns.value == 1
    assert budget.max_tool_calls.value == 0
    assert budget.max_output_tokens.value == 4000
    assert budget.max_wall_time.value == 240
    assert freeze["resource_envelope_changed_from_tier_a_direct"] is False
    assert freeze["execution_status"] == "NOT_RUN"
    assert freeze["real_provider_calls"] == 0
    assert load_experiment_plan_payload(plan.model_dump(mode="json")).digest == plan.digest


def test_tier_b_smoke_binds_exact_qualification_task_snapshot_and_verifier_identities() -> None:
    snapshot, _freeze = _snapshot()
    plan = snapshot.plan
    qualification = load_tier_b_qualification(QUALIFICATION_PATH)
    preregistration = _json(PREREGISTRATION_PATH)
    preregistered_tasks = {
        cast(str, item["task_id"]): item
        for item in cast(list[dict[str, object]], preregistration["tasks"])
    }
    qualified_tasks = {task.task_id: task for task in qualification.tasks}

    assert plan.benchmark_tier is not None
    assert plan.benchmark_tier.value == "TIER_B_REPO_ENGINEERING"
    assert plan.tier_b_qualification_id == qualification.qualification_id
    assert plan.tier_b_qualification_digest == qualification.qualification_digest
    assert {task.task_id for task in plan.tasks} == EXPECTED_TASK_IDS
    assert set(preregistered_tasks) == EXPECTED_TASK_IDS
    for task in plan.tasks:
        package = TaskPackage.load(ROOT / task.package_path)
        qualified = qualified_tasks[task.task_id]
        preregistered = preregistered_tasks[task.task_id]
        assert package.definition.version == task.task_version == qualified.task_version == "1.0.0"
        assert package.definition.content_digest == task.task_digest == qualified.task_identity
        assert package.definition.workspace.digest == task.workspace_input_digest
        assert task.workspace_input_digest == qualified.repository_snapshot_identity
        assert package.verifier_digest == task.verifier_identity == qualified.verifier_identity
        assert preregistered["task_digest"] == task.task_digest
        assert preregistered["repository_snapshot_identity"] == task.workspace_input_digest
        assert preregistered["verifier_identity"] == task.verifier_identity
        assert preregistered["language"] == qualified.language
        assert preregistered["engineering_shape"] == qualified.engineering_shape
        assert preregistered["task_tier"] == "TIER_B_REPO_ENGINEERING"


def test_tier_b_smoke_endpoint_is_pending_without_guessed_fingerprint_or_provider_observation() -> (
    None
):
    snapshot, freeze = _snapshot()
    preregistration = _json(PREREGISTRATION_PATH)
    blockers = [check for check in snapshot.preflight.checks if check.status.value == "BLOCKED"]

    assert snapshot.preflight.status is PreflightStatus.BLOCKED
    assert blockers
    assert all(check.key == "endpoint:alibaba-bailian" for check in blockers)
    assert all(check.reason_code == "RUNTIME_ENDPOINT_REFERENCE_MISSING" for check in blockers)
    assert all(
        selection.runtime_endpoint_fingerprint is None for selection in snapshot.provider_selections
    )
    assert freeze["endpoint_binding_status"] == "PENDING_OPERATOR_ENDPOINT_RECONCILIATION"
    assert freeze["non_endpoint_controls_frozen"] is True
    assert preregistration["endpoint_binding_status"] == (
        "PENDING_OPERATOR_ENDPOINT_RECONCILIATION"
    )
    assert preregistration["execution_status"] == "NOT_RUN"
    assert preregistration["model_scores"] == "NOT_AVAILABLE"
    assert preregistration["cost"] == "NOT_AVAILABLE"
    assert preregistration["provider_observations"] == "NOT_AVAILABLE"
    assert preregistration["real_provider_calls"] == 0

    combined = PLAN_PATH.read_text(encoding="utf-8") + PREREGISTRATION_PATH.read_text(
        encoding="utf-8"
    )
    assert "fake-tier-b-smoke-key" not in combined
    assert "workspace-sentinel" not in combined
    assert "cn-beijing.maas.aliyuncs.com" not in combined


def test_tier_b_smoke_identity_gates_retry_policy_and_evidence_projection_are_preregistered() -> (
    None
):
    snapshot, _freeze = _snapshot()
    preregistration = _json(PREREGISTRATION_PATH)
    slots = cast(list[dict[str, object]], preregistration["smoke_slots"])
    plan_slots = {slot.slot_id: slot for slot in snapshot.plan.run_slots}
    gates = set(cast(list[str], preregistration["success_gates"]))
    projection = cast(dict[str, object], preregistration["evidence_projection"])

    assert preregistration["plan_digest"] == TIER_B_SMOKE_PLAN_DIGEST
    assert preregistration["total_logical_slots"] == 6
    assert len(slots) == len({item["slot_id"] for item in slots}) == 6
    assert {cast(str, item["slot_id"]) for item in slots} == set(plan_slots)
    assert {cast(str, item["task_id"]) for item in slots} == EXPECTED_TASK_IDS
    assert {cast(str, item["cell_id"]) for item in slots} == {"Q", "D"}
    for item in slots:
        planned = plan_slots[cast(str, item["slot_id"])]
        assert item["slot_order"] == planned.slot_order
        assert item["task_digest"] == planned.task.task_digest
        assert item["repository_snapshot_identity"] == planned.task.workspace_input_digest
        assert item["verifier_identity"] == planned.task.verifier_identity
        assert item["resource_envelope_identity"] == planned.resource_envelope_identity

    assert {
        "TIER_B_QUALIFICATION_IDENTITY_EXACT",
        "TASK_SNAPSHOT_AND_VERIFIER_IDENTITIES_EXACT",
        "OBSERVED_PROVIDER_MODEL_IDENTITY_MATCH",
        "NO_CONTROL_DRIFT",
        "NO_VERIFIER_INFRASTRUCTURE",
        "NO_HIDDEN_TEST_LEAKAGE",
        "NO_SECRET_LEAKAGE",
        "TRACE_AND_EVIDENCE_PERSISTENCE_VALID",
        "CAPABILITY_PASS_OR_FAIL_ACCEPTABLE",
    } <= gates
    assert preregistration["capability_failure_policy"] == "TERMINAL_NO_RETRY"
    assert preregistration["infrastructure_failure_policy"] == (
        "PRESERVE_IMMUTABLE_FIRST_ATTEMPT_NO_IMMEDIATE_SEMANTIC_RETRY"
    )
    assert preregistration["score_based_stop_condition"] == "PROHIBITED"
    assert {
        "repository_snapshot_identity",
        "changed_file_identity",
        "workspace_output_identity",
        "task_language",
        "engineering_shape",
        "task_tier",
        "qualification_digest",
        "outcome_classification",
        "latency",
        "usage",
    } <= set(projection)


def test_tier_a_and_tier_b_cannot_be_mixed_before_matrix_expansion() -> None:
    snapshot, _freeze = _snapshot()
    plan = snapshot.plan
    cells = tuple(
        ExperimentCellSpec.model_validate(cell.model_dump(mode="json")) for cell in plan.cells
    )
    spec = ExperimentSpec(
        experiment_id="invalid-mixed-tier-smoke",
        name="Invalid mixed tier smoke",
        task_packages=(
            "tasks/repo-python-ledger-transfer/1.0.0",
            "tasks/core-python-quota/1.0.2",
        ),
        cells=cells,
        repeat_count=1,
        execution_seed=1,
        comparison_intent="MODEL_COMPARISON",
    )
    methodology = load_evaluation_methodology(METHODOLOGY_PATH)

    with pytest.raises(ExperimentSpecError, match="cannot aggregate Tier-A and Tier-B"):
        build_methodology_v2_plan(
            spec,
            ROOT,
            methodology=methodology,
            evaluation_mode=EvaluationMode.QUICK,
            funnel_stage=FunnelStage.BREADTH,
            schedule_seed=1,
            budget_contract=tier_b_smoke_budget(),
            tier_b_qualification_path=QUALIFICATION_PATH,
        )


def test_tier_b_smoke_is_compatible_with_model_comparison_analysis() -> None:
    snapshot, _freeze = _snapshot()
    evidence = VerifiedExperimentEvidence(plan=snapshot.plan, runs=(), observations=())

    closeout = analyze_model_comparison(evidence, repository_root=ROOT)

    assert closeout.analysis.experiment_id == TIER_B_SMOKE_EXPERIMENT_ID
    assert closeout.analysis.plan_digest == TIER_B_SMOKE_PLAN_DIGEST
    assert closeout.analysis.pairs.planned_pairs == 3
    assert closeout.analysis.pairs.missing_pairs == 3
    assert {row.value for row in closeout.analysis.breakdowns if row.dimension == "language"} == {
        "java",
        "python",
        "typescript",
    }


@pytest.mark.integration
async def test_tier_b_smoke_plan_round_trips_through_execution_queue(database_url: str) -> None:
    snapshot, _freeze = _snapshot()
    plan = snapshot.plan
    async with (
        _isolated_queue_database(database_url) as factory,
        factory() as session,
        session.begin(),
    ):
        enqueued = await enqueue_plan(session, plan)
        count = await session.scalar(
            select(func.count())
            .select_from(ExperimentRunRecord)
            .where(ExperimentRunRecord.experiment_id == plan.experiment_id)
        )
        assert enqueued.created
        assert enqueued.logical_run_count == count == 6
        persisted = tuple(
            await session.scalars(
                select(ExperimentRunRecord)
                .where(ExperimentRunRecord.experiment_id == plan.experiment_id)
                .order_by(ExperimentRunRecord.slot_order)
            )
        )
        assert tuple(item.slot_id for item in persisted) == tuple(
            slot.slot_id for slot in plan.run_slots
        )
