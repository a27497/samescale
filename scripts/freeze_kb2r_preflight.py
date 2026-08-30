from __future__ import annotations

import json
from pathlib import Path

from harnesslab.budget import (
    CallResourceCeiling,
    JudgeCampaignBudget,
    MatrixBudgetEstimateRequest,
    MatrixCellBudget,
    PricingAvailability,
    ProviderPricing,
)
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane, NetworkPolicy
from harnesslab.preflight import (
    ConfigurationKind,
    ConfigurationRequirement,
    FrozenResourceEnvelope,
    HarnessRequirement,
    MatrixCellRequirement,
    MatrixPreflightSpecification,
    ObservedModelExposure,
    PreflightAuthorizationLevel,
    PreflightSpecification,
    ProviderRouteRequirement,
    TaskRequirement,
    TraceSupport,
)
from harnesslab.release.models import CoreCorpusManifest

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"

RELAY = "gpt56-relay|responses|env:HARNESSLAB_GPT56_RELAY_BASE_URL/responses"
OPENCODE_MESSAGES = "opencode-go|messages|https://opencode.ai/zen/go/v1/messages"
DEEPSEEK = "deepseek-official|chat_completions|https://api.deepseek.com/chat/completions"
JUDGE = "opencode-go|chat_completions|https://opencode.ai/zen/go/v1/chat/completions"


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _unknown(route: str) -> ProviderPricing:
    return ProviderPricing(route_identity=route, availability=PricingAvailability.UNKNOWN)


def _envelope(
    *,
    cell_id: str,
    route: str,
    runtime: str,
    ceiling: CallResourceCeiling,
    timeout_seconds: int,
) -> FrozenResourceEnvelope:
    identity = canonical_digest(
        {
            "cell_id": cell_id,
            "route": route,
            "runtime": runtime,
            "ceiling": ceiling.model_dump(mode="json"),
            "timeout_seconds": timeout_seconds,
            "network_policy": "ALLOWLIST",
            "task_version": "1.0.2",
        }
    )
    return FrozenResourceEnvelope(expected_identity=identity, actual_identity=identity)


def _build(level: PreflightAuthorizationLevel) -> MatrixPreflightSpecification:
    corpus = CoreCorpusManifest.model_validate_json(
        (RELEASE / "core-corpus-v4.json").read_text(encoding="utf-8")
    )
    direct = CallResourceCeiling(
        input_tokens=32_768,
        output_tokens=2_000,
        provider_requests=1,
        harness_turns=0,
    )
    harness = CallResourceCeiling(
        input_tokens=32_768,
        output_tokens=2_000,
        provider_requests=16,
        harness_turns=16,
    )
    judge_ceiling = CallResourceCeiling(
        input_tokens=8_192,
        output_tokens=256,
        provider_requests=1,
        harness_turns=0,
    )
    cell_data = (
        (
            "model-gpt56-relay-responses",
            ("M", "P"),
            RELAY,
            "gpt-5.6-sol",
            "direct-model",
            "direct-gpt56-relay-gpt56-responses",
            None,
            TraceSupport.FINAL_OUTPUT_ONLY,
            ObservedModelExposure.RUN_EVIDENCE_ONLY,
            True,
            direct,
        ),
        (
            "model-qwen38-opencode-go-messages",
            ("M",),
            OPENCODE_MESSAGES,
            "qwen3.8-max",
            "direct-model",
            "direct-opencode-go-qwen38-messages",
            None,
            TraceSupport.FINAL_OUTPUT_ONLY,
            ObservedModelExposure.RUN_EVIDENCE_ONLY,
            True,
            direct,
        ),
        (
            "model-deepseek-v4pro-chat",
            ("M",),
            DEEPSEEK,
            "deepseek-v4-pro",
            "direct-model",
            "direct-deepseek-official-v4pro-chat",
            None,
            TraceSupport.FINAL_OUTPUT_ONLY,
            ObservedModelExposure.RUN_EVIDENCE_ONLY,
            True,
            direct,
        ),
        (
            "harness-codex-gpt56-medium",
            ("H", "P"),
            RELAY,
            "gpt-5.6-sol",
            "codex",
            "codex-gpt56-medium",
            "harnesslab-phase-e-codex:0.149.0",
            TraceSupport.FULL_STREAM,
            ObservedModelExposure.RUN_EVIDENCE_ONLY,
            True,
            harness,
        ),
        (
            "harness-codex-gpt56-high",
            ("H",),
            RELAY,
            "gpt-5.6-sol",
            "codex",
            "codex-gpt56-high",
            "harnesslab-phase-e-codex:0.149.0",
            TraceSupport.FULL_STREAM,
            ObservedModelExposure.RUN_EVIDENCE_ONLY,
            True,
            harness,
        ),
        (
            "harness-claude-qwen38-opencode-go",
            ("H",),
            OPENCODE_MESSAGES,
            "qwen3.8-max",
            "claude-code",
            "claude-qwen38-opencode-go",
            "harnesslab-phase-f-claude:2.1.241",
            TraceSupport.FULL_STREAM,
            ObservedModelExposure.RUN_EVIDENCE_ONLY,
            True,
            harness,
        ),
        (
            "harness-deepseek-v4flash",
            ("H",),
            DEEPSEEK,
            "deepseek-v4-flash",
            "deepseek-e1",
            "deepseek-harness-v4flash",
            "harnesslab-phase-f-deepseek:0.1.1-rc.2",
            TraceSupport.FINAL_OUTPUT_ONLY,
            ObservedModelExposure.NOT_AVAILABLE,
            False,
            harness,
        ),
    )
    cells = tuple(
        MatrixCellRequirement(
            cell_id=cell_id,
            roles=roles,
            route_identity=route,
            requested_model=model,
            harness_id=harness_id,
            runtime_profile_identity=runtime_profile,
            image_reference=image,
            trace_support=trace,
            required_trace_support=trace,
            observed_model_exposure=observed,
            observed_model_required=observed_required,
            resource_envelope=_envelope(
                cell_id=cell_id,
                route=route,
                runtime=runtime_profile,
                ceiling=ceiling,
                timeout_seconds=180,
            ),
        )
        for (
            cell_id,
            roles,
            route,
            model,
            harness_id,
            runtime_profile,
            image,
            trace,
            observed,
            observed_required,
            ceiling,
        ) in cell_data
    )
    run_count = 1 if level is PreflightAuthorizationLevel.CANARY_PREFLIGHT else 90
    judge_calls = 1 if level is PreflightAuthorizationLevel.CANARY_PREFLIGHT else 63
    budgets = tuple(
        MatrixCellBudget(
            cell_id=cell_id,
            planned_run_count=run_count,
            route_identity=route,
            resource_ceiling=ceiling,
            pricing=_unknown(route),
        )
        for cell_id, _, route, _, _, _, _, _, _, _, ceiling in cell_data
    )
    prerequisites = PreflightSpecification(
        docker_required=True,
        database_required=True,
        minimum_free_bytes=1_073_741_824,
        required_images=(
            "harnesslab-phase-e-codex:0.149.0",
            "harnesslab-phase-f-claude:2.1.241",
            "harnesslab-phase-f-deepseek:0.1.1-rc.2",
            "harnesslab-egress-proxy:1.0.0",
        ),
        configurations=(
            ConfigurationRequirement(reference="DATABASE_URL", kind=ConfigurationKind.NON_EMPTY),
            ConfigurationRequirement(
                reference="HARNESSLAB_GPT56_RELAY_BASE_URL",
                kind=ConfigurationKind.HTTPS_URL,
            ),
            ConfigurationRequirement(
                reference="HARNESSLAB_GPT56_RELAY_API_KEY",
                kind=ConfigurationKind.CREDENTIAL,
            ),
            ConfigurationRequirement(
                reference="HARNESSLAB_OPENCODE_GO_API_KEY",
                kind=ConfigurationKind.CREDENTIAL,
            ),
            ConfigurationRequirement(
                reference="DEEPSEEK_API_KEY",
                kind=ConfigurationKind.CREDENTIAL,
            ),
        ),
        provider_routes=tuple(
            ProviderRouteRequirement(route_identity=route, expected_identity=route)
            for route in (RELAY, OPENCODE_MESSAGES, DEEPSEEK, JUDGE)
        ),
        harnesses=(
            HarnessRequirement(
                harness_id="direct-model",
                requested_model="registry-bound-per-cell",
                supported_lanes=frozenset({EvaluationLane.MODEL}),
                selected_lane=EvaluationLane.MODEL,
                trace_support=TraceSupport.FINAL_OUTPUT_ONLY,
                required_trace_support=TraceSupport.FINAL_OUTPUT_ONLY,
            ),
            HarnessRequirement(
                harness_id="codex",
                requested_model="gpt-5.6-sol",
                compatible_models=frozenset({"gpt-5.6-sol"}),
                supported_lanes=frozenset({EvaluationLane.HARNESS}),
                selected_lane=EvaluationLane.HARNESS,
                trace_support=TraceSupport.FULL_STREAM,
                required_trace_support=TraceSupport.FULL_STREAM,
            ),
            HarnessRequirement(
                harness_id="claude-code",
                requested_model="qwen3.8-max",
                compatible_models=frozenset({"qwen3.8-max"}),
                supported_lanes=frozenset({EvaluationLane.HARNESS}),
                selected_lane=EvaluationLane.HARNESS,
                trace_support=TraceSupport.FULL_STREAM,
                required_trace_support=TraceSupport.FULL_STREAM,
            ),
            HarnessRequirement(
                harness_id="deepseek-e1",
                requested_model="deepseek-v4-flash",
                compatible_models=frozenset({"deepseek-v4-flash"}),
                supported_lanes=frozenset({EvaluationLane.HARNESS}),
                selected_lane=EvaluationLane.HARNESS,
                trace_support=TraceSupport.FINAL_OUTPUT_ONLY,
                required_trace_support=TraceSupport.FINAL_OUTPUT_ONLY,
            ),
        ),
        tasks=tuple(
            TaskRequirement(package_path=task.package_path, selected_lane=EvaluationLane.HARNESS)
            for task in corpus.tasks
        ),
        network_policy=NetworkPolicy.ALLOWLIST,
    )
    return MatrixPreflightSpecification(
        authorization_level=level,
        prerequisites=prerequisites,
        cells=cells,
        matrix_budget=MatrixBudgetEstimateRequest(
            subject_cells=budgets,
            judge_campaign=JudgeCampaignBudget(
                profile_id="judge-glm52-opencode-go-chat",
                planned_call_count=judge_calls,
                route_identity=JUDGE,
                resource_ceiling=judge_ceiling,
                pricing=_unknown(JUDGE),
            ),
        ),
        fixed_subject_call_count=7 * run_count,
        fixed_judge_call_count=judge_calls,
        spend_authorized=level is PreflightAuthorizationLevel.CANARY_PREFLIGHT,
    )


def main() -> None:
    canary = _build(PreflightAuthorizationLevel.CANARY_PREFLIGHT)
    full = _build(PreflightAuthorizationLevel.FULL_MATRIX_PREFLIGHT)
    _write(RELEASE / "kb2r-canary-preflight.json", canary.model_dump(mode="json"))
    _write(RELEASE / "kb2r-full-matrix-preflight.json", full.model_dump(mode="json"))
    print(f"CANARY_PREFLIGHT_DIGEST={canary.digest}")
    print(f"FULL_MATRIX_PREFLIGHT_DIGEST={full.digest}")


if __name__ == "__main__":
    main()
