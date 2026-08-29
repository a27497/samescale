from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from harnesslab.registry.model_chat import (
    MODEL_CHAT_V3_EXPERIMENT_ID,
    MODEL_CHAT_V3_PLAN_DIGEST,
    MODEL_CHAT_V3_SCHEDULE_SEED,
)
from harnesslab.registry.models import ExperimentSnapshot, PreflightStatus
from harnesslab.registry.runtime import direct_harness_control_identity
from harnesslab.registry.service import validate_frozen_runtime_contract
from harnesslab.tasks.package import TaskPackage
from tests.phase_g_helpers import ROOT

PLAN_PATH = ROOT / "release/model-chat-v3-keyless-plan.json"
CANARY_PATH = ROOT / "release/model-chat-v3-canary.json"
CONTINUATION_PATH = ROOT / "release/model-chat-v3-continuation-policy.json"
CORPUS_PATH = ROOT / "release/tier-a-verifier-robustness-v2.json"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _snapshot() -> tuple[ExperimentSnapshot, dict[str, object]]:
    payload = _json(PLAN_PATH)
    freeze = payload.pop("freeze")
    assert isinstance(freeze, dict)
    return ExperimentSnapshot.model_validate(payload), freeze


def test_model_chat_v3_frozen_plan_round_trip_and_runtime_contract() -> None:
    snapshot, freeze = _snapshot()
    plan = snapshot.plan
    profiles = validate_frozen_runtime_contract(plan, snapshot.provider_selections)

    assert plan.experiment_id == MODEL_CHAT_V3_EXPERIMENT_ID
    assert plan.digest == MODEL_CHAT_V3_PLAN_DIGEST
    assert plan.schedule_seed == MODEL_CHAT_V3_SCHEDULE_SEED
    assert plan.scheduling_policy == "BLOCKED_INTERLEAVED_SCHEDULING"
    assert plan.evaluation_mode.value == "QUICK"
    assert plan.repeat_count == 1
    assert len(plan.tasks) == len(plan.schedule_blocks) == 18
    assert len(plan.run_slots) == len({slot.slot_id for slot in plan.run_slots}) == 36
    assert {task.task_version for task in plan.tasks} == {"1.0.2"}
    assert all(len(block.slot_ids) == 2 for block in plan.schedule_blocks)
    assert all(set(block.cell_execution_order) == {"Q", "D"} for block in plan.schedule_blocks)
    assert snapshot.preflight.status is PreflightStatus.READY_WITH_WARNINGS
    assert set(profiles) == {"Q", "D"}
    assert profiles["Q"].requested_model == "qwen3.8-max"
    assert profiles["D"].requested_model == "deepseek-v4-pro"
    assert all(profile.protocol.value == "chat_completions" for profile in profiles.values())
    assert all(profile.route == "/chat/completions" for profile in profiles.values())
    assert all(profile.reasoning.max_output_tokens == 4000 for profile in profiles.values())
    assert all(profile.request_timeout_seconds == 180 for profile in profiles.values())

    cells = {cell.id: cell for cell in plan.cells}
    assert cells["Q"].resource_envelope_identity == cells["D"].resource_envelope_identity
    assert cells["Q"].profile_identity == cells["D"].profile_identity
    assert cells["Q"].harness_config_identity == cells["D"].harness_config_identity
    assert cells["Q"].harness_config_identity == direct_harness_control_identity()
    assert freeze == {
        "common_resource_envelope_identity": cells["Q"].resource_envelope_identity,
        "deepseek_runtime_identity": cells["D"].effective_runtime_profile_identity,
        "qwen_runtime_identity": cells["Q"].effective_runtime_profile_identity,
        "real_provider_calls": 0,
        "schedule_seed": MODEL_CHAT_V3_SCHEDULE_SEED,
        "strategy": "MODEL_CHAT_V3_FULL_REACQUISITION",
        "task_version": "1.0.2",
    }
    budget = plan.budget_contract
    assert budget.max_provider_requests.value == 1
    assert budget.max_model_turns.value == 1
    assert budget.max_tool_calls.value == 0
    assert budget.max_output_tokens.value == 4000
    assert budget.max_wall_time.value == 240


def test_model_chat_v3_task_and_verifier_identities_are_exact() -> None:
    snapshot, _freeze = _snapshot()
    manifest = _json(CORPUS_PATH)
    manifest_tasks = cast(list[dict[str, object]], manifest["tasks"])
    entries = {cast(str, item["task_id"]): item for item in manifest_tasks}

    for task in snapshot.plan.tasks:
        package = TaskPackage.load(ROOT / task.package_path)
        assert package.definition.version == "1.0.2"
        assert package.definition.content_digest == task.task_digest
        assert package.verifier_digest == entries[task.task_id]["verifier_identity"]


def test_model_chat_v3_canary_is_exact_six_slots_and_inert() -> None:
    snapshot, _freeze = _snapshot()
    canary = _json(CANARY_PATH)
    slots = cast(list[dict[str, object]], canary["slots"])
    plan_slots = {slot.slot_id: slot for slot in snapshot.plan.run_slots}

    assert canary["plan_digest"] == MODEL_CHAT_V3_PLAN_DIGEST
    assert canary["execution_status"] == "NOT_RUN"
    assert canary["real_provider_calls"] == 0
    assert len(slots) == len({item["slot_id"] for item in slots}) == 6
    assert {item["task_id"] for item in slots} == {
        "core-python-quota",
        "core-java-quota",
        "core-typescript-quota",
    }
    assert {item["cell_id"] for item in slots} == {"Q", "D"}
    for item in slots:
        frozen = plan_slots[cast(str, item["slot_id"])]
        assert item["slot_order"] == frozen.slot_order
        assert item["task_version"] == frozen.task.task_version == "1.0.2"
        assert item["task_digest"] == frozen.task.task_digest
        assert item["effective_runtime_profile_identity"] == (
            frozen.effective_runtime_profile_identity
        )
        assert item["resource_envelope_identity"] == frozen.resource_envelope_identity

    gates = set(cast(list[str], canary["success_gates"]))
    assert "NO_VERIFIER_INFRA" in gates
    assert "CAPABILITY_PASS_OR_FAIL_ACCEPTABLE" in gates
    assert canary["provider_infra_policy"] == ("OPERATIONAL_STOP_AND_REVIEW_NO_SEMANTIC_RETRY")


def test_model_chat_v3_continuation_policy_is_frozen_before_scores() -> None:
    snapshot, _freeze = _snapshot()
    canary = _json(CANARY_PATH)
    continuation = _json(CONTINUATION_PATH)
    canary_slots = cast(list[dict[str, object]], canary["slots"])
    canary_ids = tuple(cast(str, item["slot_id"]) for item in canary_slots)
    remaining_ids = tuple(cast(list[str], continuation["remaining_slot_ids"]))

    assert tuple(cast(list[str], continuation["canary_slot_ids"])) == canary_ids
    assert len(remaining_ids) == 30
    assert not set(canary_ids) & set(remaining_ids)
    assert set(canary_ids) | set(remaining_ids) == {
        slot.slot_id for slot in snapshot.plan.run_slots
    }
    assert continuation["continuation_action"] == ("AUTOMATICALLY_ALLOW_REMAINING_30_FROZEN_SLOTS")
    assert continuation["capability_failure_policy"] == "TERMINAL_NO_RETRY"
    assert continuation["post_breadth_recovery_policy"] == (
        "AT_MOST_ONE_IMMUTABLE_RECOVERY_ATTEMPT_PER_ELIGIBLE_SLOT"
    )
    assert continuation["score_based_stop_condition"] == "PROHIBITED"
    assert continuation["execution_status"] == "NOT_RUN"
    assert continuation["real_provider_calls"] == 0
    stop_conditions = set(cast(list[str], continuation["operational_stop_conditions"]))
    assert {
        "OBSERVED_PROVIDER_OR_MODEL_IDENTITY_DRIFT",
        "TASK_VERIFIER_OR_VERSION_DRIFT",
        "VERIFIER_INFRASTRUCTURE_REGRESSION",
        "REPEATED_PROVIDER_ROUTE_SYSTEMIC_FAILURE",
        "SECRET_EXPOSURE",
        "EVIDENCE_PERSISTENCE_FAILURE",
    } <= stop_conditions


def test_model_chat_v3_artifacts_do_not_contain_real_credentials() -> None:
    for path in (PLAN_PATH, CANARY_PATH, CONTINUATION_PATH):
        source = path.read_text(encoding="utf-8")
        assert "fake-model-chat-v3-key" not in source
        assert "api_key_value" not in source.casefold()
