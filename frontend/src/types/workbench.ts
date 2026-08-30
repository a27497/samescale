export type EvidenceStatus = 'REPORTED' | 'NOT_REPORTED'
export type Comparability = 'COMPARABLE' | 'PARTIALLY_COMPARABLE' | 'NOT_COMPARABLE'
export type MatrixComparability = Comparability | 'NOT_REPORTED'
export type RegressionIntent =
  | 'MODEL_COMPARISON'
  | 'HARNESS_UPLIFT'
  | 'NATIVE_HARNESS_SYSTEM_COMPARISON'
  | 'GENERAL'

export interface EvidenceValue {
  status: EvidenceStatus
  value: number | null
}

export interface ExperimentSummary {
  experiment_id: string
  name: string
  status: string
  plan_digest: string
  cell_count: number
  task_count: number
  planned_run_count: number
  completed_capability_count: number
  infra_count: number
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface ExperimentListResponse {
  items: ExperimentSummary[]
  total: number
  limit: number
  offset: number
}

export interface ExperimentCell {
  cell_id: string
  lane: string
  requested_model: string
  provider_route: string
  harness: string
  harness_version: string
  repeat_target: number
}

export interface ExperimentTask {
  task_id: string
  task_version: string
  task_digest: string
}

export interface ExperimentDetail extends ExperimentSummary {
  repeat_count: number
  execution_seed: number
  comparison_intent: string
  evaluation_mode: string
  evidence_tiers: string[]
  comparability_summary: Record<string, number>
  report_digest: string | null
  cells: ExperimentCell[]
  tasks: ExperimentTask[]
}

export type AnalysisAvailability = 'AVAILABLE' | 'PARTIAL' | 'NOT_AVAILABLE'

export interface AnalysisRate {
  status: 'AVAILABLE' | 'NOT_AVAILABLE'
  value: number | null
  numerator: number
  denominator: number
}

export interface AnalysisTotal {
  status: AnalysisAvailability
  known_slots: number
  expected_slots: number
  known_total: number | null
  total: number | null
  unit: string
  reason: string | null
}

export interface IdentityCoverage {
  status: AnalysisAvailability
  counts: Record<string, number>
  missing_slots: number
}

export interface TraceCoverageSummary extends IdentityCoverage {}

export interface ModelOutcomeAnalysis {
  model_label: 'MODEL_A' | 'MODEL_B'
  cell_id: string
  requested_model: string
  provider_route: string
  planned_slots: number
  acquired_slots: number
  unacquired_slots: number
  capability_denominator: number
  passed: number
  failed: number
  infra: number
  cancelled: number
  pass_rate: AnalysisRate
  evidence_tier: string
  failure_categories: Record<string, number>
  observed_models: IdentityCoverage
  observed_providers: IdentityCoverage
  trace_coverage: TraceCoverageSummary
  usage_and_cost: {
    input_tokens: AnalysisTotal
    output_tokens: AnalysisTotal
    explicit_cost: AnalysisTotal
  }
}

export interface ModelPairAnalysis {
  planned_pairs: number
  matched_capability_pairs: number
  both_pass: number
  model_a_only_pass: number
  model_b_only_pass: number
  both_fail: number
  infra_pairs: number
  missing_pairs: number
  infra_or_missing_pairs: number
}

export interface PassRateDifferenceAnalysis {
  orientation: 'MODEL_B_MINUS_MODEL_A'
  per_model_capability_pass_rate_difference_pp: number | null
  matched_capability_pair_pass_rate_difference_pp: number | null
}

export interface AnalysisBreakdown {
  dimension: 'language' | 'task_family'
  value: string
  planned_pairs: number
  matched_capability_pairs: number
  both_pass: number
  model_a_only_pass: number
  model_b_only_pass: number
  both_fail: number
  infra_pairs: number
  missing_pairs: number
  model_a_pass_rate: AnalysisRate
  model_b_pass_rate: AnalysisRate
}

export interface ModelComparisonAnalysis {
  schema_version: 1
  report_kind: 'MODEL_COMPARISON_CLOSEOUT'
  experiment_id: string
  plan_digest: string
  comparison_intent: 'MODEL_COMPARISON'
  evidence_source: 'PERSISTED_IMMUTABLE_EXPERIMENT_EVIDENCE'
  conclusion_semantics: {
    scope: 'EXPLORATORY_DESCRIPTIVE' | 'DESCRIPTIVE'
    evaluation_mode: string
    repeat_count: number
    permitted_interpretation: string
  }
  overall: {
    planned_slots: number
    acquired_slots: number
    unacquired_slots: number
    capability_denominator: number
    passed: number
    failed: number
    infra: number
    cancelled: number
    failure_categories: Record<string, number>
  }
  models: [ModelOutcomeAnalysis, ModelOutcomeAnalysis]
  pairs: ModelPairAnalysis
  pass_rate_differences: PassRateDifferenceAnalysis
  comparability: {
    category: Comparability | 'NOT_AVAILABLE'
    assessed_pairs: number
    category_counts: Record<string, number>
    reason_counts: Record<string, number>
    unassessed_planned_pairs: number
  }
  control_drift: {
    status: 'DETECTED' | 'NOT_DETECTED' | 'NOT_AVAILABLE'
    affected_pairs: number
    affected_runs: number
    assessed_pairs: number
    reason_counts: Record<string, number>
  }
  trace_coverage: TraceCoverageSummary
  observed_models: IdentityCoverage
  observed_providers: IdentityCoverage
  recovery_attempts: {
    status: 'AVAILABLE' | 'NOT_AVAILABLE'
    explicitly_marked_primary_acquisitions: number
    explicitly_marked_recovery_acquisitions: number
    unmarked_acquisitions: number
    lease_claim_attempts: number
    note: string
  }
  breakdowns: AnalysisBreakdown[]
}

export interface ModelComparisonCloseout {
  schema_version: 1
  analysis_digest: string
  analysis: ModelComparisonAnalysis
}

export type MatrixMetricKey =
  | 'success_rate'
  | 'latency_p50_ms'
  | 'latency_p95_ms'
  | 'infra_rate'
  | 'pass_at_1'
  | 'pass_at_3'
  | 'pass_at_5'

export interface MatrixPoint {
  task_id: string
  cell_id: string
  n: number
  tier: string
  comparability: MatrixComparability
  reason_codes: string[]
  metrics: Record<MatrixMetricKey, EvidenceValue>
}

export interface MatrixResponse {
  experiment_id: string
  plan_digest: string
  report_digest: string
  tasks: string[]
  cells: string[]
  points: MatrixPoint[]
  infra_count: number
}

export interface RunSummary {
  run_id: string
  experiment_id: string
  cell_id: string
  task_id: string
  task_version: string
  lane: string
  repeat_index: number
  status: string
  normalized_outcome: string | null
  attempt: number
  duration_ms: EvidenceValue
}

export interface RunListResponse {
  items: RunSummary[]
  total: number
  limit: number
  offset: number
}

export interface RunDetail extends RunSummary {
  slot_id: string
  source_outcome: string | null
  requested_model: string | null
  observed_model: string | null
  provider_route: string | null
  harness: string | null
  harness_version: string | null
  trace_coverage: string | null
  evidence_digest: string | null
  artifact_name: string | null
  verifier_passed: boolean | null
  verifier_score: EvidenceValue
  summary: string | null
  input_tokens: EvidenceValue
  output_tokens: EvidenceValue
  explicit_cost: EvidenceValue
  comparability: Comparability | null
  comparability_reason_codes: string[]
}

export interface TraceEvent {
  ordinal: number
  type: string
  status: string | null
  summary: string | null
  exit_code: number | null
}

export interface TraceResponse {
  run_id: string
  status: EvidenceStatus
  coverage: string | null
  trace_digest: string | null
  events: TraceEvent[]
}

export interface ExperimentStatus {
  experiment_id: string
  status: string
  terminal: boolean
  run_status_counts: Record<string, number>
  refreshed_at: string
}

export interface JudgeCalibrationSummary {
  calibration_id: string
  suite_id: string
  suite_version: string
  plan_digest: string
  report_digest: string | null
  status: string
  report_evidence_status: 'REPORTED' | 'NOT_REPORTED' | 'INTEGRITY_ERROR'
  judge_cell_count: number
  qualifications: string[]
  created_at: string
  finished_at: string | null
}

export interface JudgeCellDetail {
  judge_cell_id: string
  requested_judge_model: string
  qualification: string
  qualification_scope: string
  coverage: EvidenceValue
  label_accuracy: EvidenceValue
  macro_f1: EvidenceValue
  score_mae: EvidenceValue
  spearman_rho: EvidenceValue
  pairwise_accuracy: EvidenceValue
  position_consistency: EvidenceValue
  verbosity_bias_rate: EvidenceValue
  repeat_consistency: EvidenceValue
  provider_infra: number
  l0_disagreements: number
  l0_overrides: number
  qualification_reasons: string[]
}

export interface JudgeCalibrationDetail {
  calibration_id: string
  suite_id: string
  suite_version: string
  suite_digest: string
  plan_digest: string
  report_digest: string
  status: string
  real_judge_smoke: string
  cells: JudgeCellDetail[]
  limitations: string[]
}

export interface RegressionComparison {
  baseline_cell_id: string
  candidate_cell_id: string
  baseline_value: EvidenceValue
  candidate_value: EvidenceValue
  delta: EvidenceValue
  direction: 'IMPROVED' | 'DECREASED' | 'UNCHANGED' | 'NOT_REPORTED'
  baseline_tier: string
  candidate_tier: string
  comparability: Comparability
  reason_codes: string[]
  paired_observations: number
  baseline_infra_count: number
  candidate_infra_count: number
}

export interface RegressionResponse {
  baseline_experiment_id: string
  candidate_experiment_id: string
  baseline_plan_digest: string
  candidate_plan_digest: string
  baseline_report_digest: string
  candidate_report_digest: string
  intent: RegressionIntent
  common_tasks: string[]
  comparisons: RegressionComparison[]
  limitation: string
}

export interface ReadinessCheck {
  key: string
  label: string
  status: 'READY' | 'BLOCKED' | 'NOT_REPORTED' | 'NOT_VERIFIED'
  evidence: string
}

export interface CoreReadiness {
  status: 'READY' | 'NOT_READY'
  task_corpus_size: number
  checks: ReadinessCheck[]
  blockers: string[]
  evaluated_at: string
}
