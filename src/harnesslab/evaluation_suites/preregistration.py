from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.evaluation_suites.admission import (
    DiscriminativeAcceptanceCriteria,
    GovernanceNamespace,
    build_admission_policy,
    build_policy_provenance,
)
from harnesslab.evaluation_suites.exposure import ExposureState
from harnesslab.evaluation_suites.models import SuitePurpose, VersionedPolicyReference
from harnesslab.registry.models import RegistryCatalog
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.release.contracts import load_core_corpus
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.quality import TaskFamily, TaskIdentity
from harnesslab.tasks.splits import DevelopmentExposure, SplitRole
from harnesslab.tasks.tier_b import (
    TierBQualificationArtifact,
    load_tier_b_qualification,
    validate_tier_b_qualification,
)


class PreregistrationError(ValueError):
    """M.8-A source reality or preregistered evidence is inconsistent."""


class CandidateRole(StrEnum):
    CORE = "CORE"
    TIER_B = "TIER_B"


class CandidateEligibility(StrEnum):
    ELIGIBLE_FOR_EMPIRICAL_SCREENING = "ELIGIBLE_FOR_EMPIRICAL_SCREENING"
    CANDIDATE_REQUIRES_EVIDENCE = "CANDIDATE_REQUIRES_EVIDENCE"
    INELIGIBLE = "INELIGIBLE"


class CandidateReasonCode(StrEnum):
    TASK_INTEGRITY_QUALIFIED = "TASK_INTEGRITY_QUALIFIED"
    CORE_DEVELOPMENT_EXPOSED = "CORE_DEVELOPMENT_EXPOSED"
    TIER_B_DEVELOPMENT_EXPOSED = "TIER_B_DEVELOPMENT_EXPOSED"
    HOLDOUT_INELIGIBLE = "HOLDOUT_INELIGIBLE"
    DISCRIMINATIVE_REQUIRES_EMPIRICAL_EVIDENCE = "DISCRIMINATIVE_REQUIRES_EMPIRICAL_EVIDENCE"
    CORE_NOT_A_CREDIBLE_STRESS_CANDIDATE = "CORE_NOT_A_CREDIBLE_STRESS_CANDIDATE"
    TIER_B_DOES_NOT_IMPLY_STRESS = "TIER_B_DOES_NOT_IMPLY_STRESS"


class CandidateQualificationBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    qualification_id: Identifier
    source_artifact: str = Field(min_length=1)
    source_artifact_digest: Sha256Digest
    task: TaskIdentity
    qualification_identity: Sha256Digest

    @model_validator(mode="after")
    def identity_matches_payload(self) -> CandidateQualificationBinding:
        if self.qualification_identity != canonical_digest(self.payload()):
            raise ValueError("candidate qualification identity does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"qualification_identity"})


class CandidateInventoryItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task: TaskIdentity
    qualification: CandidateQualificationBinding
    package_path: str = Field(min_length=1)
    language: Literal["java", "python", "typescript"]
    task_family: TaskFamily
    category: str = Field(min_length=1)
    scenario_family: str = Field(min_length=1)
    benchmark_role: str = Field(min_length=1)
    provenance_artifact: str = Field(min_length=1)
    provenance_identity: Sha256Digest
    population: Literal[SplitRole.DEVELOPMENT] = SplitRole.DEVELOPMENT
    development_exposure: Literal[DevelopmentExposure.USED] = DevelopmentExposure.USED
    exposure_state: Literal[ExposureState.EXPOSED] = ExposureState.EXPOSED
    holdout_eligible: Literal[False] = False
    role: CandidateRole
    discriminative_eligibility: CandidateEligibility
    stress_eligibility: CandidateEligibility
    reason_codes: tuple[CandidateReasonCode, ...]
    candidate_identity: Sha256Digest

    @model_validator(mode="after")
    def item_is_canonical_and_bound(self) -> CandidateInventoryItem:
        if self.qualification.task != self.task:
            raise ValueError("qualification does not bind the inventory task")
        if tuple(sorted(set(self.reason_codes), key=str)) != self.reason_codes:
            raise ValueError("candidate reason codes must be unique and canonical")
        if CandidateReasonCode.HOLDOUT_INELIGIBLE not in self.reason_codes:
            raise ValueError("exposed candidate must remain explicitly Holdout-ineligible")
        if self.candidate_identity != canonical_digest(self.payload()):
            raise ValueError("candidate identity does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"candidate_identity"})


class CandidateInventory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    inventory_id: Literal["m8a-keyless-candidate-inventory-v1"] = (
        "m8a-keyless-candidate-inventory-v1"
    )
    inventory_version: Literal["1.0.0"] = "1.0.0"
    core_source_digest: Sha256Digest
    tier_b_source_digest: Sha256Digest
    core_count: Literal[18]
    tier_b_count: Literal[3]
    candidates: tuple[CandidateInventoryItem, ...]
    inventory_digest: Sha256Digest

    @model_validator(mode="after")
    def inventory_is_exact_and_canonical(self) -> CandidateInventory:
        ordered = tuple(
            sorted(
                self.candidates,
                key=lambda item: (
                    item.task.task_id,
                    item.task.task_version,
                    item.task.task_digest,
                ),
            )
        )
        if ordered != self.candidates:
            raise ValueError("candidate inventory must use canonical task identity order")
        if len(self.candidates) != 21 or len({item.task.task_id for item in self.candidates}) != 21:
            raise ValueError("candidate inventory must contain exactly 21 unique tasks")
        core = tuple(item for item in self.candidates if item.role is CandidateRole.CORE)
        tier_b = tuple(item for item in self.candidates if item.role is CandidateRole.TIER_B)
        if len(core) != self.core_count or len(tier_b) != self.tier_b_count:
            raise ValueError("candidate role counts do not match the frozen inventory")
        if any(item.task.task_version != "1.0.2" for item in core):
            raise ValueError("Core candidate inventory must bind version 1.0.2")
        if any(item.task.task_version != "1.0.0" for item in tier_b):
            raise ValueError("Tier-B candidate inventory must bind version 1.0.0")
        if any(item.holdout_eligible for item in self.candidates):
            raise ValueError("M.8-A candidates are exposed Development tasks, never Holdout")
        if self.inventory_digest != canonical_digest(self.payload()):
            raise ValueError("candidate inventory digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"inventory_digest"})


class ExecutionLane(StrEnum):
    DIRECT = "DIRECT"
    HARNESS = "HARNESS"


class ConfigurationBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    configuration_id: Identifier
    registry_id: Identifier
    registry_digest: Sha256Digest
    lane: ExecutionLane
    provider_id: Identifier
    provider_profile_id: Identifier
    provider_profile_identity: Sha256Digest
    model_id: Identifier
    model_family: str = Field(min_length=1)
    harness_id: Identifier
    harness_version: str = Field(min_length=1)
    harness_profile_id: Identifier
    harness_config_identity: Sha256Digest
    runner_contract: str = Field(min_length=1)
    reasoning_effort: str | None = None
    tool_surface: tuple[str, ...]
    live_provider_availability: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    configuration_identity: Sha256Digest

    @model_validator(mode="after")
    def identity_matches_payload(self) -> ConfigurationBinding:
        if self.lane is ExecutionLane.DIRECT and self.tool_surface:
            raise ValueError("Direct configuration cannot claim a harness tool surface")
        if self.lane is ExecutionLane.HARNESS and not self.tool_surface:
            raise ValueError("Harness configuration must expose a declared tool surface")
        if self.configuration_identity != canonical_digest(self.payload()):
            raise ValueError("configuration identity does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"configuration_identity"})


class PreregisteredPair(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pair_id: Identifier
    left_configuration_id: Identifier
    right_configuration_id: Identifier
    same_model_direct_harness_contrast: Literal[True] = True
    direction_neutral: Literal[True] = True


class RepresentationRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    language_axis: tuple[Literal["java", "python", "typescript"], ...] = (
        "java",
        "python",
        "typescript",
    )
    task_family_axis: tuple[Literal[TaskFamily.CORE, TaskFamily.REPO_ENGINEERING], ...] = (
        TaskFamily.CORE,
        TaskFamily.REPO_ENGINEERING,
    )
    scenario_axis_required: Literal[True] = True
    benchmark_role_axis_required: Literal[True] = True
    minimum_per_represented_language: Literal[1] = 1
    minimum_per_represented_task_family: Literal[1] = 1
    minimum_per_represented_scenario: Literal[1] = 1
    minimum_per_represented_benchmark_role: Literal[1] = 1
    underfilled_strata_rule: Literal["REPORT_GAP_WITHOUT_OUTCOME_BASED_BACKFILL"] = (
        "REPORT_GAP_WITHOUT_OUTCOME_BASED_BACKFILL"
    )
    overflow_rule: Literal["INCLUDE_ALL_QUALIFYING_CANDIDATES_IN_TASK_IDENTITY_ORDER"] = (
        "INCLUDE_ALL_QUALIFYING_CANDIDATES_IN_TASK_IDENTITY_ORDER"
    )
    rejected_candidates_retained: Literal[True] = True
    outcome_based_tiebreaking_allowed: Literal[False] = False


class DiscriminativePreregistration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    policy_label: Literal["discriminative-admission-v1"] = "discriminative-admission-v1"
    policy_reference: VersionedPolicyReference
    development_only: Literal[True] = True
    minimum_configurations: int = Field(ge=2)
    first_block_repetitions: Literal[3] = 3
    minimum_capability_eligible_coverage_numerator: Literal[4] = 4
    minimum_capability_eligible_coverage_denominator: Literal[5] = 5
    comparable_only: Literal[True] = True
    minimum_first_block_discordant_pairs: Literal[2] = 2
    minimum_absolute_pass_rate_gap_numerator: Literal[2] = 2
    minimum_absolute_pass_rate_gap_denominator: Literal[3] = 3
    require_at_least_one_pass_and_capability_fail: Literal[True] = True
    stability_block_repetitions: Literal[3] = 3
    stability_independently_scheduled: Literal[True] = True
    minimum_stability_block_discordant_pairs: Literal[1] = 1
    require_same_stability_direction: Literal[True] = True
    direction_neutral: Literal[True] = True
    named_winner: Literal[None] = None
    rerun_until_success_allowed: Literal[False] = False
    empirical_execution_authorization_required: Literal[True] = True
    selection_uses_historical_outcomes: Literal[False] = False
    live_provider_availability_claimed: Literal[False] = False
    execution_control_identity: Sha256Digest
    configuration_universe: tuple[ConfigurationBinding, ...]
    selected_panel: tuple[ConfigurationBinding, ...]
    preregistered_pairs: tuple[PreregisteredPair, ...]
    representation_rule: RepresentationRule
    policy_digest: Sha256Digest

    @model_validator(mode="after")
    def policy_is_neutral_bounded_and_canonical(self) -> DiscriminativePreregistration:
        universe = tuple(
            sorted(self.configuration_universe, key=lambda item: item.configuration_id)
        )
        panel = tuple(sorted(self.selected_panel, key=lambda item: item.configuration_id))
        pairs = tuple(sorted(self.preregistered_pairs, key=lambda item: item.pair_id))
        if universe != self.configuration_universe or panel != self.selected_panel:
            raise ValueError("configuration bindings must use canonical identity order")
        if pairs != self.preregistered_pairs:
            raise ValueError("preregistered pairs must use canonical identity order")
        universe_ids = {item.configuration_id for item in universe}
        panel_ids = {item.configuration_id for item in panel}
        if len(universe_ids) != len(universe) or len(panel_ids) != len(panel):
            raise ValueError("configuration identities must be unique")
        if not panel_ids <= universe_ids or len(panel) < self.minimum_configurations:
            raise ValueError("selected panel is incomplete or outside the candidate universe")
        if len({item.model_family for item in panel}) < 2:
            raise ValueError("selected panel must cover at least two model families")
        if {item.lane for item in panel} != {ExecutionLane.DIRECT, ExecutionLane.HARNESS}:
            raise ValueError("selected panel must cover Direct and Harness execution")
        by_id = {item.configuration_id: item for item in panel}
        for pair in pairs:
            try:
                left = by_id[pair.left_configuration_id]
                right = by_id[pair.right_configuration_id]
            except KeyError as exc:
                raise ValueError("preregistered pair is outside the selected panel") from exc
            if (
                left.provider_profile_id != right.provider_profile_id
                or left.model_id != right.model_id
                or {left.lane, right.lane} != {ExecutionLane.DIRECT, ExecutionLane.HARNESS}
            ):
                raise ValueError("pair is not an exact same-route Direct/Harness contrast")
        if len(pairs) < 2:
            raise ValueError("selected panel requires at least two same-model contrasts")
        if self.minimum_configurations != len(panel):
            raise ValueError("minimum configuration count must freeze the complete panel")
        if self.policy_digest != canonical_digest(self.payload()):
            raise ValueError("Discriminative preregistration digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"policy_digest"})


class QualificationDirection(StrEnum):
    LEFT_HIGHER = "LEFT_HIGHER"
    RIGHT_HIGHER = "RIGHT_HIGHER"


class ConfigurationBlockSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    configuration_id: Identifier
    planned: int = Field(ge=1)
    capability_eligible: int = Field(ge=0)
    capability_passes: int = Field(ge=0)
    capability_failures: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_are_coherent(self) -> ConfigurationBlockSummary:
        if self.capability_eligible > self.planned:
            raise ValueError("capability-eligible count exceeds planned observations")
        if self.capability_passes + self.capability_failures != self.capability_eligible:
            raise ValueError("capability pass/fail counts do not match the eligible denominator")
        return self


class PairBlockSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pair_id: Identifier
    comparable_pairs: int = Field(ge=0)
    discordant_pairs: int = Field(ge=0)
    all_qualifying_evidence_comparable: bool

    @model_validator(mode="after")
    def counts_are_coherent(self) -> PairBlockSummary:
        if self.discordant_pairs > self.comparable_pairs:
            raise ValueError("discordant pairs cannot exceed comparable pairs")
        return self


class QualificationBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    block_id: Identifier
    repetitions_per_configuration: int = Field(ge=1)
    independently_scheduled: bool
    configurations: tuple[ConfigurationBlockSummary, ...]
    pairs: tuple[PairBlockSummary, ...]

    @model_validator(mode="after")
    def block_is_canonical(self) -> QualificationBlock:
        if tuple(sorted(self.configurations, key=lambda item: item.configuration_id)) != (
            self.configurations
        ):
            raise ValueError("block configurations must use canonical identity order")
        if tuple(sorted(self.pairs, key=lambda item: item.pair_id)) != self.pairs:
            raise ValueError("block pairs must use canonical identity order")
        if len({item.configuration_id for item in self.configurations}) != len(self.configurations):
            raise ValueError("block configuration summaries must be unique")
        if any(item.comparable_pairs > self.repetitions_per_configuration for item in self.pairs):
            raise ValueError("pair comparability count exceeds scheduled repetitions")
        return self


class DiscriminativeQualificationEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task: TaskIdentity
    population: SplitRole
    panel_configuration_ids: tuple[Identifier, ...]
    first_block: QualificationBlock
    stability_block: QualificationBlock | None
    total_scheduled_blocks: int = Field(ge=1)
    rerun_until_success: bool = False


class QualificationFailureCode(StrEnum):
    DEVELOPMENT_REQUIRED = "DEVELOPMENT_REQUIRED"
    PANEL_IDENTITY_MISMATCH = "PANEL_IDENTITY_MISMATCH"
    FIRST_BLOCK_N3_REQUIRED = "FIRST_BLOCK_N3_REQUIRED"
    CAPABILITY_COVERAGE_BELOW_80_PERCENT = "CAPABILITY_COVERAGE_BELOW_80_PERCENT"
    NONCOMPARABLE_EVIDENCE = "NONCOMPARABLE_EVIDENCE"
    INSUFFICIENT_FIRST_BLOCK_DISCORDANCE = "INSUFFICIENT_FIRST_BLOCK_DISCORDANCE"
    ABSOLUTE_PASS_RATE_GAP_BELOW_TWO_THIRDS = "ABSOLUTE_PASS_RATE_GAP_BELOW_TWO_THIRDS"
    FLOOR_OR_CEILING = "FLOOR_OR_CEILING"
    STABILITY_BLOCK_MISSING = "STABILITY_BLOCK_MISSING"
    STABILITY_BLOCK_NOT_INDEPENDENT = "STABILITY_BLOCK_NOT_INDEPENDENT"
    STABILITY_BLOCK_N3_REQUIRED = "STABILITY_BLOCK_N3_REQUIRED"
    STABILITY_DIRECTION_MISMATCH = "STABILITY_DIRECTION_MISMATCH"
    STABILITY_DISCORDANCE_MISSING = "STABILITY_DISCORDANCE_MISSING"
    RERUN_POLICY_VIOLATION = "RERUN_POLICY_VIOLATION"


class DiscriminativeScreenResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["QUALIFIES", "REJECTED"]
    qualifying_pair_id: Identifier | None
    direction: QualificationDirection | None
    reason_codes: tuple[QualificationFailureCode, ...]

    @model_validator(mode="after")
    def result_is_coherent(self) -> DiscriminativeScreenResult:
        if self.status == "QUALIFIES" and (
            self.reason_codes or self.qualifying_pair_id is None or self.direction is None
        ):
            raise ValueError("qualifying result requires a neutral pair direction and no failures")
        if self.status == "REJECTED" and not self.reason_codes:
            raise ValueError("rejected result requires fail-closed reason codes")
        return self


def _pass_rate(summary: ConfigurationBlockSummary) -> float:
    if summary.capability_eligible == 0:
        return 0.0
    return summary.capability_passes / summary.capability_eligible


def _direction(
    left: ConfigurationBlockSummary, right: ConfigurationBlockSummary
) -> QualificationDirection | None:
    delta = _pass_rate(left) - _pass_rate(right)
    if delta > 0:
        return QualificationDirection.LEFT_HIGHER
    if delta < 0:
        return QualificationDirection.RIGHT_HIGHER
    return None


def evaluate_discriminative_qualification(
    evidence: DiscriminativeQualificationEvidence,
    policy: DiscriminativePreregistration,
) -> DiscriminativeScreenResult:
    """Evaluate frozen evidence symmetrically; no configuration is a named winner."""

    reasons: set[QualificationFailureCode] = set()
    expected_panel = tuple(item.configuration_id for item in policy.selected_panel)
    if evidence.population is not SplitRole.DEVELOPMENT:
        reasons.add(QualificationFailureCode.DEVELOPMENT_REQUIRED)
    if evidence.panel_configuration_ids != expected_panel:
        reasons.add(QualificationFailureCode.PANEL_IDENTITY_MISMATCH)
    if evidence.first_block.repetitions_per_configuration != policy.first_block_repetitions:
        reasons.add(QualificationFailureCode.FIRST_BLOCK_N3_REQUIRED)
    if evidence.total_scheduled_blocks != 2 or evidence.rerun_until_success:
        reasons.add(QualificationFailureCode.RERUN_POLICY_VIOLATION)

    expected_ids = set(expected_panel)
    first_by_id = {item.configuration_id: item for item in evidence.first_block.configurations}
    if set(first_by_id) != expected_ids:
        reasons.add(QualificationFailureCode.PANEL_IDENTITY_MISMATCH)
    if any(item.planned != policy.first_block_repetitions for item in first_by_id.values()):
        reasons.add(QualificationFailureCode.FIRST_BLOCK_N3_REQUIRED)
    coverage_threshold = (
        policy.minimum_capability_eligible_coverage_numerator
        / policy.minimum_capability_eligible_coverage_denominator
    )
    for configuration_summary in first_by_id.values():
        if (
            configuration_summary.capability_eligible / configuration_summary.planned
            < coverage_threshold
        ):
            reasons.add(QualificationFailureCode.CAPABILITY_COVERAGE_BELOW_80_PERCENT)
    if not any(item.capability_passes for item in first_by_id.values()) or not any(
        item.capability_failures for item in first_by_id.values()
    ):
        reasons.add(QualificationFailureCode.FLOOR_OR_CEILING)

    pair_policy = {item.pair_id: item for item in policy.preregistered_pairs}
    first_pairs = {item.pair_id: item for item in evidence.first_block.pairs}
    qualifying: list[tuple[str, QualificationDirection]] = []
    saw_comparable = False
    saw_discordance = False
    saw_gap = False
    gap_threshold = (
        policy.minimum_absolute_pass_rate_gap_numerator
        / policy.minimum_absolute_pass_rate_gap_denominator
    )
    for pair_id, pair in pair_policy.items():
        pair_summary = first_pairs.get(pair_id)
        if pair_summary is None or not pair_summary.all_qualifying_evidence_comparable:
            continue
        saw_comparable = True
        if pair_summary.discordant_pairs < policy.minimum_first_block_discordant_pairs:
            continue
        saw_discordance = True
        left = first_by_id.get(pair.left_configuration_id)
        right = first_by_id.get(pair.right_configuration_id)
        if left is None or right is None:
            continue
        direction = _direction(left, right)
        if direction is None or abs(_pass_rate(left) - _pass_rate(right)) < gap_threshold:
            continue
        saw_gap = True
        qualifying.append((pair_id, direction))
    if not saw_comparable:
        reasons.add(QualificationFailureCode.NONCOMPARABLE_EVIDENCE)
    if not saw_discordance:
        reasons.add(QualificationFailureCode.INSUFFICIENT_FIRST_BLOCK_DISCORDANCE)
    if not saw_gap:
        reasons.add(QualificationFailureCode.ABSOLUTE_PASS_RATE_GAP_BELOW_TWO_THIRDS)

    stability = evidence.stability_block
    if stability is None:
        reasons.add(QualificationFailureCode.STABILITY_BLOCK_MISSING)
    else:
        if not stability.independently_scheduled:
            reasons.add(QualificationFailureCode.STABILITY_BLOCK_NOT_INDEPENDENT)
        if stability.repetitions_per_configuration != policy.stability_block_repetitions:
            reasons.add(QualificationFailureCode.STABILITY_BLOCK_N3_REQUIRED)
        stable_by_id = {item.configuration_id: item for item in stability.configurations}
        if set(stable_by_id) != expected_ids:
            reasons.add(QualificationFailureCode.PANEL_IDENTITY_MISMATCH)
        if any(
            item.planned != policy.stability_block_repetitions for item in stable_by_id.values()
        ):
            reasons.add(QualificationFailureCode.STABILITY_BLOCK_N3_REQUIRED)
        for configuration_summary in stable_by_id.values():
            if (
                configuration_summary.capability_eligible / configuration_summary.planned
                < coverage_threshold
            ):
                reasons.add(QualificationFailureCode.CAPABILITY_COVERAGE_BELOW_80_PERCENT)
        stable_pairs = {item.pair_id: item for item in stability.pairs}
        reproduced: list[tuple[str, QualificationDirection]] = []
        saw_stable_comparable = False
        stable_discordance = False
        for pair_id, first_direction in qualifying:
            pair = pair_policy[pair_id]
            pair_summary = stable_pairs.get(pair_id)
            if pair_summary is None or not pair_summary.all_qualifying_evidence_comparable:
                continue
            saw_stable_comparable = True
            if pair_summary.discordant_pairs < policy.minimum_stability_block_discordant_pairs:
                continue
            stable_discordance = True
            left = stable_by_id.get(pair.left_configuration_id)
            right = stable_by_id.get(pair.right_configuration_id)
            if (
                left is not None
                and right is not None
                and _direction(left, right) is first_direction
            ):
                reproduced.append((pair_id, first_direction))
        if qualifying and not saw_stable_comparable:
            reasons.add(QualificationFailureCode.NONCOMPARABLE_EVIDENCE)
        if not stable_discordance:
            reasons.add(QualificationFailureCode.STABILITY_DISCORDANCE_MISSING)
        elif not reproduced:
            reasons.add(QualificationFailureCode.STABILITY_DIRECTION_MISMATCH)

    if reasons:
        return DiscriminativeScreenResult(
            status="REJECTED",
            qualifying_pair_id=None,
            direction=None,
            reason_codes=tuple(sorted(reasons, key=str)),
        )
    pair_id, direction = sorted(reproduced, key=lambda item: item[0])[0]
    return DiscriminativeScreenResult(
        status="QUALIFIES", qualifying_pair_id=pair_id, direction=direction, reason_codes=()
    )


class RetrospectiveReasonCode(StrEnum):
    HISTORICAL_MATRIX_NOT_PREREGISTERED_FOR_POLICY = (
        "HISTORICAL_MATRIX_NOT_PREREGISTERED_FOR_POLICY"
    )
    HISTORICAL_PANEL_IDENTITY_MISMATCH = "HISTORICAL_PANEL_IDENTITY_MISMATCH"
    FIRST_N3_BLOCK_MISSING = "FIRST_N3_BLOCK_MISSING"
    INDEPENDENT_STABILITY_N3_BLOCK_MISSING = "INDEPENDENT_STABILITY_N3_BLOCK_MISSING"
    HISTORICAL_EVIDENCE_MISSING = "HISTORICAL_EVIDENCE_MISSING"


class RetrospectiveCandidateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task: TaskIdentity
    status: Literal["RETROSPECTIVE_NON_QUALIFYING"] = "RETROSPECTIVE_NON_QUALIFYING"
    historical_behavior_available: bool
    reason_codes: tuple[RetrospectiveReasonCode, ...]


class RetrospectiveScreen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    screen_id: Literal["m8a-v6-retrospective-screen-v1"] = "m8a-v6-retrospective-screen-v1"
    status: Literal["RETROSPECTIVE_NON_QUALIFYING"] = "RETROSPECTIVE_NON_QUALIFYING"
    policy_reference: VersionedPolicyReference
    historical_control_path: Literal["release/core-real-matrix-v6-control.json"] = (
        "release/core-real-matrix-v6-control.json"
    )
    historical_control_digest: Sha256Digest
    historical_analysis_path: Literal["release/core-real-matrix-v6-final-analysis.json"] = (
        "release/core-real-matrix-v6-final-analysis.json"
    )
    historical_analysis_digest: Sha256Digest
    historical_task_count: Literal[18]
    historical_configuration_count: Literal[7]
    historical_repetitions: Literal[5]
    current_memberships_created: Literal[0] = 0
    results: tuple[RetrospectiveCandidateResult, ...]
    screen_digest: Sha256Digest

    @model_validator(mode="after")
    def screen_is_nonqualifying_and_complete(self) -> RetrospectiveScreen:
        if len(self.results) != 21 or any(
            item.status != "RETROSPECTIVE_NON_QUALIFYING" for item in self.results
        ):
            raise ValueError("retrospective screen must retain all candidates as non-qualifying")
        if tuple(sorted(self.results, key=lambda item: item.task.task_id)) != self.results:
            raise ValueError("retrospective results must use canonical task order")
        if self.screen_digest != canonical_digest(self.payload()):
            raise ValueError("retrospective screen digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"screen_digest"})


class StressEvidenceStatus(StrEnum):
    PROVEN_KEYLESS = "PROVEN_KEYLESS"
    REQUIRES_EMPIRICAL_EVIDENCE = "REQUIRES_EMPIRICAL_EVIDENCE"
    NOT_PROVEN = "NOT_PROVEN"


class StressDimensionName(StrEnum):
    TRAJECTORY = "TRAJECTORY"
    MULTI_FILE = "MULTI_FILE"
    TOOL_USE = "TOOL_USE"
    REPAIR_LOOP = "REPAIR_LOOP"
    DEPENDENCY_BUILD = "DEPENDENCY_BUILD"
    CONTEXT = "CONTEXT"
    PROTOCOL = "PROTOCOL"


class StressDimensionAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: StressDimensionName
    status: StressEvidenceStatus
    reason_code: str = Field(min_length=1)
    evidence_identity: Sha256Digest | None = None


class StressCandidateAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task: TaskIdentity
    qualification_identity: Sha256Digest
    dimensions: tuple[StressDimensionAssessment, ...]
    proven_dimension_count: int = Field(ge=0)
    has_required_anchor_dimension: bool
    stress_member_eligible: Literal[False] = False

    @model_validator(mode="after")
    def audit_is_complete_and_fail_closed(self) -> StressCandidateAudit:
        if tuple(sorted(self.dimensions, key=lambda item: item.dimension.value)) != self.dimensions:
            raise ValueError("stress dimensions must use canonical order")
        if {item.dimension for item in self.dimensions} != set(StressDimensionName):
            raise ValueError("every stress dimension requires an explicit assessment")
        proven = sum(item.status is StressEvidenceStatus.PROVEN_KEYLESS for item in self.dimensions)
        if proven != self.proven_dimension_count:
            raise ValueError("proven stress dimension count is inconsistent")
        if self.stress_member_eligible:
            raise ValueError("M.8-A cannot create Stress membership")
        return self


class StressPortfolioAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    audit_id: Literal["m8a-keyless-stress-audit-v1"] = "m8a-keyless-stress-audit-v1"
    minimum_dimensions_per_member: Literal[3] = 3
    required_anchor_dimensions: tuple[
        Literal[
            StressDimensionName.TRAJECTORY,
            StressDimensionName.CONTEXT,
            StressDimensionName.PROTOCOL,
        ],
        ...,
    ] = (
        StressDimensionName.CONTEXT,
        StressDimensionName.PROTOCOL,
        StressDimensionName.TRAJECTORY,
    )
    minimum_tasks_per_represented_dimension: Literal[3] = 3
    minimum_languages_for_language_independent_dimension: Literal[2] = 2
    maximum_single_task_credit_share_numerator: Literal[1] = 1
    maximum_single_task_credit_share_denominator: Literal[3] = 3
    candidates: tuple[StressCandidateAudit, ...]
    portfolio_reason_codes: tuple[str, ...]
    stress_suite_release_ready: Literal[False] = False
    audit_digest: Sha256Digest

    @model_validator(mode="after")
    def portfolio_is_complete_and_fail_closed(self) -> StressPortfolioAudit:
        if len(self.candidates) != 3:
            raise ValueError("Stress audit must retain all three credible Tier-B candidates")
        if tuple(sorted(self.candidates, key=lambda item: item.task.task_id)) != self.candidates:
            raise ValueError("Stress candidates must use canonical task order")
        if not self.portfolio_reason_codes:
            raise ValueError("non-release-ready Stress audit requires reason codes")
        if self.audit_digest != canonical_digest(self.payload()):
            raise ValueError("Stress audit digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"audit_digest"})


class CoverageGapReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    report_id: Literal["m8a-coverage-gap-report-v1"] = "m8a-coverage-gap-report-v1"
    candidates_screenable_now: Literal[21]
    current_discriminative_memberships: Literal[0] = 0
    current_stress_memberships: Literal[0] = 0
    empirical_discriminative_evidence_required: Literal[True] = True
    stress_suite_release_ready: Literal[False] = False
    missing_representation_or_stress_coverage: tuple[str, ...]
    new_tasks_required: Literal[True] = True
    required_new_task_coverage: tuple[str, ...]
    report_digest: Sha256Digest

    @model_validator(mode="after")
    def report_is_canonical(self) -> CoverageGapReport:
        if tuple(sorted(set(self.missing_representation_or_stress_coverage))) != (
            self.missing_representation_or_stress_coverage
        ):
            raise ValueError("coverage gaps must be unique and canonical")
        if tuple(sorted(set(self.required_new_task_coverage))) != self.required_new_task_coverage:
            raise ValueError("new-task coverage requirements must be unique and canonical")
        if self.report_digest != canonical_digest(self.payload()):
            raise ValueError("coverage gap report digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"report_digest"})


class ExternalCallCounts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Literal[0] = 0
    harness: Literal[0] = 0
    judge: Literal[0] = 0
    matrix: Literal[0] = 0
    llm_explanation: Literal[0] = 0


class M8APreregistrationBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    bundle_id: Literal["phase-m8a-keyless-preregistration-v1"] = (
        "phase-m8a-keyless-preregistration-v1"
    )
    source_main_sha: Literal["3335668f4f11e384a9f99fb0a8692f07d8937902"]
    inventory: CandidateInventory
    discriminative_policy: DiscriminativePreregistration
    retrospective: RetrospectiveScreen
    stress_audit: StressPortfolioAudit
    gap_report: CoverageGapReport
    external_calls: ExternalCallCounts = Field(default_factory=ExternalCallCounts)
    frozen_evidence_modified: Literal[False] = False
    bundle_digest: Sha256Digest

    @model_validator(mode="after")
    def bundle_is_bound_and_self_identifying(self) -> M8APreregistrationBundle:
        if self.retrospective.policy_reference != self.discriminative_policy.policy_reference:
            raise ValueError("retrospective screen is not bound to the frozen policy")
        if self.gap_report.stress_suite_release_ready != (
            self.stress_audit.stress_suite_release_ready
        ):
            raise ValueError("gap report and Stress audit disagree")
        if self.bundle_digest != canonical_digest(self.payload()):
            raise ValueError("M.8-A bundle digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"bundle_digest"})

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _qualification_binding(
    *, qualification_id: str, source_artifact: str, source_digest: str, task: TaskIdentity
) -> CandidateQualificationBinding:
    payload = {
        "qualification_id": qualification_id,
        "source_artifact": source_artifact,
        "source_artifact_digest": source_digest,
        "task": task.model_dump(mode="json"),
    }
    payload["qualification_identity"] = canonical_digest(payload)
    return CandidateQualificationBinding.model_validate(payload)


def _inventory_item(**values: Any) -> CandidateInventoryItem:
    values["reason_codes"] = [item.value for item in sorted(set(values["reason_codes"]), key=str)]
    values["candidate_identity"] = canonical_digest(values)
    return CandidateInventoryItem.model_validate(values)


def build_candidate_inventory(repository_root: Path) -> CandidateInventory:
    core_path = repository_root / "release/core-corpus-v4.json"
    tier_b_path = repository_root / "release/tier-b-qualification-v1.json"
    core = load_core_corpus(core_path)
    tier_b = load_tier_b_qualification(tier_b_path)
    validate_tier_b_qualification(repository_root, tier_b)
    if len(core.tasks) != 18 or any(item.version != "1.0.2" for item in core.tasks):
        raise PreregistrationError("repository Core reality differs from 18 tasks at version 1.0.2")
    if len(tier_b.tasks) != 3 or any(item.task_version != "1.0.0" for item in tier_b.tasks):
        raise PreregistrationError(
            "repository Tier-B reality differs from 3 tasks at version 1.0.0"
        )

    candidates: list[CandidateInventoryItem] = []
    for core_item in core.tasks:
        package = TaskPackage.load(repository_root / core_item.package_path)
        task = TaskIdentity.from_package(package)
        expected = TaskIdentity(
            task_id=core_item.task_id,
            task_version=core_item.version,
            task_digest=core_item.task_digest,
            workspace_digest=core_item.workspace_input_identity,
            verifier_digest=core_item.verifier_identity,
        )
        if task != expected:
            raise PreregistrationError(f"Core task identity drift: {core_item.task_id}")
        qualification = _qualification_binding(
            qualification_id="harnesslab-core-18-v1-task-integrity",
            source_artifact="release/core-corpus-v4.json",
            source_digest=core.digest,
            task=task,
        )
        candidates.append(
            _inventory_item(
                task=task.model_dump(mode="json"),
                qualification=qualification.model_dump(mode="json"),
                package_path=core_item.package_path,
                language=core_item.language,
                task_family=TaskFamily.CORE.value,
                category=core_item.category,
                scenario_family=core_item.scenario_family,
                benchmark_role=core_item.benchmark_role,
                provenance_artifact="release/core-corpus-v4.json",
                provenance_identity=core.digest,
                population=SplitRole.DEVELOPMENT.value,
                development_exposure=DevelopmentExposure.USED.value,
                exposure_state=ExposureState.EXPOSED.value,
                holdout_eligible=False,
                role=CandidateRole.CORE.value,
                discriminative_eligibility=(
                    CandidateEligibility.ELIGIBLE_FOR_EMPIRICAL_SCREENING.value
                ),
                stress_eligibility=CandidateEligibility.INELIGIBLE.value,
                reason_codes=(
                    CandidateReasonCode.TASK_INTEGRITY_QUALIFIED,
                    CandidateReasonCode.CORE_DEVELOPMENT_EXPOSED,
                    CandidateReasonCode.HOLDOUT_INELIGIBLE,
                    CandidateReasonCode.DISCRIMINATIVE_REQUIRES_EMPIRICAL_EVIDENCE,
                    CandidateReasonCode.CORE_NOT_A_CREDIBLE_STRESS_CANDIDATE,
                ),
            )
        )

    for tier_b_item in tier_b.tasks:
        package = TaskPackage.load(repository_root / tier_b_item.package_path)
        task = TaskIdentity.from_package(package)
        expected = TaskIdentity(
            task_id=tier_b_item.task_id,
            task_version=tier_b_item.task_version,
            task_digest=tier_b_item.task_identity,
            workspace_digest=tier_b_item.repository_snapshot_identity,
            verifier_digest=tier_b_item.verifier_identity,
        )
        if task != expected:
            raise PreregistrationError(f"Tier-B task identity drift: {tier_b_item.task_id}")
        metadata = package.definition.metadata
        qualification = _qualification_binding(
            qualification_id=tier_b.qualification_id,
            source_artifact="release/tier-b-qualification-v1.json",
            source_digest=tier_b.qualification_digest,
            task=task,
        )
        candidates.append(
            _inventory_item(
                task=task.model_dump(mode="json"),
                qualification=qualification.model_dump(mode="json"),
                package_path=tier_b_item.package_path,
                language=tier_b_item.language,
                task_family=TaskFamily.REPO_ENGINEERING.value,
                category=metadata["category"],
                scenario_family=metadata["scenario_family"],
                benchmark_role=metadata["benchmark_role"],
                provenance_artifact="release/tier-b-qualification-v1.json",
                provenance_identity=tier_b.qualification_digest,
                population=SplitRole.DEVELOPMENT.value,
                development_exposure=DevelopmentExposure.USED.value,
                exposure_state=ExposureState.EXPOSED.value,
                holdout_eligible=False,
                role=CandidateRole.TIER_B.value,
                discriminative_eligibility=(
                    CandidateEligibility.ELIGIBLE_FOR_EMPIRICAL_SCREENING.value
                ),
                stress_eligibility=CandidateEligibility.CANDIDATE_REQUIRES_EVIDENCE.value,
                reason_codes=(
                    CandidateReasonCode.TASK_INTEGRITY_QUALIFIED,
                    CandidateReasonCode.TIER_B_DEVELOPMENT_EXPOSED,
                    CandidateReasonCode.HOLDOUT_INELIGIBLE,
                    CandidateReasonCode.DISCRIMINATIVE_REQUIRES_EMPIRICAL_EVIDENCE,
                    CandidateReasonCode.TIER_B_DOES_NOT_IMPLY_STRESS,
                ),
            )
        )

    ordered = tuple(sorted(candidates, key=lambda item: item.task.task_id))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "inventory_id": "m8a-keyless-candidate-inventory-v1",
        "inventory_version": "1.0.0",
        "core_source_digest": core.digest,
        "tier_b_source_digest": tier_b.qualification_digest,
        "core_count": 18,
        "tier_b_count": 3,
        "candidates": [item.model_dump(mode="json") for item in ordered],
    }
    payload["inventory_digest"] = canonical_digest(payload)
    return CandidateInventory.model_validate(payload)


def _configuration_bindings(catalog: RegistryCatalog) -> tuple[ConfigurationBinding, ...]:
    profiles = {item.profile_id: item for item in catalog.provider_model_profiles}
    models = {item.model_id: item for item in catalog.models}
    bindings: list[ConfigurationBinding] = []
    for harness in catalog.harnesses:
        for harness_profile in harness.profiles:
            for provider_profile_id in harness_profile.supported_provider_profile_ids:
                provider_profile = profiles[provider_profile_id]
                model = models[provider_profile.model_id]
                if "coding" not in model.capabilities:
                    continue
                lane = (
                    ExecutionLane.DIRECT
                    if harness.harness_id == "direct-model"
                    else ExecutionLane.HARNESS
                )
                configuration_id = f"{lane.value.lower()}-{harness_profile.profile_id}"
                payload: dict[str, Any] = {
                    "configuration_id": configuration_id,
                    "registry_id": catalog.registry_id,
                    "registry_digest": catalog.digest,
                    "lane": lane.value,
                    "provider_id": provider_profile.provider_id,
                    "provider_profile_id": provider_profile.profile_id,
                    "provider_profile_identity": provider_profile.profile_identity,
                    "model_id": model.model_id,
                    "model_family": model.model_family,
                    "harness_id": harness.harness_id,
                    "harness_version": harness.version,
                    "harness_profile_id": harness_profile.profile_id,
                    "harness_config_identity": harness_profile.harness_config_identity,
                    "runner_contract": harness.runner_contract,
                    "reasoning_effort": harness_profile.reasoning_effort,
                    "tool_surface": list(harness.tool_surface),
                    "live_provider_availability": "NOT_ASSESSED",
                }
                payload["configuration_identity"] = canonical_digest(payload)
                bindings.append(ConfigurationBinding.model_validate(payload))
    return tuple(sorted(bindings, key=lambda item: item.configuration_id))


def build_discriminative_preregistration(
    repository_root: Path,
) -> DiscriminativePreregistration:
    catalog = build_registry_catalog(repository_root, {})
    universe = _configuration_bindings(catalog)
    direct = tuple(item for item in universe if item.lane is ExecutionLane.DIRECT)
    harness = tuple(item for item in universe if item.lane is ExecutionLane.HARNESS)
    pair_candidates: list[tuple[ConfigurationBinding, ConfigurationBinding]] = []
    for direct_item in direct:
        matches = tuple(
            sorted(
                (
                    item
                    for item in harness
                    if item.provider_profile_id == direct_item.provider_profile_id
                    and item.model_id == direct_item.model_id
                ),
                key=lambda item: item.configuration_id,
            )
        )
        if matches:
            pair_candidates.append((direct_item, matches[0]))
    by_family: dict[str, tuple[ConfigurationBinding, ConfigurationBinding]] = {}
    for pair in sorted(
        pair_candidates,
        key=lambda item: (
            item[0].model_family,
            item[0].provider_profile_id,
            item[1].configuration_id,
        ),
    ):
        by_family.setdefault(pair[0].model_family, pair)
    if len(by_family) < 2:
        raise PreregistrationError(
            "current registry cannot supply two same-model Direct/Harness contrasts"
        )
    selected_pairs = tuple(by_family[key] for key in sorted(by_family))
    panel = tuple(
        sorted(
            {item.configuration_id: item for pair in selected_pairs for item in pair}.values(),
            key=lambda item: item.configuration_id,
        )
    )
    pairs = tuple(
        sorted(
            (
                PreregisteredPair(
                    pair_id=f"direct-vs-harness-{left.model_id}",
                    left_configuration_id=left.configuration_id,
                    right_configuration_id=right.configuration_id,
                )
                for left, right in selected_pairs
            ),
            key=lambda item: item.pair_id,
        )
    )
    m1_path = repository_root / "docs/evaluation/PHASE_M1_EVALUATION_SYSTEM_2_GAP_RECONCILIATION.md"
    authority_identity = canonical_digest({"m1_contract": m1_path.read_text(encoding="utf-8")})
    provenance = build_policy_provenance(
        authority_identity=authority_identity,
        source_revision_identity=canonical_digest(
            {"source_main_sha": "3335668f4f11e384a9f99fb0a8692f07d8937902"}
        ),
    )
    base_policy = build_admission_policy(
        policy_id="discriminative-admission",
        policy_version="1.0.0",
        namespace=GovernanceNamespace.OFFICIAL,
        suite_purpose=SuitePurpose.DISCRIMINATIVE,
        acceptance_criteria=DiscriminativeAcceptanceCriteria(
            minimum_configurations=len(panel),
            minimum_repetitions_per_configuration=3,
            minimum_pairwise_effect_absolute=2 / 3,
            maximum_rank_instability=0.0,
        ),
        provenance=provenance,
    )
    controls = {
        "deterministic_verifier_authoritative": True,
        "capability_vs_infrastructure_taxonomy": True,
        "first_block_schedule_seed": 810001,
        "stability_block_schedule_seed": 810002,
        "paired_schedule": True,
        "provider_model_substitution_allowed": False,
        "semantic_retry_allowed": False,
        "score_based_retry_allowed": False,
        "score_based_early_stop_allowed": False,
    }
    payload: dict[str, Any] = {
        "schema_version": 1,
        "policy_label": "discriminative-admission-v1",
        "policy_reference": base_policy.as_reference().model_dump(mode="json"),
        "development_only": True,
        "minimum_configurations": len(panel),
        "first_block_repetitions": 3,
        "minimum_capability_eligible_coverage_numerator": 4,
        "minimum_capability_eligible_coverage_denominator": 5,
        "comparable_only": True,
        "minimum_first_block_discordant_pairs": 2,
        "minimum_absolute_pass_rate_gap_numerator": 2,
        "minimum_absolute_pass_rate_gap_denominator": 3,
        "require_at_least_one_pass_and_capability_fail": True,
        "stability_block_repetitions": 3,
        "stability_independently_scheduled": True,
        "minimum_stability_block_discordant_pairs": 1,
        "require_same_stability_direction": True,
        "direction_neutral": True,
        "named_winner": None,
        "rerun_until_success_allowed": False,
        "empirical_execution_authorization_required": True,
        "selection_uses_historical_outcomes": False,
        "live_provider_availability_claimed": False,
        "execution_control_identity": canonical_digest(controls),
        "configuration_universe": [item.model_dump(mode="json") for item in universe],
        "selected_panel": [item.model_dump(mode="json") for item in panel],
        "preregistered_pairs": [item.model_dump(mode="json") for item in pairs],
        "representation_rule": RepresentationRule().model_dump(mode="json"),
    }
    payload["policy_digest"] = canonical_digest(payload)
    return DiscriminativePreregistration.model_validate(payload)


def _json_digest(path: Path) -> str:
    return canonical_digest(json.loads(path.read_text(encoding="utf-8")))


def build_retrospective_screen(
    repository_root: Path,
    inventory: CandidateInventory,
    policy: DiscriminativePreregistration,
) -> RetrospectiveScreen:
    control_path = repository_root / "release/core-real-matrix-v6-control.json"
    analysis_path = repository_root / "release/core-real-matrix-v6-final-analysis.json"
    control = json.loads(control_path.read_text(encoding="utf-8"))
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    validation = analysis.get("dataset_validation", {})
    facts = (
        validation.get("task_count"),
        validation.get("cell_count"),
        validation.get("repeat_count"),
        control.get("corpus_reference"),
    )
    if facts != (18, 7, 5, "release/core-corpus-v4.json"):
        raise PreregistrationError("historical Matrix artifact shape is incompatible or stale")
    results: list[RetrospectiveCandidateResult] = []
    for candidate in inventory.candidates:
        if candidate.role is CandidateRole.CORE:
            retrospective_reasons: tuple[RetrospectiveReasonCode, ...] = (
                RetrospectiveReasonCode.FIRST_N3_BLOCK_MISSING,
                RetrospectiveReasonCode.HISTORICAL_MATRIX_NOT_PREREGISTERED_FOR_POLICY,
                RetrospectiveReasonCode.HISTORICAL_PANEL_IDENTITY_MISMATCH,
                RetrospectiveReasonCode.INDEPENDENT_STABILITY_N3_BLOCK_MISSING,
            )
            available = True
        else:
            retrospective_reasons = (RetrospectiveReasonCode.HISTORICAL_EVIDENCE_MISSING,)
            available = False
        results.append(
            RetrospectiveCandidateResult(
                task=candidate.task,
                historical_behavior_available=available,
                reason_codes=tuple(sorted(retrospective_reasons, key=str)),
            )
        )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "screen_id": "m8a-v6-retrospective-screen-v1",
        "status": "RETROSPECTIVE_NON_QUALIFYING",
        "policy_reference": policy.policy_reference.model_dump(mode="json"),
        "historical_control_path": "release/core-real-matrix-v6-control.json",
        "historical_control_digest": _json_digest(control_path),
        "historical_analysis_path": "release/core-real-matrix-v6-final-analysis.json",
        "historical_analysis_digest": _json_digest(analysis_path),
        "historical_task_count": 18,
        "historical_configuration_count": 7,
        "historical_repetitions": 5,
        "current_memberships_created": 0,
        "results": [item.model_dump(mode="json") for item in results],
    }
    payload["screen_digest"] = canonical_digest(payload)
    return RetrospectiveScreen.model_validate(payload)


def _stress_dimensions(
    task: CandidateInventoryItem,
    tier_b: TierBQualificationArtifact,
) -> tuple[StressDimensionAssessment, ...]:
    evidence = next(item for item in tier_b.tasks if item.task_id == task.task.task_id)
    declared_multi_module = "module" in evidence.engineering_shape
    multi_file_proven = len(evidence.oracle_changed_files) >= 3 and declared_multi_module
    shared_identity = canonical_digest(
        {
            "qualification_digest": tier_b.qualification_digest,
            "task_id": evidence.task_id,
            "oracle_changed_files": evidence.oracle_changed_files,
            "engineering_shape": evidence.engineering_shape,
            "verifier_identity": evidence.verifier_identity,
            "robustness_variants": [
                item.model_dump(mode="json") for item in evidence.robustness_variants
            ],
        }
    )
    statuses = {
        StressDimensionName.TRAJECTORY: (
            StressEvidenceStatus.REQUIRES_EMPIRICAL_EVIDENCE,
            "TWO_INDEPENDENT_NORMALIZED_TRACE_BLOCKS_REQUIRED",
            None,
        ),
        StressDimensionName.MULTI_FILE: (
            (
                StressEvidenceStatus.PROVEN_KEYLESS
                if multi_file_proven
                else StressEvidenceStatus.NOT_PROVEN
            ),
            (
                "THREE_FILES_AND_DECLARED_MODULE_BOUNDARY_PROVEN"
                if multi_file_proven
                else "THREE_FILE_CROSS_BOUNDARY_THRESHOLD_NOT_PROVEN"
            ),
            shared_identity if multi_file_proven else None,
        ),
        StressDimensionName.TOOL_USE: (
            StressEvidenceStatus.NOT_PROVEN,
            "CAPABILITY_WITHHOLDING_BOUNDARIES_NOT_EVIDENCED",
            None,
        ),
        StressDimensionName.REPAIR_LOOP: (
            StressEvidenceStatus.NOT_PROVEN,
            "PARTIAL_MILESTONES_AND_TRACE_RECOVERY_NOT_EVIDENCED",
            None,
        ),
        StressDimensionName.DEPENDENCY_BUILD: (
            StressEvidenceStatus.NOT_PROVEN,
            "LOCK_IDENTITY_AND_TWO_PHASE_BUILD_NOT_EVIDENCED",
            None,
        ),
        StressDimensionName.CONTEXT: (
            StressEvidenceStatus.NOT_PROVEN,
            "RELEVANCE_MANIFEST_AND_CONTEXT_THRESHOLD_NOT_EVIDENCED",
            None,
        ),
        StressDimensionName.PROTOCOL: (
            StressEvidenceStatus.NOT_PROVEN,
            "TWO_PROTOCOL_FAULT_INJECTIONS_NOT_EVIDENCED",
            None,
        ),
    }
    return tuple(
        StressDimensionAssessment(
            dimension=dimension,
            status=statuses[dimension][0],
            reason_code=statuses[dimension][1],
            evidence_identity=statuses[dimension][2],
        )
        for dimension in sorted(StressDimensionName, key=lambda item: item.value)
    )


def build_stress_audit(
    repository_root: Path, inventory: CandidateInventory
) -> StressPortfolioAudit:
    tier_b = load_tier_b_qualification(repository_root / "release/tier-b-qualification-v1.json")
    validate_tier_b_qualification(repository_root, tier_b)
    candidates: list[StressCandidateAudit] = []
    for candidate in inventory.candidates:
        if candidate.role is not CandidateRole.TIER_B:
            continue
        dimensions = _stress_dimensions(candidate, tier_b)
        proven = sum(item.status is StressEvidenceStatus.PROVEN_KEYLESS for item in dimensions)
        anchors = {
            StressDimensionName.TRAJECTORY,
            StressDimensionName.CONTEXT,
            StressDimensionName.PROTOCOL,
        }
        has_anchor = any(
            item.dimension in anchors and item.status is StressEvidenceStatus.PROVEN_KEYLESS
            for item in dimensions
        )
        candidates.append(
            StressCandidateAudit(
                task=candidate.task,
                qualification_identity=candidate.qualification.qualification_identity,
                dimensions=dimensions,
                proven_dimension_count=proven,
                has_required_anchor_dimension=has_anchor,
            )
        )
    reasons = tuple(
        sorted(
            {
                "NO_CANDIDATE_PROVES_THREE_STRESS_DIMENSIONS",
                "NO_CANDIDATE_PROVES_TRAJECTORY_CONTEXT_OR_PROTOCOL",
                "REPRESENTED_MULTI_FILE_DIMENSION_HAS_FEWER_THAN_THREE_TASKS",
                "SINGLE_TASK_CREDIT_SHARE_EXCEEDS_ONE_THIRD",
                "TIER_B_QUALIFICATION_IS_NOT_STRESS_MEMBERSHIP",
            }
        )
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "audit_id": "m8a-keyless-stress-audit-v1",
        "minimum_dimensions_per_member": 3,
        "required_anchor_dimensions": ["CONTEXT", "PROTOCOL", "TRAJECTORY"],
        "minimum_tasks_per_represented_dimension": 3,
        "minimum_languages_for_language_independent_dimension": 2,
        "maximum_single_task_credit_share_numerator": 1,
        "maximum_single_task_credit_share_denominator": 3,
        "candidates": [
            item.model_dump(mode="json")
            for item in sorted(candidates, key=lambda item: item.task.task_id)
        ],
        "portfolio_reason_codes": list(reasons),
        "stress_suite_release_ready": False,
    }
    payload["audit_digest"] = canonical_digest(payload)
    return StressPortfolioAudit.model_validate(payload)


def build_gap_report(
    inventory: CandidateInventory, stress_audit: StressPortfolioAudit
) -> CoverageGapReport:
    gaps = tuple(
        sorted(
            {
                "DISCRIMINATIVE_FIRST_N3_BLOCK_NOT_RUN",
                "DISCRIMINATIVE_INDEPENDENT_STABILITY_N3_BLOCK_NOT_RUN",
                "DISCRIMINATIVE_MEMBERSHIP_EMPTY",
                "STRESS_ANCHOR_DIMENSIONS_UNPROVEN",
                "STRESS_MEMBER_THRESHOLD_UNMET",
                "STRESS_MULTI_FILE_PORTFOLIO_FLOOR_UNMET",
                "STRESS_PORTFOLIO_CREDIT_SHARE_FLOOR_UNMET",
            }
        )
    )
    required = tuple(
        sorted(
            {
                "ADD_NATURAL_TASKS_SO_EACH_FUTURE_MEMBER_CAN_PROVE_AT_LEAST_THREE_DIMENSIONS",
                "ADD_TASK_COVERAGE_FOR_TRAJECTORY_CONTEXT_OR_PROTOCOL_ANCHOR_EVIDENCE",
                "ADD_A_THIRD_KEYLESS_MULTI_FILE_CROSS_BOUNDARY_CANDIDATE",
                "ADD_CONTEXT_TASKS_WITH_20_RELEVANT_FILES_OR_50_KIB_AND_A_RELEVANCE_MANIFEST",
                "ADD_PROTOCOL_TASKS_WITH_TWO_CLASSIFIED_FAULT_INJECTIONS",
                "ENSURE_EACH_REPRESENTED_DIMENSION_HAS_THREE_TASKS_ACROSS_TWO_LANGUAGES",
                "ENSURE_NO_TASK_EXCEEDS_ONE_THIRD_OF_TOTAL_DIMENSION_CREDITS",
            }
        )
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "report_id": "m8a-coverage-gap-report-v1",
        "candidates_screenable_now": len(inventory.candidates),
        "current_discriminative_memberships": 0,
        "current_stress_memberships": 0,
        "empirical_discriminative_evidence_required": True,
        "stress_suite_release_ready": stress_audit.stress_suite_release_ready,
        "missing_representation_or_stress_coverage": list(gaps),
        "new_tasks_required": True,
        "required_new_task_coverage": list(required),
    }
    payload["report_digest"] = canonical_digest(payload)
    return CoverageGapReport.model_validate(payload)


def build_m8a_preregistration_bundle(repository_root: Path) -> M8APreregistrationBundle:
    inventory = build_candidate_inventory(repository_root)
    policy = build_discriminative_preregistration(repository_root)
    retrospective = build_retrospective_screen(repository_root, inventory, policy)
    stress_audit = build_stress_audit(repository_root, inventory)
    gap_report = build_gap_report(inventory, stress_audit)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "bundle_id": "phase-m8a-keyless-preregistration-v1",
        "source_main_sha": "3335668f4f11e384a9f99fb0a8692f07d8937902",
        "inventory": inventory.model_dump(mode="json"),
        "discriminative_policy": policy.model_dump(mode="json"),
        "retrospective": retrospective.model_dump(mode="json"),
        "stress_audit": stress_audit.model_dump(mode="json"),
        "gap_report": gap_report.model_dump(mode="json"),
        "external_calls": ExternalCallCounts().model_dump(mode="json"),
        "frozen_evidence_modified": False,
    }
    payload["bundle_digest"] = canonical_digest(payload)
    return M8APreregistrationBundle.model_validate(payload)


def load_m8a_preregistration_bundle(path: Path) -> M8APreregistrationBundle:
    try:
        return M8APreregistrationBundle.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PreregistrationError(
            f"invalid M.8-A preregistration bundle: {type(exc).__name__}"
        ) from exc
