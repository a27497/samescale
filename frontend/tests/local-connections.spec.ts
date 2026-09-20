import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LocalConnections from '@/components/LocalConnections.vue'
import fixture from './fixtures/registry-connections.json'
import { preferences } from '@/composables/preferences'
import type { ProviderDefinition } from '@/types/registry'
const api = vi.hoisted(() => ({ credentials: vi.fn(), connections: vi.fn(), saveCredential: vi.fn(), saveConnection: vi.fn(), checkConnection: vi.fn() }))
vi.mock('@/api/localConfiguration', () => ({ localConfigurationApi: api }))
const credential = { credential_id: 'my-key', name: 'My key', revision: 2, enabled: true, present: true, reference: 'KEY_REF_V2' }
const connection = { connection_id: 'my-service', name: 'My service', revision: 3, enabled: true, template_provider_id: 'gpt56-relay', protocol: 'responses', credential_id: 'my-key', credential_revision: 1, ready_for_planning: false }
const editor = () => mount(LocalConnections, { props: { token: 'test-token', providers: fixture.providers.items as ProviderDefinition[] } })
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); sessionStorage.clear(); preferences.language = 'zh-CN'; api.credentials.mockResolvedValue({ items: [credential] }); api.connections.mockResolvedValue({ items: [connection] }) })
describe('local connections', () => {
  it('rotates credentials with exact revision and clears write-only input immediately', async () => {
    const wrapper = editor(); await flushPromises()
    await wrapper.get('.credential-editor li button').trigger('click')
    await wrapper.get('input[type=password]').setValue('fake-key-sentinel')
    let done!: () => void; api.saveCredential.mockReturnValue(new Promise<void>(resolve => { done = resolve }))
    await wrapper.get('.credential-editor form').trigger('submit')
    expect((wrapper.get('input[type=password]').element as HTMLInputElement).value).toBe('')
    expect(api.saveCredential).toHaveBeenCalledWith('my-key', { name: 'My key', expected_revision: 2, enabled: true, value: 'fake-key-sentinel' }, 'test-token')
    done(); await flushPromises(); expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(localStorage.length + sessionStorage.length).toBe(0)
    expect(api.checkConnection).not.toHaveBeenCalled()
  })
  it('keeps an existing URL private and explicitly rebinds the latest credential version', async () => {
    const wrapper = editor(); await flushPromises()
    await wrapper.get('.connection-editor li button').trigger('click')
    expect((wrapper.get('input[type=url]').element as HTMLInputElement).value).toBe('')
    await wrapper.get('.connection-editor form').trigger('submit'); await flushPromises()
    expect(api.saveConnection).toHaveBeenCalledWith('my-service', expect.objectContaining({ expected_revision: 3, credential_id: 'my-key', credential_revision: 2 }), 'test-token')
    expect(api.saveConnection.mock.calls[0]![1]).not.toHaveProperty('base_url')
    expect(api.checkConnection).not.toHaveBeenCalled()
  })
  it('disables without resending the stored key and does not echo failure details', async () => {
    const wrapper = editor(); await flushPromises(); await wrapper.get('.credential-editor li button').trigger('click')
    await wrapper.get('.credential-editor input[type=checkbox]').setValue(false)
    api.saveCredential.mockRejectedValue(new Error('private-response-secret'))
    await wrapper.get('.credential-editor form').trigger('submit'); await flushPromises()
    expect(api.saveCredential.mock.calls[0]![1]).toEqual({ name: 'My key', expected_revision: 2, enabled: false })
    expect(wrapper.get('[role=alert]').text()).toContain('保存未确认')
    expect(wrapper.text()).not.toContain('private-response-secret'); expect(wrapper.emitted('changed')).toBeUndefined()
  })
  it('runs local checks only on explicit action and never calls health verified', async () => {
    const wrapper = editor(); await flushPromises(); expect(api.checkConnection).not.toHaveBeenCalled()
    api.checkConnection.mockResolvedValue({ connection: { ready_for_planning: true }, connection_health: 'NOT_VERIFIED', network_requests: 0, provider_requests: 0 })
    await wrapper.findAll('button').find(b => b.text() === '校验配置（不联网）')!.trigger('click'); await flushPromises()
    expect(wrapper.get('[role=status]').text()).toContain('连接健康与密钥有效性仍未验证')
  })
  it('ignores a save completion after leaving the editor', async () => {
    const wrapper = editor(); await flushPromises(); await wrapper.get('.credential-editor li button').trigger('click')
    let done!: () => void; api.saveCredential.mockReturnValue(new Promise<void>(resolve => { done = resolve }))
    await wrapper.get('.credential-editor form').trigger('submit'); wrapper.unmount(); done(); await flushPromises()
    expect(api.credentials).toHaveBeenCalledTimes(1); expect(wrapper.emitted('changed')).toBeUndefined()
  })
  it('renders English connection controls and retains an explicit load error', async () => {
    preferences.language = 'en'; api.connections.mockRejectedValue(new Error('private-load-secret'))
    const wrapper = editor(); await flushPromises()
    expect(wrapper.text()).toContain('Service connections and credentials'); expect(wrapper.text()).toContain('Reload connections and credentials')
    expect(wrapper.get('[role=alert]').text()).toContain('Could not load'); expect(wrapper.text()).not.toContain('private-load-secret')
  })
})
