from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from harnesslab.comparability.models import canonical_digest
from harnesslab.experiment.dispatch import DispatchProfile
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.release.throughput import simulate_v6_throughput
from harnesslab.release.v6 import (
    V6_CELL_BINDINGS,
    V6_CORPUS_REFERENCE,
    V6_EXECUTION_SEED,
    V6_EXPERIMENT_ID,
    V6_JUDGE_CANDIDATES,
    V6_METHODOLOGY_REFERENCE,
    V6_SCHEDULE_SEED,
    build_v6_plan,
    v6_binding_identity,
    v6_dispatch_profiles,
)


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _fallback_profile() -> DispatchProfile:
    return DispatchProfile(
        profile_id="V6_FALLBACK_C2",
        global_concurrency=2,
        max_harness_concurrency=1,
        max_direct_concurrency=2,
        provider_concurrency={
            "gpt56-relay": 1,
            "alibaba-bailian": 1,
            "deepseek-official": 1,
        },
    )


def build_control_artifact(repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    plan = build_v6_plan(root, {})
    catalog = build_registry_catalog(root, {})
    profiles = {item.profile_id: item for item in catalog.provider_model_profiles}
    harness_profiles = {
        profile.profile_id: (harness, profile)
        for harness in catalog.harnesses
        for profile in harness.profiles
    }
    candidates = v6_dispatch_profiles()
    simulations = tuple(simulate_v6_throughput(plan, profile) for profile in candidates)
    replay = tuple(simulate_v6_throughput(plan, profile) for profile in candidates)
    if simulations != replay:
        raise RuntimeError("V6 throughput simulation is not deterministic")
    passing = [item for item in simulations if item.hard_checks_passed]
    if passing:
        selected_simulation = min(passing, key=lambda item: item.simulated_wall_time_seconds)
        selected = next(
            profile
            for profile in candidates
            if profile.profile_id == selected_simulation.profile_id
        )
    else:
        selected = _fallback_profile()
        selected_simulation = simulate_v6_throughput(plan, selected)
        if not selected_simulation.hard_checks_passed:
            raise RuntimeError("V6 fallback concurrency 2 failed a hard qualification check")
        simulations = (*simulations, selected_simulation)
    schedule_payload = [block.model_dump(mode="json") for block in plan.schedule_blocks]
    cells: list[dict[str, Any]] = []
    plan_cells = {cell.id: cell for cell in plan.cells}
    for binding in V6_CELL_BINDINGS:
        provider = profiles[binding.provider_profile_id]
        harness, harness_profile = harness_profiles[binding.harness_profile_id]
        cells.append(
            {
                "cell_id": binding.cell_id,
                "lane": "M" if harness.harness_id == "direct-model" else "H",
                "requested_model": provider.requested_model,
                "provider_id": provider.provider_id,
                "provider_profile_id": provider.profile_id,
                "provider_profile_identity": provider.profile_identity,
                "protocol": provider.protocol.value,
                "runtime_endpoint_fingerprint": provider.runtime_endpoint_fingerprint,
                "harness_id": harness.harness_id,
                "harness_profile_id": harness_profile.profile_id,
                "harness_config_identity": harness_profile.harness_config_identity,
                "execution_binding_identity": v6_binding_identity(plan_cells[binding.cell_id]),
                "reasoning_effort": harness_profile.reasoning_effort,
                "request_timeout_seconds": provider.request_timeout_seconds,
                "max_output_tokens": provider.max_output_tokens,
                "provider_availability_at_freeze": "AVAILABLE_PENDING_REAL_PREFLIGHT",
            }
        )
    judge_candidates = []
    for index, profile_id in enumerate(V6_JUDGE_CANDIDATES):
        profile = profiles[profile_id]
        judge_candidates.append(
            {
                "rank": index + 1,
                "provider_profile_id": profile.profile_id,
                "provider_profile_identity": profile.profile_identity,
                "requested_model": profile.requested_model,
                "protocol": profile.protocol.value,
                "runtime_endpoint_fingerprint": profile.runtime_endpoint_fingerprint,
                "json_contract": "OPENAI_CHAT_NORMALIZED_JSON_PARSE_CONTRACT_KEYLESS_PASS",
                "schema_adherence": "REQUIRES_SMALL_REAL_CANARY",
                "observed_model_capability": profile.observed_model_capability.value,
                "route_stability": "REFERENCE_FROZEN_ENDPOINT_FINGERPRINT_NOT_CONFIGURED",
                "cost_accounting": "EXACT_OPERATOR_RATE_INPUT_REQUIRED",
                "model_role_independence": (
                    "INDEPENDENT_FROM_ALL_SUBJECT_MODEL_FAMILIES"
                    if profile.requested_model == "glm-5.2"
                    else "INDEPENDENT_FROM_QWEN_BUT_OVERLAPS_DEEPSEEK_SUBJECT_FAMILY"
                ),
                "reproducibility": "PROFILE_IDENTITY_FROZEN_RUNTIME_CANARY_PENDING",
            }
        )
    return {
        "schema_version": 1,
        "phase": "K_B3_V6_BAILIAN_REDESIGN",
        "experiment_id": V6_EXPERIMENT_ID,
        "successor_of": "core-real-matrix-v5",
        "base_sha": "1efeaae4e6a0240380042176b245b499cf7774cc",
        "execution_seed": V6_EXECUTION_SEED,
        "schedule_seed": V6_SCHEDULE_SEED,
        "schema_plan_version": plan.schema_version,
        "scheduling_policy": plan.scheduling_policy,
        "block_key": ["task_id", "repeat_index"],
        "plan_digest": plan.digest,
        "schedule_digest": canonical_digest(schedule_payload),
        "methodology_reference": V6_METHODOLOGY_REFERENCE,
        "methodology_digest": plan.methodology_digest,
        "corpus_reference": V6_CORPUS_REFERENCE,
        "corpus_sha256": _sha256_file(root / V6_CORPUS_REFERENCE),
        "task_count": len(plan.tasks),
        "repeat_count": plan.repeat_count,
        "cell_count": len(plan.cells),
        "block_count": len(plan.schedule_blocks),
        "subject_slot_count": len(plan.run_slots),
        "cells": cells,
        "schedule_blocks": schedule_payload,
        "logical_slots": [
            {
                "slot_id": slot.slot_id,
                "slot_order": slot.slot_order,
                "cell_id": slot.cell_id,
                "task_id": slot.task.task_id,
                "repeat_index": slot.repeat_index,
            }
            for slot in plan.run_slots
        ],
        "controls": {
            "deterministic_verifier_authority": True,
            "capability_vs_infrastructure_taxonomy": True,
            "semantic_retry_allowed": False,
            "score_based_retry_allowed": False,
            "provider_model_substitution_allowed": False,
            "score_based_early_stop_allowed": False,
            "opencode_subject_dependency": 0,
        },
        "judge": {
            "decision": "JUDGE_REDESIGN_REQUIRES_SMALL_REAL_CANARY",
            "preferred_candidate": V6_JUDGE_CANDIDATES[0],
            "candidates": judge_candidates,
            "opencode_runtime_dependency": 0,
            "formal_judge_execution_gate": "BLOCKED_PENDING_SELECTED_CANDIDATE_CANARY",
        },
        "execution_profile_candidates": [
            {
                "profile": profile.model_dump(mode="json"),
                "profile_digest": profile.digest,
                "simulation": simulation.model_dump(mode="json"),
            }
            for profile, simulation in zip(candidates, simulations, strict=False)
        ],
        "throughput_evidence_class": {
            "scheduler": "ACTUAL_BLOCK_DISPATCH_COORDINATOR_LOGIC",
            "providers": "DETERMINISTIC_KEYLESS_DISCRETE_EVENT_MODEL",
            "resource_peaks": "MODELLED_NOT_PRODUCTION_HOST_TELEMETRY",
            "qualification_envelope": {"cpu_count": 8, "memory_gib": 16},
        },
        "selected_execution_profile": {
            "profile": selected.model_dump(mode="json"),
            "profile_digest": selected.digest,
            "selection_rule": "FASTEST_PROFILE_PASSING_ALL_HARD_CHECKS",
            "simulation": selected_simulation.model_dump(mode="json"),
            "runtime_adaptive_concurrency": False,
        },
        "block_pipelining": {
            "enabled": True,
            "rule": "NEXT_BLOCK_AFTER_ALL_SEVEN_CURRENT_BLOCK_SLOTS_ARE_DURABLY_REPRESENTED",
            "prior_block_completion_barrier": False,
        },
        "transport": {
            "shared_http_pooling": "ENABLED",
            "isolation_key": ["provider_route_identity", "credential_reference"],
            "max_connections_per_route": 2,
            "redirects": "DISABLED",
            "semantic_retries": 0,
            "transport_runtime_identity": canonical_digest(
                {
                    "implementation": "CampaignHTTPClientPool",
                    "isolation_key": ["route", "credential_reference"],
                    "max_connections_per_route": 2,
                    "follow_redirects": False,
                    "trust_env": False,
                }
            ),
        },
        "campaign_preflight_cache": {
            "decision": "SKIPPED_WITH_REASON",
            "reason": (
                "Existing backends revalidate the local Docker endpoint at each privileged "
                "boundary; introducing a process cache without plumbing an immutable campaign "
                "token through every backend could hide endpoint drift."
            ),
        },
        "verifier_staging_cache": {
            "decision": "SKIPPED_WITH_REASON",
            "reason": (
                "The current verifier lifecycle copies protected source into per-run isolation. "
                "A read-only shared mount would require a broader sandbox lifecycle redesign."
            ),
        },
        "workspace_materialization": {
            "decision": "SKIPPED_LOW_PRIORITY",
            "reason": "No copy-on-write optimization is needed to qualify the selected profile.",
        },
        "canary_preregistration": {
            "status": "PREREGISTERED_NOT_AUTHORIZED_NOT_RUN",
            "max_future_calls": 3,
            "calls": [
                "DIRECT_QWEN38_ALIBABA_ONE_CALL",
                "CLAUDE_CODE_QWEN38_ALIBABA_ONE_CALL",
                "PREFERRED_ALIBABA_GLM52_JUDGE_ONE_CALL",
            ],
            "retries": 0,
            "unchanged_gpt_deepseek_codex_revalidation": False,
            "matrix_acquisition_allowed": False,
        },
        "pricing": {
            "spend_authorized": False,
            "v5_authorization_reusable": False,
            "status": "PUBLIC_BASE_RATES_VERIFIED_OPERATOR_BILLING_INPUTS_REQUIRED",
            "authoritative_public_source": (
                "https://help.aliyun.com/zh/model-studio/model-pricing"
            ),
            "retrieved_at": "2026-08-31",
            "public_rate_evidence": {
                "currency": "CNY",
                "unit": "per_1_million_tokens",
                "region": "China (Beijing)",
                "qwen3.8-max": {
                    "input": "12",
                    "output": "36",
                    "token_tier": "0<Token<=1M",
                },
                "glm-5.2": {
                    "input": "8",
                    "output": "28",
                    "token_tier": "flat-rate",
                },
            },
            "public_rate_fact_digest": canonical_digest(
                {
                    "source": "Aliyun China Model Studio model pricing",
                    "retrieved_at": "2026-08-31",
                    "currency": "CNY",
                    "region": "China (Beijing)",
                    "qwen3.8-max": ["12", "36", "0<Token<=1M"],
                    "glm-5.2": ["8", "28", "flat-rate"],
                }
            ),
            "required_inputs": [
                "billing_region_and_currency",
                "exact_deployed_model_id_for_qwen3.8-max",
                "cache_or_batch_adjustments_if_any",
                "account_specific_promotions_if_any",
                "tax_and_fx_treatment",
                "operator_confirmation_that_public_region_and_model_rates_apply",
            ],
        },
        "unresolved_operator_inputs": [
            "Alibaba OpenAI-compatible endpoint fingerprint",
            "Alibaba Anthropic-compatible endpoint fingerprint from the same workspace",
            "Alibaba credential presence",
            "exact deployed Alibaba model IDs",
            "operator confirmation that the public China (Beijing) rates apply to the account",
            "production host telemetry confirmation before canary dispatch",
            "new V6 spend authorization",
            "three-call V6 canary authorization",
        ],
        "execution_state": {
            "keyless_provider_calls": 0,
            "real_harness_calls": 0,
            "real_judge_calls": 0,
            "real_v6_execution_started": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("release/core-real-matrix-v6-control.json"),
    )
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    if output.exists():
        raise FileExistsError(f"append-only V6 control artifact already exists: {output}")
    artifact = build_control_artifact(root)
    output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"FROZEN={output}")
    print(f"DIGEST={_sha256_file(output)}")


if __name__ == "__main__":
    main()
