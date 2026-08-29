from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from harnesslab.experiment.methodology import load_evaluation_methodology
from harnesslab.model_lane.prompt import (
    MAX_PROMPT_BYTES,
    MAX_PROMPT_TREE_BYTES,
    render_direct_prompt,
)
from harnesslab.registry.models import CheckStatus, PreflightStatus
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.registry.service import build_experiment_snapshot
from harnesslab.registry.tier_b_smoke import (
    TIER_B_SMOKE_EXPERIMENT_ID,
    TIER_B_SMOKE_PLAN_DIGEST,
    TIER_B_SMOKE_SCHEDULE_SEED,
    tier_b_smoke_builder_request,
)
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.tier_b import load_tier_b_qualification

ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = Path("release/tier-b-qualification-v1.json")
PLAN_PATH = ROOT / "release/tier-b-smoke-keyless-plan.json"
PREREGISTRATION_PATH = ROOT / "release/tier-b-smoke-preregistration.json"
ENDPOINT_BINDING_STATUS = "PENDING_OPERATOR_ENDPOINT_RECONCILIATION"
KEYLESS_ENVIRONMENT = {
    "HARNESSLAB_ALIBABA_BAILIAN_API_KEY": "fake-tier-b-smoke-key",
}


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _prompt_analysis(packages: tuple[TaskPackage, ...]) -> list[dict[str, Any]]:
    analysis: list[dict[str, Any]] = []
    for package in packages:
        materialized = package.materialize()
        try:
            prompt = render_direct_prompt(
                task_instruction=package.definition.instruction,
                workspace=materialized.root,
                context=materialized.context,
            )
        finally:
            materialized.cleanup()
        workspace_files = tuple(
            path
            for path in (package.root / package.manifest.workspace_path).rglob("*")
            if path.is_file()
        )
        analysis.append(
            {
                "task_id": package.definition.id,
                "task_version": package.definition.version,
                "workspace_file_count": len(workspace_files),
                "workspace_utf8_bytes": sum(path.stat().st_size for path in workspace_files),
                "rendered_prompt_bytes": len(prompt.input.encode("utf-8")),
                "direct_prompt_tree_limit_bytes": MAX_PROMPT_TREE_BYTES,
                "direct_prompt_total_limit_bytes": MAX_PROMPT_BYTES,
                "prompt_contract_status": "PASS",
            }
        )
    return analysis


def _payloads() -> tuple[dict[str, Any], dict[str, Any]]:
    qualification_path = ROOT / QUALIFICATION
    qualification = load_tier_b_qualification(qualification_path)
    catalog = build_registry_catalog(
        ROOT,
        KEYLESS_ENVIRONMENT,
        task_corpus_path=QUALIFICATION,
    )
    methodology = load_evaluation_methodology(ROOT / "release/evaluation-methodology-v2.json")
    request = tier_b_smoke_builder_request(catalog, methodology)
    snapshot = build_experiment_snapshot(
        request,
        ROOT,
        KEYLESS_ENVIRONMENT,
        task_corpus_path=QUALIFICATION,
        tier_b_qualification_path=qualification_path,
    )
    plan = snapshot.plan
    if plan.digest != TIER_B_SMOKE_PLAN_DIGEST:
        raise RuntimeError(
            "Tier-B smoke frozen plan identity drifted: "
            f"expected={TIER_B_SMOKE_PLAN_DIGEST} actual={plan.digest}"
        )
    if (
        plan.experiment_id != TIER_B_SMOKE_EXPERIMENT_ID
        or plan.schedule_seed != TIER_B_SMOKE_SCHEDULE_SEED
        or plan.evaluation_mode.value != "QUICK"
        or plan.repeat_count != 1
        or len(plan.tasks) != 3
        or len(plan.schedule_blocks) != 3
        or len(plan.run_slots) != 6
        or plan.benchmark_tier is None
        or plan.benchmark_tier.value != "TIER_B_REPO_ENGINEERING"
        or plan.tier_b_qualification_id != qualification.qualification_id
        or plan.tier_b_qualification_digest != qualification.qualification_digest
    ):
        raise RuntimeError("Tier-B smoke frozen plan shape or qualification identity drifted")

    cells = {cell.id: cell for cell in plan.cells}
    if set(cells) != {"Q", "D"}:
        raise RuntimeError("Tier-B smoke model cells drifted")
    if cells["Q"].resource_envelope_identity != cells["D"].resource_envelope_identity:
        raise RuntimeError("Tier-B smoke model cells do not share one resource envelope")
    endpoint_blockers = tuple(
        check
        for check in snapshot.preflight.checks
        if check.status is CheckStatus.BLOCKED and check.key.startswith("endpoint:")
    )
    other_blockers = tuple(
        check
        for check in snapshot.preflight.checks
        if check.status is CheckStatus.BLOCKED and not check.key.startswith("endpoint:")
    )
    if (
        snapshot.preflight.status is not PreflightStatus.BLOCKED
        or len(endpoint_blockers) != 2
        or other_blockers
    ):
        raise RuntimeError("Tier-B keyless preflight must be blocked only on endpoint binding")
    if any(
        selection.runtime_endpoint_fingerprint is not None
        for selection in snapshot.provider_selections
    ):
        raise RuntimeError("pending Tier-B plan must not freeze an endpoint fingerprint")

    packages = tuple(TaskPackage.load(ROOT / task.package_path) for task in plan.tasks)
    prompt_analysis = _prompt_analysis(packages)
    tasks_by_id = {task.task_id: task for task in qualification.tasks}
    plan_payload = snapshot.model_dump(mode="json")
    plan_payload["freeze"] = {
        "strategy": "TIER_B_THREE_TASK_TWO_MODEL_KEYLESS_SMOKE",
        "endpoint_binding_status": ENDPOINT_BINDING_STATUS,
        "non_endpoint_controls_frozen": True,
        "qualification_id": qualification.qualification_id,
        "qualification_digest": qualification.qualification_digest,
        "common_resource_envelope_identity": cells["Q"].resource_envelope_identity,
        "qwen_runtime_identity": cells["Q"].effective_runtime_profile_identity,
        "deepseek_runtime_identity": cells["D"].effective_runtime_profile_identity,
        "resource_envelope_changed_from_tier_a_direct": False,
        "prompt_workspace_analysis": prompt_analysis,
        "execution_status": "NOT_RUN",
        "real_provider_calls": 0,
    }

    preregistration_payload = {
        "schema_version": 1,
        "preregistration_id": "tier-b-keyless-smoke-preregistration-v1",
        "experiment_id": plan.experiment_id,
        "plan_digest": plan.digest,
        "experiment_intent": "MODEL_COMPARISON",
        "evaluation_mode": "QUICK",
        "funnel_stage": "BREADTH",
        "scheduling_policy": "BLOCKED_INTERLEAVED_SCHEDULING",
        "schedule_seed": plan.schedule_seed,
        "repeat_count": plan.repeat_count,
        "total_logical_slots": len(plan.run_slots),
        "benchmark_tier": "TIER_B_REPO_ENGINEERING",
        "qualification_id": qualification.qualification_id,
        "qualification_digest": qualification.qualification_digest,
        "endpoint_binding_status": ENDPOINT_BINDING_STATUS,
        "endpoint_binding_rule": (
            "Operator reconciliation must produce and re-freeze the endpoint fingerprint before "
            "execution; no endpoint URL or fingerprint is guessed by this plan."
        ),
        "models": [
            {
                "cell_id": selection.cell_id,
                "provider": selection.provider_id,
                "requested_model": selection.requested_model,
                "provider_profile_id": selection.provider_profile_id,
                "effective_runtime_profile_identity": selection.effective_runtime_profile_identity,
                "runtime_endpoint_fingerprint": selection.runtime_endpoint_fingerprint,
            }
            for selection in snapshot.provider_selections
        ],
        "tasks": [
            {
                "task_id": task.task_id,
                "task_version": task.task_version,
                "task_digest": task.task_digest,
                "repository_snapshot_identity": task.workspace_input_digest,
                "verifier_identity": task.verifier_identity,
                "language": tasks_by_id[task.task_id].language,
                "engineering_shape": tasks_by_id[task.task_id].engineering_shape,
                "task_tier": "TIER_B_REPO_ENGINEERING",
            }
            for task in plan.tasks
        ],
        "smoke_slots": [
            {
                "slot_id": slot.slot_id,
                "slot_order": slot.slot_order,
                "paired_slot_identity": slot.paired_slot_identity,
                "task_id": slot.task.task_id,
                "task_version": slot.task.task_version,
                "task_digest": slot.task.task_digest,
                "repository_snapshot_identity": slot.task.workspace_input_digest,
                "verifier_identity": slot.task.verifier_identity,
                "cell_id": slot.cell_id,
                "requested_model": slot.requested_model,
                "resource_envelope_identity": slot.resource_envelope_identity,
            }
            for slot in plan.run_slots
        ],
        "resource_envelope": {
            "provider_requests_per_logical_run": 1,
            "model_turns_per_logical_run": 1,
            "tool_calls_per_logical_run": 0,
            "max_output_tokens": 4000,
            "provider_request_timeout_seconds": 180,
            "logical_wall_time_seconds": 240,
            "symmetric_between_cells": True,
            "identity": cells["Q"].resource_envelope_identity,
        },
        "resource_envelope_changed_from_tier_a_direct": False,
        "resource_envelope_change_reason": (
            "UNCHANGED: every frozen Tier-B workspace is below 5 KiB and every rendered Direct "
            "prompt is below 7 KiB, within the existing one-turn Direct prompt contract; the "
            "smoke intentionally tests the established 4000-token output bound."
        ),
        "prompt_workspace_analysis": prompt_analysis,
        "success_gates": [
            "TIER_B_QUALIFICATION_IDENTITY_EXACT",
            "TASK_SNAPSHOT_AND_VERIFIER_IDENTITIES_EXACT",
            "OPERATOR_ENDPOINT_BINDING_RECONCILED",
            "OBSERVED_PROVIDER_MODEL_IDENTITY_MATCH",
            "NO_CONTROL_DRIFT",
            "NO_VERIFIER_INFRASTRUCTURE",
            "NO_HIDDEN_TEST_LEAKAGE",
            "NO_SECRET_LEAKAGE",
            "TRACE_AND_EVIDENCE_PERSISTENCE_VALID",
            "CAPABILITY_PASS_OR_FAIL_ACCEPTABLE",
        ],
        "evidence_projection": {
            "repository_snapshot_identity": "plan.tasks[].workspace_input_digest",
            "changed_file_identity": (
                "manifest.parsed_patch_digest plus paths parsed from persisted direct-patch-v1 "
                "operations"
            ),
            "workspace_output_identity": "manifest.workspace_output_digest",
            "task_language": "qualification.tasks[].language",
            "engineering_shape": "qualification.tasks[].engineering_shape",
            "task_tier": "plan.benchmark_tier",
            "qualification_digest": "plan.tier_b_qualification_digest",
            "outcome_classification": "capability versus verifier/provider infrastructure",
            "latency": "manifest.provider_result.latency_ms when reported",
            "usage": "manifest.provider_result.usage when reported",
        },
        "capability_failure_policy": "TERMINAL_NO_RETRY",
        "infrastructure_failure_policy": (
            "PRESERVE_IMMUTABLE_FIRST_ATTEMPT_NO_IMMEDIATE_SEMANTIC_RETRY"
        ),
        "score_based_stop_condition": "PROHIBITED",
        "execution_status": "NOT_RUN",
        "model_scores": "NOT_AVAILABLE",
        "cost": "NOT_AVAILABLE",
        "provider_observations": "NOT_AVAILABLE",
        "historical_evidence_changed": 0,
        "real_provider_calls": 0,
    }
    return plan_payload, preregistration_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze the keyless Tier-B smoke experiment")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that both frozen artifacts exactly match the current planner output",
    )
    args = parser.parse_args()
    plan_payload, preregistration_payload = _payloads()
    expected = {
        PLAN_PATH: _json_bytes(plan_payload),
        PREREGISTRATION_PATH: _json_bytes(preregistration_payload),
    }
    if args.check:
        for path, content in expected.items():
            if not path.is_file() or path.read_bytes() != content:
                raise SystemExit(f"Tier-B smoke artifact is stale: {path.relative_to(ROOT)}")
    else:
        for path, content in expected.items():
            path.write_bytes(content)

    print("TIER_B_SMOKE_KEYLESS_PREFLIGHT=PASS_WITH_EXPECTED_ENDPOINT_BLOCK")
    print(f"TIER_B_SMOKE_EXPERIMENT_ID={plan_payload['plan']['experiment_id']}")
    print(f"TIER_B_SMOKE_PLAN_DIGEST={TIER_B_SMOKE_PLAN_DIGEST}")
    print(f"TIER_B_SMOKE_SCHEDULE_SEED={TIER_B_SMOKE_SCHEDULE_SEED}")
    print("TIER_B_SMOKE_TOTAL_SLOTS=6")
    print(f"ENDPOINT_BINDING_STATUS={ENDPOINT_BINDING_STATUS}")
    print("REAL_PROVIDER_CALLS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
