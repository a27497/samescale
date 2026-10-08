import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { preferences } from '@/composables/preferences'
import { copy, setLocale } from '@/composables/visualLocale'
import { safeTrace, eligibleDirection } from '@/utils/visualEvidence'
import StatusBadge from '@/components/StatusBadge.vue'
import EvidenceValue from '@/components/EvidenceValue.vue'
import RunDetailView from '@/views/RunDetailView.vue'
import RegressionView from '@/views/RegressionView.vue'
import PublicDemoView from '@/views/PublicDemoView.vue'
import DiagnosisView from '@/views/DiagnosisView.vue'
import router from '@/router'
import type { RegressionComparison, RunDetail, TraceResponse } from '@/types/workbench'
const api = vi.hoisted(() => ({ getRun: vi.fn(), getTrace: vi.fn(), getPublicDemo: vi.fn(), listExperiments: vi.fn(), getDiagnosis: vi.fn(), compare: vi.fn(), exportBadCases: vi.fn() }))
vi.mock('@/api/client', () => ({ workbenchApi: api }))
const missing = { status: 'NOT_REPORTED' as const, value: null }
const run: RunDetail = {
  run_id: 'run-v1', experiment_id: 'v1-baseline', cell_id: 'cell', task_id: 'task', task_version: '1', slot_id: 'slot',
  lane: 'H', repeat_index: 1, status: 'completed', provenance: 'FIXTURE_OFFLINE', normalized_outcome: 'capability_fail',
  attempt: 1, duration_ms: missing, source_outcome: 'verified_fail', requested_model: 'fixture', observed_model: null,
  provider_route: null, harness: 'codex', harness_version: 'frozen', trace_coverage: 'FULL_STREAM', evidence_digest: 'sha256:run',
  artifact_name: null, verifier_passed: null, verifier_score: missing, summary: 'Original verifier summary',
  input_tokens: missing, output_tokens: missing, explicit_cost: missing, comparability: null, comparability_reason_codes: [],
}
const trace: TraceResponse = { run_id: run.run_id, status: 'REPORTED', coverage: 'FULL_STREAM', trace_digest: 'sha256:trace', events: [{ ordinal: 4, type: 'AGENT_MESSAGE', summary: 'Implemented successfully; tests pass.', status: null, exit_code: null }, { ordinal: 5, type: 'REASONING_PRESENT', summary: 'PRIVATE_TEST_CONTENT', status: null, exit_code: null }] }
const pair: RegressionComparison = {
  baseline_cell_id: 'base', candidate_cell_id: 'cand', baseline_value: missing, candidate_value: missing, delta: { status: 'REPORTED', value: .5 },
  direction: 'IMPROVED', overall_baseline_value: { status: 'REPORTED', value: 0 }, overall_candidate_value: { status: 'REPORTED', value: 1 }, overall_delta: { status: 'REPORTED', value: 1 },
  common_baseline_value: missing, common_candidate_value: missing, eligible_paired_observations: 0, baseline_tier: 'L0', candidate_tier: 'L0', comparability: 'NOT_COMPARABLE', reason_codes: ['UNKNOWN_REASON_V1'], paired_observations: 6, baseline_infra_count: 0, candidate_infra_count: 0,
}
const comparison = { baseline_experiment_id: 'v1-baseline', candidate_experiment_id: 'v1-candidate', baseline_plan_digest: 'sha256:bp', candidate_plan_digest: 'sha256:cp', baseline_report_digest: 'sha256:br', candidate_report_digest: 'sha256:cr', intent: 'MODEL_COMPARISON', baseline_provenance: 'FIXTURE_OFFLINE', candidate_provenance: 'FIXTURE_OFFLINE', comparisons: [pair], common_tasks: ['task'], limitation: 'SOURCE_LIMITATION_STAYS_VERBATIM' }
const demo = { demo_id: 'demo-v1', generated_at: '2026-10-08', provenance: 'FIXTURE_OFFLINE', public_demo_ready: true, baseline_id: run.experiment_id, candidate_id: 'v1-candidate', failed_run_id: run.run_id, run_count: 2, artifact_file_count: 2, manifest_digest: 'sha256:demo', historical_integrity_failures: [], limitation: 'ORIGINAL_DEMO_LIMITATION' }
beforeEach(async () => {
  vi.resetAllMocks(); preferences.language = 'zh-CN'; localStorage.clear()
  await router.push('/analyst')
  api.getRun.mockResolvedValue(run); api.getTrace.mockResolvedValue(trace); api.getPublicDemo.mockResolvedValue(demo)
  api.listExperiments.mockResolvedValue({ items: [{ experiment_id: run.experiment_id, name: 'ORIGINAL_EXPERIMENT_NAME' }] })
  api.compare.mockResolvedValue(comparison)
  api.getDiagnosis.mockResolvedValue({ experiment_id: run.experiment_id, cells: [], failure_run_count: 0, real_run_count: 2, synthetic_run_count: 0, correlation_warning: 'ORIGINAL_WARNING', classification_limitations: [], cluster_dimensions: [] })
})
const options = { global: { plugins: [router] } }
describe('Visual v1 evidence and locale contracts', () => {
  it.each(['zh-CN', 'en-US'] as const)('retains status codes, missing values and semantic tones in %s', locale => {
    setLocale(locale)
    expect(copy('中文标签', 'English label')).toBe(locale === 'zh-CN' ? '中文标签' : 'English label')
    const absent = mount(EvidenceValue, { props: { evidence: missing, localized: true } })
    const zero = mount(EvidenceValue, { props: { evidence: { status: 'REPORTED', value: 0 }, localized: true } })
    expect(absent.text()).toContain('NOT_REPORTED'); expect(absent.text()).not.toContain('0.00'); expect(zero.text()).toBe('0.00')
    expect(mount(StatusBadge, { props: { value: 'VERIFIED_PASS', localized: true } }).classes()).toContain('good')
    expect(mount(StatusBadge, { props: { value: 'NOT_COMPARABLE', localized: true } }).classes()).toContain('warn')
    expect(mount(StatusBadge, { props: { value: 'NOT_RUN', localized: true } }).classes()).toContain('neutral')
    const unknown = mount(StatusBadge, { props: { value: 'UNKNOWN_STATUS_V1', localized: true } })
    expect(unknown.text()).toBe('UNKNOWN_STATUS_V1'); expect(unknown.classes()).toContain('neutral')
  })
  it('supports the existing English preference and saves only an interface locale', () => {
    preferences.language = 'en'; expect(copy('标签', 'Label')).toBe('Label')
    setLocale('en-US'); expect(localStorage.getItem('samescale.interface-locale')).toBe('en-US')
    expect(localStorage.length).toBe(1)
  })
  it.each(['NOT_COMPARABLE', 'PARTIALLY_COMPARABLE'] as const)('suppresses an improved direction for %s', comparability => {
    expect(eligibleDirection({ ...pair, comparability, eligible_paired_observations: 3 })).toBe('NOT_REPORTED')
  })
  it('requires comparable observations for a descriptive direction', () => {
    expect(eligibleDirection({ ...pair, comparability: 'COMPARABLE' })).toBe('NOT_REPORTED')
    expect(eligibleDirection({ ...pair, comparability: 'COMPARABLE', eligible_paired_observations: 3 })).toBe('IMPROVED')
  })
  it('redacts private reasoning while preserving original events and ordinals', () => {
    const safe = safeTrace(trace)!
    expect(safe.events[1]?.summary).toBe('Private reasoning withheld.')
    expect(trace.events[1]?.summary).toBe('PRIVATE_TEST_CONTENT')
    expect(safe.events.map(event => event.ordinal)).toEqual([4, 5])
    expect(safe.events[0]?.summary).toBe(trace.events[0]?.summary)
  })
  it.each(['zh-CN', 'en-US'] as const)('does not turn a completed lifecycle or success message into a verifier pass in %s', async locale => {
    setLocale(locale); await router.push('/runs/run-v1')
    const wrapper = mount(RunDetailView, options); await flushPromises()
    expect(wrapper.get('.verifier-column').text()).toContain('NOT_VERIFIED')
    expect(wrapper.get('.agent-column').text()).toContain(trace.events[0]!.summary)
    expect(wrapper.find('.conflict-banner').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('PRIVATE_TEST_CONTENT')
    expect(wrapper.text()).toContain(run.summary)
    wrapper.unmount()
  })
  it('keeps verifier evidence when trace fails, and offers a retry', async () => {
    api.getTrace.mockRejectedValueOnce(new Error('trace unavailable'))
    api.getRun.mockResolvedValue({ ...run, verifier_passed: false })
    await router.push('/runs/run-v1'); const wrapper = mount(RunDetailView, options); await flushPromises()
    expect(wrapper.get('.verifier-column').text()).toContain('VERIFIED_FAIL')
    expect(wrapper.get('#run-trace').text()).toContain('Trace 暂不可读取')
    await wrapper.get('#run-trace button').trigger('click'); await flushPromises()
    expect(wrapper.get('#run-trace').text()).toContain('AGENT_MESSAGE')
  })
  it('does not expose artifact links based only on a public-demo ID prefix', async () => {
    api.getPublicDemo.mockRejectedValue(new Error('integrity error'))
    api.getRun.mockResolvedValue({ ...run, experiment_id: 'public-demo-not-authorized' })
    await router.push('/runs/run-v1'); const wrapper = mount(RunDetailView, options); await flushPromises()
    expect(wrapper.find('a[href*="public-artifact"]').exists()).toBe(false)
  })
  it('clears an old comparison when the intent changes, preserves query context and source text', async () => {
    await router.push('/regression?baseline=v1-baseline&candidate=v1-candidate&run=run-v1')
    const wrapper = mount(RegressionView, options); await flushPromises()
    expect(wrapper.text()).toContain(comparison.limitation)
    expect(wrapper.get('.direction-row').text()).not.toContain('IMPROVED')
    await wrapper.get('[data-test="intent"]').setValue('GENERAL')
    expect(wrapper.find('.regression-comparison').exists()).toBe(false)
    await wrapper.get('.comparison-toolbar button').trigger('click'); await flushPromises()
    expect(router.currentRoute.value.query.run).toBe('run-v1')
    expect(api.compare).toHaveBeenLastCalledWith('v1-baseline', 'v1-candidate', 'GENERAL')
  })
  it('loads demo stage summaries from actual API responses and preserves raw evidence across language changes', async () => {
    const wrapper = mount(PublicDemoView, options); await flushPromises()
    expect(api.getRun).toHaveBeenCalledWith(demo.failed_run_id)
    expect(api.getDiagnosis).toHaveBeenCalledWith(demo.baseline_id)
    expect(api.compare).toHaveBeenCalledWith(demo.baseline_id, demo.candidate_id, 'MODEL_COMPARISON')
    expect(wrapper.get('#demo-step-2').text()).toContain(run.summary)
    setLocale('en-US'); await flushPromises()
    expect(wrapper.get('h2').text()).toContain('What does verification show')
    expect(wrapper.text()).toContain('ORIGINAL_DEMO_LIMITATION')
    expect(wrapper.text()).toContain('ORIGINAL_WARNING')
  })
  it('isolates a failed demo stage and retries without substituting screenshot data', async () => {
    api.getTrace.mockRejectedValueOnce(new Error('failed trace'))
    const wrapper = mount(PublicDemoView, options); await flushPromises()
    expect(wrapper.get('#demo-step-2').text()).toContain('这一阶段的证据暂不可用')
    expect(wrapper.get('#demo-step-2').text()).not.toContain(trace.events[0]!.summary)
    expect(wrapper.get('#demo-step-4').text()).toContain('UNKNOWN_REASON_V1')
    await wrapper.findAll('button').find(button => button.text() === '重试阶段证据')!.trigger('click'); await flushPromises()
    expect(wrapper.get('#demo-step-2').text()).toContain(trace.events[0]!.summary)
  })
  it('does not request supplemental evidence when the main demo identity fails closed', async () => {
    api.getPublicDemo.mockResolvedValue({ ...demo, public_demo_ready: false })
    const wrapper = mount(PublicDemoView, options); await flushPromises()
    expect(wrapper.find('.demo-walkthrough').exists()).toBe(false)
    expect(api.getRun).not.toHaveBeenCalled(); expect(api.compare).not.toHaveBeenCalled()
  })
  it('zero classified failures neither enables export nor implies all tasks passed', async () => {
    await router.push('/diagnosis?experiment=v1-baseline')
    const wrapper = mount(DiagnosisView, options); await flushPromises()
    expect(wrapper.get('button.primary-button').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('这不证明所有任务通过')
    expect(api.exportBadCases).not.toHaveBeenCalled()
  })

  it.each(['zh-CN', 'en-US'] as const)('labels subject lifecycle failure independently of verification in %s', locale => {
    setLocale(locale)
    const badge = mount(StatusBadge, { props: { value: 'failed_subject', localized: true } })
    expect(badge.get('.status-pill > span').text()).toBe(locale === 'zh-CN' ? '主体运行失败' : 'Subject run failed')
    expect(badge.get('code').text()).toBe('failed_subject')
    expect(badge.text()).not.toMatch(/验收|verification/i)
    expect(badge.classes()).toContain('bad')
    expect(mount(StatusBadge, { props: { value: 'failed_subject' } }).text()).toBe('Subject run failed')
  })
  it.each([
    ['zh-CN', true, 'VERIFIED_PASS', '查看实验诊断'],
    ['zh-CN', false, 'VERIFIED_FAIL', '查看失败诊断'],
    ['zh-CN', null, 'NOT_VERIFIED', '查看诊断记录'],
    ['en-US', true, 'VERIFIED_PASS', 'View experiment diagnosis'],
    ['en-US', false, 'VERIFIED_FAIL', 'View failure diagnosis'],
    ['en-US', null, 'NOT_VERIFIED', 'View diagnosis records'],
  ] as const)('keeps verifier %s / %s authoritative over failed_subject and agent claims', async (locale, passed, verdict, action) => {
    setLocale(locale)
    api.getRun.mockResolvedValue({ ...run, status: 'failed_subject', verifier_passed: passed })
    await router.push('/runs/run-v1?candidate=v1-candidate')
    const wrapper = mount(RunDetailView, options); await flushPromises()
    expect(wrapper.get('.run-id-strip [data-status="failed_subject"]').text()).toContain(locale === 'zh-CN' ? '主体运行失败' : 'Subject run failed')
    expect(wrapper.get('.verifier-column [data-status]').attributes('data-status')).toBe(verdict)
    expect(wrapper.get('.agent-column [data-status]').attributes('data-status')).toBe('UNVERIFIED_CLAIM')
    expect(wrapper.get('.agent-column').text()).toContain(trace.events[0]!.summary)
    expect(wrapper.find('.conflict-banner').exists()).toBe(passed === false)
    const link = wrapper.get('.run-toolbar a.primary-button')
    expect(link.text()).toBe(action)
    const url = new URL(link.attributes('href')!, 'http://localhost')
    expect(url.pathname).toBe('/diagnosis')
    expect(Object.fromEntries(url.searchParams)).toEqual({ experiment: run.experiment_id, candidate: demo.candidate_id, run: run.run_id })
    wrapper.unmount()
  })
  it.each(['zh-CN', 'en-US'] as const)('recovers a failed demo stage and removes retry controls after fresh success in %s', async locale => {
    setLocale(locale)
    api.getDiagnosis.mockRejectedValueOnce(new Error('temporary diagnosis error'))
    const wrapper = mount(PublicDemoView, options); await flushPromises()
    expect(wrapper.get('#demo-step-3').text()).not.toContain('ORIGINAL_WARNING')
    const retry = wrapper.findAll('button').find(button => button.text() === (locale === 'zh-CN' ? '重试阶段证据' : 'Retry step evidence'))!
    await retry.trigger('click'); await flushPromises()
    expect(wrapper.get('#demo-step-3').text()).toContain('ORIGINAL_WARNING')
    expect(wrapper.find('.notice').exists()).toBe(false)
    expect(wrapper.get('#demo-step-5 button').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
  it.each((['zh-CN', 'en-US'] as const).flatMap(locale => (['run', 'trace', 'diagnosis', 'comparison'] as const).map(stage => ({ locale, stage }))))('clears successful $stage evidence before a failed retry in $locale and preserves other fresh stages', async ({ locale, stage }) => {
    setLocale(locale)
    const stages = {
      run: { mock: api.getRun, selector: '#demo-step-2', original: run.summary },
      trace: { mock: api.getTrace, selector: '#demo-step-2', original: trace.events[0]!.summary },
      diagnosis: { mock: api.getDiagnosis, selector: '#demo-step-3', original: 'ORIGINAL_WARNING' },
      comparison: { mock: api.compare, selector: '#demo-step-4', original: 'UNKNOWN_REASON_V1' },
    }
    const target = stages[stage]
    // A different initial error makes the retry reachable while this stage first succeeds.
    stages[stage === 'comparison' ? 'trace' : 'comparison'].mock.mockRejectedValueOnce(new Error('initial error'))
    const wrapper = mount(PublicDemoView, options); await flushPromises()
    expect(wrapper.get(target.selector).text()).toContain(target.original)
    let rejectStage!: (reason: Error) => void
    target.mock.mockImplementationOnce(() => new Promise((_, reject) => { rejectStage = reject }))
    const retryText = locale === 'zh-CN' ? '重试阶段证据' : 'Retry step evidence'
    await wrapper.findAll('button').find(button => button.text() === retryText)!.trigger('click')
    await flushPromises()
    expect(wrapper.get(target.selector).text()).not.toContain(target.original)
    expect(wrapper.get('#demo-step-5 button').attributes('disabled')).toBeDefined()
    const unaffected = stages[stage === 'diagnosis' ? 'trace' : 'diagnosis']
    expect(wrapper.get(unaffected.selector).text()).toContain(unaffected.original)
    rejectStage(new Error('success followed by failure')); await flushPromises()
    expect(wrapper.get(target.selector).text()).not.toContain(target.original)
    expect(wrapper.get(target.selector).text()).toContain(locale === 'zh-CN' ? '这一阶段的证据暂不可用' : 'Evidence for this step is unavailable')
    expect(wrapper.get(unaffected.selector).text()).toContain(unaffected.original)
    if (stage === 'run') {
      expect(wrapper.get('#demo-step-2').find('[data-status="NOT_VERIFIED"]').exists()).toBe(false)
      expect(wrapper.get('#demo-step-5').text()).not.toContain(run.evidence_digest)
      expect(wrapper.get('#demo-step-5 button').attributes('disabled')).toBeDefined()
    }
    await wrapper.findAll('button').find(button => button.text() === retryText)!.trigger('click'); await flushPromises()
    expect(wrapper.get(target.selector).text()).toContain(target.original)
    expect(wrapper.find('.notice').exists()).toBe(false)
    wrapper.unmount()
  })
})
