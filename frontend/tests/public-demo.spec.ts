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
    expect(wrapper.text()).toContain('Offline fixture demonstration')
    expect(wrapper.text()).toContain('no real Provider/model execution')
    expect(wrapper.find('.primary-button').attributes('data-target')).toContain('public-demo-new-baseline')
    expect(wrapper.text()).toContain('Historical QA evidence — artifact integrity failed')
    expect(wrapper.find('details').attributes('open')).toBeUndefined()
  })
  it('fails closed when evidence integrity fails', async () => {
    api.getPublicDemo.mockRejectedValue({ response: { data: { error: { code: 'ARTIFACT_INTEGRITY_ERROR' } } } })
    const wrapper = mount(PublicDemoView, options)
    await flushPromises()
    expect(wrapper.text()).toContain('Evidence integrity failed')
    expect(wrapper.find('.primary-button').exists()).toBe(false)
  })
  it('does not show a ready journey when the gate is false', async () => {
    api.getPublicDemo.mockResolvedValue({ ...demo, public_demo_ready: false })
    const wrapper = mount(PublicDemoView, options)
    await flushPromises()
    expect(wrapper.text()).toContain('Public demo validation did not pass')
    expect(wrapper.find('.primary-button').exists()).toBe(false)
  })
  it('shows an explicit state when no demo is configured', async () => {
    api.getPublicDemo.mockRejectedValue({ response: { data: { error: { code: 'DEMO_NOT_CONFIGURED' } } } })
    const wrapper = mount(PublicDemoView, options)
    await flushPromises()
    expect(wrapper.text()).toContain('No public demo is configured')
  })
})
