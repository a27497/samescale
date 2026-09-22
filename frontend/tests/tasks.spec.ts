import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, expect, it, vi } from 'vitest'
import TasksView from '@/views/TasksView.vue'
import { productModeKey } from '@/composables/productContext'
import { preferences } from '@/composables/preferences'

const api = vi.hoisted(() => ({ tasks: vi.fn() }))
vi.mock('@/api/client', () => ({ registryApi: api }))
const items = [
  { task_id: 'micro-python-dedupe', task_version: '1', task_digest: 'sha256:python', package_path: 'tasks/python', tier: 'TIER_A_MICRO_CONTRACT' },
  { task_id: 'micro-typescript-clamp', task_version: '2', task_digest: 'sha256:ts', package_path: 'tasks/typescript', tier: 'TIER_A_MICRO_CONTRACT' },
]
beforeEach(() => { vi.resetAllMocks(); preferences.language = 'zh-CN'; api.tasks.mockResolvedValue({ items }) })
function setup(mode = ref('workspace')) {
  return mount(TasksView, { global: { provide: { [productModeKey as symbol]: mode }, stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })
}
it('reads registered task identities and filters them without inventing results', async () => {
  const wrapper = setup(); await flushPromises()
  expect(api.tasks).toHaveBeenCalledTimes(1)
  expect(wrapper.findAll('article')).toHaveLength(2)
  expect(wrapper.text()).toContain('不能代表通用工程能力')
  await wrapper.get('input').setValue('PYTHON')
  expect(wrapper.findAll('article')).toHaveLength(1)
  expect(wrapper.get('article').text()).toContain('sha256:python')
  await wrapper.get('input').setValue('missing')
  expect(wrapper.text()).toContain('没有匹配的任务')
  expect(api.tasks).toHaveBeenCalledTimes(1)
})
it('distinguishes unavailable reads from empty data and retries explicitly', async () => {
  api.tasks.mockRejectedValueOnce(new Error('unavailable'))
  const wrapper = setup(); await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('无法读取任务集')
  expect(wrapper.text()).not.toContain('当前没有已注册任务')
  api.tasks.mockResolvedValueOnce({ items: [] })
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.text()).toContain('当前没有已注册任务')
})
it('only offers workspace planning after its mode is known', async () => {
  const mode = ref('unknown'); const wrapper = setup(mode); await flushPromises()
  expect(wrapper.find('a').exists()).toBe(false)
  mode.value = 'demo'; await flushPromises()
  expect(wrapper.find('a').exists()).toBe(false)
  mode.value = 'workspace'; await flushPromises()
  expect(wrapper.get('a').attributes('href')).toBe('/experiments/new')
  expect(api.tasks).toHaveBeenCalledTimes(1)
})
