from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from harnesslab.registry.model_chat import (
    MODEL_CHAT_V3R1_ENDPOINT_FINGERPRINT,
    MODEL_CHAT_V3R1_EXPERIMENT_ID,
    MODEL_CHAT_V3R1_PLAN_DIGEST,
    MODEL_CHAT_V3R1_SCHEDULE_SEED,
)
from harnesslab.registry.models import ExperimentSnapshot, PreflightStatus
from harnesslab.registry.runtime import direct_harness_control_identity
from harnesslab.registry.service import validate_frozen_runtime_contract
from harnesslab.tasks.package import TaskPackage
from tests.phase_g_helpers import ROOT

PLAN_PATH = ROOT / "release/model-chat-v3r1-keyless-plan.json"
CANARY_PATH = ROOT / "release/model-chat-v3r1-canary.json"
CONTINUATION_PATH = ROOT / "release/model-chat-v3r1-continuation-policy.json"
CORPUS_PATH = ROOT / "release/tier-a-verifier-robustness-v2.json"
ORIGINAL_V3_DIGESTS = {
    "release/model-chat-v3-keyless-plan.json": (
        "6fe30658b2b2794738eca3523669790c820fc4903812d7c54a540d52b4f15f48"
    ),
    "release/model-chat-v3-canary.json": (
        "f1a30c4f6090037e57374be5c79ccf92e1fa87d4e6817619680023de3b8db784"
    ),
    "release/model-chat-v3-continuation-policy.json": (
        "1e0da3d230e0a2ab544569f367e849ea08ad2fd588d971e0f8a8ce3180b2d07e"
    ),
}


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _snapshot() -> tuple[ExperimentSnapshot, dict[str, object]]:
    payload = _json(PLAN_PATH)
    freeze = payload.pop("freeze")
    assert isinstance(freeze, dict)
    return ExperimentSnapshot.model_validate(payload), freeze


def test_model_chat_v3r1_frozen_plan_round_trip_and_live_endpoint_identity() -> None:
    snapshot, freeze = _snapshot()
    plan = snapshot.plan
    profiles = validate_frozen_runtime_contract(plan, snapshot.provider_selections)

    assert plan.experiment_id == MODEL_CHAT_V3R1_EXPERIMENT_ID
    assert plan.digest == MODEL_CHAT_V3R1_PLAN_DIGEST
    assert plan.schedule_seed == MODEL_CHAT_V3R1_SCHEDULE_SEED
    assert plan.scheduling_policy == "BLOCKED_INTERLEAVED_SCHEDULING"
    assert plan.evaluation_mode.value == "QUICK"
    assert plan.repeat_count == 1
    assert len(plan.tasks) == len(plan.schedule_blocks) == 18
    assert len(plan.run_slots) == len({slot.slot_id for slot in plan.run_slots}) == 36
    assert {task.task_version for task in plan.tasks} == {"1.0.2"}
    assert snapshot.preflight.status is PreflightStatus.READY_WITH_WARNINGS
    assert {item.runtime_endpoint_fingerprint for item in snapshot.provider_selections} == {
        MODEL_CHAT_V3R1_ENDPOINT_FINGERPRINT
    }
    assert set(profiles) == {"Q", "D"}
    assert profiles["Q"].requested_model == "qwen3.8-max"
    assert profiles["D"].requested_model == "deepseek-v4-pro"
    assert all(profile.protocol.value == "chat_completions" for profile in profiles.values())
    assert all(profile.route == "/chat/completions" for profile in profiles.values())
    assert all(profile.reasoning.max_output_tokens == 4000 for profile in profiles.values())
    assert all(profile.request_timeout_seconds == 180 for profile in profiles.values())
    cells = {cell.id: cell for cell in plan.cells}
    assert cells["Q"].resource_envelope_identity == cells["D"].resource_envelope_identity
    assert cells["Q"].harness_config_identity == direct_harness_control_identity()
    assert cells["D"].harness_config_identity == direct_harness_control_identity()
    assert freeze["strategy"] == "MODEL_CHAT_V3R1_ENDPOINT_RECONCILED_FULL_REACQUISITION"
    assert freeze["predecessor_status"] == ("PRE_ACQUISITION_ABORTED_CONTROL_IDENTITY_MISMATCH")
    assert freeze["endpoint_fingerprint"] == MODEL_CHAT_V3R1_ENDPOINT_FINGERPRINT
    assert freeze["real_provider_calls"] == 0


def test_model_chat_v3r1_task_and_verifier_identities_are_exact() -> None:
    snapshot, _freeze = _snapshot()
    corpus = _json(CORPUS_PATH)
    entries = {
        cast(str, item["task_id"]): item for item in cast(list[dict[str, object]], corpus["tasks"])
    }
    for task in snapshot.plan.tasks:
        package = TaskPackage.load(ROOT / task.package_path)
        assert package.definition.version == "1.0.2"
        assert package.definition.content_digest == task.task_digest
        assert package.verifier_digest == entries[task.task_id]["verifier_identity"]


def test_model_chat_v3r1_canary_and_continuation_are_exact_and_inert() -> None:
    snapshot, _freeze = _snapshot()
    canary = _json(CANARY_PATH)
    continuation = _json(CONTINUATION_PATH)
    slots = cast(list[dict[str, object]], canary["slots"])
    canary_ids = tuple(cast(str, item["slot_id"]) for item in slots)
    remaining_ids = tuple(cast(list[str], continuation["remaining_slot_ids"]))
    plan_slots = {slot.slot_id: slot for slot in snapshot.plan.run_slots}

    assert canary["plan_digest"] == MODEL_CHAT_V3R1_PLAN_DIGEST
    assert canary["execution_status"] == "NOT_RUN"
    assert canary["real_provider_calls"] == 0
    assert len(canary_ids) == len(set(canary_ids)) == 6
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
        assert item["verifier_identity"] == frozen.task.verifier_identity
        assert item["effective_runtime_profile_identity"] == (
            frozen.effective_runtime_profile_identity
        )
        assert item["resource_envelope_identity"] == frozen.resource_envelope_identity
    assert tuple(cast(list[str], continuation["canary_slot_ids"])) == canary_ids
    assert len(remaining_ids) == 30
    assert not set(canary_ids) & set(remaining_ids)
    assert set(canary_ids) | set(remaining_ids) == set(plan_slots)
    assert continuation["capability_failure_policy"] == "TERMINAL_NO_RETRY"
    assert continuation["post_breadth_recovery_policy"] == (
        "AT_MOST_ONE_IMMUTABLE_RECOVERY_ATTEMPT_PER_ELIGIBLE_SLOT"
    )
    assert continuation["score_based_stop_condition"] == "PROHIBITED"


def test_model_chat_v3r1_preserves_original_v3_and_contains_no_runtime_values() -> None:
    for relative, expected in ORIGINAL_V3_DIGESTS.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected
    for path in (PLAN_PATH, CANARY_PATH, CONTINUATION_PATH):
        source = path.read_text(encoding="utf-8")
        assert "api_key_value" not in source.casefold()
        assert "workspace-" not in source.casefold()
