import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StatusBadge from '@/components/StatusBadge.vue'
import CoreReadinessView from '@/views/CoreReadinessView.vue'
import RunsHomeView from '@/views/RunsHomeView.vue'
import SourceText from '@/components/SourceText.vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { setLocale } from '@/composables/visualLocale'
import { statusLabel, statusTone } from '@/utils/statusLabels'
import { readinessEvidence } from '@/utils/readinessCopy'
const api = vi.hoisted(() => ({ readiness: vi.fn(), listExperiments: vi.fn(), getRuns: vi.fn(), getRun: vi.fn() }))
vi.mock('@/api/client', () => ({ workbenchApi: api }))
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div />' } }] })
beforeEach(() => { vi.resetAllMocks(); setLocale('zh-CN') })

describe('Chinese workbench presentation', () => {
  it.each([
    ['NOT_REPORTED', '未报告', 'neutral'], ['NOT_AVAILABLE', '暂无数据', 'neutral'],
    ['MISSING', '未配置', 'warn'], ['UNKNOWN', '未知', 'neutral'], ['NOT_RUN', '未运行', 'warn'],
    ['NOT_VERIFIED', '尚未核验', 'warn'], ['failed_infra', '基础设施失败', 'bad'],
    ['VERIFIED_PASS', '独立验收通过', 'good'], ['future_state', '未识别状态', 'neutral'],
    ['__proto__', '未识别状态', 'neutral'], ['toString', '未识别状态', 'neutral'],
  ])('keeps %s out of prose while retaining the raw identity', (value, label, tone) => {
    const wrapper = mount(StatusBadge, { props: { value } })
    expect(wrapper.text()).toBe(label); expect(wrapper.classes()).toContain(tone)
    expect(wrapper.attributes('title')).toBe(value); expect(wrapper.attributes('data-status')).toBe(value)
  })
  it('does not turn process completion, readiness or metadata presence into independent acceptance', () => {
    expect(statusLabel('completed', 'run')).toBe('运行已结束')
    expect(statusLabel('completed', 'event')).toBe('事件已结束')
    expect(statusLabel('succeeded', 'verifier')).toBe('验收执行已结束')
    expect(statusLabel('AVAILABLE', 'provider')).toBe('环境可用')
    expect(statusLabel('FAILED', 'session')).toBe('调查失败')
    expect(statusTone('completed')).toBe('neutral')
  })
  it('labels planning checks separately from task verification', () => {
    expect(statusLabel('PASS', 'preflight')).toBe('检查通过')
    expect(statusLabel('READY', 'preflight')).toBe('可规划')
    expect(statusLabel('PASS')).toBe('验收通过')
  })
  it('preserves source text in a closed disclosure and never translates an unknown claim into a pass', () => {
    const claim = 'A future Agent claims success; NOT_VERIFIED'
    const wrapper = mount(SourceText, { props: { text: claim } })
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    expect(wrapper.get('details p').text()).toBe(claim)
    expect(wrapper.get('.source-text > p').text()).toBe('已保存来源文本，可展开核对原文。')
  })
  it('explains unavailable readiness and provides configuration and evidence entry points', async () => {
    api.readiness.mockRejectedValue(new Error('private-runtime-sentinel'))
    const wrapper = mount(CoreReadinessView, { global: { plugins: [router] } }); await flushPromises()
    expect(wrapper.text()).toContain('目前无法确认具体原因')
    expect(wrapper.text()).toContain('缺少就绪度证据不能视为验收通过')
    expect(wrapper.find('a[href="/settings"]').exists()).toBe(true)
    expect(wrapper.find('a[href="/experiments"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('private-runtime-sentinel')
  })
  it('does not fabricate a readiness summary from an unknown or changed source statement', () => {
    const source = 'Frozen release snapshot: REAL_JUDGE_SMOKE=VERIFIED'
    expect(readinessEvidence(source)).toContain('不代表当前工作区已运行校准')
    expect(readinessEvidence(source + ' altered')).toContain('尚无对应的中文证据摘要')
    expect(readinessEvidence('__proto__')).toContain('尚无对应的中文证据摘要')
  })
  it('keeps personal runs and fixtures separate and passes original IDs to existing endpoints', async () => {
    api.listExperiments.mockResolvedValue({ items: [
      { experiment_id: 'sample-id', name: 'Public Demo — offline fixture baseline', provenance: 'FIXTURE_OFFLINE', planned_run_count: 6 },
      { experiment_id: 'personal-id', name: 'Owned experiment', provenance: 'UNVERIFIED_SOURCE' },
    ] })
    api.getRuns.mockImplementation((id: string) => Promise.resolve({ total: 1, items: [{ run_id: id === 'personal-id' ? 'owned-run' : 'sample-run', task_id: 'task', task_version: '1', status: 'completed', normalized_outcome: null, provenance: id === 'personal-id' ? 'UNVERIFIED_SOURCE' : 'FIXTURE_OFFLINE' }] }))
    api.getRun.mockResolvedValue({ verifier_passed: null })
    const wrapper = mount(RunsHomeView, { global: { plugins: [router] } }); await flushPromises()
    expect(api.getRuns).toHaveBeenCalledWith('personal-id', { limit: 50 })
    expect(api.getRuns).toHaveBeenCalledWith('sample-id', { limit: 50 })
    expect(api.getRun).toHaveBeenCalledExactlyOnceWith('sample-run')
    expect(wrapper.get('[data-test=runs-table]').text()).toContain('owned-run')
    expect(wrapper.get('[data-test=runs-table]').text()).not.toContain('sample-id')
    expect(wrapper.get('[data-test=example-entry] a[href="/experiments/sample-id"]').text()).toContain('公开演示 · 基线')
  })
})
