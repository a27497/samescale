import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AnalystHomeView from '@/views/AnalystHomeView.vue'
import InvestigationReport from '@/components/InvestigationReport.vue'
import router from '@/router'
const api = vi.hoisted(() => ({ offline: vi.fn(), historical: vi.fn() }))
vi.mock('@/api/analyst', () => ({ analystApi: api }))
const report = {
  summary: 'Output order differs',
  verified_facts: [{ statement: 'Observed mismatch', evidence_refs: ['run:demo'] }],
  hypotheses: [{ statement: 'Possibly sorted', additional_evidence_needed: 'Inspect patch', evidence_refs: ['run:demo'] }],
  limitations: ['Synthetic inputs only'],
  evidence_catalog: [{ ref: { id: 'run:demo' }, digest_bindings: ['digest'], data_by_tool: { inspect_failure: { observed: ['a', 'b'] } } }],
}
function mountHome() { return mount(AnalystHomeView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } }) }
function button(wrapper: ReturnType<typeof mount>, name: string) { return wrapper.findAll('button').find(button => button.text() === name)! }
beforeEach(() => {
  vi.resetAllMocks()
  api.offline.mockResolvedValue({ kind: 'offline_fake', provenance: 'Fake / synthetic', report, metadata: { decisions: 2, tools: 2, provider_requests: 0 }, next_steps: ['Add regression'], proposal: null })
  api.historical.mockResolvedValue({ kind: 'historical_real', provenance: 'Historical real / read only', report, metadata: { decision_limit: 4 }, next_steps: ['Review historical plan'], proposal: null })
})
describe('Agent product entry', () => {
  it('lands at Analyst and preserves advanced routes without starting anything', async () => {
    expect(router.getRoutes().find(route => route.path === '/')?.redirect).toBe('/analyst')
    for (const path of ['/overview', '/experiments', '/judgelab', '/analyst/sessions']) expect(router.getRoutes().some(route => route.path === path)).toBe(true)
    const wrapper = mountHome(); await flushPromises()
    expect(wrapper.text()).toContain('无需 Provider Key')
    expect(api.offline).not.toHaveBeenCalled()
    expect(api.historical).not.toHaveBeenCalled()
  })
  it('keeps Fake, frozen real and current sessions visibly distinct', async () => {
    const wrapper = mountHome()
    await button(wrapper, '运行离线演示').trigger('click'); await flushPromises()
    expect(wrapper.get('[aria-label="调查案例"]').text()).toContain('Fake / synthetic')
    expect(api.historical).not.toHaveBeenCalled()
    await button(wrapper, '查看历史真实记录').trigger('click'); await flushPromises()
    expect(wrapper.get('[aria-label="调查案例"]').text()).toContain('Historical real / read only')
    expect(wrapper.get('[aria-label="调查案例"]').text()).not.toContain('Fake / synthetic')
    expect(wrapper.findAll('button').some(button => /Resume|Approve/.test(button.text()))).toBe(false)
  })
  it('removes stale results on failure and allows an explicit retry without fallback', async () => {
    const wrapper = mountHome()
    await button(wrapper, '运行离线演示').trigger('click'); await flushPromises()
    api.historical.mockRejectedValueOnce(new Error('Invalid digest'))
    await button(wrapper, '查看历史真实记录').trigger('click'); await flushPromises()
    expect(wrapper.find('[aria-label="调查案例"]').exists()).toBe(false)
    expect(wrapper.get('[role="alert"]').text()).toContain('不会显示替代结果')
    expect(api.offline).toHaveBeenCalledTimes(1)
    await button(wrapper, '查看历史真实记录').trigger('click'); await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="调查案例"]').text()).toContain('Historical real')
  })
  it('opens and focuses the cited evidence and labels missing sources', async () => {
    const wrapper = mount(InvestigationReport, { props: { report, evidence: report.evidence_catalog }, attachTo: document.body })
    await wrapper.get('button.citation').trigger('click'); await flushPromises()
    const entry = wrapper.get('[data-evidence-index="0"]')
    expect(document.activeElement).toBe(entry.element)
    expect(entry.get('details').attributes('open')).toBeDefined()
    expect(entry.text()).toContain('inspect_failure')
    await wrapper.get('button.return-citation').trigger('click')
    expect(document.activeElement).toBe(wrapper.get('button.citation').element)
    await wrapper.get('.report-nav button').trigger('click')
    expect(document.activeElement).toBe(wrapper.get('[data-report-section="0"]').element)
    expect(wrapper.findAll('h3').map(item => item.text())).toEqual(['1 · 结论', '2 · 证据', '3 · 限制与待验证假设', '4 · 下一步'])
    await wrapper.setProps({ evidence: [] })
    expect(wrapper.text().match(/来源不可用：run:demo/g)).toHaveLength(2)
    expect(wrapper.find('.return-citation').exists()).toBe(false)
    expect(wrapper.find('button.citation').exists()).toBe(false)
    wrapper.unmount()
  })
})

it('focuses the loaded result after keyboard activation', async () => {
  const wrapper = mount(AnalystHomeView, { attachTo: document.body, global: { stubs: { RouterLink: true } } })
  await button(wrapper, '运行离线演示').trigger('click'); await flushPromises()
  expect(document.activeElement).toBe(wrapper.get('[aria-label="调查案例"]').element)
  wrapper.unmount()
})
