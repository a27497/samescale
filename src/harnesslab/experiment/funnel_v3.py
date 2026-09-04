from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.comparability.models import ComparabilityStatus, canonical_digest
from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.evaluation_suites.admission import GovernanceNamespace
from harnesslab.evaluation_suites.models import (
    ImmutableArtifactReference,
    SuiteManifestReference,
    SuitePurpose,
    VersionedPolicyReference,
)


class FunnelV3Error(ValueError):
    """Funnel-v3 methodology, evidence, decision, or chain is invalid."""


class FunnelV3Stage(StrEnum):
    PREFLIGHT = "PREFLIGHT"
    SMOKE = "SMOKE"
    INFORMAL = "INFORMAL"
    FORMAL = "FORMAL"
    DISCRIMINATIVE = "DISCRIMINATIVE"
    STRESS = "STRESS"

    @property
    def number(self) -> int:
        return tuple(FunnelV3Stage).index(self)

    @property
    def repeat_count(self) -> int | None:
        return {
            FunnelV3Stage.PREFLIGHT: None,
            FunnelV3Stage.SMOKE: 1,
            FunnelV3Stage.INFORMAL: 3,
            FunnelV3Stage.FORMAL: 5,
            FunnelV3Stage.DISCRIMINATIVE: None,
            FunnelV3Stage.STRESS: None,
        }[self]

    @property
    def suite_purpose(self) -> SuitePurpose | None:
        return {
            FunnelV3Stage.PREFLIGHT: None,
            FunnelV3Stage.SMOKE: None,
            FunnelV3Stage.INFORMAL: None,
            FunnelV3Stage.FORMAL: None,
            FunnelV3Stage.DISCRIMINATIVE: SuitePurpose.DISCRIMINATIVE,
            FunnelV3Stage.STRESS: SuitePurpose.STRESS,
        }[self]


class StageDecisionValue(StrEnum):
    GO = "GO"
    STOP = "STOP"


class StageDecisionReasonCode(StrEnum):
    SOURCE_EXIT_SATISFIED = "SOURCE_EXIT_SATISFIED"
    TARGET_ENTRY_SATISFIED = "TARGET_ENTRY_SATISFIED"
    EXPLICIT_AUTHORIZED_ACTOR = "EXPLICIT_AUTHORIZED_ACTOR"
    SOURCE_EXIT_NOT_SATISFIED = "SOURCE_EXIT_NOT_SATISFIED"
    TARGET_ENTRY_NOT_SATISFIED = "TARGET_ENTRY_NOT_SATISFIED"
    NONCOMPARABLE_EVIDENCE = "NONCOMPARABLE_EVIDENCE"
    INCOMPLETE_COVERAGE = "INCOMPLETE_COVERAGE"
    OPERATOR_STOP = "OPERATOR_STOP"


class EvidenceRoleV3(StrEnum):
    PRIMARY = "PRIMARY"
    RECOVERY = "RECOVERY"


class FunnelMethodologyReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    methodology_id: Identifier
    methodology_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    methodology_digest: Sha256Digest


class FunnelStagePolicyV3(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage_number: int = Field(ge=0, le=5)
    stage: FunnelV3Stage
    repeat_count: Literal[1, 3, 5] | None = None
    selection_scope: str = Field(min_length=1, max_length=500)
    entry_policy: VersionedPolicyReference
    exit_policy: VersionedPolicyReference
    suite_requirement: SuitePurpose | None = None
    explicit_decision_required: Literal[True] = True
    auto_promote: Literal[False] = False

    @model_validator(mode="after")
    def semantics_match_stage(self) -> FunnelStagePolicyV3:
        if self.stage_number != self.stage.number:
            raise ValueError("stage number does not match Funnel v3 semantics")
        if self.repeat_count != self.stage.repeat_count:
            raise ValueError("repeat count does not match Funnel v3 stage semantics")
        if self.suite_requirement is not self.stage.suite_purpose:
            raise ValueError("suite requirement does not match Funnel v3 stage semantics")
        return self


class FunnelMethodologyV3(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[3] = 3
    methodology_id: Literal["harnesslab-evaluation-funnel-v3"] = "harnesslab-evaluation-funnel-v3"
    methodology_version: Literal["3.0.0"] = "3.0.0"
    stages: tuple[FunnelStagePolicyV3, ...]
    automatic_promotion_allowed: Literal[False] = False
    execution_authorization_separate: Literal[True] = True
    methodology_digest: Sha256Digest

    @model_validator(mode="after")
    def methodology_is_complete_and_self_identifying(self) -> FunnelMethodologyV3:
        if tuple(item.stage for item in self.stages) != tuple(FunnelV3Stage):
            raise ValueError("Funnel v3 stages must be complete and canonical")
        if self.methodology_digest != canonical_digest(self.payload()):
            raise ValueError("Funnel v3 methodology digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"methodology_digest"})

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def as_reference(self) -> FunnelMethodologyReference:
        return FunnelMethodologyReference(
            methodology_id=self.methodology_id,
            methodology_version=self.methodology_version,
            methodology_digest=self.methodology_digest,
        )

    def policy_for(self, stage: FunnelV3Stage) -> FunnelStagePolicyV3:
        return self.stages[stage.number]


def _policy_reference(label: str) -> VersionedPolicyReference:
    payload = {
        "policy_id": f"funnel-v3-{label}",
        "policy_version": "3.0.0",
    }
    return VersionedPolicyReference(
        **payload,
        policy_digest=canonical_digest(payload),
    )


def build_funnel_v3_methodology() -> FunnelMethodologyV3:
    scopes = {
        FunnelV3Stage.PREFLIGHT: "keyless validation of one exact frozen plan and snapshot",
        FunnelV3Stage.SMOKE: "bounded exact one-repeat selection",
        FunnelV3Stage.INFORMAL: "bounded exact three-repeat selection",
        FunnelV3Stage.FORMAL: "bounded exact five-repeat fail-closed comparable selection",
        FunnelV3Stage.DISCRIMINATIVE: "exact versioned Discriminative Suite membership",
        FunnelV3Stage.STRESS: "exact versioned Stress Suite membership",
    }
    stages = tuple(
        FunnelStagePolicyV3(
            stage_number=stage.number,
            stage=stage,
            repeat_count=stage.repeat_count,
            selection_scope=scopes[stage],
            entry_policy=_policy_reference(f"stage-{stage.number}-entry"),
            exit_policy=_policy_reference(f"stage-{stage.number}-exit"),
            suite_requirement=stage.suite_purpose,
        )
        for stage in FunnelV3Stage
    )
    payload = {
        "schema_version": 3,
        "methodology_id": "harnesslab-evaluation-funnel-v3",
        "methodology_version": "3.0.0",
        "stages": [item.model_dump(mode="json") for item in stages],
        "automatic_promotion_allowed": False,
        "execution_authorization_separate": True,
    }
    payload["methodology_digest"] = canonical_digest(payload)
    return FunnelMethodologyV3.model_validate(payload)


class StageCoverageFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    planned_observations: int = Field(ge=0)
    terminal_observations: int = Field(ge=0)
    capability_observations: int = Field(ge=0)
    infrastructure_observations: int = Field(ge=0)
    missing_observations: int = Field(ge=0)
    eligible_primary_observations: int = Field(ge=0)
    primary_repeats_per_unit: int = Field(ge=0)
    primary_repeat_indices: tuple[int, ...] = ()
    all_scheduled_accounted: bool
    optional_stopping_observed: Literal[False] = False

    @model_validator(mode="after")
    def counts_and_repeats_reconcile(self) -> StageCoverageFacts:
        if self.terminal_observations + self.missing_observations != self.planned_observations:
            raise ValueError("coverage terminal and missing observations do not reconcile")
        if (
            self.capability_observations + self.infrastructure_observations
            != self.terminal_observations
        ):
            raise ValueError("capability and infrastructure observations do not reconcile")
        if self.eligible_primary_observations > self.capability_observations:
            raise ValueError("eligible primary observations cannot exceed capability evidence")
        expected = tuple(range(self.primary_repeats_per_unit))
        if self.primary_repeat_indices != expected:
            raise ValueError("primary repeat indices must be exact, unique, and zero-based")
        if self.all_scheduled_accounted != (self.missing_observations == 0):
            raise ValueError("coverage accounting flag disagrees with missing observations")
        return self


class StageComparabilityFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ComparabilityStatus
    comparability_reference: ImmutableArtifactReference
    primary_recovery_separated: Literal[True] = True
    deterministic_verifier_authoritative: Literal[True] = True
    infrastructure_outside_capability_denominator: Literal[True] = True


class PreflightBudgetFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    preflight_reference: ImmutableArtifactReference
    budget_reference: ImmutableArtifactReference
    preflight_passed: bool
    provider_calls: int = Field(ge=0)
    harness_calls: int = Field(ge=0)
    judge_calls: int = Field(ge=0)
    matrix_calls: int = Field(ge=0)
    external_execution_authorized: Literal[False] = False


def _policy_key(reference: VersionedPolicyReference) -> tuple[str, str, str]:
    return reference.policy_id, reference.policy_version, reference.policy_digest


class StageMaterialIdentity(BaseModel):
    """Scientifically material identities that determine chain continuity and reuse."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace: GovernanceNamespace
    methodology: FunnelMethodologyReference
    task_selection_identity: Sha256Digest
    cell_configuration_identity: Sha256Digest
    controls_identity: Sha256Digest
    resource_envelope_identity: Sha256Digest
    relevant_policies: tuple[VersionedPolicyReference, ...]
    suite_manifest: SuiteManifestReference | None = None

    @model_validator(mode="after")
    def policy_identities_are_unique_and_canonical(self) -> StageMaterialIdentity:
        ordered = tuple(sorted(set(self.relevant_policies), key=_policy_key))
        if self.relevant_policies != ordered:
            raise ValueError("material policy identities must be unique and canonical")
        return self

    @property
    def identity(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class StageEvidence(BaseModel):
    """Immutable source-stage evidence snapshot used by exactly one explicit decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    evidence_id: Identifier
    stage: FunnelV3Stage
    source_plan: ImmutableArtifactReference
    source_report: ImmutableArtifactReference
    material_identity: StageMaterialIdentity
    coverage: StageCoverageFacts
    comparability: StageComparabilityFacts
    budget_preflight: PreflightBudgetFacts
    evidence_digest: Sha256Digest

    @model_validator(mode="after")
    def evidence_is_stage_bound_and_self_identifying(self) -> StageEvidence:
        required_purpose = self.stage.suite_purpose
        suite = self.material_identity.suite_manifest
        if required_purpose is not None and (
            suite is None or suite.purpose is not required_purpose
        ):
            raise ValueError("source-stage evidence requires the exact stage suite purpose")
        if required_purpose is None and suite is not None:
            raise ValueError("pre-suite stage evidence cannot claim a suite identity")
        if self.evidence_digest != canonical_digest(self.payload()):
            raise ValueError("stage evidence digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"evidence_digest"})

    def as_reference(self) -> ImmutableArtifactReference:
        return ImmutableArtifactReference(
            artifact_id=self.evidence_id,
            schema_version=self.schema_version,
            artifact_digest=self.evidence_digest,
        )


class DecisionActorAuthorization(BaseModel):
    """Authority to decide plan eligibility; deliberately not execution authorization."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_id: Identifier
    actor_identity: Sha256Digest
    decision_authorization_identity: Sha256Digest
    external_execution_authorized: Literal[False] = False


def _reason_key(reason: StageDecisionReasonCode) -> str:
    return reason.value


_GO_REASONS = (
    StageDecisionReasonCode.EXPLICIT_AUTHORIZED_ACTOR,
    StageDecisionReasonCode.SOURCE_EXIT_SATISFIED,
    StageDecisionReasonCode.TARGET_ENTRY_SATISFIED,
)


class StageDecision(BaseModel):
    """Immutable evidence-bound Funnel-v3 decision; never an execution authorization."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    decision_id: Identifier
    source_stage: FunnelV3Stage
    target_stage: FunnelV3Stage
    decision: StageDecisionValue
    source_plan: ImmutableArtifactReference
    source_report: ImmutableArtifactReference
    source_evidence: ImmutableArtifactReference
    source_material_identity: StageMaterialIdentity
    target_material_identity: StageMaterialIdentity
    methodology: FunnelMethodologyReference
    suite_manifest: SuiteManifestReference | None = None
    relevant_policies: tuple[VersionedPolicyReference, ...]
    coverage_facts: StageCoverageFacts
    comparability_facts: StageComparabilityFacts
    budget_preflight_facts: PreflightBudgetFacts
    reason_codes: tuple[StageDecisionReasonCode, ...]
    actor_authorization: DecisionActorAuthorization
    authorizes_plan_creation_only: Literal[True] = True
    external_execution_authorized: Literal[False] = False
    decision_digest: Sha256Digest

    @model_validator(mode="after")
    def decision_is_adjacent_bound_and_self_identifying(self) -> StageDecision:
        if self.target_stage.number != self.source_stage.number + 1:
            raise ValueError("Funnel v3 transitions must be adjacent and forward")
        if self.methodology != self.source_material_identity.methodology:
            raise ValueError("source evidence methodology identity is stale or mismatched")
        if self.methodology != self.target_material_identity.methodology:
            raise ValueError("target methodology identity is stale or mismatched")
        if self.suite_manifest != self.target_material_identity.suite_manifest:
            raise ValueError("target suite identity is stale or mismatched")
        reconstructed_source = {
            "schema_version": self.source_evidence.schema_version,
            "evidence_id": self.source_evidence.artifact_id,
            "stage": self.source_stage.value,
            "source_plan": self.source_plan.model_dump(mode="json"),
            "source_report": self.source_report.model_dump(mode="json"),
            "material_identity": self.source_material_identity.model_dump(mode="json"),
            "coverage": self.coverage_facts.model_dump(mode="json"),
            "comparability": self.comparability_facts.model_dump(mode="json"),
            "budget_preflight": self.budget_preflight_facts.model_dump(mode="json"),
        }
        if canonical_digest(reconstructed_source) != self.source_evidence.artifact_digest:
            raise ValueError("source plan/report or evidence facts are stale or mismatched")
        required_purpose = self.target_stage.suite_purpose
        if required_purpose is not None and (
            self.suite_manifest is None or self.suite_manifest.purpose is not required_purpose
        ):
            raise ValueError("target stage requires the correct versioned suite identity")
        if required_purpose is None and self.suite_manifest is not None:
            raise ValueError("non-suite target stage cannot claim a suite identity")
        ordered_policies = tuple(sorted(set(self.relevant_policies), key=_policy_key))
        if self.relevant_policies != ordered_policies:
            raise ValueError("decision policy identities must be unique and canonical")
        ordered_reasons = tuple(sorted(set(self.reason_codes), key=_reason_key))
        if self.reason_codes != ordered_reasons:
            raise ValueError("decision reason codes must be unique and canonical")
        if self.decision is StageDecisionValue.GO and self.reason_codes != _GO_REASONS:
            raise ValueError("GO requires exact mechanical and actor authorization reasons")
        if self.decision is StageDecisionValue.STOP and (
            not self.reason_codes or set(self.reason_codes) & set(_GO_REASONS)
        ):
            raise ValueError("STOP requires only explicit blocking reason codes")
        if self.decision is StageDecisionValue.GO:
            _validate_source_exit_facts(
                stage=self.source_stage,
                coverage=self.coverage_facts,
                comparability=self.comparability_facts,
                budget_preflight=self.budget_preflight_facts,
            )
        if self.decision_digest != canonical_digest(self.payload()):
            raise ValueError("stage decision digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"decision_digest"})

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def as_reference(self) -> ImmutableArtifactReference:
        return ImmutableArtifactReference(
            artifact_id=self.decision_id,
            schema_version=self.schema_version,
            artifact_digest=self.decision_digest,
        )


def _validate_source_exit_facts(
    *,
    stage: FunnelV3Stage,
    coverage: StageCoverageFacts,
    comparability: StageComparabilityFacts,
    budget_preflight: PreflightBudgetFacts,
) -> None:
    if stage is FunnelV3Stage.PREFLIGHT:
        facts = budget_preflight
        if not facts.preflight_passed:
            raise FunnelV3Error("Stage 0 exit requires a passing preflight reference")
        if any((facts.provider_calls, facts.harness_calls, facts.judge_calls, facts.matrix_calls)):
            raise FunnelV3Error("Stage 0 must remain keyless with zero external calls")
        return
    if not coverage.all_scheduled_accounted or coverage.eligible_primary_observations == 0:
        raise FunnelV3Error(
            "source stage coverage is incomplete or lacks eligible primary evidence"
        )
    required_repeats = stage.repeat_count
    if required_repeats is not None and coverage.primary_repeats_per_unit != required_repeats:
        raise FunnelV3Error(f"{stage.value} evidence requires n={required_repeats}")
    if stage is FunnelV3Stage.FORMAL and (
        comparability.status is not ComparabilityStatus.COMPARABLE
    ):
        raise FunnelV3Error("Formal evidence must be COMPARABLE to support GO")


def _validate_source_exit_for_go(evidence: StageEvidence) -> None:
    _validate_source_exit_facts(
        stage=evidence.stage,
        coverage=evidence.coverage,
        comparability=evidence.comparability,
        budget_preflight=evidence.budget_preflight,
    )


def build_stage_evidence(
    *,
    evidence_id: str,
    stage: FunnelV3Stage,
    source_plan: ImmutableArtifactReference,
    source_report: ImmutableArtifactReference,
    material_identity: StageMaterialIdentity,
    coverage: StageCoverageFacts,
    comparability: StageComparabilityFacts,
    budget_preflight: PreflightBudgetFacts,
) -> StageEvidence:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "evidence_id": evidence_id,
        "stage": stage.value,
        "source_plan": source_plan.model_dump(mode="json"),
        "source_report": source_report.model_dump(mode="json"),
        "material_identity": material_identity.model_dump(mode="json"),
        "coverage": coverage.model_dump(mode="json"),
        "comparability": comparability.model_dump(mode="json"),
        "budget_preflight": budget_preflight.model_dump(mode="json"),
    }
    payload["evidence_digest"] = canonical_digest(payload)
    try:
        return StageEvidence.model_validate(payload)
    except ValueError as exc:
        raise FunnelV3Error(str(exc)) from exc


def validate_stage_decision(
    decision: StageDecision,
    *,
    source_evidence: StageEvidence,
    methodology: FunnelMethodologyV3,
) -> None:
    if decision.source_evidence != source_evidence.as_reference():
        raise FunnelV3Error("stage decision source evidence is stale or mismatched")
    if decision.source_plan != source_evidence.source_plan:
        raise FunnelV3Error("stage decision source plan digest is stale or mismatched")
    if decision.source_report != source_evidence.source_report:
        raise FunnelV3Error("stage decision source report digest is stale or mismatched")
    if decision.source_material_identity != source_evidence.material_identity:
        raise FunnelV3Error("stage decision source controls or identity changed")
    if decision.source_stage is not source_evidence.stage:
        raise FunnelV3Error("stage decision does not identify the source evidence stage")
    if decision.methodology != methodology.as_reference():
        raise FunnelV3Error("stage decision methodology identity is stale or mismatched")
    source_policy = methodology.policy_for(decision.source_stage)
    target_policy = methodology.policy_for(decision.target_stage)
    required = {source_policy.exit_policy, target_policy.entry_policy}
    if not required <= set(decision.relevant_policies):
        raise FunnelV3Error("stage decision is missing source-exit or target-entry policy identity")
    if decision.decision is StageDecisionValue.GO:
        _validate_source_exit_for_go(source_evidence)


def build_stage_decision(
    *,
    decision_id: str,
    decision: StageDecisionValue,
    source_evidence: StageEvidence,
    target_stage: FunnelV3Stage,
    target_material_identity: StageMaterialIdentity,
    methodology: FunnelMethodologyV3,
    actor_authorization: DecisionActorAuthorization,
    reason_codes: tuple[StageDecisionReasonCode, ...] = (),
) -> StageDecision:
    if target_stage.number != source_evidence.stage.number + 1:
        raise FunnelV3Error("Funnel v3 transitions must be adjacent and forward")
    if source_evidence.material_identity.methodology != methodology.as_reference():
        raise FunnelV3Error("source evidence methodology identity is stale or mismatched")
    if target_material_identity.methodology != methodology.as_reference():
        raise FunnelV3Error("target methodology identity is stale or mismatched")
    source_policy = methodology.policy_for(source_evidence.stage)
    target_policy = methodology.policy_for(target_stage)
    policies = tuple(
        sorted(
            set(target_material_identity.relevant_policies)
            | {source_policy.exit_policy, target_policy.entry_policy},
            key=_policy_key,
        )
    )
    reasons = (
        _GO_REASONS
        if decision is StageDecisionValue.GO
        else tuple(sorted(set(reason_codes), key=_reason_key))
    )
    if decision is StageDecisionValue.GO:
        _validate_source_exit_for_go(source_evidence)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "decision_id": decision_id,
        "source_stage": source_evidence.stage.value,
        "target_stage": target_stage.value,
        "decision": decision.value,
        "source_plan": source_evidence.source_plan.model_dump(mode="json"),
        "source_report": source_evidence.source_report.model_dump(mode="json"),
        "source_evidence": source_evidence.as_reference().model_dump(mode="json"),
        "source_material_identity": source_evidence.material_identity.model_dump(mode="json"),
        "target_material_identity": target_material_identity.model_dump(mode="json"),
        "methodology": methodology.as_reference().model_dump(mode="json"),
        "suite_manifest": (
            None
            if target_material_identity.suite_manifest is None
            else target_material_identity.suite_manifest.model_dump(mode="json")
        ),
        "relevant_policies": [item.model_dump(mode="json") for item in policies],
        "coverage_facts": source_evidence.coverage.model_dump(mode="json"),
        "comparability_facts": source_evidence.comparability.model_dump(mode="json"),
        "budget_preflight_facts": source_evidence.budget_preflight.model_dump(mode="json"),
        "reason_codes": [item.value for item in reasons],
        "actor_authorization": actor_authorization.model_dump(mode="json"),
        "authorizes_plan_creation_only": True,
        "external_execution_authorized": False,
    }
    payload["decision_digest"] = canonical_digest(payload)
    try:
        result = StageDecision.model_validate(payload)
        validate_stage_decision(result, source_evidence=source_evidence, methodology=methodology)
        return result
    except ValueError as exc:
        if isinstance(exc, FunnelV3Error):
            raise
        raise FunnelV3Error(str(exc)) from exc


class StageChainLink(BaseModel):
    """One append-only proof that a GO decision made a target plan eligible."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    chain_id: Sha256Digest
    sequence: int = Field(ge=0)
    stage: FunnelV3Stage
    material_identity: StageMaterialIdentity
    source_evidence: ImmutableArtifactReference
    stage_decision: ImmutableArtifactReference
    eligible_plan: ImmutableArtifactReference
    predecessor_chain_id: Sha256Digest | None = None
    predecessor_link_digest: Sha256Digest | None = None
    started_new_chain: bool
    link_digest: Sha256Digest

    @model_validator(mode="after")
    def link_is_complete_and_self_identifying(self) -> StageChainLink:
        if (self.predecessor_chain_id is None) != (self.predecessor_link_digest is None):
            raise ValueError("chain predecessor identity and digest must appear together")
        if self.link_digest != canonical_digest(self.payload()):
            raise ValueError("stage chain link digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"link_digest"})


def build_stage_chain_link(
    *,
    decision: StageDecision,
    eligible_plan: ImmutableArtifactReference,
    predecessor: StageChainLink | None = None,
) -> StageChainLink:
    if decision.decision is not StageDecisionValue.GO:
        raise FunnelV3Error("STOP terminates a chain and cannot make a plan eligible")
    if predecessor is not None and (
        predecessor.stage is not decision.source_stage
        or predecessor.material_identity != decision.source_material_identity
        or predecessor.eligible_plan != decision.source_plan
    ):
        raise FunnelV3Error("chain predecessor does not bind the exact source stage plan")
    material_changed = (
        predecessor is None or predecessor.material_identity != decision.target_material_identity
    )
    if material_changed or predecessor is None:
        chain_id = canonical_digest(
            {
                "material_identity": decision.target_material_identity.identity,
                "originating_decision": decision.decision_digest,
            }
        )
        sequence = 0
    else:
        chain_id = predecessor.chain_id
        sequence = predecessor.sequence + 1
    payload: dict[str, Any] = {
        "schema_version": 1,
        "chain_id": chain_id,
        "sequence": sequence,
        "stage": decision.target_stage.value,
        "material_identity": decision.target_material_identity.model_dump(mode="json"),
        "source_evidence": decision.source_evidence.model_dump(mode="json"),
        "stage_decision": decision.as_reference().model_dump(mode="json"),
        "eligible_plan": eligible_plan.model_dump(mode="json"),
        "predecessor_chain_id": None if predecessor is None else predecessor.chain_id,
        "predecessor_link_digest": None if predecessor is None else predecessor.link_digest,
        "started_new_chain": material_changed,
    }
    payload["link_digest"] = canonical_digest(payload)
    return StageChainLink.model_validate(payload)


__all__ = [
    "DecisionActorAuthorization",
    "EvidenceRoleV3",
    "FunnelMethodologyReference",
    "FunnelMethodologyV3",
    "FunnelStagePolicyV3",
    "FunnelV3Error",
    "FunnelV3Stage",
    "PreflightBudgetFacts",
    "StageChainLink",
    "StageComparabilityFacts",
    "StageCoverageFacts",
    "StageDecision",
    "StageDecisionReasonCode",
    "StageDecisionValue",
    "StageEvidence",
    "StageMaterialIdentity",
    "build_funnel_v3_methodology",
    "build_stage_chain_link",
    "build_stage_decision",
    "build_stage_evidence",
    "validate_stage_decision",
]
