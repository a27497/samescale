from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harnesslab.comparability.models import ComparabilityIntent

EvidenceStatus = Literal["REPORTED", "NOT_REPORTED"]
ComparabilityValue = Literal["COMPARABLE", "PARTIALLY_COMPARABLE", "NOT_COMPARABLE"]
MatrixComparabilityValue = Literal[
    "COMPARABLE", "PARTIALLY_COMPARABLE", "NOT_COMPARABLE", "NOT_REPORTED"
]
JudgeReportEvidenceStatus = Literal["REPORTED", "NOT_REPORTED", "INTEGRITY_ERROR"]


class WorkbenchModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NumericEvidence(WorkbenchModel):
    status: EvidenceStatus
    value: float | None = None

    @model_validator(mode="after")
    def status_matches_value(self) -> NumericEvidence:
        if (self.status == "REPORTED") != (self.value is not None):
            raise ValueError("REPORTED evidence requires a value and NOT_REPORTED requires null")
        return self


class IntegerEvidence(WorkbenchModel):
    status: EvidenceStatus
    value: int | None = None

    @model_validator(mode="after")
    def status_matches_value(self) -> IntegerEvidence:
        if (self.status == "REPORTED") != (self.value is not None):
            raise ValueError("REPORTED evidence requires a value and NOT_REPORTED requires null")
        return self


class PublicError(WorkbenchModel):
    code: str
    message: str


class PublicErrorResponse(WorkbenchModel):
    error: PublicError


class ExperimentSummary(WorkbenchModel):
    experiment_id: str
    name: str
    status: str
    plan_digest: str
    cell_count: int
    task_count: int
    planned_run_count: int
    completed_capability_count: int
    infra_count: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ExperimentListResponse(WorkbenchModel):
    items: tuple[ExperimentSummary, ...]
    total: int
    limit: int
    offset: int


class ExperimentCell(WorkbenchModel):
    cell_id: str
    lane: str
    requested_model: str
    provider_route: str
    harness: str
    harness_version: str
    repeat_target: int


class ExperimentTask(WorkbenchModel):
    task_id: str
    task_version: str
    task_digest: str


class ExperimentDetail(ExperimentSummary):
    repeat_count: int
    execution_seed: int
    comparison_intent: str
    evaluation_mode: str
    evidence_tiers: tuple[str, ...]
    comparability_summary: dict[str, int]
    report_digest: str | None
    cells: tuple[ExperimentCell, ...]
    tasks: tuple[ExperimentTask, ...]


class ExperimentStatusResponse(WorkbenchModel):
    experiment_id: str
    status: str
    terminal: bool
    run_status_counts: dict[str, int]
    refreshed_at: datetime


class MatrixMetricSet(WorkbenchModel):
    success_rate: NumericEvidence
    latency_p50_ms: NumericEvidence
    latency_p95_ms: NumericEvidence
    infra_rate: NumericEvidence
    pass_at_1: NumericEvidence
    pass_at_3: NumericEvidence
    pass_at_5: NumericEvidence


class MatrixPoint(WorkbenchModel):
    task_id: str
    cell_id: str
    n: int
    tier: str
    comparability: MatrixComparabilityValue
    reason_codes: tuple[str, ...]
    metrics: MatrixMetricSet


class MatrixResponse(WorkbenchModel):
    experiment_id: str
    plan_digest: str
    report_digest: str
    tasks: tuple[str, ...]
    cells: tuple[str, ...]
    points: tuple[MatrixPoint, ...]
    infra_count: int


class ExperimentReportResponse(WorkbenchModel):
    experiment_id: str
    plan_digest: str
    report_digest: str
    planned_runs: int
    formal_ranking: tuple[str, ...]
    formal_ranking_note: str
    cells: tuple[dict[str, object], ...]
    pairs: tuple[dict[str, object], ...]


class RunSummary(WorkbenchModel):
    run_id: str
    experiment_id: str
    cell_id: str
    task_id: str
    task_version: str
    lane: str
    repeat_index: int
    status: str
    normalized_outcome: str | None
    attempt: int
    duration_ms: IntegerEvidence


class RunListResponse(WorkbenchModel):
    items: tuple[RunSummary, ...]
    total: int
    limit: int
    offset: int


class RunDetail(RunSummary):
    slot_id: str
    source_outcome: str | None
    requested_model: str | None
    observed_model: str | None
    provider_route: str | None
    harness: str | None
    harness_version: str | None
    trace_coverage: str | None
    evidence_digest: str | None
    artifact_name: str | None
    verifier_passed: bool | None
    verifier_score: NumericEvidence
    summary: str | None
    input_tokens: IntegerEvidence
    output_tokens: IntegerEvidence
    explicit_cost: NumericEvidence
    comparability: ComparabilityValue | None
    comparability_reason_codes: tuple[str, ...]


class TraceEvent(WorkbenchModel):
    ordinal: int
    type: str
    status: str | None
    summary: str | None
    exit_code: int | None


class TraceResponse(WorkbenchModel):
    run_id: str
    status: EvidenceStatus
    coverage: str | None
    trace_digest: str | None
    events: tuple[TraceEvent, ...]


class JudgeCalibrationSummary(WorkbenchModel):
    calibration_id: str
    suite_id: str
    suite_version: str
    plan_digest: str
    report_digest: str | None
    status: str
    report_evidence_status: JudgeReportEvidenceStatus
    judge_cell_count: int
    qualifications: tuple[str, ...]
    created_at: datetime
    finished_at: datetime | None


class JudgeCalibrationListResponse(WorkbenchModel):
    items: tuple[JudgeCalibrationSummary, ...]
    total: int
    limit: int
    offset: int


class JudgeCellDetail(WorkbenchModel):
    judge_cell_id: str
    requested_judge_model: str
    qualification: str
    qualification_scope: str
    coverage: NumericEvidence
    label_accuracy: NumericEvidence
    macro_f1: NumericEvidence
    score_mae: NumericEvidence
    spearman_rho: NumericEvidence
    pairwise_accuracy: NumericEvidence
    position_consistency: NumericEvidence
    verbosity_bias_rate: NumericEvidence
    repeat_consistency: NumericEvidence
    provider_infra: int
    l0_disagreements: int
    l0_overrides: int
    qualification_reasons: tuple[str, ...]


class JudgeCalibrationDetail(WorkbenchModel):
    calibration_id: str
    suite_id: str
    suite_version: str
    suite_digest: str
    plan_digest: str
    report_digest: str
    status: str
    real_judge_smoke: str
    cells: tuple[JudgeCellDetail, ...]
    limitations: tuple[str, ...]


class RegressionCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_experiment_id: str = Field(min_length=1, max_length=100)
    candidate_experiment_id: str = Field(min_length=1, max_length=100)
    intent: ComparabilityIntent
    cell_mapping: dict[str, str] = Field(default_factory=dict, max_length=100)

    @field_validator("cell_mapping")
    @classmethod
    def cell_mapping_is_bounded(cls, value: dict[str, str]) -> dict[str, str]:
        if any(
            not key or len(key) > 100 or not target or len(target) > 100
            for key, target in value.items()
        ):
            raise ValueError("cell mapping identities must contain 1 to 100 characters")
        return value


class RegressionCellComparison(WorkbenchModel):
    baseline_cell_id: str
    candidate_cell_id: str
    baseline_value: NumericEvidence
    candidate_value: NumericEvidence
    delta: NumericEvidence
    direction: Literal["IMPROVED", "DECREASED", "UNCHANGED", "NOT_REPORTED"]
    baseline_tier: str
    candidate_tier: str
    comparability: ComparabilityValue
    reason_codes: tuple[str, ...]
    paired_observations: int
    baseline_infra_count: int
    candidate_infra_count: int


class RegressionCompareResponse(WorkbenchModel):
    baseline_experiment_id: str
    candidate_experiment_id: str
    baseline_plan_digest: str
    candidate_plan_digest: str
    baseline_report_digest: str
    candidate_report_digest: str
    intent: ComparabilityIntent
    common_tasks: tuple[str, ...]
    comparisons: tuple[RegressionCellComparison, ...]
    limitation: str


class ReadinessCheck(WorkbenchModel):
    key: str
    label: str
    status: Literal["READY", "BLOCKED", "NOT_REPORTED", "NOT_VERIFIED"]
    evidence: str


class CoreReadinessResponse(WorkbenchModel):
    status: Literal["READY", "NOT_READY"]
    task_corpus_size: int
    checks: tuple[ReadinessCheck, ...]
    blockers: tuple[str, ...]
    evaluated_at: datetime
