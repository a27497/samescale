import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import EvidenceValue from '@/components/EvidenceValue.vue'
import MatrixHeatmap from '@/components/MatrixHeatmap.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import TraceTimeline from '@/components/TraceTimeline.vue'
import { escapeTooltipText } from '@/charts/safeTooltip'
import router from '@/router'
import { useExperimentStore } from '@/stores/experiments'
import CoreReadinessView from '@/views/CoreReadinessView.vue'
import ExperimentsView from '@/views/ExperimentsView.vue'
import ExperimentDetailView from '@/views/ExperimentDetailView.vue'
import JudgeDetailView from '@/views/JudgeDetailView.vue'
import JudgeLabView from '@/views/JudgeLabView.vue'
import RegressionView from '@/views/RegressionView.vue'
import RunDetailView from '@/views/RunDetailView.vue'

const api = vi.hoisted(() => ({
  listExperiments: vi.fn(),
  getExperiment: vi.fn(),
  getMatrix: vi.fn(),
  getModelComparisonAnalysis: vi.fn(),
  getRuns: vi.fn(),
  getStatus: vi.fn(),
  getRun: vi.fn(),
  getTrace: vi.fn(),
  listCalibrations: vi.fn(),
  getCalibration: vi.fn(),
  compare: vi.fn(),
  readiness: vi.fn(),
}))

vi.mock('@/api/client', () => ({ workbenchApi: api }))

const reported = (value: number) => ({ status: 'REPORTED' as const, value })
const notReported = { status: 'NOT_REPORTED' as const, value: null }

const experiment = {
  experiment_id: 'matrix-keyless', name: 'Keyless Matrix', status: 'completed',
  plan_digest: 'sha256:plan', cell_count: 2, task_count: 2, planned_run_count: 12,
  completed_capability_count: 12, infra_count: 0, created_at: '2026-08-23T00:00:00Z',
  started_at: '2026-08-23T00:00:01Z', finished_at: '2026-08-23T00:01:00Z',
}

const matrix = {
  experiment_id: 'matrix-keyless', plan_digest: 'sha256:plan', report_digest: 'sha256:report',
  tasks: ['micro-python-clamp', 'micro-typescript-clamp'], cells: ['direct', 'codex'], infra_count: 0,
  points: [
    {
      task_id: 'micro-python-clamp', cell_id: 'direct', n: 3, tier: 'INFORMAL',
      comparability: 'NOT_COMPARABLE' as const, reason_codes: ['HARD_CONTROL_MISMATCH'],
      metrics: {
        success_rate: reported(1), latency_p50_ms: reported(12), latency_p95_ms: reported(18),
        infra_rate: reported(0), pass_at_1: reported(1), pass_at_3: reported(1), pass_at_5: notReported,
      },
    },
    {
      task_id: 'micro-typescript-clamp', cell_id: 'direct', n: 3, tier: 'INFORMAL',
      comparability: 'NOT_REPORTED' as const, reason_codes: [],
      metrics: {
        success_rate: reported(.25), latency_p50_ms: reported(31), latency_p95_ms: reported(39),
        infra_rate: reported(0), pass_at_1: reported(.25), pass_at_3: reported(.5), pass_at_5: notReported,
      },
    },
    {
      task_id: 'micro-typescript-clamp', cell_id: 'codex', n: 3, tier: 'INFORMAL',
      comparability: 'PARTIALLY_COMPARABLE' as const, reason_codes: ['TRACE_COVERAGE_LIMITED'],
      metrics: {
        success_rate: reported(.75), latency_p50_ms: reported(41), latency_p95_ms: reported(49),
        infra_rate: reported(0), pass_at_1: reported(.75), pass_at_3: reported(1), pass_at_5: notReported,
      },
    },
    {
      task_id: 'micro-python-clamp', cell_id: 'codex', n: 3, tier: 'INFORMAL',
      comparability: 'PARTIALLY_COMPARABLE' as const, reason_codes: ['OBSERVED_MODEL_MISSING'],
      metrics: {
        success_rate: reported(1), latency_p50_ms: reported(20), latency_p95_ms: reported(25),
        infra_rate: reported(0), pass_at_1: reported(1), pass_at_3: reported(1), pass_at_5: notReported,
      },
    },
  ],
}

const run = {
  run_id: 'run-safe', experiment_id: 'matrix-keyless', cell_id: 'codex', task_id: 'micro-python-clamp',
  task_version: '1.0.0', lane: 'H', repeat_index: 0, status: 'completed',
  normalized_outcome: 'capability_pass', attempt: 1, duration_ms: reported(20), slot_id: 'sha256:slot',
  source_outcome: 'verified_pass', requested_model: 'fake-model', observed_model: null,
  provider_route: 'fake-route', harness: 'codex', harness_version: '0.149.0',
  trace_coverage: 'FULL_STREAM', evidence_digest: 'sha256:evidence', artifact_name: 'manifest.json',
  verifier_passed: true, verifier_score: reported(1), summary: 'safe summary',
  input_tokens: reported(10), output_tokens: reported(4), explicit_cost: notReported,
  comparability: 'PARTIALLY_COMPARABLE' as const, comparability_reason_codes: ['OBSERVED_MODEL_MISSING'],
}

const trace = {
  run_id: 'run-safe', status: 'REPORTED' as const, coverage: 'FULL_STREAM', trace_digest: 'sha256:trace',
  events: [{ ordinal: 1, type: 'REASONING_PRESENT', status: null, summary: 'NATIVE_REASONING_CONTENT_MUST_STAY_HIDDEN', exit_code: null }],
}

const modelComparison = {
  schema_version: 1 as const,
  analysis_digest: 'sha256:analysis',
  analysis: {
    schema_version: 1 as const, report_kind: 'MODEL_COMPARISON_CLOSEOUT' as const,
    experiment_id: 'matrix-keyless', plan_digest: 'sha256:plan', comparison_intent: 'MODEL_COMPARISON' as const,
    evidence_source: 'PERSISTED_IMMUTABLE_EXPERIMENT_EVIDENCE' as const,
    conclusion_semantics: { scope: 'EXPLORATORY_DESCRIPTIVE' as const, evaluation_mode: 'QUICK', repeat_count: 1, permitted_interpretation: 'QUICK n=1 results are exploratory/descriptive only.' },
    overall: { planned_slots: 8, acquired_slots: 7, unacquired_slots: 1, capability_denominator: 5, passed: 3, failed: 2, infra: 2, cancelled: 0, failure_categories: { CAPABILITY_FAILURE: 1, PROVIDER_INFRASTRUCTURE: 1, VERIFIER_INFRASTRUCTURE: 1, BUDGET_EXHAUSTION: 1, INCOMPLETE_PROVIDER_OUTPUT: 1, CONTROL_DRIFT: 1, UNACQUIRED_SLOT: 1 } },
    models: [
      { model_label: 'MODEL_A' as const, cell_id: 'a', requested_model: 'fixture-a', provider_route: 'fixture-route', planned_slots: 4, acquired_slots: 4, unacquired_slots: 0, capability_denominator: 3, passed: 2, failed: 1, infra: 1, cancelled: 0, pass_rate: { status: 'AVAILABLE' as const, value: 2 / 3, numerator: 2, denominator: 3 }, evidence_tier: 'SMOKE', failure_categories: {}, observed_models: { status: 'AVAILABLE' as const, counts: { 'fixture-a': 4 }, missing_slots: 0 }, observed_providers: { status: 'AVAILABLE' as const, counts: { fixture: 4 }, missing_slots: 0 }, trace_coverage: { status: 'PARTIAL' as const, counts: { FULL_STREAM: 3 }, missing_slots: 1 }, usage_and_cost: { input_tokens: { status: 'AVAILABLE' as const, known_slots: 4, expected_slots: 4, known_total: 100, total: 100, unit: 'tokens', reason: null }, output_tokens: { status: 'AVAILABLE' as const, known_slots: 4, expected_slots: 4, known_total: 40, total: 40, unit: 'tokens', reason: null }, explicit_cost: { status: 'NOT_AVAILABLE' as const, known_slots: 0, expected_slots: 4, known_total: null, total: null, unit: 'USD', reason: 'incomplete' } } },
      { model_label: 'MODEL_B' as const, cell_id: 'b', requested_model: 'fixture-b', provider_route: 'fixture-route', planned_slots: 4, acquired_slots: 3, unacquired_slots: 1, capability_denominator: 2, passed: 1, failed: 1, infra: 1, cancelled: 0, pass_rate: { status: 'AVAILABLE' as const, value: .5, numerator: 1, denominator: 2 }, evidence_tier: 'SMOKE', failure_categories: {}, observed_models: { status: 'PARTIAL' as const, counts: { 'fixture-b': 2 }, missing_slots: 1 }, observed_providers: { status: 'AVAILABLE' as const, counts: { fixture: 3 }, missing_slots: 0 }, trace_coverage: { status: 'PARTIAL' as const, counts: { FINAL_OUTPUT_ONLY: 2 }, missing_slots: 1 }, usage_and_cost: { input_tokens: { status: 'PARTIAL' as const, known_slots: 2, expected_slots: 3, known_total: 50, total: null, unit: 'tokens', reason: null }, output_tokens: { status: 'PARTIAL' as const, known_slots: 2, expected_slots: 3, known_total: 20, total: null, unit: 'tokens', reason: null }, explicit_cost: { status: 'NOT_AVAILABLE' as const, known_slots: 0, expected_slots: 3, known_total: null, total: null, unit: 'USD', reason: 'incomplete' } } },
    ],
    pairs: { planned_pairs: 4, matched_capability_pairs: 2, both_pass: 1, model_a_only_pass: 1, model_b_only_pass: 0, both_fail: 0, infra_pairs: 1, missing_pairs: 1, infra_or_missing_pairs: 2 },
    pass_rate_differences: { orientation: 'MODEL_B_MINUS_MODEL_A' as const, per_model_capability_pass_rate_difference_pp: -(100 / 6), matched_capability_pair_pass_rate_difference_pp: -50 },
    comparability: { category: 'PARTIALLY_COMPARABLE' as const, assessed_pairs: 3, category_counts: { COMPARABLE: 2, PARTIALLY_COMPARABLE: 1 }, reason_counts: { TRACE_COVERAGE_LIMITED: 1 }, unassessed_planned_pairs: 1 },
    control_drift: { status: 'DETECTED' as const, affected_pairs: 0, affected_runs: 1, assessed_pairs: 3, reason_counts: {} },
    trace_coverage: { status: 'PARTIAL' as const, counts: { FULL_STREAM: 3, FINAL_OUTPUT_ONLY: 2 }, missing_slots: 2 },
    observed_models: { status: 'PARTIAL' as const, counts: { 'fixture-a': 4, 'fixture-b': 2 }, missing_slots: 1 },
    observed_providers: { status: 'AVAILABLE' as const, counts: { fixture: 7 }, missing_slots: 0 },
    recovery_attempts: { status: 'NOT_AVAILABLE' as const, explicitly_marked_primary_acquisitions: 0, explicitly_marked_recovery_acquisitions: 0, unmarked_acquisitions: 7, lease_claim_attempts: 7, note: 'Lease claims are not recovery evidence.' },
    breakdowns: [{ dimension: 'language' as const, value: 'python', planned_pairs: 2, matched_capability_pairs: 1, both_pass: 1, model_a_only_pass: 0, model_b_only_pass: 0, both_fail: 0, infra_pairs: 1, missing_pairs: 0, model_a_pass_rate: { status: 'AVAILABLE' as const, value: 1, numerator: 1, denominator: 1 }, model_b_pass_rate: { status: 'AVAILABLE' as const, value: 1, numerator: 1, denominator: 1 } }],
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  api.listExperiments.mockResolvedValue({ items: [experiment], total: 1, limit: 25, offset: 0 })
  api.getExperiment.mockResolvedValue({
    ...experiment, repeat_count: 3, execution_seed: 1, evidence_tiers: ['INFORMAL'],
    comparison_intent: 'HARNESS_UPLIFT', evaluation_mode: 'NOT_AVAILABLE',
    comparability_summary: { NOT_COMPARABLE: 3 }, report_digest: 'sha256:report',
    cells: [], tasks: [],
  })
  api.getMatrix.mockResolvedValue(matrix)
  api.getRuns.mockResolvedValue({ items: [run], total: 1, limit: 100, offset: 0 })
  api.getModelComparisonAnalysis.mockResolvedValue(modelComparison)
  api.getStatus.mockResolvedValue({ experiment_id: 'matrix-keyless', status: 'completed', terminal: true, run_status_counts: { completed: 6 }, refreshed_at: '2026-08-23T00:01:00Z' })
  api.getRun.mockResolvedValue(run)
  api.getTrace.mockResolvedValue(trace)
})

describe('Workbench contracts', () => {
  it('registers every major route and no Analyst route', () => {
    const paths = router.getRoutes().map((item) => item.path)
    expect(paths).toEqual(expect.arrayContaining(['/', '/experiments', '/experiments/:id', '/runs/:runId', '/regression', '/judgelab', '/judgelab/:calibrationId', '/core-readiness']))
    expect(paths.some((path) => path.includes('analyst'))).toBe(false)
  })

  it('renders reported zero differently from NOT_REPORTED', () => {
    const zero = mount(EvidenceValue, { props: { evidence: reported(0) } })
    const missing = mount(EvidenceValue, { props: { evidence: notReported } })
    expect(zero.text()).toContain('0.00')
    expect(missing.text()).toContain('NOT_REPORTED')
  })

  it('keeps NOT_REPORTED visually distinct from NOT_COMPARABLE', () => {
    const missing = mount(StatusBadge, { props: { value: 'NOT_REPORTED' } })
    const blocked = mount(StatusBadge, { props: { value: 'NOT_COMPARABLE' } })
    expect(missing.classes()).toContain('warn')
    expect(blocked.classes()).toContain('bad')
  })

  it('renders Matrix values, tiers, missing metrics, and comparability from the DTO', () => {
    const wrapper = mount(MatrixHeatmap, { props: { matrix, metric: 'pass_at_5' } })
    expect(wrapper.text()).toContain('NOT_REPORTED')
    expect(wrapper.text()).toContain('NOT_COMPARABLE')
    expect(wrapper.text()).toContain('PARTIALLY_COMPARABLE')
    expect(wrapper.text()).toContain('micro-typescript-clamp')
    expect(wrapper.text()).toContain('INFORMAL')
  })

  it('renders descriptive model-comparison closeout without unsupported claims', async () => {
    api.getExperiment.mockResolvedValueOnce({
      ...experiment, repeat_count: 1, execution_seed: 1, evaluation_mode: 'QUICK',
      comparison_intent: 'MODEL_COMPARISON', evidence_tiers: ['SMOKE'],
      comparability_summary: {}, report_digest: 'sha256:report', cells: [], tasks: [],
    })
    await router.push('/experiments/matrix-keyless')
    const wrapper = mount(ExperimentDetailView, { global: { plugins: [createPinia(), router] } })
    await flushPromises()
    await wrapper.findAll('.tab-button')[3].trigger('click')
    const text = wrapper.text()
    expect(text).toContain('exploratory/descriptive only')
    expect(text).toContain('Matched capability pairs')
    expect(text).toContain('Per-model capability rates (B − A)')
    expect(text).toContain('Matched capability-pair rates (B − A)')
    expect(text).toContain('BUDGET_EXHAUSTION')
    expect(text).toContain('NOT_AVAILABLE')
    expect(text).toContain('Lease claims')
    expect(text.toLowerCase()).not.toContain('statistically significant')
    expect(text.toLowerCase()).not.toContain('universally better')
    expect(text.toLowerCase()).not.toContain('causal uplift')
  })

  it('HTML-encodes persisted Matrix labels before ECharts tooltip rendering', () => {
    expect(escapeTooltipText('<img src=x onerror="bad()"> & test')).toBe(
      '&lt;img src=x onerror=&quot;bad()&quot;&gt; &amp; test',
    )
  })

  it('withholds content for REASONING_PRESENT', () => {
    const wrapper = mount(TraceTimeline, { props: { trace } })
    expect(wrapper.text()).toContain('private content is withheld')
    expect(wrapper.text()).not.toContain('NATIVE_REASONING_CONTENT_MUST_STAY_HIDDEN')
    expect(wrapper.text()).toContain('FULL_STREAM')
  })

  it('renders experiment list evidence', async () => {
    const wrapper = mount(ExperimentsView, { global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('Keyless Matrix')
    expect(wrapper.text()).toContain('completed')
  })

  it('renders run status, trace coverage, and cost missingness', async () => {
    await router.push('/runs/run-safe')
    const wrapper = mount(RunDetailView, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('capability_pass')
    expect(wrapper.text()).toContain('FULL_STREAM')
    expect(wrapper.text()).toContain('NOT_REPORTED')
    expect(wrapper.text()).not.toContain('NATIVE_REASONING_CONTENT_MUST_STAY_HIDDEN')
  })

  it('renders suite-scoped Judge qualification', async () => {
    api.getCalibration.mockResolvedValue({
      calibration_id: 'judge-keyless', suite_id: 'core-calibration', suite_version: '1.0.0',
      suite_digest: 'sha256:suite', plan_digest: 'sha256:plan', report_digest: 'sha256:report',
      status: 'completed', real_judge_smoke: 'NOT_RUN', limitations: [],
      cells: [{
        judge_cell_id: 'good', requested_judge_model: 'fake-good', qualification: 'QUALIFIED_FOR_SUITE',
        qualification_scope: 'core-calibration@1.0.0', coverage: reported(1), label_accuracy: reported(.8),
        macro_f1: reported(1), score_mae: reported(0), spearman_rho: reported(1), pairwise_accuracy: reported(1),
        position_consistency: reported(1), verbosity_bias_rate: reported(0), repeat_consistency: reported(1),
        provider_infra: 0, l0_disagreements: 0, l0_overrides: 0, qualification_reasons: [],
      }],
    })
    await router.push('/judgelab/judge-keyless')
    const wrapper = mount(JudgeDetailView, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('QUALIFIED_FOR_SUITE')
    expect(wrapper.text()).toContain('core-calibration@1.0.0')
  })

  it('distinguishes corrupt Judge report evidence from an unreported report', async () => {
    api.listCalibrations.mockResolvedValue({
      items: [{
        calibration_id: 'judge-corrupt', suite_id: 'core-calibration', suite_version: '1.0.0',
        plan_digest: 'sha256:plan', report_digest: 'sha256:report', status: 'completed',
        report_evidence_status: 'INTEGRITY_ERROR', judge_cell_count: 2, qualifications: [],
        created_at: '2026-08-23T00:00:00Z', finished_at: '2026-08-23T00:01:00Z',
      }], total: 1, limit: 25, offset: 0,
    })
    const wrapper = mount(JudgeLabView, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('INTEGRITY_ERROR')
    expect(wrapper.text()).not.toContain('No Judge calibration is reported')
  })

  it('renders deterministic regression limitations and NOT_COMPARABLE', async () => {
    api.compare.mockResolvedValue({
      baseline_experiment_id: 'a', candidate_experiment_id: 'b', baseline_plan_digest: 'sha256:a',
      candidate_plan_digest: 'sha256:b', baseline_report_digest: 'sha256:ra', candidate_report_digest: 'sha256:rb',
      intent: 'MODEL_COMPARISON', common_tasks: ['task'], limitation: 'Directional evidence only; no causal attribution.',
      comparisons: [{ baseline_cell_id: 'direct', candidate_cell_id: 'codex', baseline_value: reported(1), candidate_value: reported(.5), delta: reported(-.5), direction: 'DECREASED', baseline_tier: 'INFORMAL', candidate_tier: 'INFORMAL', comparability: 'NOT_COMPARABLE', reason_codes: ['HARD_CONTROL_MISMATCH'], paired_observations: 3, baseline_infra_count: 0, candidate_infra_count: 1 }],
    })
    const wrapper = mount(RegressionView)
    await wrapper.get('[aria-label="Baseline experiment ID"]').setValue('a')
    await wrapper.get('[aria-label="Candidate experiment ID"]').setValue('b')
    await wrapper.get('[aria-label="Comparison intent"]').setValue('MODEL_COMPARISON')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('NOT_COMPARABLE')
    expect(wrapper.text()).toContain('no causal attribution')
    expect(wrapper.text()).toContain('HARD_CONTROL_MISMATCH')
    expect(wrapper.text()).toContain('Raw direction')
    expect(api.compare).toHaveBeenCalledWith('a', 'b', 'MODEL_COMPARISON')
  })

  it('renders Core readiness blockers', async () => {
    api.readiness.mockResolvedValue({ status: 'NOT_READY', task_corpus_size: 1, evaluated_at: '2026-08-23T00:00:00Z', blockers: ['REAL_JUDGE_EVIDENCE'], checks: [{ key: 'REAL_JUDGE_EVIDENCE', label: 'Real Judge evidence', status: 'NOT_VERIFIED', evidence: 'REAL_JUDGE_SMOKE=NOT_RUN' }] })
    const wrapper = mount(CoreReadinessView)
    await flushPromises()
    expect(wrapper.text()).toContain('NOT_READY')
    expect(wrapper.text()).toContain('NOT_VERIFIED')
    expect(wrapper.text()).toContain('REAL_JUDGE_SMOKE=NOT_RUN')
  })

  it('stops polling when PostgreSQL reports a terminal status', async () => {
    vi.useFakeTimers()
    const store = useExperimentStore()
    store.startPolling('matrix-keyless', 50)
    await vi.runAllTicks()
    await Promise.resolve()
    expect(api.getStatus).toHaveBeenCalled()
    expect(store.pollingHandle).toBeNull()
    vi.useRealTimers()
  })

  it('refetches authoritative evidence after reconstructed-page loads', async () => {
    const first = useExperimentStore()
    await first.fetchExperiment('matrix-keyless')
    const secondPinia = createPinia()
    setActivePinia(secondPinia)
    const reconstructed = useExperimentStore()
    await reconstructed.fetchExperiment('matrix-keyless')
    expect(api.getExperiment).toHaveBeenCalledTimes(2)
    expect(reconstructed.selected?.experiment_id).toBe('matrix-keyless')
  })
})
