import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { preferences } from '@/composables/preferences'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ConnectionsView from '@/views/ConnectionsView.vue'
import SettingsView from '@/views/SettingsView.vue'
import ModelsView from '@/views/ModelsView.vue'
import HarnessesView from '@/views/HarnessesView.vue'
import ProvidersView from '@/views/ProvidersView.vue'
import ConnectionStates from '@/components/ConnectionStates.vue'
import { productModeKey } from '@/composables/productContext'
import fixture from './fixtures/registry-connections.json'
const api = vi.hoisted(() => ({ models: vi.fn(), providers: vi.fn(), harnesses: vi.fn(), capabilities: vi.fn(), settings: vi.fn() }))
vi.mock('@/api/client', () => ({ registryApi: api }))
vi.mock('@/api/localConfiguration', () => ({ localConfigurationApi: { status: async () => ({ enabled: false }) } }))
const profile = 'gpt56-relay-gpt56-responses'
const harness = 'codex-gpt56-medium'
const location = `/connections?profile=${profile}&harness=${harness}`
function routerFor() {
  return createRouter({ history: createMemoryHistory(), routes: ['/connections','/settings','/models','/providers','/harnesses','/capabilities','/experiments/new'].map(path => ({ path, component: { template: '<div />' } })) })
}
async function open(path = location) {
  const router = routerFor(); await router.push(path)
  const wrapper = mount(ConnectionsView, { global: { plugins: [router], provide: { [productModeKey as symbol]: ref('workspace') } } })
  await flushPromises(); return { wrapper, router }
}
beforeEach(() => {
  preferences.language = 'zh-CN'
  vi.resetAllMocks()
  for (const key of Object.keys(api) as (keyof typeof api)[]) api[key].mockResolvedValue(structuredClone(fixture[key]))
})
describe('read-only connections and independent state', () => {
  it('does not turn configured credentials or supported pairs into health or authorization', async () => {
    const settings = structuredClone(fixture.settings)
    settings.credentials.find(c => c.credential_ref === 'HARNESSLAB_GPT56_RELAY_API_KEY')!.status = 'SET'
    api.settings.mockResolvedValue(settings)
    const { wrapper } = await open()
    expect(wrapper.get('[data-state="credential"] [data-status]').attributes('data-status')).toBe('SET')
    expect(wrapper.get('[data-state="compatibility"] [data-status]').attributes('data-status')).toBe('SUPPORTED')
    expect(wrapper.get('[data-state="health"]').findAll('[data-status]').every(s => s.attributes('data-status') === 'UNKNOWN')).toBe(true)
    expect(wrapper.get('[data-state="authorization"]').text()).toContain('实际执行仍需单独授权')
    expect(wrapper.find('input[type="password"]').exists()).toBe(false)
    expect(wrapper.find('a[href="/models?id=gpt-5.6-sol"]').exists()).toBe(true)
    expect(wrapper.find('a[href="/providers?id=gpt56-relay"]').exists()).toBe(true)
  })
  it('keeps a missing credential distinct from declared health, including quota failure', async () => {
    const providers = structuredClone(fixture.providers); providers.items[0]!.health_status = 'QUOTA_EXHAUSTED'
    api.providers.mockResolvedValue(providers)
    const { wrapper } = await open()
    expect(wrapper.get('[data-state="credential"] [data-status]').attributes('data-status')).toBe('MISSING')
    expect(wrapper.get('[data-state="health"]').text()).toContain('额度耗尽')
    expect(wrapper.get('[data-state="compatibility"] [data-status]').attributes('data-status')).toBe('SUPPORTED')
    expect(wrapper.get('[data-state="authorization"] [data-status]').attributes('data-status')).toBe('NO_EXECUTION_GRANT')
  })
  it('explains unsupported and partial pairs using exact server pairs as selections change', async () => {
    const { wrapper, router } = await open()
    await wrapper.get('[aria-label="模型服务配置"]').setValue('opencode-go-glm52-chat'); await flushPromises()
    expect(router.currentRoute.value.query.profile).toBe('opencode-go-glm52-chat')
    expect(wrapper.get('[data-state="compatibility"]').text()).toContain('此执行方式不支持该协议。')
    expect(wrapper.get('[data-state="compatibility"]').text()).toContain('PROVIDER_MODEL_PROFILE_UNSUPPORTED_BY_HARNESS')
    await router.push(`/connections?profile=${profile}&harness=direct-${profile}`); await flushPromises()
    expect(wrapper.get('[data-state="compatibility"] [data-status]').attributes('data-status')).toBe('PARTIALLY_SUPPORTED')
    expect(wrapper.get('[data-state="compatibility"]').text()).toContain('轨迹覆盖有限')
    expect(api.models).toHaveBeenCalledTimes(1)
  })
  it('clears stale values on refresh, isolates failed reads, and restores them only after retry', async () => {
    const { wrapper } = await open()
    api.settings.mockRejectedValueOnce(new Error('private sentinel'))
    api.capabilities.mockRejectedValueOnce(new Error('private sentinel'))
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('凭据与默认值')
    expect(wrapper.text()).not.toContain('private sentinel')
    expect(wrapper.get('[data-state="credential"] [data-status]').attributes('data-status')).toBe('NOT_REPORTED')
    expect(wrapper.get('[data-state="compatibility"] [data-status]').attributes('data-status')).toBe('NOT_VERIFIED')
    expect(wrapper.text()).toContain('Codex')
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('[data-state="compatibility"] [data-status]').attributes('data-status')).toBe('SUPPORTED')
  })
  it('does not substitute the first profile for a removed URL identity or an absent assessment', async () => {
    const { wrapper, router } = await open('/connections?profile=removed&harness=removed')
    expect(wrapper.text()).toContain('链接中的配置已不存在')
    expect(wrapper.get('[data-state="compatibility"] [data-status]').attributes('data-status')).toBe('NOT_VERIFIED')
    expect(wrapper.find('.connection-relations a').exists()).toBe(false)
    api.capabilities.mockResolvedValue({ items: [] })
    await router.push(location); await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-state="compatibility"]').text()).toContain('缺少此组合')
    expect(wrapper.get('[data-state="compatibility"] [data-status]').attributes('data-status')).toBe('NOT_VERIFIED')
  })
  it('shows registered resources without inventing a configured model and keeps defaults unknown', async () => {
    api.models.mockResolvedValue({ models: [], provider_profiles: [] })
    const { wrapper } = await open('/connections')
    expect(wrapper.text()).toContain('模型或运行配置缺失。')
    expect(wrapper.get('[data-state="credential"] [data-status]').attributes('data-status')).toBe('NOT_REPORTED')
    expect(wrapper.get('#runtime').text()).toContain('未配置')
    expect(wrapper.get('a[href="/providers"]').text()).toBe('全部模型服务')
  })
  it('does not reveal a planning link in demo or unknown mode', async () => {
    const router = routerFor(); await router.push(location)
    const mode = ref('unknown')
    const wrapper = mount(ConnectionsView, { global: { plugins: [router], provide: { [productModeKey as symbol]: mode } } }); await flushPromises()
    expect(wrapper.find('a[href="/experiments/new"]').exists()).toBe(false)
    mode.value = 'demo'; await flushPromises()
    expect(wrapper.find('a[href="/experiments/new"]').exists()).toBe(false)
    mode.value = 'workspace'; await flushPromises()
    expect(wrapper.find('a[href="/experiments/new"]').exists()).toBe(true)
  })
  it('explains unknown reason codes without converting them to success', async () => {
    api.capabilities.mockResolvedValue({ items: [{ ...fixture.capabilities.items[0], provider_profile_id: profile, harness_profile_id: harness, status: 'UNSUPPORTED', reason_codes: ['FUTURE_LIMIT'] }] })
    const { wrapper } = await open()
    const state = wrapper.getComponent(ConnectionStates)
    expect(state.text()).toContain('服务端报告了此限制')
    expect(state.text()).toContain('FUTURE_LIMIT')
  })
  it('links resource details back to the selected connection and preserves unknown identities', async () => {
    const router = routerFor(); await router.push('/models?id=gpt-5.6-sol')
    const options = { global: { plugins: [router] } }
    const models = mount(ModelsView, options); await flushPromises()
    expect(models.find(`a[href="/connections?profile=${profile}"]`).exists()).toBe(true)
    models.unmount(); await router.push('/harnesses?id=codex')
    const harnesses = mount(HarnessesView, options); await flushPromises()
    expect(harnesses.find(`a[href="/connections?harness=${harness}"]`).exists()).toBe(true)
    await router.push('/harnesses?id=removed'); await flushPromises()
    expect(harnesses.get('.resource-detail').text()).toContain('未找到所选资源')
    expect(harnesses.find('.harness-card').exists()).toBe(false)
    harnesses.unmount(); await router.push('/providers?id=opencode-go')
    const providers = mount(ProvidersView, options); await flushPromises()
    expect(providers.get('.resource-detail').text()).toContain('opencode-go')
    expect(providers.get('.resource-detail').text()).not.toContain('HARNESSLAB_GPT56_RELAY_API_KEY')
  })
  it('keeps settings usable without any registry requests and links to the canonical defaults', async () => {
    const router = routerFor(); await router.push('/settings')
    const wrapper = mount(SettingsView, { global: { plugins: [router] } }); await flushPromises()
    expect(wrapper.find('a[href="/connections#runtime"]').exists()).toBe(true)
    expect(wrapper.find('a[href="/analyst/sessions"]').exists()).toBe(false)
    for (const method of Object.values(api)) expect(method).not.toHaveBeenCalled()
  })
})

 it.each(['zh-CN', 'en'] as const)('separates direct baselines from agent runtimes without changing identities in %s', async language => {
  preferences.language = language
  const router = routerFor(); await router.push('/harnesses?id=direct-model')
  const wrapper = mount(HarnessesView, { global: { plugins: [router] } }); await flushPromises()
  expect(wrapper.get('[data-resource-group="直接调用"]').text()).toContain('direct-model')
  expect(wrapper.get('[data-resource-group="编程 Agent"]').text()).not.toContain('direct-model')
  expect(wrapper.get('[data-resource-group="编程 Agent"]').text()).toContain('Codex')
  expect(wrapper.get('.harness-card').text()).toContain(language === 'en' ? 'Direct model calls' : '直接调用')
  expect(wrapper.get('.harness-card').text()).toContain('direct-model')
  wrapper.unmount()
  const { wrapper: connections, router: connectionRouter } = await open()
  const select = connections.get('select[aria-label="' + (language === 'en' ? 'Execution mode' : '执行方式') + '"]')
  expect(select.get('optgroup[label="' + (language === 'en' ? 'Coding agents' : '编程 Agent') + '"]').find('option[value^="direct-"]').exists()).toBe(false)
  await select.setValue('direct-gpt56-relay-gpt56-responses'); await flushPromises()
  expect(connectionRouter.currentRoute.value.query.harness).toBe('direct-gpt56-relay-gpt56-responses')
 })
