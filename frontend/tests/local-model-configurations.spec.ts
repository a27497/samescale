import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LocalModelConfigurations from '@/components/LocalModelConfigurations.vue'
import fixture from './fixtures/registry-connections.json'
import { preferences } from '@/composables/preferences'
import type { ProviderModelProfile, HarnessDefinition, ProviderDefinition } from '@/types/registry'

const api = vi.hoisted(() => ({ status: vi.fn(), list: vi.fn(), save: vi.fn(), credentials: vi.fn(), connections: vi.fn(), options: vi.fn(), harnesses: vi.fn() }))
vi.mock('@/api/localConfiguration', () => ({ localConfigurationApi: api }))
const stored = { configuration_id: 'my-model', name: 'My model', revision: 1, template_profile_id: fixture.models.provider_profiles[0]!.profile_id, request_timeout_seconds: 60, enabled: true, origin: 'LOCAL', template_digest: 'sha256:template', profile: { ...fixture.models.provider_profiles[0], profile_id: 'local-my-model-v1' } }
const mountEditor = () => mount(LocalModelConfigurations, { props: { providers: fixture.providers.items as ProviderDefinition[], profiles: fixture.models.provider_profiles as ProviderModelProfile[], harnesses: fixture.harnesses.items as HarnessDefinition[] } })
beforeEach(() => { vi.resetAllMocks(); preferences.language = 'zh-CN'; localStorage.clear(); api.status.mockResolvedValue({ enabled: true }); api.list.mockResolvedValue({ items: [] }); api.save.mockResolvedValue(stored); api.credentials.mockResolvedValue({ items: [] }); api.connections.mockResolvedValue({ items: [] }); api.harnesses.mockResolvedValue({ items: [] }); api.options.mockResolvedValue({ model_controls: fixture.models.provider_profiles.map(p => ({ profile_id: p.profile_id, max_output_tokens: p.max_output_tokens, reasoning_efforts: ['low','medium','high'], temperature_supported: false })), harness_templates: [] }) })
async function unlock(wrapper: ReturnType<typeof mountEditor>) {
  await flushPromises(); await wrapper.get('input[type=password]').setValue('test-operator-token'); await wrapper.get('form').trigger('submit'); await flushPromises()
}
describe('local configuration editing', () => {
  it('distinguishes disabled and failed status and does not request protected data', async () => {
    api.status.mockResolvedValueOnce({ enabled: false }); const disabled = mountEditor(); await flushPromises()
    expect(disabled.text()).toContain('本地编辑尚未启用'); expect(disabled.find('input').exists()).toBe(false); expect(api.list).not.toHaveBeenCalled()
    api.status.mockRejectedValueOnce(new Error('private-sentinel')); const failed = mountEditor(); await flushPromises()
    expect(failed.get('[role=alert]').text()).toContain('无法读取本地编辑状态'); expect(failed.text()).not.toContain('private-sentinel')
    await failed.get('button').trigger('click'); await flushPromises(); expect(failed.find('input[type=password]').exists()).toBe(true)
  })
  it('creates a versioned configuration and never stores the operator token', async () => {
    const wrapper = mountEditor(); await unlock(wrapper)
    const inputs = wrapper.findAll('.model-editor fieldset input'); await inputs[0]!.setValue('my-model'); await inputs[1]!.setValue('My model')
    await wrapper.get('.model-editor').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith('my-model', expect.objectContaining({ expected_revision: 0, request_timeout_seconds: 60, enabled: true }), 'test-operator-token')
    expect(wrapper.emitted('changed')).toHaveLength(1); expect(wrapper.text()).toContain('保存不会执行评测')
    expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0)
    expect(wrapper.get('.model-editor fieldset input').attributes('disabled')).toBeDefined()
    await wrapper.findAll('button').find(b => b.text() === '锁定')!.trigger('click')
    expect((wrapper.get('input[type=password]').element as HTMLInputElement).value).toBe('')
  })
  it('uses the loaded revision to disable and keeps conflicts explicit', async () => {
    api.list.mockResolvedValue({ items: [stored] }); const wrapper = mountEditor(); await unlock(wrapper)
    await wrapper.get('.local-list button').trigger('click'); await wrapper.get('.model-editor input[type=checkbox]').setValue(false)
    api.save.mockRejectedValueOnce(new Error('conflict-with-private-value'))
    await wrapper.get('.model-editor').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith('my-model', expect.objectContaining({ expected_revision: 1, enabled: false }), 'test-operator-token')
    expect(wrapper.emitted('changed')).toBeUndefined(); expect(wrapper.get('[role=alert]').text()).toContain('重新读取配置')
    expect(wrapper.text()).not.toContain('conflict-with-private-value')
  })
  it('ignores an unlock response after the editor unmounts', async () => {
    let resolve!: (value: { items: typeof stored[] }) => void
    api.list.mockReturnValue(new Promise(r => { resolve = r }))
    const wrapper = mountEditor(); await unlock(wrapper); wrapper.unmount(); resolve({ items: [stored] }); await flushPromises()
    expect(api.save).not.toHaveBeenCalled(); expect(localStorage.length).toBe(0)
  })
  it('shows English copy for the new management controls', async () => {
    preferences.language = 'en'; const wrapper = mountEditor(); await flushPromises()
    expect(wrapper.text()).toContain('Local model configurations'); expect(wrapper.text()).toContain('Unlock local configurations')
    await unlock(wrapper); expect(wrapper.text()).toContain('Reload'); expect(wrapper.text()).not.toContain('重新读取')
  })
})

 it('uses browser Unicode-sets patterns that accept legal IDs and reject malformed IDs', async () => {
   const wrapper = mountEditor(); await unlock(wrapper)
   const fields = wrapper.findAll('input[pattern]')
   expect(fields.length).toBeGreaterThan(0)
   for (const field of fields) {
     const pattern = new RegExp(`^(?:${field.attributes('pattern')})$`, 'v')
     expect(pattern.test('uat-valid-123')).toBe(true)
     for (const invalid of ['Invalid', '-bad', 'bad space', 'bad/key', 'a'.repeat(Number(field.attributes('maxlength')) + 1)]) expect(pattern.test(invalid)).toBe(false)
   }
 })
