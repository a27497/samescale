import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { comparisonFixture } from './fixtures/comparison'
import ExamplesView from '@/views/ExamplesView.vue'
import InvestigationReport from '@/components/InvestigationReport.vue'
import { reactive } from 'vue'
const routeStub = reactive<{ query: Record<string, string> }>({ query: {} })
const navigate = vi.hoisted(() => vi.fn())
vi.mock('vue-router', async importOriginal => ({ ...await importOriginal<typeof import('vue-router')>(), useRouter: () => ({ push: navigate }), useRoute: () => routeStub }))
const api = vi.hoisted(() => ({ comparison: vi.fn(), offline: vi.fn(), historical: vi.fn() }))
vi.mock('@/api/analyst', () => ({ analystApi: api }))
const report = {
  summary: 'Output order differs',
  verified_facts: [{ statement: 'Observed mismatch', evidence_refs: ['run:demo'] }],
  hypotheses: [{ statement: 'Possibly sorted', additional_evidence_needed: 'Inspect patch', evidence_refs: ['run:demo'] }],
  limitations: ['Synthetic inputs only'],
  evidence_catalog: [{ ref: { id: 'run:demo' }, digest_bindings: ['digest'], data_by_tool: { inspect_failure: { observed: ['a', 'b'] } } }],
}
function mountHome() { return mount(ExamplesView, { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } }) }
function button(wrapper: ReturnType<typeof mount>, name: string) { return wrapper.findAll('button').find(button => button.text() === name)! }
beforeEach(() => {
  window.history.replaceState(null, '')
  vi.resetAllMocks()
  routeStub.query = {}
  api.comparison.mockResolvedValue(comparisonFixture)
  navigate.mockImplementation(async to => {
    if (to === '/analyst' || to.path === '/examples') routeStub.query = to.query ?? {}
  })
  api.offline.mockResolvedValue({ kind: 'offline_fake', provenance: 'Fake / synthetic', report, metadata: { decisions: 2, tools: 2, provider_requests: 0 }, next_steps: ['Add regression'], proposal: null })
  api.historical.mockResolvedValue({ kind: 'historical_real', provenance: 'Historical real / read only', report, metadata: { decision_limit: 4 }, next_steps: ['Review historical plan'], proposal: null })
})
describe('Evaluation product entry', () => {
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
    expect(wrapper.get('[role="alert"]').text()).toContain('示例加载失败')
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
    expect(wrapper.get('dialog').attributes('open')).toBeDefined()
    expect(entry.get('.evidence-fields').text()).toContain('["a","b"]')
    expect(entry.get('details').attributes('open')).toBeUndefined()
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
  const wrapper = mount(ExamplesView, { attachTo: document.body, global: { stubs: { RouterLink: true } } })
  await button(wrapper, '运行离线演示').trigger('click'); await flushPromises()
  expect(document.activeElement).toBe(wrapper.get('[aria-label="调查案例"]').element)
  wrapper.unmount()
})

 it('closes the evidence drawer with Escape and clears a replaced source', async () => {
  const wrapper = mount(InvestigationReport, { props: { report, evidence: report.evidence_catalog }, attachTo: document.body })
  await wrapper.get('button.citation').trigger('click'); await flushPromises()
  await wrapper.get('dialog').trigger('keydown', { key: 'Escape' }); await flushPromises()
  expect(document.activeElement).toBe(wrapper.get('button.citation').element)
  await wrapper.get('button.citation').trigger('click'); await flushPromises()
  await wrapper.setProps({ evidence: [] })
  expect(wrapper.find('[data-evidence-index]').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('inspect_failure')
  wrapper.unmount()
})


it('ignores an old example response after navigating back to the home', async () => {
  let finish!: (value: unknown) => void
  api.offline.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const wrapper = mountHome()
  await button(wrapper, '运行离线演示').trigger('click'); await flushPromises()
  routeStub.query = {}; await flushPromises()
  finish({ kind: 'offline_fake', report, metadata: {}, next_steps: [], provenance: 'stale' }); await flushPromises()
  expect(wrapper.find('[aria-label="调查案例"]').exists()).toBe(false)
  expect(wrapper.find('.example-intro').exists()).toBe(true)
})



it('opens a comparison on demand and clears it when another example fails', async () => {
  const wrapper = mountHome()
  expect(wrapper.text()).toContain('直接调用与 Codex')
  expect(api.comparison).not.toHaveBeenCalled()
  await button(wrapper, '比较案例').trigger('click'); await flushPromises()
  expect(routeStub.query.example).toBe('comparison')
  expect(wrapper.find('.comparison-case').exists()).toBe(true)
  api.historical.mockRejectedValueOnce(new Error('digest mismatch'))
  await button(wrapper, '查看历史真实记录').trigger('click'); await flushPromises()
  expect(wrapper.find('.comparison-case').exists()).toBe(false)
  expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  expect(api.offline).not.toHaveBeenCalled()
})

it('reloads comparison URLs and retries failed reads without substituting another case', async () => {
  routeStub.query = { example: 'comparison' }
  api.comparison.mockRejectedValueOnce(new Error('missing evidence'))
  const wrapper = mountHome(); await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('示例加载失败')
  expect(wrapper.find('.comparison-case').exists()).toBe(false)
  await button(wrapper, '重试加载').trigger('click'); await flushPromises()
  expect(wrapper.find('.comparison-case').exists()).toBe(true)
  expect(api.comparison).toHaveBeenCalledTimes(2)
  expect(api.offline).not.toHaveBeenCalled()
  expect(api.historical).not.toHaveBeenCalled()
})

it('ignores a comparison response after leaving its URL', async () => {
  let finish!: (value: unknown) => void
  api.comparison.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  routeStub.query = { example: 'comparison' }
  const wrapper = mountHome(); await flushPromises()
  routeStub.query = {}; await flushPromises()
  finish(comparisonFixture); await flushPromises()
  expect(wrapper.find('.comparison-case').exists()).toBe(false)
  expect(wrapper.find('.example-intro').exists()).toBe(true)
})
