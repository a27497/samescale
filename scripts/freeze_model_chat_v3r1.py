from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from harnesslab.experiment.methodology import load_evaluation_methodology
from harnesslab.registry.model_chat import (
    MODEL_CHAT_V3R1_ENDPOINT_FINGERPRINT,
    MODEL_CHAT_V3R1_EXPERIMENT_ID,
    MODEL_CHAT_V3R1_PLAN_DIGEST,
    MODEL_CHAT_V3R1_SCHEDULE_SEED,
    model_chat_v3r1_builder_request,
)
from harnesslab.registry.models import ExperimentSnapshot, PreflightStatus
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.registry.service import (
    build_experiment_snapshot,
    validate_frozen_runtime_contract,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = Path("release/tier-a-verifier-robustness-v2.json")
PLAN_PATH = ROOT / "release/model-chat-v3r1-keyless-plan.json"
CANARY_PATH = ROOT / "release/model-chat-v3r1-canary.json"
CONTINUATION_PATH = ROOT / "release/model-chat-v3r1-continuation-policy.json"
ORIGINAL_V3_PATHS = (
    ROOT / "release/model-chat-v3-keyless-plan.json",
    ROOT / "release/model-chat-v3-canary.json",
    ROOT / "release/model-chat-v3-continuation-policy.json",
)
CANARY_TASK_IDS = (
    "core-python-quota",
    "core-java-quota",
    "core-typescript-quota",
)
REQUIRED_RUNTIME_REFERENCES = (
    "HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL",
    "HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL",
    "HARNESSLAB_ALIBABA_BAILIAN_API_KEY",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_snapshot() -> tuple[ExperimentSnapshot, dict[str, object]]:
    payload = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Model Chat v3r1 plan artifact must contain an object")
    freeze = payload.pop("freeze", None)
    if not isinstance(freeze, dict):
        raise RuntimeError("Model Chat v3r1 plan artifact lacks freeze metadata")
    return ExperimentSnapshot.model_validate(payload), freeze


def _validate_snapshot(snapshot: ExperimentSnapshot) -> None:
    plan = snapshot.plan
    if MODEL_CHAT_V3R1_PLAN_DIGEST == "PENDING_LIVE_FREEZE":
        raise RuntimeError("Model Chat v3r1 plan digest constant is not frozen")
    if plan.digest != MODEL_CHAT_V3R1_PLAN_DIGEST:
        raise RuntimeError(
            "Model Chat v3r1 frozen plan identity drifted: "
            f"expected={MODEL_CHAT_V3R1_PLAN_DIGEST} actual={plan.digest}"
        )
    profiles = validate_frozen_runtime_contract(plan, snapshot.provider_selections)
    endpoint_fingerprints = {
        item.runtime_endpoint_fingerprint for item in snapshot.provider_selections
    }
    if endpoint_fingerprints != {MODEL_CHAT_V3R1_ENDPOINT_FINGERPRINT}:
        raise RuntimeError("Model Chat v3r1 endpoint fingerprint drifted")
    if (
        plan.experiment_id != MODEL_CHAT_V3R1_EXPERIMENT_ID
        or plan.schedule_seed != MODEL_CHAT_V3R1_SCHEDULE_SEED
        or plan.scheduling_policy != "BLOCKED_INTERLEAVED_SCHEDULING"
        or plan.evaluation_mode.value != "QUICK"
        or plan.repeat_count != 1
        or len(plan.tasks) != 18
        or len(plan.schedule_blocks) != 18
        or len(plan.run_slots) != 36
        or {task.task_version for task in plan.tasks} != {"1.0.2"}
        or set(profiles) != {"Q", "D"}
    ):
        raise RuntimeError("Model Chat v3r1 frozen plan shape drifted")
    cells = {cell.id: cell for cell in plan.cells}
    if (
        profiles["Q"].requested_model != "qwen3.8-max"
        or profiles["D"].requested_model != "deepseek-v4-pro"
        or any(profile.protocol.value != "chat_completions" for profile in profiles.values())
        or any(profile.route != "/chat/completions" for profile in profiles.values())
        or any(profile.reasoning.max_output_tokens != 4000 for profile in profiles.values())
        or any(profile.request_timeout_seconds != 180 for profile in profiles.values())
        or cells["Q"].resource_envelope_identity != cells["D"].resource_envelope_identity
    ):
        raise RuntimeError("Model Chat v3r1 runtime contract drifted")


def _validate_campaign_files(snapshot: ExperimentSnapshot) -> None:
    canary = json.loads(CANARY_PATH.read_text(encoding="utf-8"))
    continuation = json.loads(CONTINUATION_PATH.read_text(encoding="utf-8"))
    canary_slots = canary.get("slots", [])
    canary_ids = tuple(item["slot_id"] for item in canary_slots)
    remaining_ids = tuple(continuation.get("remaining_slot_ids", []))
    plan_ids = {slot.slot_id for slot in snapshot.plan.run_slots}
    if (
        canary.get("experiment_id") != MODEL_CHAT_V3R1_EXPERIMENT_ID
        or canary.get("plan_digest") != MODEL_CHAT_V3R1_PLAN_DIGEST
        or canary.get("execution_status") != "NOT_RUN"
        or canary.get("real_provider_calls") != 0
        or len(canary_ids) != 6
        or len(set(canary_ids)) != 6
        or {item["task_id"] for item in canary_slots} != set(CANARY_TASK_IDS)
        or {item["task_version"] for item in canary_slots} != {"1.0.2"}
    ):
        raise RuntimeError("Model Chat v3r1 canary artifact drifted")
    if (
        continuation.get("experiment_id") != MODEL_CHAT_V3R1_EXPERIMENT_ID
        or continuation.get("plan_digest") != MODEL_CHAT_V3R1_PLAN_DIGEST
        or tuple(continuation.get("canary_slot_ids", [])) != canary_ids
        or continuation.get("execution_status") != "NOT_RUN"
        or continuation.get("real_provider_calls") != 0
        or len(remaining_ids) != 30
        or set(canary_ids) & set(remaining_ids)
        or set(canary_ids) | set(remaining_ids) != plan_ids
    ):
        raise RuntimeError("Model Chat v3r1 continuation artifact drifted")


def validate_frozen() -> None:
    snapshot, freeze = _load_snapshot()
    _validate_snapshot(snapshot)
    _validate_campaign_files(snapshot)
    if freeze.get("strategy") != "MODEL_CHAT_V3R1_ENDPOINT_RECONCILED_FULL_REACQUISITION":
        raise RuntimeError("Model Chat v3r1 freeze strategy drifted")
    for path in (PLAN_PATH, CANARY_PATH, CONTINUATION_PATH):
        source = path.read_text(encoding="utf-8")
        if "api_key_value" in source.casefold() or "workspace-" in source.casefold():
            raise RuntimeError("Model Chat v3r1 artifact contains protected runtime material")


def _build_live_snapshot(environment: Mapping[str, str]) -> ExperimentSnapshot:
    missing = [
        name for name in REQUIRED_RUNTIME_REFERENCES if not environment.get(name, "").strip()
    ]
    if missing:
        raise RuntimeError("Model Chat v3r1 live freeze is missing required runtime references")
    catalog = build_registry_catalog(ROOT, environment, task_corpus_path=CORPUS)
    methodology = load_evaluation_methodology(ROOT / "release/evaluation-methodology-v2.json")
    request = model_chat_v3r1_builder_request(catalog, methodology)
    snapshot = build_experiment_snapshot(
        request,
        ROOT,
        environment,
        task_corpus_path=CORPUS,
    )
    if snapshot.preflight.status is PreflightStatus.BLOCKED:
        raise RuntimeError("Model Chat v3r1 live preflight is blocked")
    fingerprints = {item.runtime_endpoint_fingerprint for item in snapshot.provider_selections}
    if fingerprints != {MODEL_CHAT_V3R1_ENDPOINT_FINGERPRINT}:
        raise RuntimeError("Model Chat v3r1 live endpoint identity does not match provenance")
    return snapshot


def freeze_from_live_environment() -> None:
    original_hashes = {path: _sha256(path) for path in ORIGINAL_V3_PATHS}
    environment = dict(os.environ)
    snapshot = _build_live_snapshot(environment)
    plan = snapshot.plan
    if (
        MODEL_CHAT_V3R1_PLAN_DIGEST != "PENDING_LIVE_FREEZE"
        and plan.digest != MODEL_CHAT_V3R1_PLAN_DIGEST
    ):
        raise RuntimeError("Model Chat v3r1 live plan does not match its frozen digest")
    cells = {cell.id: cell for cell in plan.cells}
    corpus = json.loads((ROOT / CORPUS).read_text(encoding="utf-8"))
    verifier_identities = {item["task_id"]: item["verifier_identity"] for item in corpus["tasks"]}
    canary_slots = tuple(
        slot for slot in plan.run_slots if slot.task.task_id in set(CANARY_TASK_IDS)
    )
    canary_ids = tuple(slot.slot_id for slot in canary_slots)
    remaining_ids = tuple(slot.slot_id for slot in plan.run_slots if slot.slot_id not in canary_ids)
    if len(canary_slots) != 6 or len(remaining_ids) != 30:
        raise RuntimeError("Model Chat v3r1 campaign selection drifted")

    plan_payload = snapshot.model_dump(mode="json")
    plan_payload["freeze"] = {
        "strategy": "MODEL_CHAT_V3R1_ENDPOINT_RECONCILED_FULL_REACQUISITION",
        "predecessor_experiment_id": "portfolio-alibaba-model-chat-v3",
        "predecessor_status": "PRE_ACQUISITION_ABORTED_CONTROL_IDENTITY_MISMATCH",
        "task_version": "1.0.2",
        "schedule_seed": MODEL_CHAT_V3R1_SCHEDULE_SEED,
        "endpoint_fingerprint": MODEL_CHAT_V3R1_ENDPOINT_FINGERPRINT,
        "qwen_runtime_identity": cells["Q"].effective_runtime_profile_identity,
        "deepseek_runtime_identity": cells["D"].effective_runtime_profile_identity,
        "common_resource_envelope_identity": cells["Q"].resource_envelope_identity,
        "real_provider_calls": 0,
    }
    _write(PLAN_PATH, plan_payload)
    _write(
        CANARY_PATH,
        {
            "schema_version": 1,
            "canary_id": "portfolio-alibaba-model-chat-v3r1-canary",
            "experiment_id": MODEL_CHAT_V3R1_EXPERIMENT_ID,
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
        },
    )
    _write(
        CONTINUATION_PATH,
        {
            "schema_version": 1,
            "policy_id": "portfolio-alibaba-model-chat-v3r1-continuation",
            "experiment_id": MODEL_CHAT_V3R1_EXPERIMENT_ID,
            "plan_digest": plan.digest,
            "scheduling_policy": "BLOCKED_INTERLEAVED_SCHEDULING",
            "canary_slot_ids": canary_ids,
            "remaining_slot_ids": remaining_ids,
            "continuation_condition": "ALL_FIXED_CANARY_SUCCESS_GATES_PASS",
            "continuation_action": "AUTOMATICALLY_ALLOW_REMAINING_30_FROZEN_SLOTS",
            "capability_failure_policy": "TERMINAL_NO_RETRY",
            "infrastructure_failure_policy": "PRESERVE_IMMUTABLE_FIRST_ATTEMPT_NO_IMMEDIATE_RETRY",
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
                "FROZEN_PLAN_MISMATCH",
                "UNSAFE_OPERATOR_STATE_AMBIGUITY",
            ],
            "score_based_stop_condition": "PROHIBITED",
            "execution_status": "NOT_RUN",
            "real_provider_calls": 0,
        },
    )
    protected = tuple(
        value.encode()
        for name in REQUIRED_RUNTIME_REFERENCES
        if (value := environment.get(name, ""))
    )
    for path in (PLAN_PATH, CANARY_PATH, CONTINUATION_PATH):
        raw = path.read_bytes()
        if any(value in raw for value in protected):
            raise RuntimeError("Model Chat v3r1 artifact persisted protected runtime material")
    if any(_sha256(path) != digest for path, digest in original_hashes.items()):
        raise RuntimeError("original Model Chat v3 artifact changed during successor freeze")
    print("MODEL_CHAT_V3R1_LIVE_FREEZE=PASS")
    print(f"MODEL_CHAT_V3R1_PLAN_DIGEST={plan.digest}")
    print(f"MODEL_CHAT_V3R1_ENDPOINT_FINGERPRINT={MODEL_CHAT_V3R1_ENDPOINT_FINGERPRINT}")
    print("MODEL_CHAT_V3R1_TOTAL_SLOTS=36")
    print("MODEL_CHAT_V3R1_CANARY_SLOTS=6")
    print("REAL_PROVIDER_CALLS=0")


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze or validate Model Chat v3r1")
    parser.add_argument(
        "--freeze-from-live-environment",
        action="store_true",
        help="Freeze v3r1 from the authorized local endpoint without provider access.",
    )
    args = parser.parse_args()
    if args.freeze_from_live_environment:
        freeze_from_live_environment()
    else:
        validate_frozen()
        print("MODEL_CHAT_V3R1_KEYLESS_VALIDATION=PASS")
        print(f"MODEL_CHAT_V3R1_PLAN_DIGEST={MODEL_CHAT_V3R1_PLAN_DIGEST}")
        print(f"MODEL_CHAT_V3R1_ENDPOINT_FINGERPRINT={MODEL_CHAT_V3R1_ENDPOINT_FINGERPRINT}")
        print("REAL_PROVIDER_CALLS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
