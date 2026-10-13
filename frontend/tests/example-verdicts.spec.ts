import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import RunsHomeView from '@/views/RunsHomeView.vue'
import { setLocale } from '@/composables/visualLocale'
const api = vi.hoisted(() => ({ listExperiments: vi.fn(), getRuns: vi.fn(), getRun: vi.fn() }))
vi.mock('@/api/client', () => ({ workbenchApi: api }))
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div />' } }] })
const mountHome = async () => { const wrapper = mount(RunsHomeView, { global: { plugins: [router] } }); await flushPromises(); return wrapper }
beforeEach(() => {
  vi.resetAllMocks(); setLocale('zh-CN')
  api.listExperiments.mockResolvedValue({ items: [{ experiment_id: 'fixture', name: 'Public Demo — offline fixture baseline', provenance: 'FIXTURE_OFFLINE', planned_run_count: 2 }] })
  api.getRuns.mockResolvedValue({ items: [{ run_id: 'r1', status: 'completed', normalized_outcome: 'capability_pass' }, { run_id: 'r2', status: 'completed', normalized_outcome: 'capability_pass' }], total: 2 })
  api.getRun.mockResolvedValue({ verifier_passed: null, verifier_score: { status: 'REPORTED', value: 1 } })
})
it('shows missing verdicts as unverified even when lifecycle, normalized outcome and scores suggest success', async () => {
  const wrapper = await mountHome(), row = wrapper.get('[data-test=example-acceptance-row]')
  expect(row.text()).toContain('尚未核验'); expect(row.text()).toContain('未提供独立验收结论')
  expect(row.text()).not.toContain('有已保存的独立验收结论')
  expect(api.getRun.mock.calls.map(args => args[0])).toEqual(['r1', 'r2'])
})
it('counts a failed independent verdict as a reported conclusion without describing it as a pass', async () => {
  api.getRun.mockResolvedValueOnce({ verifier_passed: false }).mockResolvedValueOnce({ verifier_passed: null })
  const wrapper = await mountHome(), row = wrapper.get('[data-test=example-acceptance-row]')
  expect(row.text()).toContain('有已保存的独立验收结论：1 / 2')
  expect(row.text()).toContain('有结论不代表全部通过')
  expect(row.text()).toContain('其余已读取记录尚未核验或暂不可读')
  expect(row.find('[data-status=VERIFIED_PASS]').exists()).toBe(false)
})
it('counts both explicit boolean verdicts without guessing from truthy values', async () => {
  api.getRun.mockResolvedValueOnce({ verifier_passed: true }).mockResolvedValueOnce({ verifier_passed: 'true' })
  const wrapper = await mountHome()
  expect(wrapper.get('[data-test=example-acceptance-row]').text()).toContain('1 / 2')
})
it('distinguishes inaccessible evidence from a missing verdict and hides private errors', async () => {
  api.getRun.mockRejectedValue(new Error('private-error-sentinel'))
  const wrapper = await mountHome(), row = wrapper.get('[data-test=example-acceptance-row]')
  expect(row.text()).toContain('验收结论暂时无法读取')
  expect(row.text()).not.toContain('尚未核验')
  expect(row.text()).not.toContain('private-error-sentinel')
})
it('keeps empty saved examples distinct from unverified runs', async () => {
  api.getRuns.mockResolvedValue({ items: [], total: 0 })
  const wrapper = await mountHome()
  expect(wrapper.text()).toContain('暂无已保存的示例运行记录')
  expect(api.getRun).not.toHaveBeenCalled()
})
it('states the bounded page scope instead of claiming every planned run has a verdict', async () => {
  api.getRuns.mockResolvedValue({ items: [{ run_id: 'r1' }], total: 60 })
  api.getRun.mockResolvedValue({ verifier_passed: false })
  const wrapper = await mountHome()
  expect(wrapper.text()).toContain('1 / 1 条已读取记录')
  expect(wrapper.text()).toContain('这里只读取前 50 条运行')
  expect(api.getRuns).toHaveBeenCalledExactlyOnceWith('fixture', { limit: 50 })
})
it('stops scheduling later batches when the home page is unmounted', async () => {
  api.getRuns.mockResolvedValue({ items: Array.from({ length: 10 }, (_, index) => ({ run_id: `r${index}` })), total: 10 })
  const resolvers: ((value: unknown) => void)[] = []
  api.getRun.mockImplementation(() => new Promise(done => { resolvers.push(done) }))
  const wrapper = await mountHome()
  expect(api.getRun).toHaveBeenCalledTimes(5)
  wrapper.unmount(); resolvers.forEach(resolve => resolve({ verifier_passed: true })); await flushPromises()
  expect(api.getRun).toHaveBeenCalledTimes(5)
})
