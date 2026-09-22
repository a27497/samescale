import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import SavedPlans from '@/components/SavedPlans.vue'
import { preferences } from '@/composables/preferences'
const api = vi.hoisted(() => ({ snapshots: vi.fn(), getSnapshot: vi.fn(), preflight: vi.fn(), snapshot: vi.fn() }))
vi.mock('@/api/client', () => ({ registryApi: api }))
const saved = { snapshot_id: 'snapshot-one', snapshot_digest: 'sha256:one', plan: { name: 'Saved UAT plan', evaluation_mode: 'QUICK' }, preflight: { status: 'READY_WITH_WARNINGS' }, comparison_type: 'END_TO_END_SYSTEM_COMPARISON' }
beforeEach(() => {
  vi.resetAllMocks(); preferences.language = 'zh-CN'
  api.snapshots.mockResolvedValue({ items: [{ ...saved, name: saved.plan.name, created_at: '2026-09-22T00:00:00Z' }], total: 1, limit: 25, offset: 0 })
  api.getSnapshot.mockResolvedValue(saved)
})
async function open(url = '/experiments') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/experiments', component: SavedPlans }] })
  await router.push(url); await router.isReady()
  const wrapper = mount(SavedPlans, { global: { plugins: [router] } }); await flushPromises()
  return { wrapper, router }
}
it('finds server-saved plans and reconstructs the selected detail after refresh without preflight or writes', async () => {
  const { wrapper, router } = await open()
  await wrapper.get('.plan-list a').trigger('click'); await flushPromises()
  expect(router.currentRoute.value.query.snapshot).toBe('snapshot-one')
  expect(wrapper.get('article').text()).toContain('sha256:one')
  const reentry = router.currentRoute.value.fullPath; wrapper.unmount()
  const again = await open(reentry)
  expect(again.wrapper.get('article').text()).toContain('Saved UAT plan')
  expect(again.wrapper.text()).toContain('保存时的预检状态；不是当前连接健康或执行授权。')
  expect(api.getSnapshot).toHaveBeenCalledTimes(2)
  expect(api.preflight).not.toHaveBeenCalled(); expect(api.snapshot).not.toHaveBeenCalled()
})
it('keeps empty, failed and missing/corrupt detail states distinct and retries read-only', async () => {
  api.snapshots.mockRejectedValueOnce(new Error('private response'))
  api.getSnapshot.mockRejectedValueOnce(new Error('integrity error'))
  const { wrapper } = await open('/experiments?snapshot=missing')
  expect(wrapper.text()).toContain('无法读取已保存计划'); expect(wrapper.text()).not.toContain('尚无已保存计划')
  expect(wrapper.text()).not.toContain('private response'); expect(wrapper.find('article').exists()).toBe(false)
  api.snapshots.mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 })
  await wrapper.findAll('button').find(b => b.text() === '重新读取计划')!.trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('尚无已保存计划')
  await wrapper.findAll('button').find(b => b.text() === '重新读取此计划')!.trigger('click'); await flushPromises()
  // An unrelated successful response must not replace the requested identity.
  expect(wrapper.find('article').exists()).toBe(false)
  expect(wrapper.text()).toContain('无法读取或校验此计划')
})
it('does not reopen an older selection after navigation, and pages server history', async () => {
  let finish!: (v: unknown) => void
  api.getSnapshot.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  api.snapshots.mockResolvedValue({ items: [{ ...saved, name: 'First page' }], total: 26, limit: 25, offset: 0 })
  const { wrapper, router } = await open('/experiments?snapshot=old')
  await router.push('/experiments?snapshot=snapshot-one'); await flushPromises()
  finish({ ...saved, snapshot_id: 'old', plan: { name: 'stale sentinel' } }); await flushPromises()
  expect(wrapper.get('article').text()).not.toContain('stale sentinel')
  api.snapshots.mockResolvedValue({ items: [], total: 26, limit: 25, offset: 25 })
  await wrapper.findAll('button').find(b => b.text() === '下一页计划')!.trigger('click'); await flushPromises()
  expect(api.snapshots).toHaveBeenLastCalledWith(25)
  await router.push('/experiments'); await flushPromises()
  expect(wrapper.find('article').exists()).toBe(false)
})
