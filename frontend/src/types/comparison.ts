export interface ComparisonCell {
  cell_id: string
  requested_model: string
  provider: string
  harness: string
  reasoning_effort: string
  planned: number
  passed: number
  failed: number
  denominator: number
  infra_missing: number
  cancelled: number
  primary_passed: number
  recovery_attempts: number
  recovered_passes: number
  test_failures: number
  budget_failures: number
  output_failures: number
  primary_latency_ms: number | null
  latency_observations: number
  estimated_cost_usd: number | null
  explicit_cost_usd: null
}
export interface ComparisonSource {
  id: string
  path: string
  sha256: string
  pointer: string
  data: unknown
}
export interface ComparisonExample {
  kind: 'historical_comparison'
  case_id: 'gpt56-relay-direct-vs-codex'
  experiment_id: string
  recorded_at: string
  plan_digest: string
  dataset_digest: string
  task_count: number
  repeat_count: number
  request_timeout_seconds: number
  output_tokens_per_request: number
  plan_timeout_seconds: number
  read_only: true
  cells: [ComparisonCell, ComparisonCell]
  comparison: {
    causal_interpretation_permitted: false
    comparability: { formal_eligible: false; complete_pair_comparability: Record<string, number> }
    descriptive_statistics: {
      capability: {
        complete_pairs: number; total_possible_pairs: number; both_pass: number; both_fail: number
        discordant_baseline_pass_variant_fail: number; discordant_baseline_fail_variant_pass: number
        delta: number; complete_pair_row_weighted_delta: number
        cluster_bootstrap_ci: { low: number; high: number }
      }
    }
    discordance_summary: { excluded_missing_pairs: number; failure_taxonomy: Record<string, number> }
  }
  failure: {
    case_id: string; task_id: string; task_version: string; run_id: string; cell_id: string
    input_expression: string
    verifier: { passed: false; score: number; checks: { name: string; passed: boolean }[] }
    source_diffs: string[]; root_cause: null; trace_status: string; both_member_bundles_verified: boolean
  }
  sources: ComparisonSource[]
}
