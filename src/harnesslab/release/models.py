from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.contracts.provider import ConfigurationState, ProviderProfile


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CanonicalModel(StrictModel):
    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode()).hexdigest()


class EvidenceState(StrEnum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    NOT_RUN = "NOT_RUN"
    DEFERRED_NOT_VERIFIED = "DEFERRED_NOT_VERIFIED"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"


class PairedClaimPolicy(StrEnum):
    NOT_SELECTED = "NOT_SELECTED"
    HARNESS_UPLIFT_CLAIM = "HARNESS_UPLIFT_CLAIM"
    NO_HARNESS_UPLIFT_CLAIM = "NO_HARNESS_UPLIFT_CLAIM"


class ValidationResult(StrictModel):
    passed: bool
    score: float = Field(ge=0, le=1)


class CoreTaskInventoryEntry(StrictModel):
    package_path: str
    task_id: Identifier
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    language: Literal["python", "java", "typescript"]
    domain: str
    category: str
    scenario_family: Identifier
    benchmark_role: Literal["CROSS_LANGUAGE_CONTROL", "INDEPENDENT"]
    difficulty_band: Literal["foundation", "intermediate", "advanced"]
    task_digest: Sha256Digest
    verifier_identity: Sha256Digest
    workspace_input_identity: Sha256Digest
    lane_support: tuple[Literal["M", "H", "P"], ...]
    expected_toolchain: tuple[str, ...]
    baseline: ValidationResult
    oracle: ValidationResult

    @model_validator(mode="after")
    def validation_polarity_is_core(self) -> CoreTaskInventoryEntry:
        if self.baseline.passed:
            raise ValueError("Core task baseline must fail")
        if not self.oracle.passed or self.oracle.score != 1.0:
            raise ValueError("Core task oracle must pass with score 1")
        if "M" not in self.lane_support or "H" not in self.lane_support:
            raise ValueError("Core release tasks must support M and H lanes")
        return self


class CoreCorpusManifest(CanonicalModel):
    schema_version: Literal[1] = 1
    corpus_id: Literal["harnesslab-core-18-v1"] = "harnesslab-core-18-v1"
    tasks: tuple[CoreTaskInventoryEntry, ...]

    @model_validator(mode="after")
    def corpus_is_balanced_and_unique(self) -> CoreCorpusManifest:
        if len(self.tasks) != 18 or not 15 <= len(self.tasks) <= 25:
            raise ValueError("Core corpus must contain exactly 18 tasks within the 15-25 range")
        identities = {(task.task_id, task.version) for task in self.tasks}
        if len(identities) != len(self.tasks):
            raise ValueError("Core corpus contains duplicate task identities")
        if tuple(sorted(self.tasks, key=lambda task: (task.task_id, task.version))) != self.tasks:
            raise ValueError("Core corpus tasks must use deterministic identity order")
        languages = {language: 0 for language in ("python", "java", "typescript")}
        for task in self.tasks:
            languages[task.language] += 1
        if languages != {"python": 6, "java": 6, "typescript": 6}:
            raise ValueError("Core corpus must contain six tasks per language")
        if len({task.category for task in self.tasks}) < 5:
            raise ValueError("Core corpus category diversity is insufficient")
        controls = tuple(
            task for task in self.tasks if task.benchmark_role == "CROSS_LANGUAGE_CONTROL"
        )
        independent = tuple(task for task in self.tasks if task.benchmark_role == "INDEPENDENT")
        control_families = {task.scenario_family for task in controls}
        if len(controls) != 3 or len(control_families) != 1:
            raise ValueError("Core corpus requires exactly one three-language control family")
        if {task.language for task in controls} != {"python", "java", "typescript"}:
            raise ValueError("Core control family must span all three languages")
        independent_families = {task.scenario_family for task in independent}
        if len(independent) != 15 or len(independent_families) != 15:
            raise ValueError("Every independent task requires a unique scenario family")
        if control_families & independent_families:
            raise ValueError("Control and independent scenario families must be disjoint")
        if len(control_families | independent_families) < 16:
            raise ValueError("Core corpus requires at least sixteen semantic scenario families")
        if len({task.difficulty_band for task in self.tasks}) < 2:
            raise ValueError("Core corpus requires multiple difficulty bands")
        return self


class ModelProfileSlot(StrictModel):
    slot_id: Identifier
    release_name: str
    protocol: Literal["responses", "messages", "chat_completions"]
    provider: str | None
    base_url: str | None
    route: str
    requested_model: str | None
    reasoning_effort: str | None
    max_output_tokens: int = Field(gt=0)
    request_timeout_seconds: int = Field(gt=0, le=600)
    credential_reference: str | None
    selection_state: Literal[ConfigurationState.CONFIGURED_NOT_SMOKED] = (
        ConfigurationState.CONFIGURED_NOT_SMOKED
    )
    limitation: str

    @model_validator(mode="after")
    def selected_model_is_complete(self) -> ModelProfileSlot:
        if any(
            value is None
            for value in (
                self.provider,
                self.base_url,
                self.requested_model,
                self.credential_reference,
            )
        ):
            raise ValueError("K-B0 Model-only profile selection must be complete")
        return self


class ReleaseCellPlan(StrictModel):
    cell_id: Identifier
    lane: Literal["M", "H"]
    runtime: Literal["direct-model", "codex", "claude-code", "deepseek-e1"]
    profile_slot: str | None = None
    requested_model: str | None = None
    provider_route: str | None = None
    reasoning_effort: str | None = None
    repeat_count: Literal[5] = 5
    task_count: Literal[18] = 18
    planned_runs: Literal[90] = 90
    configuration_state: Literal[ConfigurationState.CONFIGURED_NOT_SMOKED] = (
        ConfigurationState.CONFIGURED_NOT_SMOKED
    )
    evidence_state: Literal[EvidenceState.NOT_VERIFIED] = EvidenceState.NOT_VERIFIED


class PairedLanePlan(StrictModel):
    pair_id: Identifier
    left_cell_id: Identifier
    right_cell_id: Identifier
    intent: Literal["HARNESS_UPLIFT"] = "HARNESS_UPLIFT"
    required_frozen_controls: tuple[str, ...]
    expected_paired_observations: Literal[90] = 90
    configuration_state: Literal["CONFIGURED_NOT_VERIFIED"] = "CONFIGURED_NOT_VERIFIED"
    comparability_state: Literal[EvidenceState.NOT_VERIFIED] = EvidenceState.NOT_VERIFIED
    blocker: str


class ControlledAblationPlan(StrictModel):
    ablation_id: Identifier
    base_cell_id: Identifier
    variant_cell_id: Identifier
    changed_dimension: Literal["reasoning_effort"] = "reasoning_effort"
    base_value: str
    variant_value: str
    frozen_hard_controls: tuple[str, ...]
    expected_paired_observations: Literal[90] = 90
    evidence_tier_expectation: Literal["FORMAL_PER_TASK_N5"] = "FORMAL_PER_TASK_N5"
    configuration_state: Literal["CONFIGURED_NOT_RUN"] = "CONFIGURED_NOT_RUN"
    evidence_state: Literal[EvidenceState.NOT_RUN] = EvidenceState.NOT_RUN


class JudgeEvidencePlan(StrictModel):
    suite_reference: str
    suite_id: str
    suite_version: str
    suite_digest: Sha256Digest
    profile_id: Identifier
    judge_profile_selection: Literal[ConfigurationState.CONFIGURED_NOT_SMOKED] = (
        ConfigurationState.CONFIGURED_NOT_SMOKED
    )
    judge_cell_count: Literal[1] = 1
    repeat_count: Literal[3] = 3
    public_case_count: Literal[15] = 15
    planned_calls: Literal[63] = 63
    max_output_tokens_per_call: Literal[256] = 256
    planned_output_token_ceiling: Literal[16128] = 16128


class CallPreflight(StrictModel):
    task_count: Literal[18] = 18
    cell_count: Literal[7] = 7
    repeat_count: Literal[5] = 5
    total_subject_runs: Literal[630] = 630
    direct_model_runs: Literal[270] = 270
    codex_runs: Literal[180] = 180
    claude_runs: Literal[90] = 90
    deepseek_runs: Literal[90] = 90
    judge_calls: Literal[63] = 63
    total_top_level_external_calls: Literal[693] = 693
    ablation_paired_observations: Literal[90] = 90
    subject_output_token_ceiling: Literal[1260000] = 1_260_000
    judge_output_token_ceiling: Literal[16128] = 16_128
    total_output_token_ceiling: Literal[1276128] = 1_276_128
    internal_harness_provider_request_count: Literal["NOT_CALCULATED_UNTIL_REAL_SMOKE"] = (
        "NOT_CALCULATED_UNTIL_REAL_SMOKE"
    )
    monetary_cost: Literal["NOT_CALCULATED_UNTIL_REAL_SMOKE_USAGE_AND_RELAY_PRICE"] = (
        "NOT_CALCULATED_UNTIL_REAL_SMOKE_USAGE_AND_RELAY_PRICE"
    )


class RealEvidencePlan(CanonicalModel):
    schema_version: Literal[3] = 3
    plan_id: Literal["core-real-evidence-v2", "core-real-evidence-v3"] = "core-real-evidence-v2"
    supersedes_plan_id: Literal["core-real-evidence-v1", "core-real-evidence-v2"] = (
        "core-real-evidence-v1"
    )
    history_reference: Literal["release/history/core-real-v1.json"]
    history_digest: Sha256Digest
    official_route_snapshot_reference: Literal["release/opencode-go-route-snapshot.json"]
    official_route_snapshot_digest: Sha256Digest
    corpus_reference: str
    corpus_digest: Sha256Digest
    experiment_id: Literal["core-real-matrix-v2", "core-real-matrix-v3"] = "core-real-matrix-v2"
    execution_seed: int
    selected_profiles: tuple[ProviderProfile, ...]
    model_profile_slots: tuple[ModelProfileSlot, ...]
    cells: tuple[ReleaseCellPlan, ...]
    paired_lane: PairedLanePlan
    ablation: ControlledAblationPlan
    judge: JudgeEvidencePlan
    preflight: CallPreflight
    credential_references: tuple[str, ...]
    unresolved_authorization_items: tuple[str, ...]
    deepseek_e2: Literal[EvidenceState.DEFERRED_NOT_VERIFIED] = EvidenceState.DEFERRED_NOT_VERIFIED
    real_evidence_authorization_required: Literal[True] = True

    @model_validator(mode="after")
    def release_plan_is_complete_but_unexecuted(self) -> RealEvidencePlan:
        expected_version_binding = {
            "core-real-evidence-v2": ("core-real-evidence-v1", "core-real-matrix-v2", 90),
            "core-real-evidence-v3": ("core-real-evidence-v2", "core-real-matrix-v3", 180),
        }
        supersedes, experiment_id, subject_timeout = expected_version_binding[self.plan_id]
        if self.supersedes_plan_id != supersedes or self.experiment_id != experiment_id:
            raise ValueError("Core real plan version binding drifted")
        if len(self.selected_profiles) != 8:
            raise ValueError("Core v2 release plan requires exactly eight configured profiles")
        profile_ids = {profile.profile_id for profile in self.selected_profiles}
        expected_profile_models = {
            "model-gpt56-relay-responses": "gpt-5.6-sol",
            "model-qwen38-opencode-go-messages": "qwen3.8-max",
            "model-deepseek-v4pro-chat": "deepseek-v4-pro",
            "harness-codex-gpt56-medium": "gpt-5.6-sol",
            "harness-codex-gpt56-high": "gpt-5.6-sol",
            "harness-claude-qwen38-opencode-go": "qwen3.8-max",
            "harness-deepseek-v4flash": "deepseek-v4-flash",
            "judge-glm52-opencode-go-chat": "glm-5.2",
        }
        if profile_ids != set(expected_profile_models):
            raise ValueError("Core v2 configured profile identity set drifted")
        profiles = {profile.profile_id: profile for profile in self.selected_profiles}
        if any(
            profile.requested_model != expected_profile_models[profile_id]
            for profile_id, profile in profiles.items()
        ):
            raise ValueError("Core v2 selected requested model drifted")
        if any(
            profile.timeout_seconds
            != (90 if profile_id == "judge-glm52-opencode-go-chat" else subject_timeout)
            for profile_id, profile in profiles.items()
        ):
            raise ValueError("Core real selected profile timeout budget drifted")
        if any(
            slot.request_timeout_seconds != subject_timeout for slot in self.model_profile_slots
        ):
            raise ValueError("Core real Model-only slot timeout budget drifted")
        expected_provenance = {
            "model-gpt56-relay-responses": "TRUSTED_THIRD_PARTY_RELAY",
            "model-qwen38-opencode-go-messages": "THIRD_PARTY_INFERENCE_PLATFORM",
            "model-deepseek-v4pro-chat": "FIRST_PARTY_MODEL_API",
            "harness-codex-gpt56-medium": "TRUSTED_THIRD_PARTY_RELAY",
            "harness-codex-gpt56-high": "TRUSTED_THIRD_PARTY_RELAY",
            "harness-claude-qwen38-opencode-go": "THIRD_PARTY_INFERENCE_PLATFORM",
            "harness-deepseek-v4flash": "FIRST_PARTY_MODEL_API",
            "judge-glm52-opencode-go-chat": "THIRD_PARTY_INFERENCE_PLATFORM",
        }
        if any(
            profile.provider_provenance.value != expected_provenance[profile_id]
            for profile_id, profile in profiles.items()
        ):
            raise ValueError("Core v2 selected provider provenance drifted")
        opencode_profiles = {
            profile_id: profiles[profile_id]
            for profile_id in (
                "model-qwen38-opencode-go-messages",
                "harness-claude-qwen38-opencode-go",
                "judge-glm52-opencode-go-chat",
            )
        }
        if any(
            (
                profile.provider_id,
                profile.provider_display_name,
                profile.fixed_base_url,
                profile.base_url_reference,
                profile.credential_reference,
                profile.inference_provider,
            )
            != (
                "opencode-go",
                "OpenCode Go",
                "https://opencode.ai/zen/go",
                None,
                "HARNESSLAB_OPENCODE_GO_API_KEY",
                "OpenCode Go",
            )
            for profile in opencode_profiles.values()
        ):
            raise ValueError("OpenCode Go fixed provider identity drifted")
        qwen_direct = opencode_profiles["model-qwen38-opencode-go-messages"]
        qwen_claude = opencode_profiles["harness-claude-qwen38-opencode-go"]
        judge = opencode_profiles["judge-glm52-opencode-go-chat"]
        if (
            qwen_direct.protocol.value != "messages"
            or qwen_direct.route != "/v1/messages"
            or qwen_direct.route_identity != qwen_claude.route_identity
            or judge.protocol.value != "chat_completions"
            or judge.route != "/v1/chat/completions"
            or judge.thinking_mode is not None
            or judge.thinking_transport is not None
        ):
            raise ValueError("OpenCode Go model route contract drifted")
        if len(self.model_profile_slots) != 3:
            raise ValueError("release plan requires exactly three Model-only slots")
        if len(self.cells) != 7:
            raise ValueError("release plan requires seven planned cells")
        if {cell.cell_id for cell in self.cells} != set(expected_profile_models) - {
            "judge-glm52-opencode-go-chat"
        }:
            raise ValueError("Core v2 release cell identity set drifted")
        if {cell.runtime for cell in self.cells} != {
            "direct-model",
            "codex",
            "claude-code",
            "deepseek-e1",
        }:
            raise ValueError("release plan omits a required runtime")
        if sum(int(cell.planned_runs) for cell in self.cells) != self.preflight.total_subject_runs:
            raise ValueError("release cell expansion disagrees with call preflight")
        cell_ids = {cell.cell_id for cell in self.cells}
        referenced = {
            self.paired_lane.left_cell_id,
            self.paired_lane.right_cell_id,
            self.ablation.base_cell_id,
            self.ablation.variant_cell_id,
        }
        if not referenced <= cell_ids:
            raise ValueError("pair or ablation references an unknown release cell")
        if self.paired_lane.pair_id != "gpt56-relay-direct-vs-codex":
            raise ValueError("Core Pair identity drifted")
        if self.ablation.ablation_id != "codex-gpt56-reasoning-effort":
            raise ValueError("Core ablation identity drifted")
        referenced_profiles = {cell.profile_slot for cell in self.cells} | {self.judge.profile_id}
        if None in referenced_profiles or referenced_profiles != profile_ids:
            raise ValueError("release cells and Judge must reference every configured profile once")
        direct = profiles["model-gpt56-relay-responses"]
        codex_medium = profiles["harness-codex-gpt56-medium"]
        if direct.route_identity != codex_medium.route_identity:
            raise ValueError("Direct and Codex-medium GPT relay routes must be identical")
        if self.credential_references != (
            "HARNESSLAB_GPT56_RELAY_BASE_URL",
            "HARNESSLAB_GPT56_RELAY_API_KEY",
            "HARNESSLAB_OPENCODE_GO_API_KEY",
            "DEEPSEEK_API_KEY",
        ):
            raise ValueError("Core v2 configuration reference set drifted")
        return self


class RealSmokeCall(StrictModel):
    call_id: Identifier
    lane: Literal["M", "H", "J"]
    task_id: Identifier | None = None
    task_digest: Sha256Digest | None = None
    judge_case_reference: str | None = None
    profile_id: Identifier
    requested_model: str
    provider_route: str
    max_output_tokens: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0, le=600)
    top_level_launches: Literal[1] = 1
    credential_references: tuple[str, ...]
    expected_evidence: tuple[str, ...]

    @model_validator(mode="after")
    def target_is_exact(self) -> RealSmokeCall:
        if self.lane in {"M", "H"} and (self.task_id is None or self.task_digest is None):
            raise ValueError("subject smoke requires an exact task identity")
        if self.lane == "J" and self.judge_case_reference is None:
            raise ValueError("Judge smoke requires an exact calibration case")
        return self


class RealSmokePlan(CanonicalModel):
    schema_version: Literal[2, 3] = 2
    plan_id: Literal["core-real-smoke-v2", "core-real-smoke-v3"] = "core-real-smoke-v2"
    release_plan_reference: Literal[
        "release/core-real-evidence-plan.json",
        "release/core-real-evidence-plan-v3.json",
    ]
    release_plan_digest: Sha256Digest
    calls: tuple[RealSmokeCall, ...]
    max_top_level_launch_count: Literal[8] = 8
    max_output_token_ceiling: Literal[14256] = 14_256
    abort_conditions: tuple[str, ...]
    execution_state: Literal[EvidenceState.NOT_RUN] = EvidenceState.NOT_RUN
    real_evaluation_call_count: Literal[0] = 0
    authorization_required: Literal[True] = True

    @model_validator(mode="after")
    def bounded_smoke_is_exact(self) -> RealSmokePlan:
        expected = {
            "core-real-smoke-v2": (2, "release/core-real-evidence-plan.json", 90),
            "core-real-smoke-v3": (3, "release/core-real-evidence-plan-v3.json", 180),
        }
        schema_version, plan_reference, subject_timeout = expected[self.plan_id]
        if self.schema_version != schema_version or self.release_plan_reference != plan_reference:
            raise ValueError("Core real smoke version binding drifted")
        if len(self.calls) != 8 or len({item.call_id for item in self.calls}) != 8:
            raise ValueError("Core v2 smoke plan requires exactly eight unique top-level calls")
        if sum(item.max_output_tokens for item in self.calls) != 14_256:
            raise ValueError("Core v2 smoke output-token ceiling drifted")
        if {item.lane for item in self.calls} != {"M", "H", "J"}:
            raise ValueError("Core v2 smoke omits a required lane")
        if any(
            call.timeout_seconds != (90 if call.lane == "J" else subject_timeout)
            for call in self.calls
        ):
            raise ValueError("Core real smoke timeout budget drifted")
        required_abort_conditions = {
            "auth error",
            "route mismatch",
            "schema mismatch",
            "observed model conflict",
            "model alias unexpectedly resolves elsewhere",
            "secret appears in artifact or trace",
            "proxy bypass",
            "unrestricted network detected",
            "verifier receives network",
            "provider-route identity mismatch in intended P-Lane",
            "task binding mismatch",
            "artifact integrity error",
            "Codex relay provider falls back to OpenAI or ChatGPT default",
            "Claude Code leaves the fixed OpenCode Go route",
            "DeepSeek Harness uses non-official route",
            "Judge persistence or integrity failure",
        }
        if set(self.abort_conditions) != required_abort_conditions:
            raise ValueError("Core v2 abort policy must contain the exact fail-closed set")
        return self


class EvidenceBinding(StrictModel):
    state: EvidenceState
    identity: str | None = None
    digest: Sha256Digest | None = None
    limitation: str | None = None

    @model_validator(mode="after")
    def state_matches_evidence(self) -> EvidenceBinding:
        if (
            self.state is EvidenceState.VERIFIED
            and self.identity is not None
            and "DIAGNOSTIC_ONLY" in self.identity.upper()
        ):
            raise ValueError("DIAGNOSTIC_ONLY evidence is never release-promotable")
        if self.state is EvidenceState.VERIFIED and (not self.identity or not self.digest):
            raise ValueError("VERIFIED evidence requires identity and digest")
        if self.state in {EvidenceState.NOT_RUN, EvidenceState.DEFERRED_NOT_VERIFIED} and (
            self.identity is not None or self.digest is not None
        ):
            raise ValueError(f"{self.state.value} evidence cannot carry result identity or digest")
        return self


class KeylessRepairSummary(StrictModel):
    repair_id: Identifier
    after_attempt_id: str = Field(pattern=r"^core-real-smoke-v2-attempt-[1-9][0-9]*$")
    state: Literal["KEYLESS_VERIFIED"]
    real_calls: Literal[0] = 0


class ReleaseHistorySummary(StrictModel):
    smoke_plan_id: Literal["core-real-smoke-v2"] = "core-real-smoke-v2"
    attempt_references: tuple[str, ...]
    latest_attempt_id: str = Field(pattern=r"^core-real-smoke-v2-attempt-[1-9][0-9]*$")
    latest_attempt_status: Literal["ABORTED", "SUCCEEDED"]
    latest_failing_call_id: Identifier | None
    latest_not_run_call_ids: tuple[Identifier, ...]
    keyless_repairs: tuple[KeylessRepairSummary, ...]
    complete_smoke: Literal[EvidenceState.NOT_VERIFIED] = EvidenceState.NOT_VERIFIED
    matrix_evidence: Literal[EvidenceState.NOT_RUN] = EvidenceState.NOT_RUN
    release_verification: Literal[EvidenceState.NOT_VERIFIED] = EvidenceState.NOT_VERIFIED

    @model_validator(mode="after")
    def history_shape_is_generic_and_contiguous(self) -> ReleaseHistorySummary:
        pattern = re.compile(r"^release/history/core-real-v2-attempt-([1-9][0-9]*)\.json$")
        attempt_numbers: list[int] = []
        for reference in self.attempt_references:
            match = pattern.fullmatch(reference)
            if match is None:
                raise ValueError("release history contains an invalid v2 attempt reference")
            attempt_numbers.append(int(match.group(1)))
        if not attempt_numbers:
            raise ValueError("release history must contain at least one v2 attempt")
        if attempt_numbers != list(range(1, attempt_numbers[-1] + 1)):
            raise ValueError("release history must be contiguous beginning at v2 attempt 1")
        expected_latest = f"{self.smoke_plan_id}-attempt-{attempt_numbers[-1]}"
        if self.latest_attempt_id != expected_latest:
            raise ValueError("latest attempt id must agree with the final attempt reference")
        if len(set(self.latest_not_run_call_ids)) != len(self.latest_not_run_call_ids):
            raise ValueError("latest NOT_RUN call ids must be unique")
        if self.latest_attempt_status == "SUCCEEDED":
            if self.latest_failing_call_id is not None or self.latest_not_run_call_ids:
                raise ValueError("successful latest attempt cannot carry failure or NOT_RUN calls")
        elif self.latest_failing_call_id is None:
            raise ValueError("aborted latest attempt requires a failing call id")
        attempt_ids = {
            f"{self.smoke_plan_id}-attempt-{attempt_number}" for attempt_number in attempt_numbers
        }
        if len({repair.repair_id for repair in self.keyless_repairs}) != len(self.keyless_repairs):
            raise ValueError("keyless repair ids must be unique")
        if any(repair.after_attempt_id not in attempt_ids for repair in self.keyless_repairs):
            raise ValueError("keyless repair must reference an ingested prior attempt")
        return self


class ReleaseEvidenceManifest(CanonicalModel):
    schema_version: Literal[1] = 1
    release_id: Literal["v1.0.0-core"] = "v1.0.0-core"
    core_corpus: EvidenceBinding
    release_commit: EvidenceBinding
    experiment_plan: EvidenceBinding
    release_history: ReleaseHistorySummary
    real_matrix: EvidenceBinding
    paired_lane: EvidenceBinding
    controlled_ablation: EvidenceBinding
    judge_suite: EvidenceBinding
    judge_report: EvidenceBinding
    analyst_report: EvidenceBinding
    badcase_evidence: tuple[EvidenceBinding, EvidenceBinding, EvidenceBinding]
    resume_claim_map: EvidenceBinding
    remote_ci: EvidenceBinding
    paired_claim_policy: PairedClaimPolicy = PairedClaimPolicy.NOT_SELECTED
    real_statuses: dict[str, EvidenceState]
    core_release_ready: bool
    real_evidence_authorization_required: bool

    @model_validator(mode="after")
    def release_readiness_cannot_be_forged(self) -> ReleaseEvidenceManifest:
        required_real = {
            "REAL_PROVIDER_SMOKE",
            "REAL_CODEX_SMOKE",
            "REAL_CLAUDE_SMOKE",
            "REAL_DEEPSEEK_SMOKE",
            "REAL_MATRIX_EVIDENCE",
            "REAL_JUDGE_SMOKE",
        }
        if set(self.real_statuses) != required_real:
            raise ValueError("release evidence REAL_* status set is incomplete")
        mandatory = (
            self.core_corpus,
            self.release_commit,
            self.experiment_plan,
            self.real_matrix,
            self.paired_lane,
            self.controlled_ablation,
            self.judge_suite,
            self.judge_report,
            *self.badcase_evidence,
            self.resume_claim_map,
            self.remote_ci,
        )
        complete = all(binding.state is EvidenceState.VERIFIED for binding in mandatory) and all(
            state is EvidenceState.VERIFIED for state in self.real_statuses.values()
        )
        if self.core_release_ready != complete:
            raise ValueError("CORE_RELEASE_READY must be derived from all mandatory evidence")
        if self.core_release_ready and self.real_evidence_authorization_required:
            raise ValueError("ready release cannot still require real-evidence authorization")
        if self.core_release_ready and self.paired_claim_policy is PairedClaimPolicy.NOT_SELECTED:
            raise ValueError("ready release requires an explicit paired-claim policy")
        return self


class SemanticReleaseReceipt(StrictModel):
    semantic_verified: Literal[True] = True
    release_manifest_digest: Sha256Digest
    release_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    remote_ci_run_id: str = Field(min_length=1, max_length=100)


class ResumeClaim(StrictModel):
    claim_id: Identifier
    claim: str
    status: EvidenceState
    required_evidence_type: str
    evidence_refs: tuple[str, ...]
    source_phase: str
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def verified_claim_has_evidence(self) -> ResumeClaim:
        if self.status is EvidenceState.VERIFIED and not self.evidence_refs:
            raise ValueError("VERIFIED resume claim requires evidence references")
        if self.status is not EvidenceState.VERIFIED and self.evidence_refs:
            raise ValueError("unverified resume claim cannot imply authoritative evidence")
        return self


class ResumeClaimMap(CanonicalModel):
    schema_version: Literal[1] = 1
    claims: tuple[ResumeClaim, ...]

    @model_validator(mode="after")
    def claim_ids_are_unique(self) -> ResumeClaimMap:
        if len({claim.claim_id for claim in self.claims}) != len(self.claims):
            raise ValueError("duplicate resume claim id")
        return self


class BadCaseSlot(StrictModel):
    slot_id: Identifier
    status: Literal[EvidenceState.NOT_VERIFIED, EvidenceState.VERIFIED]
    task_identity: str | None = None
    run_identity: str | None = None
    cell_identity: str | None = None
    evidence_refs: tuple[str, ...] = ()
    observed_failure: str | None = None
    safe_trace_facts: tuple[str, ...] = ()
    verifier_result: str | None = None
    attribution_classification: str | None = None
    root_cause: str | None = None
    mitigation_lesson: str | None = None
    harnesslab_detection: str | None = None
    placeholder: str | None = None

    @model_validator(mode="after")
    def state_matches_badcase_evidence(self) -> BadCaseSlot:
        evidence_fields = (
            self.task_identity,
            self.run_identity,
            self.cell_identity,
            self.observed_failure,
            self.verifier_result,
            self.attribution_classification,
            self.mitigation_lesson,
            self.harnesslab_detection,
        )
        if self.status is EvidenceState.NOT_VERIFIED:
            if any(value is not None for value in evidence_fields) or self.evidence_refs:
                raise ValueError("pending BadCase cannot carry real evidence")
            if self.safe_trace_facts or self.root_cause is not None:
                raise ValueError("pending BadCase cannot carry attribution facts")
            if self.placeholder != "NOT_VERIFIED — REAL EVIDENCE PENDING":
                raise ValueError("pending BadCase requires the explicit K-A placeholder")
        elif (
            any(value is None for value in evidence_fields)
            or not self.evidence_refs
            or not self.safe_trace_facts
            or self.placeholder is not None
        ):
            raise ValueError("VERIFIED BadCase requires bound real evidence and no placeholder")
        return self


class BadCasePlan(CanonicalModel):
    schema_version: Literal[1] = 1
    slots: tuple[BadCaseSlot, BadCaseSlot, BadCaseSlot]


class ReleaseReadiness(StrictModel):
    core_release_ready: bool
    blockers: tuple[str, ...]
    real_evidence_authorization_required: bool
