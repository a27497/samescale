from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.contracts.common import Identifier, Sha256Digest


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
    selection_state: Literal[EvidenceState.NOT_VERIFIED] = EvidenceState.NOT_VERIFIED
    limitation: str

    @model_validator(mode="after")
    def unresolved_selection_has_no_fake_model(self) -> ModelProfileSlot:
        if self.requested_model is not None:
            raise ValueError("K-A Model-only slots cannot invent a final requested model")
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
    evidence_state: Literal[EvidenceState.NOT_VERIFIED] = EvidenceState.NOT_VERIFIED


class PairedLanePlan(StrictModel):
    pair_id: Identifier
    left_cell_id: Identifier
    right_cell_id: Identifier
    intent: Literal["HARNESS_UPLIFT"] = "HARNESS_UPLIFT"
    required_frozen_controls: tuple[str, ...]
    expected_paired_observations: Literal[90] = 90
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
    evidence_state: Literal[EvidenceState.NOT_RUN] = EvidenceState.NOT_RUN


class JudgeEvidencePlan(StrictModel):
    suite_reference: str
    suite_id: str
    suite_version: str
    suite_digest: Sha256Digest
    judge_profile_selection: Literal[EvidenceState.NOT_VERIFIED] = EvidenceState.NOT_VERIFIED
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
    internal_harness_provider_request_count: Literal["NOT_CALCULATED_FROM_REPOSITORY_EVIDENCE"] = (
        "NOT_CALCULATED_FROM_REPOSITORY_EVIDENCE"
    )
    monetary_cost: Literal["NOT_CALCULATED_FROM_REPOSITORY_EVIDENCE"] = (
        "NOT_CALCULATED_FROM_REPOSITORY_EVIDENCE"
    )


class RealEvidencePlan(CanonicalModel):
    schema_version: Literal[1] = 1
    plan_id: Literal["core-real-evidence-v1"] = "core-real-evidence-v1"
    corpus_reference: str
    corpus_digest: Sha256Digest
    experiment_id: Literal["core-real-matrix-v1"] = "core-real-matrix-v1"
    execution_seed: int
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
        if len(self.model_profile_slots) != 3:
            raise ValueError("release plan requires exactly three Model-only slots")
        if len(self.cells) != 7:
            raise ValueError("release plan requires seven planned cells")
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
        return self


class EvidenceBinding(StrictModel):
    state: EvidenceState
    identity: str | None = None
    digest: Sha256Digest | None = None
    limitation: str | None = None

    @model_validator(mode="after")
    def state_matches_evidence(self) -> EvidenceBinding:
        if self.state is EvidenceState.VERIFIED and (not self.identity or not self.digest):
            raise ValueError("VERIFIED evidence requires identity and digest")
        if self.state in {EvidenceState.NOT_RUN, EvidenceState.DEFERRED_NOT_VERIFIED} and (
            self.identity is not None or self.digest is not None
        ):
            raise ValueError(f"{self.state.value} evidence cannot carry result identity or digest")
        return self


class ReleaseEvidenceManifest(CanonicalModel):
    schema_version: Literal[1] = 1
    release_id: Literal["v1.0.0-core"] = "v1.0.0-core"
    core_corpus: EvidenceBinding
    release_commit: EvidenceBinding
    experiment_plan: EvidenceBinding
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
