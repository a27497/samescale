import type { ComparisonExample } from '@/types/comparison'

// UI fixture only. Python tests independently reconcile the actual frozen sources.
export const comparisonFixture: ComparisonExample = {
  kind: 'historical_comparison', case_id: 'gpt56-relay-direct-vs-codex', experiment_id: 'fixture-comparison',
  recorded_at: '2026-09-02T00:00:00Z', plan_digest: 'sha256:fixture-plan', dataset_digest: 'sha256:fixture-data',
  task_count: 18, repeat_count: 5, request_timeout_seconds: 180, output_tokens_per_request: 2000, plan_timeout_seconds: 300, read_only: true,
  cells: [
    { cell_id: 'direct-fixture', requested_model: 'fixture-model', provider: 'fixture-relay', harness: 'direct-model', reasoning_effort: 'medium', planned: 90, passed: 83, failed: 3, denominator: 86, infra_missing: 4, cancelled: 0, primary_passed: 73, recovery_attempts: 14, recovered_passes: 10, test_failures: 2, budget_failures: 0, output_failures: 1, primary_latency_ms: 14971, latency_observations: 77, estimated_cost_usd: 1.8977553, explicit_cost_usd: null },
    { cell_id: 'codex-fixture', requested_model: 'fixture-model', provider: 'fixture-relay', harness: 'codex', reasoning_effort: 'medium', planned: 90, passed: 65, failed: 21, denominator: 86, infra_missing: 3, cancelled: 1, primary_passed: 50, recovery_attempts: 19, recovered_passes: 15, test_failures: 3, budget_failures: 18, output_failures: 0, primary_latency_ms: 108293.5, latency_observations: 90, estimated_cost_usd: 6.57549, explicit_cost_usd: null },
  ],
  comparison: {
    causal_interpretation_permitted: false,
    comparability: { formal_eligible: false, complete_pair_comparability: { PARTIALLY_COMPARABLE: 82 } },
    descriptive_statistics: { capability: { complete_pairs: 82, total_possible_pairs: 90, both_pass: 62, both_fail: 2, discordant_baseline_pass_variant_fail: 17, discordant_baseline_fail_variant_pass: 1, delta: -.193518518519, complete_pair_row_weighted_delta: -.19512195122, cluster_bootstrap_ci: { low: -.2574, high: -.1287 } } },
    discordance_summary: { excluded_missing_pairs: 8, failure_taxonomy: { Timeout: 16, 'Test Failure': 2 } },
  },
  failure: { case_id: 'badcase-fixture', task_id: 'core-python-deduplicate', task_version: '1.0.2', run_id: 'fixture-run', cell_id: 'direct-fixture', input_expression: 'record_success("", "x")', verifier: { passed: false, score: .8, checks: [{ name: 'first-records', passed: true }, { name: 'identical-retry-idempotent', passed: true }, { name: 'conflict-rejected', passed: true }, { name: 'conflict-preserves-original', passed: true }, { name: 'empty-key-rejected', passed: false }] }, source_diffs: ['+ fixture source'], root_cause: null, trace_status: 'NOT_REPORTED', both_member_bundles_verified: false },
  sources: [
    { id: 'result-0', path: 'release/fixture.json', sha256: 'sha256:fixture', pointer: '/cells/direct', data: { capability_pass: 83, capability_evaluable: 86 } },
    { id: 'failure', path: 'release/failure-fixture.json', sha256: 'sha256:failure-fixture', pointer: '/slots/2', data: { root_cause: null, observed: '<img src=x onerror=alert(1)>' } },
  ],
}
