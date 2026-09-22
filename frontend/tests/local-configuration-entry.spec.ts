import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from '@/App.vue'
import applicationRouter from '@/router'
import ConnectionsView from '@/views/ConnectionsView.vue'
import { preferences } from '@/composables/preferences'
import fixture from './fixtures/registry-connections.json'

const registry = vi.hoisted(() => ({ models: vi.fn(), providers: vi.fn(), harnesses: vi.fn(), capabilities: vi.fn(), settings: vi.fn() }))
const local = vi.hoisted(() => ({ status: vi.fn(), list: vi.fn(), options: vi.fn(), credentials: vi.fn(), connections: vi.fn(), harnesses: vi.fn(), save: vi.fn() }))
vi.mock('@/api/client', () => ({ registryApi: registry }))
vi.mock('@/api/localConfiguration', () => ({ localConfigurationApi: local }))
afterEach(() => vi.unstubAllGlobals())
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); sessionStorage.clear(); preferences.language = 'zh-CN'
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/product') return { ok: true, json: async () => ({ mode: 'workspace' }) }
    if (url === '/api/health') return { ok: true, json: async () => ({ status: 'ok', database: 'ok' }) }
    throw new Error(`Unexpected test request: ${url}`)
  }))
  registry.capabilities.mockResolvedValue(structuredClone(fixture.capabilities))
  registry.models.mockResolvedValue(structuredClone(fixture.models))
  registry.providers.mockResolvedValue(structuredClone(fixture.providers))
  registry.harnesses.mockResolvedValue(structuredClone(fixture.harnesses))
  registry.settings.mockResolvedValue(structuredClone(fixture.settings))
  local.status.mockResolvedValue({ enabled: true }); local.list.mockResolvedValue({ items: [] })
  local.options.mockResolvedValue({ model_controls: fixture.models.provider_profiles.map(p => ({ profile_id: p.profile_id, max_output_tokens: p.max_output_tokens, reasoning_efforts: ['low', 'medium', 'high'], temperature_supported: false })), harness_templates: [] })
  local.credentials.mockResolvedValue({ items: [] }); local.connections.mockResolvedValue({ items: [] }); local.harnesses.mockResolvedValue({ items: [] })
})
async function open() {
  const router = createRouter({ history: createMemoryHistory(), routes: applicationRouter.options.routes })
  await router.push('/connections'); await router.isReady()
  const wrapper = mount(App, { global: { plugins: [router] } }); await flushPromises()
  return { wrapper, router }
}
describe('local configuration application entry', () => {
  it('uses the real application route and navigation, and honors disabled server status', async () => {
    local.status.mockResolvedValue({ enabled: false })
    const { wrapper } = await open()
    expect(wrapper.find('a[href="/connections"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('本地编辑尚未启用')
    expect(wrapper.find('input[type=password]').exists()).toBe(false)
    expect(local.list).not.toHaveBeenCalled()
  })
  it('refreshes catalog after a save without unmounting the unlocked editor, then clears on navigation', async () => {
    const { wrapper, router } = await open()
    const before = wrapper.findComponent(ConnectionsView).element
    await wrapper.get('input[type=password]').setValue('operator-placeholder')
    await wrapper.get('.local-models form').trigger('submit'); await flushPromises()
    await wrapper.get('.model-editor input[aria-label="配置 ID"]').setValue('my-model')
    const inputs = wrapper.findAll('.model-editor fieldset input'); await inputs[1]!.setValue('My model')
    local.save.mockResolvedValue({ configuration_id: 'my-model', name: 'My model', revision: 1, template_profile_id: fixture.models.provider_profiles[0]!.profile_id, request_timeout_seconds: 60, enabled: true, profile: { ...fixture.models.provider_profiles[0], profile_id: 'local-my-model-v1' } })
    await wrapper.get('.model-editor').trigger('submit'); await flushPromises()
    expect(local.save).toHaveBeenCalledOnce(); expect(registry.models).toHaveBeenCalledTimes(2)
    expect(wrapper.findComponent(ConnectionsView).element).toBe(before)
    expect(wrapper.text()).toContain('配置已保存')
    expect(localStorage.length + sessionStorage.length).toBe(0)
    await router.push('/settings'); await flushPromises(); await router.push('/connections'); await flushPromises()
    expect((wrapper.get('input[type=password]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.find('.model-editor').exists()).toBe(false)
  })
  it('clears stale catalog templates on failure and reloads without echoing private errors', async () => {
    registry.models.mockRejectedValueOnce(new Error('private-endpoint-sentinel'))
    const { wrapper } = await open()
    expect(wrapper.get('.connections-page > [role=alert]').text()).toContain('模型配置')
    expect(wrapper.text()).not.toContain('private-endpoint-sentinel')
    await wrapper.get('.connections-page .connections-toolbar button').trigger('click'); await flushPromises()
    expect(wrapper.find('.connections-page > [role=alert]').exists()).toBe(false)
    expect(registry.models).toHaveBeenCalledTimes(2)
  })
})
