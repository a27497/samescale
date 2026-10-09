import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StatusBadge from '@/components/StatusBadge.vue'
import TraceTimeline from '@/components/TraceTimeline.vue'
import ExperimentPicker from '@/components/ExperimentPicker.vue'
import App from '@/App.vue'
import ExperimentsView from '@/views/ExperimentsView.vue'
import ExperimentDetailView from '@/views/ExperimentDetailView.vue'
import RunDetailView from '@/views/RunDetailView.vue'
import RegressionView from '@/views/RegressionView.vue'
import { checkedOutcomeCounts, loadOutcomeCounts } from '@/utils/experimentResults'
import { preferences } from '@/composables/preferences'
import router from '@/router'
import type { ExperimentSummary, RunSummary, RunListResponse } from '@/types/workbench'
const api = vi.hoisted(() => ({ listExperiments: vi.fn(), getExperiment: vi.fn(), getRuns: vi.fn(), getMatrix: vi.fn(), getRun: vi.fn(), getTrace: vi.fn(), compare: vi.fn() }))
const capabilities = vi.hoisted(() => vi.fn())
vi.mock('@/api/client', () => ({ workbenchApi: api }))
vi.mock('@/api/analyst', () => ({ analystApi: { capabilities } }))
const summary: ExperimentSummary = { experiment_id: 'p0-baseline', name: 'Public Demo — offline fixture baseline', status: 'completed', provenance: 'FIXTURE_OFFLINE', integrity_status: 'VERIFIED', plan_digest: 'sha256:source-plan', cell_count: 1, task_count: 2, planned_run_count: 6, completed_capability_count: 6, infra_count: 0, created_at: 'source-date', started_at: null, finished_at: null }
const detail = { ...summary, repeat_count: 3, execution_seed: 1, comparison_intent: 'GENERAL', evaluation_mode: 'NOT_AVAILABLE', evidence_tiers: ['INFORMAL'], comparability_summary: {}, report_digest: 'sha256:source-report', cells: [], tasks: [] }
const run = (outcome: string): RunSummary => ({ run_id: `original-${outcome}`, experiment_id: summary.experiment_id, task_id: 'micro-typescript-clamp', cell_id: 'original-cell', lane: 'H', task_version: '1', repeat_index: 0, attempt: 1, status: 'completed', provenance: 'FIXTURE_OFFLINE', normalized_outcome: outcome, duration_ms: { status: 'NOT_REPORTED', value: null } })
const page = (outcome: string, total: number): RunListResponse => ({ items: total ? [run(outcome)] : [], total, limit: 1, offset: 0 })
const options = () => ({ global: { plugins: [createPinia(), router] } })
beforeEach(async () => {
  vi.resetAllMocks(); preferences.language = 'zh-CN'
  await router.push('/analyst')
  capabilities.mockResolvedValue({ public_demo_read_only: true, persistent_sessions_allowed: false })
  api.listExperiments.mockResolvedValue({ items: [summary], total: 1, limit: 25, offset: 0 })
  api.getExperiment.mockResolvedValue(detail)
  api.getMatrix.mockResolvedValue({ experiment_id: summary.experiment_id, points: [], tasks: [], cells: [] })
  api.getRuns.mockImplementation((_id, params) => Promise.resolve(params?.outcome ? page(params.outcome, 3) : { items: [run('capability_pass'), run('capability_fail')], total: 6, limit: 100, offset: 0 }))
})

describe('State scope and accessible evidence', () => {
  it.each([
    ['run', 'completed', '运行已结束'], ['event', 'completed', '事件已结束'],
    ['verifier', 'succeeded', '验收执行已结束'], ['experiment', 'completed', '实验已结束'],
  ] as const)('labels %s / %s without inventing a task pass', (context, value, expected) => {
    const badge = mount(StatusBadge, { props: { value, context, localized: true } })
    expect(badge.text()).toBe(expected); expect(badge.classes()).toContain('neutral')
    expect(badge.attributes('data-status')).toBe(value)
    expect(badge.attributes('tabindex')).toBeUndefined(); expect(badge.attributes('title')).toBeUndefined()
    expect(badge.attributes('aria-label')).toBeUndefined(); expect(badge.find('code').exists()).toBe(false)
  })
  it('does not interpret a failed event as a failed run or task verdict', () => {
    const badge = mount(StatusBadge, { props: { value: 'failed', context: 'event', localized: true } })
    expect(badge.text()).toBe('事件执行失败'); expect(badge.text()).not.toContain('运行失败')
  })
  it('preserves FILE_CHANGE status and source in explicit details without overlay/focus duplication', () => {
    const source = 'item.completed — original saved event'
    const wrapper = mount(TraceTimeline, { props: { localized: true, trace: { run_id: 'original', status: 'REPORTED', coverage: 'FULL_STREAM', trace_digest: 'sha256:original', events: [{ ordinal: 3, type: 'FILE_CHANGE', status: 'completed', exit_code: null, summary: source }] } } })
    expect(wrapper.get('.trace-event > summary').text()).toContain('事件已结束')
    expect(wrapper.get('.trace-event > summary').text()).not.toContain('运行已结束')
    expect(wrapper.get('.trace-source').text()).toBe(source)
    expect(wrapper.get('.technical-fields').text()).toContain('FILE_CHANGE')
    expect(wrapper.get('.technical-fields').text()).toContain('completed')
    expect(wrapper.find('.status-pill[tabindex]').exists()).toBe(false)
    expect(wrapper.find('.status-pill[title]').exists()).toBe(false)
  })
  it('keeps the same sidebar links when entering or leaving Run Detail', async () => {
    const wrapper = mount(App, { global: { plugins: [router], stubs: { RouterView: true } } })
    const links = () => wrapper.findAll('nav .nav-link').map(link => link.attributes('href'))
    const before = links(); await router.push('/runs/original-run'); await flushPromises()
    expect(links()).toEqual(before); await router.push('/diagnosis'); await flushPromises(); expect(links()).toEqual(before)
  })
})

describe('Authoritative experiment result counts', () => {
  it('uses filtered API totals beyond the loaded page, including genuine zero', () => {
    const large = { ...summary, completed_capability_count: 401 }
    expect(checkedOutcomeCounts(large, page('capability_pass', 400), page('capability_fail', 1))).toEqual({ passed: 400, failed: 1 })
    expect(checkedOutcomeCounts(summary, page('capability_pass', 6), page('capability_fail', 0))).toEqual({ passed: 6, failed: 0 })
  })
  it.each([undefined, -1, 3.5, '3'])('shows unreported for invalid or missing count %s', total => {
    const bad = { ...page('capability_pass', 3), total } as RunListResponse
    expect(checkedOutcomeCounts(summary, bad, page('capability_fail', 3))).toEqual({ passed: null, failed: null })
  })
  it('rejects inconsistent sums and mismatched outcome/experiment identities', () => {
    expect(checkedOutcomeCounts(summary, page('capability_pass', 4), page('capability_fail', 3)).passed).toBeNull()
    expect(checkedOutcomeCounts(summary, page('capability_fail', 3), page('capability_fail', 3)).passed).toBeNull()
    const foreign = { ...page('capability_pass', 3), items: [{ ...run('capability_pass'), experiment_id: 'other' }] }
    expect(checkedOutcomeCounts(summary, foreign, page('capability_fail', 3)).passed).toBeNull()
  })
  it('never derives counts from a rate or lifecycle when evidence reading fails', async () => {
    api.getRuns.mockRejectedValue(new Error('missing evidence'))
    expect(await loadOutcomeCounts({ ...summary, status: 'completed' })).toEqual({ passed: null, failed: null })
  })
  it('does not probe records already marked integrity failed', async () => {
    expect(await loadOutcomeCounts({ ...summary, integrity_status: 'INTEGRITY_FAILED' })).toEqual({ passed: null, failed: null })
    expect(api.getRuns).not.toHaveBeenCalled()
  })
  it('shows matching collected/pass/fail/infra counts in list and overview, with read-only action gating', async () => {
    await router.push('/experiments'); const list = mount(ExperimentsView, options()); await flushPromises()
    const row = list.get('tbody tr'); expect(row.findAll('td').slice(-4).map(td => td.text())).toEqual(['6 / 6', '3', '3', '0'])
    expect(list.text()).toContain('已收集任务结果 / 计划'); expect(list.find('a[href="/experiments/new"]').exists()).toBe(false)
    list.unmount(); await router.push('/experiments/p0-baseline?tab=overview'); const overview = mount(ExperimentDetailView, options()); await flushPromises()
    expect(overview.findAll('.result-metrics .value').map(el => el.text())).toEqual(['6', '6', '3', '3', '0'])
    expect(api.getRuns).toHaveBeenCalledWith('p0-baseline', { outcome: 'capability_pass', limit: 1 })
    expect(api.getRuns).toHaveBeenCalledWith('p0-baseline', { outcome: 'capability_fail', limit: 1 })
  })
  it('keeps the existing private plan action when the server explicitly permits editing', async () => {
    capabilities.mockResolvedValue({ public_demo_read_only: false, persistent_sessions_allowed: true })
    const list = mount(ExperimentsView, options()); await flushPromises()
    expect(list.find('a[href="/experiments/new"]').exists()).toBe(true)
  })
})

describe('Prefill and denied/missing records', () => {
  it('does not turn a prefilled candidate ID into an English tail fragment', async () => {
    const id = 'public-demo-original-identity-candidate'
    const wrapper = mount(ExperimentPicker, { props: { modelValue: id, experiments: [], label: '候选实验', loading: true } })
    expect(wrapper.get('select').text()).toContain('名称读取中'); expect(wrapper.get('select').text()).not.toContain('andidate')
    await wrapper.setProps({ loading: false }); expect(wrapper.get('select').text()).toContain('名称未报告')
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe(id)
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe(id)
  })
  it('distinguishes a real product 404 from a gateway/API permission denial and skips secondary probes', async () => {
    for (const status of [404, 403]) {
      api.getRun.mockRejectedValueOnce({ response: { status, data: { error: { code: status === 403 ? 'PUBLIC_DEMO_READ_ONLY' : 'NOT_FOUND' } } } })
      await router.push('/runs/unknown-'+status); const wrapper = mount(RunDetailView, options()); await flushPromises()
      const alert = wrapper.get('[role="alert"]').text()
      expect(alert).toContain(status === 404 ? '运行记录不存在' : '无法确认记录是否存在')
      if (status === 403) { expect(alert).not.toContain('运行记录不存在'); expect(alert).toContain('PUBLIC_DEMO_READ_ONLY') }
      expect(wrapper.find('.verifier-column').exists()).toBe(false); expect(api.getTrace).not.toHaveBeenCalled()
      expect(wrapper.find('a[href="/experiments"]').exists()).toBe(true); wrapper.unmount()
    }
  })
  it('resolves real names after a failed list without changing prefilled identities', async () => {
    api.listExperiments.mockRejectedValueOnce(new Error('unavailable'))
    api.getExperiment.mockImplementation(id => Promise.resolve({ ...detail, experiment_id: id, name: `原始名称 ${id}` }))
    api.compare.mockResolvedValue({ comparisons: [], baseline_experiment_id: 'base', candidate_experiment_id: 'cand', common_tasks: [], limitation: '' })
    await router.push('/regression?baseline=base&candidate=cand'); const wrapper = mount(RegressionView, options()); await flushPromises()
    expect(wrapper.get('[data-test="baseline"]').text()).toContain('原始名称 base'); expect(wrapper.get('[data-test="candidate"]').text()).toContain('原始名称 cand')
    expect(api.compare).toHaveBeenCalledWith('base', 'cand', 'MODEL_COMPARISON')
  })
})
