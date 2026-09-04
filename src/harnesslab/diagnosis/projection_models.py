from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from harnesslab.diagnosis.models import CausalStrength, DiagnosisModel, FailureClass, FailureScope


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class AttemptSelectionPolicy(StrEnum):
    PRIMARY_ONLY = "PRIMARY_ONLY"
    EFFECTIVE_EXPLICIT = "EFFECTIVE_EXPLICIT"


class AttemptReadPath(StrEnum):
    AUTHORITATIVE_ATTEMPT = "AUTHORITATIVE_ATTEMPT"
    LEGACY_COMPATIBILITY = "LEGACY_COMPATIBILITY"


class ProjectionDimension(StrEnum):
    MODEL = "MODEL"
    HARNESS = "HARNESS"
    TASK = "TASK"
    LANGUAGE = "LANGUAGE"
    TASK_FAMILY = "TASK_FAMILY"
    FAILURE_CLASS = "FAILURE_CLASS"
    FAILURE_SCOPE = "FAILURE_SCOPE"
    TRACE_PATTERN = "TRACE_PATTERN"
    TOOL_PATTERN = "TOOL_PATTERN"
    WORKSPACE_DIFF_PATTERN = "WORKSPACE_DIFF_PATTERN"


class MissingValuePolicy(StrEnum):
    SEPARATE_UNKNOWN = "SEPARATE_UNKNOWN"
    EXCLUDE_WITH_REASON = "EXCLUDE_WITH_REASON"


class CohortPolicy(StrEnum):
    EXPLICIT_COMPATIBLE_EXPERIMENTS = "EXPLICIT_COMPATIBLE_EXPERIMENTS"


class OperationalTerminalState(StrEnum):
    FAILED_CAPABILITY = "FAILED_CAPABILITY"
    FAILED_INFRA = "FAILED_INFRA"
    CANCELLED = "CANCELLED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class DiagnosticLayer(StrEnum):
    DETERMINISTIC_FACT = "DETERMINISTIC_FACT"
    DIAGNOSTIC_CLUSTER = "DIAGNOSTIC_CLUSTER"
    ATTRIBUTION_HYPOTHESIS = "ATTRIBUTION_HYPOTHESIS"
    CONTROLLED_EVIDENCE = "CONTROLLED_EVIDENCE"


FULL_TUPLE_PROJECTION_DIMENSIONS = tuple(ProjectionDimension)
FAILURE_FACT_CONTRACT_VERSION = "failure-fact-v1"
FAILURE_NORMALIZATION_VERSION = "diagnosis-normalization-v1"
UNKNOWN_DIMENSION_VALUE = "__UNKNOWN__"
PROJECTED_CLUSTER_CAUSAL_LIMITATION = (
    "Trace correlation is not causality; diagnostic clustering does not establish a shared root "
    "cause or increase causal strength."
)


class RawFailureFact(DiagnosisModel):
    """Allowlisted immutable failure evidence, independent of cluster projection identity."""

    schema_version: Literal[1] = 1
    contract_version: Literal["failure-fact-v1"] = "failure-fact-v1"
    normalization_version: str = Field(min_length=1, max_length=100)
    fact_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    experiment_id: str = Field(min_length=1, max_length=100)
    plan_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    logical_run_id: str = Field(min_length=1, max_length=100)
    cell_id: str = Field(min_length=1, max_length=100)
    slot_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    physical_attempt_id: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    attempt_number: int | None = Field(default=None, ge=1)
    attempt_role: Literal["PRIMARY", "RECOVERY", "LEGACY_COMPATIBILITY"]
    is_primary_attempt: bool
    is_effective_attempt_at_snapshot: bool
    read_path: AttemptReadPath
    evidence_identity: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    artifact_verified: bool
    model: str | None = Field(default=None, min_length=1, max_length=300)
    harness: str | None = Field(default=None, min_length=1, max_length=100)
    task_id: str | None = Field(default=None, min_length=1, max_length=100)
    task_version: str = Field(min_length=1, max_length=100)
    language: str | None = Field(default=None, min_length=1, max_length=100)
    task_family: str | None = Field(default=None, min_length=1, max_length=100)
    failure_class: FailureClass
    failure_scope: FailureScope
    trace_pattern: str | None = Field(default=None, min_length=1, max_length=500)
    tool_pattern: str | None = Field(default=None, min_length=1, max_length=500)
    workspace_diff_pattern: str | None = Field(default=None, min_length=1, max_length=500)
    deterministic_layer: Literal[DiagnosticLayer.DETERMINISTIC_FACT] = (
        DiagnosticLayer.DETERMINISTIC_FACT
    )

    @model_validator(mode="after")
    def identity_is_stable_and_attempt_shape_is_explicit(self) -> RawFailureFact:
        if self.artifact_verified != (self.evidence_identity is not None):
            raise ValueError("verified raw-fact artifact state and evidence identity disagree")
        if self.read_path is AttemptReadPath.AUTHORITATIVE_ATTEMPT:
            if self.physical_attempt_id is None or self.attempt_number is None:
                raise ValueError("authoritative raw facts require a physical attempt identity")
            if self.attempt_role == "LEGACY_COMPATIBILITY":
                raise ValueError("authoritative raw facts cannot use the legacy attempt role")
        elif (
            self.physical_attempt_id is not None
            or self.attempt_number is not None
            or self.attempt_role != "LEGACY_COMPATIBILITY"
        ):
            raise ValueError("legacy raw facts cannot fabricate a physical attempt")
        payload = self.model_dump(
            mode="json",
            exclude={"fact_digest", "is_effective_attempt_at_snapshot"},
        )
        if self.fact_digest != _canonical_digest(payload):
            raise ValueError("raw failure fact digest does not match its immutable source facts")
        return self


class ClusterProjection(DiagnosisModel):
    schema_version: Literal[1] = 1
    projection_id: str = Field(min_length=1, max_length=100)
    projection_version: str = Field(min_length=1, max_length=100)
    normalization_version: str = Field(min_length=1, max_length=100)
    dimensions: tuple[ProjectionDimension, ...] = Field(min_length=1)
    missing_value_policy: MissingValuePolicy
    evidence_snapshot_identity: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    cohort_policy: CohortPolicy
    namespace: str = Field(min_length=1, max_length=100)
    projection_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def dimensions_and_digest_are_canonical(self) -> ClusterProjection:
        if len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError("cluster projection dimensions must be unique")
        payload = self.model_dump(mode="json", exclude={"projection_digest"})
        if self.projection_digest != _canonical_digest(payload):
            raise ValueError("cluster projection digest does not match its policy")
        return self


class ClusterProjectionRequest(DiagnosisModel):
    projection_id: str = Field(min_length=1, max_length=100)
    projection_version: str = Field(min_length=1, max_length=100)
    normalization_version: str = Field(
        default=FAILURE_NORMALIZATION_VERSION, min_length=1, max_length=100
    )
    dimensions: tuple[ProjectionDimension, ...] = Field(
        default=FULL_TUPLE_PROJECTION_DIMENSIONS, min_length=1
    )
    missing_value_policy: MissingValuePolicy = MissingValuePolicy.SEPARATE_UNKNOWN
    namespace: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def dimensions_are_unique(self) -> ClusterProjectionRequest:
        if len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError("cluster projection dimensions must be unique")
        return self


class ProjectedClusterReadRequest(DiagnosisModel):
    attempt_selection: AttemptSelectionPolicy
    projection: ClusterProjectionRequest
    additional_experiment_ids: tuple[str, ...] = Field(default=(), max_length=24)

    @model_validator(mode="after")
    def additional_experiments_are_unique(self) -> ProjectedClusterReadRequest:
        if len(set(self.additional_experiment_ids)) != len(self.additional_experiment_ids):
            raise ValueError("cohort experiment identities must be unique")
        return self


class CohortMember(DiagnosisModel):
    experiment_id: str = Field(min_length=1, max_length=100)
    plan_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence_snapshot_identity: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence_contract_version: Literal["failure-fact-v1"] = "failure-fact-v1"


class FailureCohort(DiagnosisModel):
    namespace: str = Field(min_length=1, max_length=100)
    projection_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    projection_version: str = Field(min_length=1, max_length=100)
    normalization_version: str = Field(min_length=1, max_length=100)
    policy: Literal[CohortPolicy.EXPLICIT_COMPATIBLE_EXPERIMENTS] = (
        CohortPolicy.EXPLICIT_COMPATIBLE_EXPERIMENTS
    )
    members: tuple[CohortMember, ...] = Field(min_length=1)
    diagnostic_only: Literal[True] = True
    comparability_claim: Literal[False] = False
    cohort_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def members_and_digest_are_canonical(self) -> FailureCohort:
        identities = tuple(member.experiment_id for member in self.members)
        if identities != tuple(sorted(identities)) or len(set(identities)) != len(identities):
            raise ValueError("cohort members must be unique and sorted")
        payload = self.model_dump(mode="json", exclude={"cohort_digest"})
        if self.cohort_digest != _canonical_digest(payload):
            raise ValueError("failure cohort digest does not match its exact members")
        return self


class ExcludedFailureFact(DiagnosisModel):
    fact_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason: Literal["MISSING_SELECTED_DIMENSION"] = "MISSING_SELECTED_DIMENSION"
    missing_dimensions: tuple[ProjectionDimension, ...] = Field(min_length=1)


class ControlledEvidenceBinding(DiagnosisModel):
    fact_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence_reference: str = Field(min_length=1, max_length=500)
    layer: Literal[DiagnosticLayer.CONTROLLED_EVIDENCE] = DiagnosticLayer.CONTROLLED_EVIDENCE
    causal_strength: Literal[CausalStrength.CONTROLLED_ABLATION_ASSOCIATION] = (
        CausalStrength.CONTROLLED_ABLATION_ASSOCIATION
    )
    limitation: Literal[
        "Controlled evidence remains separately bound; cluster membership does not increase "
        "causal strength."
    ] = (
        "Controlled evidence remains separately bound; cluster membership does not increase "
        "causal strength."
    )


class ProjectedFailureCluster(DiagnosisModel):
    cluster_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    projection_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    cohort_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence_snapshot_identity: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dimensions: dict[ProjectionDimension, str]
    raw_fact_digests: tuple[str, ...] = Field(min_length=1)
    facts: tuple[RawFailureFact, ...] = Field(min_length=1)
    layer: Literal[DiagnosticLayer.DIAGNOSTIC_CLUSTER] = DiagnosticLayer.DIAGNOSTIC_CLUSTER
    causal_strength: Literal[CausalStrength.CORRELATION_ONLY] = CausalStrength.CORRELATION_ONLY
    causal_limitation: Literal[
        "Trace correlation is not causality; diagnostic clustering does not establish a shared "
        "root cause or increase causal strength."
    ] = (
        "Trace correlation is not causality; diagnostic clustering does not establish a shared "
        "root cause or increase causal strength."
    )

    @model_validator(mode="after")
    def membership_is_exact_and_non_causal(self) -> ProjectedFailureCluster:
        digests = tuple(fact.fact_digest for fact in self.facts)
        if digests != self.raw_fact_digests or digests != tuple(sorted(digests)):
            raise ValueError("projected cluster fact membership must be exact and sorted")
        return self


class AttemptReadSummary(DiagnosisModel):
    experiment_id: str
    logical_run_id: str
    read_path: AttemptReadPath
    selection_policy: AttemptSelectionPolicy
    primary_attempt_id: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    primary_outcome: str
    recovery_attempt_ids: tuple[str, ...] = ()
    recovery_outcomes: tuple[str, ...] = ()
    selected_attempt_id: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    selected_attempt_role: Literal["PRIMARY", "RECOVERY", "LEGACY_COMPATIBILITY"]
    recovery_selected_as_effective: bool

    @model_validator(mode="after")
    def attempt_lists_and_selection_match(self) -> AttemptReadSummary:
        if len(self.recovery_attempt_ids) != len(self.recovery_outcomes):
            raise ValueError("recovery attempt identities and outcomes disagree")
        if self.read_path is AttemptReadPath.LEGACY_COMPATIBILITY and (
            self.primary_attempt_id is not None
            or self.selected_attempt_id is not None
            or self.recovery_attempt_ids
            or self.selected_attempt_role != "LEGACY_COMPATIBILITY"
        ):
            raise ValueError("legacy read summaries cannot fabricate physical attempts")
        if self.recovery_selected_as_effective != (self.selected_attempt_role == "RECOVERY"):
            raise ValueError("effective recovery selection flag disagrees with selected role")
        return self


class OperationalTerminalCounts(DiagnosisModel):
    failed_capability: int = Field(ge=0)
    failed_infra: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    budget_exhausted: int = Field(ge=0)


class ProjectedClusterReport(DiagnosisModel):
    schema_version: Literal[1] = 1
    report_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    projection: ClusterProjection
    cohort: FailureCohort
    attempt_selection: AttemptSelectionPolicy
    evidence_contract_version: Literal["failure-fact-v1"] = "failure-fact-v1"
    raw_fact_count: int = Field(ge=0)
    clustered_fact_count: int = Field(ge=0)
    excluded_fact_count: int = Field(ge=0)
    unknown_grouped_fact_count: int = Field(ge=0)
    operational_terminal_counts: OperationalTerminalCounts
    all_attempt_terminal_counts: OperationalTerminalCounts
    attempt_reads: tuple[AttemptReadSummary, ...]
    excluded_facts: tuple[ExcludedFailureFact, ...]
    controlled_evidence: tuple[ControlledEvidenceBinding, ...] = ()
    clusters: tuple[ProjectedFailureCluster, ...]
    causal_layers: tuple[DiagnosticLayer, ...] = (
        DiagnosticLayer.DETERMINISTIC_FACT,
        DiagnosticLayer.DIAGNOSTIC_CLUSTER,
        DiagnosticLayer.ATTRIBUTION_HYPOTHESIS,
        DiagnosticLayer.CONTROLLED_EVIDENCE,
    )
    causal_limitation: Literal[
        "Trace correlation is not causality; diagnostic clustering does not establish a shared "
        "root cause or increase causal strength."
    ] = (
        "Trace correlation is not causality; diagnostic clustering does not establish a shared "
        "root cause or increase causal strength."
    )
    cross_experiment_limitation: Literal[
        "Cross-experiment clustering is diagnostic grouping, not a formal comparability or "
        "performance claim."
    ] = (
        "Cross-experiment clustering is diagnostic grouping, not a formal comparability or "
        "performance claim."
    )

    @model_validator(mode="after")
    def counts_match_auditable_membership(self) -> ProjectedClusterReport:
        clustered = sum(len(cluster.facts) for cluster in self.clusters)
        if clustered != self.clustered_fact_count:
            raise ValueError("projected clustered fact count does not match membership")
        if len(self.excluded_facts) != self.excluded_fact_count:
            raise ValueError("projected excluded fact count does not match audit records")
        if self.raw_fact_count != self.clustered_fact_count + self.excluded_fact_count:
            raise ValueError("projected raw fact accounting is incomplete")
        return self
