from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harnesslab.experiment.methodology import load_evaluation_methodology
from harnesslab.registry.model_chat import (
    MODEL_CHAT_V3_EXPERIMENT_ID,
    MODEL_CHAT_V3_PLAN_DIGEST,
    MODEL_CHAT_V3_SCHEDULE_SEED,
    model_chat_v3_builder_request,
)
from harnesslab.registry.models import PreflightStatus
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.registry.service import build_experiment_snapshot

ROOT = Path(__file__).resolve().parents[1]
CORPUS = Path("release/tier-a-verifier-robustness-v2.json")
PLAN_PATH = ROOT / "release/model-chat-v3-keyless-plan.json"
CANARY_PATH = ROOT / "release/model-chat-v3-canary.json"
CONTINUATION_PATH = ROOT / "release/model-chat-v3-continuation-policy.json"
CANARY_TASK_IDS = (
    "core-python-quota",
    "core-java-quota",
    "core-typescript-quota",
)
KEYLESS_ENVIRONMENT = {
    "HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL": (
        "https://workspace-sentinel.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    ),
    "HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL": (
        "https://workspace-sentinel.cn-beijing.maas.aliyuncs.com/apps/anthropic"
    ),
    "HARNESSLAB_ALIBABA_BAILIAN_API_KEY": "fake-model-chat-v3-key",
    "HARNESSLAB_ALIBABA_BAILIAN_STATUS": "AVAILABLE",
}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    catalog = build_registry_catalog(ROOT, KEYLESS_ENVIRONMENT, task_corpus_path=CORPUS)
    methodology = load_evaluation_methodology(ROOT / "release/evaluation-methodology-v2.json")
    request = model_chat_v3_builder_request(catalog, methodology)
    snapshot = build_experiment_snapshot(
        request,
        ROOT,
        KEYLESS_ENVIRONMENT,
        task_corpus_path=CORPUS,
    )
    plan = snapshot.plan
    if plan.digest != MODEL_CHAT_V3_PLAN_DIGEST:
        raise RuntimeError(
            "Model Chat v3 frozen plan identity drifted: "
            f"expected={MODEL_CHAT_V3_PLAN_DIGEST} actual={plan.digest}"
        )
    if snapshot.preflight.status is PreflightStatus.BLOCKED:
        raise RuntimeError("Model Chat v3 keyless preflight is blocked")
    if (
        plan.experiment_id != MODEL_CHAT_V3_EXPERIMENT_ID
        or plan.schedule_seed != MODEL_CHAT_V3_SCHEDULE_SEED
        or len(plan.tasks) != 18
        or len(plan.schedule_blocks) != 18
        or len(plan.run_slots) != 36
        or {task.task_version for task in plan.tasks} != {"1.0.2"}
    ):
        raise RuntimeError("Model Chat v3 frozen plan shape drifted")

    cells = {cell.id: cell for cell in plan.cells}
    if set(cells) != {"Q", "D"}:
        raise RuntimeError("Model Chat v3 treatment/control cells drifted")
    if cells["Q"].resource_envelope_identity != cells["D"].resource_envelope_identity:
        raise RuntimeError("Model Chat v3 treatment/control resource envelopes differ")
    corpus = json.loads((ROOT / CORPUS).read_text(encoding="utf-8"))
    verifier_identities = {item["task_id"]: item["verifier_identity"] for item in corpus["tasks"]}
    runtime_identities = {
        cell_id: cells[cell_id].effective_runtime_profile_identity for cell_id in ("Q", "D")
    }

    canary_slots = tuple(
        slot for slot in plan.run_slots if slot.task.task_id in set(CANARY_TASK_IDS)
    )
    if (
        len(canary_slots) != 6
        or {slot.task.task_id for slot in canary_slots} != set(CANARY_TASK_IDS)
        or {slot.cell_id for slot in canary_slots} != {"Q", "D"}
        or {slot.repeat_index for slot in canary_slots} != {0}
    ):
        raise RuntimeError("Model Chat v3 canary selection drifted")
    canary_slot_ids = tuple(slot.slot_id for slot in canary_slots)
    remaining_slot_ids = tuple(
        slot.slot_id for slot in plan.run_slots if slot.slot_id not in set(canary_slot_ids)
    )
    if len(remaining_slot_ids) != 30:
        raise RuntimeError("Model Chat v3 continuation selection drifted")

    plan_payload = snapshot.model_dump(mode="json")
    plan_payload["freeze"] = {
        "strategy": "MODEL_CHAT_V3_FULL_REACQUISITION",
        "task_version": "1.0.2",
        "schedule_seed": MODEL_CHAT_V3_SCHEDULE_SEED,
        "qwen_runtime_identity": runtime_identities["Q"],
        "deepseek_runtime_identity": runtime_identities["D"],
        "common_resource_envelope_identity": cells["Q"].resource_envelope_identity,
        "real_provider_calls": 0,
    }
    _write(PLAN_PATH, plan_payload)

    canary_payload = {
        "schema_version": 1,
        "canary_id": "portfolio-alibaba-model-chat-v3-canary",
        "experiment_id": MODEL_CHAT_V3_EXPERIMENT_ID,
        "plan_digest": plan.digest,
        "schedule_seed": plan.schedule_seed,
        "selection_policy": "THREE_LANGUAGE_FIXED_SIX_SLOT_CANARY",
        "slots": [
            {
                "slot_id": slot.slot_id,
                "slot_order": slot.slot_order,
                "task_id": slot.task.task_id,
                "task_version": slot.task.task_version,
                "task_digest": slot.task.task_digest,
                "verifier_identity": verifier_identities[slot.task.task_id],
                "cell_id": slot.cell_id,
                "requested_model": slot.requested_model,
                "effective_runtime_profile_identity": slot.effective_runtime_profile_identity,
                "resource_envelope_identity": slot.resource_envelope_identity,
            }
            for slot in canary_slots
        ],
        "success_gates": [
            "OBSERVED_PROVIDER_MODEL_IDENTITY_MATCH",
            "NO_CONTROL_DRIFT",
            "NO_VERIFIER_INFRA",
            "NO_SECRET_LEAKAGE",
            "TRACE_AND_EVIDENCE_VALID",
            "TASK_VERSION_EXACTLY_1.0.2",
            "VERIFIER_IDENTITY_EXACTLY_FROZEN",
            "CAPABILITY_PASS_OR_FAIL_ACCEPTABLE",
        ],
        "provider_infra_policy": "OPERATIONAL_STOP_AND_REVIEW_NO_SEMANTIC_RETRY",
        "execution_status": "NOT_RUN",
        "real_provider_calls": 0,
    }
    _write(CANARY_PATH, canary_payload)

    continuation_payload = {
        "schema_version": 1,
        "policy_id": "portfolio-alibaba-model-chat-v3-continuation",
        "experiment_id": MODEL_CHAT_V3_EXPERIMENT_ID,
        "plan_digest": plan.digest,
        "scheduling_policy": "BLOCKED_INTERLEAVED_SCHEDULING",
        "canary_slot_ids": canary_slot_ids,
        "remaining_slot_ids": remaining_slot_ids,
        "continuation_condition": "ALL_FIXED_CANARY_SUCCESS_GATES_PASS",
        "continuation_action": "AUTOMATICALLY_ALLOW_REMAINING_30_FROZEN_SLOTS",
        "capability_failure_policy": "TERMINAL_NO_RETRY",
        "infrastructure_failure_policy": ("PRESERVE_IMMUTABLE_FIRST_ATTEMPT_NO_IMMEDIATE_RETRY"),
        "post_breadth_recovery_policy": (
            "AT_MOST_ONE_IMMUTABLE_RECOVERY_ATTEMPT_PER_ELIGIBLE_SLOT"
        ),
        "operational_stop_conditions": [
            "OBSERVED_PROVIDER_OR_MODEL_IDENTITY_DRIFT",
            "TASK_VERIFIER_OR_VERSION_DRIFT",
            "VERIFIER_INFRASTRUCTURE_REGRESSION",
            "REPEATED_PROVIDER_ROUTE_SYSTEMIC_FAILURE",
            "SECRET_EXPOSURE",
            "EVIDENCE_PERSISTENCE_FAILURE",
        ],
        "score_based_stop_condition": "PROHIBITED",
        "execution_status": "NOT_RUN",
        "real_provider_calls": 0,
    }
    _write(CONTINUATION_PATH, continuation_payload)

    print("MODEL_CHAT_V3_KEYLESS_PREFLIGHT=PASS")
    print(f"MODEL_CHAT_V3_EXPERIMENT_ID={plan.experiment_id}")
    print(f"MODEL_CHAT_V3_PLAN_DIGEST={plan.digest}")
    print(f"MODEL_CHAT_V3_SCHEDULE_SEED={plan.schedule_seed}")
    print(f"MODEL_CHAT_V3_TOTAL_SLOTS={len(plan.run_slots)}")
    print(f"MODEL_CHAT_V3_CANARY_SLOTS={len(canary_slots)}")
    print(f"MODEL_CHAT_V3_QWEN_RUNTIME_ID={runtime_identities['Q']}")
    print(f"MODEL_CHAT_V3_DEEPSEEK_RUNTIME_ID={runtime_identities['D']}")
    print(f"MODEL_CHAT_V3_RESOURCE_ENVELOPE_ID={cells['Q'].resource_envelope_identity}")
    print("REAL_PROVIDER_CALLS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
