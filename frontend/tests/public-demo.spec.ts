import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PublicDemoView from '@/views/PublicDemoView.vue'

const api = vi.hoisted(() => ({ getPublicDemo: vi.fn() }))
vi.mock('@/api/client', () => ({ workbenchApi: api }))
const demo = {
  demo_id: 'public-demo-new', generated_at: '2026-09-30T00:00:00Z', provenance: 'FIXTURE_OFFLINE',
  baseline_id: 'public-demo-new-baseline', candidate_id: 'public-demo-new-candidate', failed_run_id: 'new-run',
  run_count: 12, artifact_file_count: 108, manifest_digest: 'sha256:new', public_demo_ready: true,
  historical_integrity_failures: ['phase-i-matrix-multi-task'],
  limitation: 'Keyless Fake fixture; no real Provider/model execution.',
}
const options = { global: { stubs: { RouterLink: { props: ['to'], template: '<a :data-target="JSON.stringify(to)"><slot /></a>' } } } }
beforeEach(() => { api.getPublicDemo.mockReset() })
describe('Public demo identity', () => {
  it('routes the main journey to new identities and explicitly labels offline evidence', async () => {
    api.getPublicDemo.mockResolvedValue(demo)
    const wrapper = mount(PublicDemoView, options)
    await flushPromises()
    expect(wrapper.text()).toContain('不会启动 Agent 或调用真实模型')
    expect(wrapper.text()).toContain('FIXTURE_OFFLINE')
    expect(wrapper.text()).toContain('no real Provider/model execution')
    expect(wrapper.get('#demo-step-1 [data-target]').attributes('data-target')).toContain('public-demo-new-baseline')
    expect(wrapper.text()).toContain('历史 QA 证据不可用')
    expect(wrapper.find('details').attributes('open')).toBeUndefined()
    const destinations = wrapper.findAll('[data-target]').map(link => JSON.parse(link.attributes('data-target')!))
    expect(destinations).toEqual([
      { path: '/experiments/public-demo-new-baseline', query: { tab: 'runs', candidate: demo.candidate_id } },
      { path: '/runs/new-run', query: { candidate: demo.candidate_id } },
      { path: '/diagnosis', query: { experiment: demo.baseline_id, candidate: demo.candidate_id, run: demo.failed_run_id } },
      { path: '/regression', query: { baseline: demo.baseline_id, candidate: demo.candidate_id, run: demo.failed_run_id } },
      '/experiments/phase-i-matrix-multi-task',
    ])
    expect(wrapper.get('a[target="_blank"]').attributes('href')).toBe('/api/workbench/runs/new-run/public-artifact')
    expect(wrapper.text()).toContain(demo.manifest_digest)
  })
  it('fails closed when evidence integrity fails', async () => {
    api.getPublicDemo.mockRejectedValue({ response: { data: { error: { code: 'ARTIFACT_INTEGRITY_ERROR' } } } })
    const wrapper = mount(PublicDemoView, options)
    await flushPromises()
    expect(wrapper.text()).toContain('完整性校验未通过')
    expect(wrapper.find('.primary-button').exists()).toBe(false)
    expect(wrapper.find('.demo-identity').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('FIXTURE_OFFLINE')
  })
  it('does not show a ready journey when the gate is false', async () => {
    api.getPublicDemo.mockResolvedValue({ ...demo, public_demo_ready: false })
    const wrapper = mount(PublicDemoView, options)
    await flushPromises()
    expect(wrapper.text()).toContain('完整性校验未通过')
    expect(wrapper.find('.primary-button').exists()).toBe(false)
  })
  it('shows an explicit state when no demo is configured', async () => {
    api.getPublicDemo.mockRejectedValue({ response: { data: { error: { code: 'DEMO_NOT_CONFIGURED' } } } })
    const wrapper = mount(PublicDemoView, options)
    await flushPromises()
    expect(wrapper.text()).toContain('此工作区尚未配置公开演示')
  })
})
