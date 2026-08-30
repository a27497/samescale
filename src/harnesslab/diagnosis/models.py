from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DiagnosisModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


BadCaseLimitation = Literal[
    "Real BadCases require verified immutable evidence; synthetic qualification cases are "
    "labeled and never counted as real BadCases."
]


class FailureClass(StrEnum):
    COMPILE_FAILURE = "Compile Failure"
    TEST_FAILURE = "Test Failure"
    TIMEOUT = "Timeout"
    PROVIDER_FAILURE = "Provider Failure"
    HARNESS_PROTOCOL_FAILURE = "Harness Protocol Failure"
    TOOL_FAILURE = "Tool Failure"
    NO_MODIFICATION = "No Modification"
    WRONG_FILES = "Wrong Files"
    PROTECTED_FILE_MUTATION = "Protected File Mutation"
    DEPENDENCY_FAILURE = "Dependency Failure"
    VERIFIER_FAILURE = "Verifier Failure"
    ARTIFACT_FAILURE = "Artifact Failure"


class FailureScope(StrEnum):
    CAPABILITY = "CAPABILITY"
    INFRASTRUCTURE = "INFRASTRUCTURE"


class EvidenceOrigin(StrEnum):
    IMMUTABLE_EXPERIMENT = "IMMUTABLE_EXPERIMENT"
    SYNTHETIC_QUALIFICATION = "SYNTHETIC_QUALIFICATION"


class AttributionKind(StrEnum):
    VERIFIED_FACT = "VERIFIED_FACT"
    HYPOTHESIS = "HYPOTHESIS"


class CausalStrength(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CORRELATION_ONLY = "CORRELATION_ONLY"
    CONTROLLED_ABLATION_ASSOCIATION = "CONTROLLED_ABLATION_ASSOCIATION"


class TraceEventEvidence(DiagnosisModel):
    ordinal: int = Field(ge=1)
    type: str = Field(min_length=1, max_length=100)
    status: str | None = Field(default=None, max_length=100)
    exit_code: int | None = None


class TraceEvidence(DiagnosisModel):
    status: Literal["REPORTED", "NOT_REPORTED"]
    coverage: str | None = Field(default=None, max_length=100)
    digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    pattern: str = Field(min_length=1, max_length=500)
    events: tuple[TraceEventEvidence, ...] = ()


class WorkspacePathEvidence(DiagnosisModel):
    path: str = Field(min_length=1, max_length=1000)
    status: str = Field(min_length=1, max_length=100)


class WorkspaceDiffEvidence(DiagnosisModel):
    status: Literal["REPORTED", "DIGEST_ONLY", "NOT_REPORTED"]
    input_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    output_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    pattern: str = Field(min_length=1, max_length=500)
    changed_paths: tuple[WorkspacePathEvidence, ...] = ()
    protected_paths_changed: tuple[str, ...] = ()


class ToolCallEvidence(DiagnosisModel):
    status: Literal["REPORTED", "NOT_REPORTED"]
    count: int | None = Field(default=None, ge=0)
    pattern: str = Field(min_length=1, max_length=500)
    failed_exit_codes: tuple[int, ...] = ()


class VerifierEvidence(DiagnosisModel):
    status: Literal["PASSED", "FAILED", "NOT_RUN", "NOT_REPORTED"]
    score: float | None = Field(default=None, ge=0, le=1)
    sandbox_status: str | None = Field(default=None, max_length=100)
    failure_subtype: str | None = Field(default=None, max_length=100)


class DiagnosisInput(DiagnosisModel):
    """Safe normalized facts accepted by the deterministic diagnosis engine.

    Production inputs are assembled only from database identities, verified manifests,
    normalized traces, and frozen task metadata. Synthetic inputs must remain explicitly labeled.
    """

    run_id: str = Field(min_length=1, max_length=100)
    origin: EvidenceOrigin
    cell_id: str = Field(min_length=1, max_length=100)
    task_id: str = Field(min_length=1, max_length=100)
    task_version: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=300)
    harness: str = Field(min_length=1, max_length=100)
    language: str = Field(min_length=1, max_length=100)
    task_family: str = Field(min_length=1, max_length=100)
    normalized_outcome: str = Field(min_length=1, max_length=100)
    source_outcome: str | None = Field(default=None, max_length=100)
    declared_failure_class: FailureClass | None = None
    provider_failure: str | None = Field(default=None, max_length=100)
    harness_failure: str | None = Field(default=None, max_length=100)
    artifact_available: bool
    evidence_identity: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    trace: TraceEvidence
    workspace_diff: WorkspaceDiffEvidence
    tool_calls: ToolCallEvidence
    verifier: VerifierEvidence


class Attribution(DiagnosisModel):
    kind: AttributionKind
    statement: str = Field(min_length=1, max_length=500)
    evidence_references: tuple[str, ...] = ()
    causal_strength: CausalStrength
    caveat: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def facts_and_hypotheses_are_explicit(self) -> Attribution:
        if self.kind is AttributionKind.VERIFIED_FACT:
            if (
                not self.evidence_references
                or self.causal_strength is not CausalStrength.NOT_APPLICABLE
            ):
                raise ValueError("verified facts require evidence and cannot claim causal strength")
            if self.caveat is not None:
                raise ValueError("verified facts cannot carry a hypothesis caveat")
        elif self.caveat is None or self.causal_strength is CausalStrength.NOT_APPLICABLE:
            raise ValueError("hypotheses require a causal caveat and strength")
        return self


class DiagnosisRun(DiagnosisModel):
    run_id: str = Field(min_length=1, max_length=100)
    origin: EvidenceOrigin
    task_id: str = Field(min_length=1, max_length=100)
    task_version: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=300)
    harness: str = Field(min_length=1, max_length=100)
    language: str = Field(min_length=1, max_length=100)
    task_family: str = Field(min_length=1, max_length=100)
    failure_class: FailureClass
    failure_scope: FailureScope
    artifact_verified: bool
    evidence_identity: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    trace: TraceEvidence
    workspace_diff: WorkspaceDiffEvidence
    tool_calls: ToolCallEvidence
    verifier: VerifierEvidence
    attributions: tuple[Attribution, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def attribution_kinds_are_complete(self) -> DiagnosisRun:
        if self.artifact_verified != (self.evidence_identity is not None):
            raise ValueError("verified artifact state and evidence identity disagree")
        kinds = {item.kind for item in self.attributions}
        if kinds != {AttributionKind.VERIFIED_FACT, AttributionKind.HYPOTHESIS}:
            raise ValueError("each diagnosed run requires verified fact and hypothesis attribution")
        return self


class FailureCluster(DiagnosisModel):
    cluster_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dimensions: dict[str, str]
    failure_class: FailureClass
    failure_scope: FailureScope
    run_count: int = Field(ge=1)
    real_run_count: int = Field(ge=0)
    synthetic_run_count: int = Field(ge=0)
    runs: tuple[DiagnosisRun, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def counts_match_runs(self) -> FailureCluster:
        real = sum(run.origin is EvidenceOrigin.IMMUTABLE_EXPERIMENT for run in self.runs)
        synthetic = len(self.runs) - real
        if (self.run_count, self.real_run_count, self.synthetic_run_count) != (
            len(self.runs),
            real,
            synthetic,
        ):
            raise ValueError("cluster counts do not match runs")
        return self


class TaskFamilyDiagnosis(DiagnosisModel):
    task_family: str
    clusters: tuple[FailureCluster, ...] = Field(min_length=1)


class CellDiagnosis(DiagnosisModel):
    cell_id: str
    task_families: tuple[TaskFamilyDiagnosis, ...] = Field(min_length=1)


class DiagnosisReport(DiagnosisModel):
    schema_version: Literal[1] = 1
    experiment_id: str
    plan_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    report_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    cluster_dimensions: tuple[str, ...]
    correlation_warning: Literal[
        "Trace correlation is not causality; only controlled ablation can strengthen attribution."
    ] = "Trace correlation is not causality; only controlled ablation can strengthen attribution."
    classification_limitations: tuple[str, ...] = (
        "Compile, dependency, and wrong-file subtypes require explicit structured evidence; "
        "free-form output is never guessed into a taxonomy.",
        "Trace, tool, and workspace patterns are correlation features, not causal findings.",
    )
    failure_run_count: int = Field(ge=0)
    real_run_count: int = Field(ge=0)
    synthetic_run_count: int = Field(ge=0)
    cells: tuple[CellDiagnosis, ...]


class BadCaseExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_ids: tuple[str, ...] = Field(default=(), max_length=100)
    include_synthetic_qualification: bool = False


class BadCase(DiagnosisModel):
    case_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    run_id: str
    origin: EvidenceOrigin
    cluster_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    task_id: str
    task_version: str
    model: str
    harness: str
    language: str
    task_family: str
    failure_class: FailureClass
    failure_scope: FailureScope
    evidence_identity: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    identity_kind: Literal["IMMUTABLE_EVIDENCE", "SYNTHETIC_QUALIFICATION"]
    verifier_status: Literal["PASSED", "FAILED", "NOT_RUN", "NOT_REPORTED"]
    verifier_score: float | None = Field(default=None, ge=0, le=1)
    trace_pattern: str
    tool_pattern: str
    workspace_diff_pattern: str
    attribution_kinds: tuple[AttributionKind, ...]


class BadCaseExport(DiagnosisModel):
    schema_version: Literal[1] = 1
    experiment_id: str
    source_report_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    export_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    requested_cluster_ids: tuple[str, ...]
    real_case_count: int = Field(ge=0)
    synthetic_qualification_case_count: int = Field(ge=0)
    cases: tuple[BadCase, ...]
    limitation: BadCaseLimitation = (
        "Real BadCases require verified immutable evidence; synthetic qualification cases are "
        "labeled and never counted as real BadCases."
    )
