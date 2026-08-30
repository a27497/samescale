from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, select

from harnesslab.contracts.common import Protocol
from harnesslab.core.config import Settings
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.experiment.dispatch import (
    BlockDispatchCoordinator,
    SlotResourceClass,
    slot_resource_class,
)
from harnesslab.experiment.plan import MethodologyV2ExperimentPlan
from harnesslab.experiment.queue import claim_next_run, enqueue_plan
from harnesslab.judgelab.models import JudgeDefinition, JudgeMode, PublicCase
from harnesslab.judgelab.output import parse_judge_output
from harnesslab.model_lane.models import ProviderRequest
from harnesslab.model_lane.providers import CampaignHTTPClientPool, OpenAICompatibleChatAdapter
from harnesslab.registry.alibaba import configured_alibaba_bailian_profile
from harnesslab.release.throughput import simulate_v6_throughput
from harnesslab.release.v6 import (
    V6_EXPERIMENT_ID,
    build_v6_plan,
    v6_binding_identity,
    v6_dispatch_profiles,
)

ROOT = Path(__file__).resolve().parents[1]
V5_INCIDENT = ROOT / "release/kb3-v5-attempt1-scheduling-incident.json"
V6_CONTROL = ROOT / "release/core-real-matrix-v6-control.json"


@pytest.fixture(scope="session")
def v6_plan() -> MethodologyV2ExperimentPlan:
    return build_v6_plan(ROOT, {})


@pytest.fixture(scope="session")
def v6_control() -> dict[str, Any]:
    value = json.loads(V6_CONTROL.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_v5_incident_is_append_only_and_non_promotable() -> None:
    incident = json.loads(V5_INCIDENT.read_text(encoding="utf-8"))
    assert incident["append_only"] is True
    assert incident["result"] == "HARD_STOPPED_METHODOLOGY_SCHEDULING_DRIFT"
    assert incident["evidence_class"] == "REAL_DIAGNOSTIC_DESCRIPTIVE_ONLY"
    assert incident["formal_kb3_eligibility"] == "NON_PROMOTABLE"
    assert incident["formal_salvage_audit"]["salvageable_blocks"] == 0
    assert incident["immutability"] == {
        "old_database_rows_modified": False,
        "old_manifests_modified": False,
        "old_timestamps_modified": False,
        "old_artifacts_modified": False,
        "freeze_artifact_is_new_append_only_record": True,
    }


def test_v6_plan_is_exact_methodology_v2(v6_plan: MethodologyV2ExperimentPlan) -> None:
    assert v6_plan.experiment_id == V6_EXPERIMENT_ID
    assert v6_plan.experiment_id != "core-real-matrix-v5"
    assert v6_plan.schema_version == 2
    assert v6_plan.scheduling_policy == "BLOCKED_INTERLEAVED_SCHEDULING"
    assert len(v6_plan.schedule_blocks) == 90
    assert len(v6_plan.run_slots) == 630
    assert {block.repeat_index for block in v6_plan.schedule_blocks} == set(range(5))
    assert len({(block.task_id, block.repeat_index) for block in v6_plan.schedule_blocks}) == 90
    assert all(len(block.slot_ids) == 7 for block in v6_plan.schedule_blocks)
    assert all(len(set(block.cell_execution_order)) == 7 for block in v6_plan.schedule_blocks)


def test_v6_frozen_digests_and_schedule_are_reproducible(
    v6_plan: MethodologyV2ExperimentPlan,
    v6_control: dict[str, Any],
) -> None:
    assert v6_control["plan_digest"] == v6_plan.digest
    assert [block.model_dump(mode="json") for block in v6_plan.schedule_blocks] == v6_control[
        "schedule_blocks"
    ]
    assert [slot.slot_id for slot in v6_plan.run_slots] == [
        item["slot_id"] for item in v6_control["logical_slots"]
    ]


def test_v6_has_no_opencode_subject_and_freezes_alibaba_profiles(
    v6_plan: MethodologyV2ExperimentPlan,
    v6_control: dict[str, Any],
) -> None:
    assert all("opencode-go" not in cell.provider_route for cell in v6_plan.cells)
    cells = {item["cell_id"]: item for item in v6_control["cells"]}
    assert cells["model-qwen38-alibaba-bailian-chat"]["provider_profile_id"] == (
        "alibaba-bailian-qwen3.8-max-chat"
    )
    assert cells["harness-claude-qwen38-alibaba-bailian"]["provider_profile_id"] == (
        "alibaba-bailian-qwen3.8-max-messages"
    )
    assert cells["model-qwen38-alibaba-bailian-chat"]["runtime_endpoint_fingerprint"] is None
    assert {cell.id: v6_binding_identity(cell) for cell in v6_plan.cells} == {
        cell_id: item["execution_binding_identity"] for cell_id, item in cells.items()
    }
    assert v6_control["controls"]["opencode_subject_dependency"] == 0


def test_v6_judge_redesign_is_non_opencode_and_canary_gated(
    v6_control: dict[str, Any],
) -> None:
    judge = v6_control["judge"]
    assert judge["decision"] == "JUDGE_REDESIGN_REQUIRES_SMALL_REAL_CANARY"
    assert judge["opencode_runtime_dependency"] == 0
    assert len(judge["candidates"]) == 2
    assert all(
        item["provider_profile_id"].startswith("alibaba-bailian-") for item in judge["candidates"]
    )
    assert judge["preferred_candidate"] == "alibaba-bailian-glm-5.2-chat"


def test_v6_prohibits_retry_substitution_and_score_early_stop(
    v6_control: dict[str, Any],
) -> None:
    controls = v6_control["controls"]
    assert controls["semantic_retry_allowed"] is False
    assert controls["score_based_retry_allowed"] is False
    assert controls["provider_model_substitution_allowed"] is False
    assert controls["score_based_early_stop_allowed"] is False
    assert v6_control["canary_preregistration"]["retries"] == 0
    assert v6_control["canary_preregistration"]["max_future_calls"] == 3


def test_block_coordinator_pipelines_only_after_seven_slots_are_represented(
    v6_plan: MethodologyV2ExperimentPlan,
) -> None:
    profile = v6_dispatch_profiles()[1]
    coordinator = BlockDispatchCoordinator(v6_plan, profile)
    block_by_slot = {
        slot_id: block_index
        for block_index, block in enumerate(v6_plan.schedule_blocks)
        for slot_id in block.slot_ids
    }
    active: dict[str, SlotResourceClass] = {}
    dispatch_blocks: list[int] = []
    while len(dispatch_blocks) < 14:
        slot = coordinator.next_slot(active)
        if slot is None:
            first_slot = next(iter(active))
            active.pop(first_slot)
            continue
        active[slot.slot_id] = slot_resource_class(slot)
        dispatch_blocks.append(block_by_slot[slot.slot_id])
    assert dispatch_blocks[:7] == [0] * 7
    assert dispatch_blocks[7:] == [1] * 7


def test_throughput_profiles_pass_all_caps_and_select_fastest(
    v6_plan: MethodologyV2ExperimentPlan,
    v6_control: dict[str, Any],
) -> None:
    profiles = v6_dispatch_profiles()
    simulations = [simulate_v6_throughput(v6_plan, profile) for profile in profiles]
    assert all(item.hard_checks_passed for item in simulations)
    assert all(item.duplicate_claims == 0 for item in simulations)
    assert all(item.scheduling_violations == 0 for item in simulations)
    assert all(item.workspace_collisions == item.artifact_collisions == 0 for item in simulations)
    assert all(item.lease_losses == item.cleanup_failures == 0 for item in simulations)
    assert all(item.peak_harness_workers <= 2 for item in simulations)
    assert all(max(item.peak_provider_concurrency.values()) <= 2 for item in simulations)
    fastest = min(simulations, key=lambda item: item.simulated_wall_time_seconds)
    selected = v6_control["selected_execution_profile"]
    assert selected["profile"]["profile_id"] == fastest.profile_id == "V6_PROFILE_B_C6"
    assert selected["profile_digest"] == fastest.profile_digest
    assert selected["runtime_adaptive_concurrency"] is False


@pytest.mark.asyncio
async def test_campaign_http_pool_isolates_routes_and_credentials() -> None:
    async with CampaignHTTPClientPool(max_connections_per_route=2) as pool:
        first = pool.client_for("provider-a|chat|env:ROUTE_A/chat", "CREDENTIAL_A")
        same = pool.client_for("provider-a|chat|env:ROUTE_A/chat", "CREDENTIAL_A")
        other_route = pool.client_for("provider-a|messages|env:ROUTE_B/messages", "CREDENTIAL_A")
        other_credential = pool.client_for("provider-a|chat|env:ROUTE_A/chat", "CREDENTIAL_B")
        assert first is same
        assert first is not other_route
        assert first is not other_credential
        assert pool.route_count == 3
    assert first.is_closed and other_route.is_closed and other_credential.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("requested_model", ["glm-5.2", "deepseek-v4-pro"])
async def test_alibaba_judge_candidates_pass_keyless_chat_and_strict_json_contract(
    requested_model: str,
) -> None:
    profile = configured_alibaba_bailian_profile(
        requested_model,
        Protocol.CHAT_COMPLETIONS,
        max_output_tokens=256,
    ).model_copy(update={"request_timeout_seconds": 90})

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "keyless-judge-contract",
                "model": requested_model,
                "choices": [
                    {
                        "message": {"content": '{"schema_version":1,"label":"PASS","reason":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    environment = {
        "HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL": "https://keyless.invalid/v1",
        "HARNESSLAB_ALIBABA_BAILIAN_API_KEY": "development-placeholder",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenAICompatibleChatAdapter(
            client=client,
            environment=environment,
        ).invoke(ProviderRequest(profile=profile, instructions="judge", input="case"))
    case = PublicCase(
        case_id="keyless-label",
        mode=JudgeMode.LABEL,
        question="keyless",
        rubric="return PASS or FAIL",
        candidate="candidate",
        allowed_labels=("PASS", "FAIL"),
    )
    definition = JudgeDefinition(
        definition_id="keyless-judge",
        version="1",
        public_instruction="Return strict public JSON.",
        supported_modes=(JudgeMode.LABEL,),
        maximum_public_justification_length=100,
        allow_abstention=True,
        pairwise_blinding_required=False,
        order_swap_policy="DISABLED",
        private_reasoning_exclusion_policy="REJECT_PRIVATE_REASONING_FIELDS",
    )
    parsed = parse_judge_output(result.public_output_text, case, definition)
    assert result.observed_model == requested_model
    assert parsed.model_dump(mode="json") == {
        "schema_version": 1,
        "label": "PASS",
        "reason": "ok",
    }


@pytest.mark.integration
async def test_postgresql_v6_queue_claims_frozen_schedule_and_resumes_terminal_slots(
    database_url: str,
    v6_plan: MethodologyV2ExperimentPlan,
) -> None:
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    now = datetime(2026, 8, 31, 0, 0, tzinfo=UTC)
    try:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == V6_EXPERIMENT_ID)
            )
        async with factory() as session, session.begin():
            await enqueue_plan(session, v6_plan)
            first_record = await session.scalar(
                select(ExperimentRunRecord)
                .where(ExperimentRunRecord.experiment_id == V6_EXPERIMENT_ID)
                .order_by(ExperimentRunRecord.slot_order)
                .limit(1)
                .with_for_update()
            )
            assert first_record is not None
            first_record.status = "completed"
            first_record.attempt = 1
            first_record.normalized_outcome = "capability_pass"
            first_record.started_at = now
            first_record.finished_at = now
        session_a = factory()
        session_b = factory()
        try:
            async with session_a.begin():
                claimed_a = await claim_next_run(
                    session_a,
                    V6_EXPERIMENT_ID,
                    "v6-a",
                    now=now + timedelta(seconds=1),
                    ttl=timedelta(minutes=1),
                )
                assert claimed_a is not None
                async with session_b.begin():
                    claimed_b = await claim_next_run(
                        session_b,
                        V6_EXPERIMENT_ID,
                        "v6-b",
                        now=now + timedelta(seconds=1),
                        ttl=timedelta(minutes=1),
                    )
                    assert claimed_b is not None
        finally:
            await session_a.close()
            await session_b.close()
        assert claimed_a.slot_order == 1
        assert claimed_b.slot_order == 2
        assert claimed_a.slot_id != claimed_b.slot_id
        assert claimed_a.slot_id == v6_plan.run_slots[1].slot_id
        assert claimed_b.slot_id == v6_plan.run_slots[2].slot_id
    finally:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == V6_EXPERIMENT_ID)
            )
        await engine.dispose()


def test_v6_optimization_decisions_preserve_isolation(v6_control: dict[str, Any]) -> None:
    assert v6_control["transport"]["shared_http_pooling"] == "ENABLED"
    assert v6_control["transport"]["isolation_key"] == [
        "provider_route_identity",
        "credential_reference",
    ]
    assert v6_control["campaign_preflight_cache"]["decision"] == "SKIPPED_WITH_REASON"
    assert v6_control["verifier_staging_cache"]["decision"] == "SKIPPED_WITH_REASON"
    assert v6_control["block_pipelining"]["enabled"] is True
    assert v6_control["pricing"]["status"] == (
        "PUBLIC_BASE_RATES_VERIFIED_OPERATOR_BILLING_INPUTS_REQUIRED"
    )
    assert v6_control["pricing"]["public_rate_evidence"]["qwen3.8-max"] == {
        "input": "1.65",
        "output": "4.951",
        "token_tier": "0<Token<=1M",
    }
    assert v6_control["execution_state"] == {
        "keyless_provider_calls": 0,
        "real_harness_calls": 0,
        "real_judge_calls": 0,
        "real_v6_execution_started": False,
    }
