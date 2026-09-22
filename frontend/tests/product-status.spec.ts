import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import ProductStatus from '@/components/ProductStatus.vue'
import { preferences } from '@/composables/preferences'

afterEach(() => vi.unstubAllGlobals())
const response = (body: object, ok = true) => ({ ok, json: async () => body })

it('keeps healthy mode compact and exposes workspace help on demand', async () => {
  preferences.language = 'zh-CN'
  const fetch = vi.fn().mockResolvedValueOnce(response({ mode: 'demo' })).mockResolvedValueOnce(response({ mode: 'demo', status: 'ready' }))
  vi.stubGlobal('fetch', fetch)
  const wrapper = mount(ProductStatus); await flushPromises()
  expect(wrapper.text()).toContain('演示模式')
  expect(wrapper.get('details').attributes('open')).toBeUndefined()
  expect(wrapper.get('summary').text()).toBe('演示模式')
  expect(wrapper.text()).toContain('samescale up')
  expect(fetch.mock.calls[1]?.[0]).toBe('/api/demo/health')
})

it('does not claim a workspace is ready from mode metadata and supports recovery', async () => {
  preferences.language = 'zh-CN'
  const fetch = vi.fn().mockResolvedValueOnce(response({ mode: 'workspace' })).mockResolvedValueOnce(response({ status: 'unhealthy' }, false))
  vi.stubGlobal('fetch', fetch)
  const wrapper = mount(ProductStatus); await flushPromises()
  expect(wrapper.text()).toContain('服务异常')
  expect(wrapper.text()).not.toContain('服务正常')
  fetch.mockResolvedValueOnce(response({ mode: 'workspace' })).mockResolvedValueOnce(response({ status: 'ok', database: 'ok' }))
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('服务正常')
})
