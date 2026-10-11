import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ExternalEvidenceView from '@/views/ExternalEvidenceView.vue'
import { externalEvidenceApi, type EvidenceDetail } from '@/api/externalEvidence'

vi.mock('@/api/externalEvidence', () => ({ externalEvidenceApi: { check: vi.fn(), sources: vi.fn(), records: vi.fn(), ingest: vi.fn(), detail: vi.fn(), export: vi.fn() } }))
const source = { source_id: 'saved-real', source_kind: 'historical' as const, format: 'verified-hook-v1', digest: 'sha256:a', workspace_digest: 'sha256:b', task_reference: null, task_digest: null }
const detail: EvidenceDetail = { identity: 'a'.repeat(64), record: { source, episode_identity: 'sha256:c', original_acceptance: 'NOT_VERIFIED', workspace_digest: 'sha256:b', workspace_files: { 'events.py': 'sha256:d' }, completeness: { status: 'PARTIAL', coverage: 'PAIRED_HOOKS_ONLY', missing_fields: ['usage', 'tool_exit_codes'], integrity: 'PINNED_BYTES_VERIFIED', origin: 'NOT_ATTESTED' }, trace: [{ ordinal: 1, type: 'COMMAND_EXECUTION', status: 'observed', exit_code: null, file_paths: [], agent_report: null }] }, diagnosis: { original_episode_acceptance: 'NOT_VERIFIED', workspace_acceptance: 'VERIFIED_PASS', independent_verification: { checks: 5, passed_checks: 5 }, agent_self_reports: [], observed_failed_tools: [], file_changes: { status: 'DIGEST_BOUND_BASELINE', paths: ['events.py'] }, infrastructure: { status: 'UNKNOWN', root_cause: null }, limits: ['Digests do not attest origin.'] } }
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(externalEvidenceApi.check).mockResolvedValue({ status: 'CONFIGURED', issues: [], operator_configured: true, source_contents_checked: false, pins_verified: false, record_integrity_checked: false })
  vi.mocked(externalEvidenceApi.sources).mockResolvedValue({ items: [source] })
  vi.mocked(externalEvidenceApi.records).mockResolvedValue({ items: [] })
  vi.mocked(externalEvidenceApi.ingest).mockResolvedValue(detail)
  vi.mocked(externalEvidenceApi.detail).mockResolvedValue(detail)
})
async function screen(path = '/external-runs') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/external-runs/:identity?', component: ExternalEvidenceView }] })
  await router.push(path); await router.isReady()
  const wrapper = mount(ExternalEvidenceView, { global: { plugins: [router] } })
  return { wrapper, router }
}
async function unlocked(path?: string) {
  const result = await screen(path)
  await result.wrapper.get('[data-test=operator]').setValue('operator-placeholder-only')
  await result.wrapper.get('form').trigger('submit'); await flushPromises()
  return result
}
describe('Private saved Codex evidence', () => {
  it('does not invent an Episode for supplied JSONL or partial hooks', async () => {
    vi.mocked(externalEvidenceApi.detail).mockResolvedValue({ ...detail, record: { ...detail.record, episode_identity: null }, diagnosis: { ...detail.diagnosis, workspace_acceptance: 'NOT_VERIFIED', independent_verification: { checks: 0, passed_checks: 0 } } })
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    expect(wrapper.text()).toContain('未提供可导入的原 Episode')
    expect(wrapper.text()).not.toContain('原 Episode 保留'); wrapper.unmount()
  })
  it('requires operator access and explicit source consent; never stores credentials', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem')
    const { wrapper } = await screen()
    expect(externalEvidenceApi.sources).not.toHaveBeenCalled()
    await wrapper.get('[data-test=operator]').setValue('operator-placeholder-only')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    await wrapper.get('[data-test=source]').setValue('saved-real')
    expect(wrapper.get('[data-test=import]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test=consent]').setValue(true)
    expect(wrapper.get('[data-test=import]').attributes('disabled')).toBeUndefined()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(externalEvidenceApi.ingest).toHaveBeenCalledWith('saved-real', 'operator-placeholder-only')
    expect(storage).not.toHaveBeenCalled(); storage.mockRestore(); wrapper.unmount()
  })
  it('keeps original Episode separate from independent acceptance and unknown tool exits', async () => {
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    expect(wrapper.get('[data-test=acceptance]').text()).toContain('VERIFIED_PASS')
    expect(wrapper.text()).toContain('NOT_VERIFIED'); expect(wrapper.text()).toContain('UNKNOWN')
    expect(wrapper.text()).toContain('tool_exit_codes'); expect(wrapper.text()).toContain('historical')
    wrapper.unmount()
  })
  it('keeps missing reliable task evidence unverified', async () => {
    vi.mocked(externalEvidenceApi.detail).mockResolvedValue({ ...detail, diagnosis: { ...detail.diagnosis, workspace_acceptance: 'NOT_VERIFIED', independent_verification: { checks: 0, passed_checks: 0 } } })
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    expect(wrapper.get('[data-test=acceptance]').text()).toContain('NOT_VERIFIED')
    expect(wrapper.text()).toContain('保持未验证'); wrapper.unmount()
  })
  it('shows permission and integrity errors without inventing records', async () => {
    vi.mocked(externalEvidenceApi.sources).mockRejectedValue({ response: { data: { error: { code: 'LOCAL_CONFIGURATION_DISABLED' } } } })
    const { wrapper } = await unlocked()
    expect(wrapper.get('[role=alert]').text()).toContain('LOCAL_CONFIGURATION_DISABLED')
    expect(wrapper.find('[data-test=detail]').exists()).toBe(false); wrapper.unmount()
  })
  it('exports only on user request and displays the separately retained digest', async () => {
    const create = vi.fn(() => 'blob:local'); const revoke = vi.fn()
    vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: revoke })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    vi.mocked(externalEvidenceApi.export).mockResolvedValue({ blob: new Blob(['sanitized']), digest: 'sha256:export-pin' })
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    expect(externalEvidenceApi.export).not.toHaveBeenCalled()
    await wrapper.get('[data-test=export]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('sha256:export-pin'); expect(revoke).toHaveBeenCalledWith('blob:local')
    click.mockRestore(); vi.unstubAllGlobals(); wrapper.unmount()
  })
  it('discards a late response for a previous record', async () => {
    const { wrapper, router } = await unlocked(`/external-runs/${detail.identity}`)
    let resolve!: (value: EvidenceDetail) => void
    vi.mocked(externalEvidenceApi.detail).mockReturnValueOnce(new Promise(r => { resolve = r }))
    await router.push('/external-runs/old'); await flushPromises()
    await router.push('/external-runs/new'); await flushPromises()
    resolve({ ...detail, record: { ...detail.record, source: { ...source, source_id: 'stale-record' } } }); await flushPromises()
    expect(wrapper.text()).not.toContain('stale-record'); wrapper.unmount()
  })
})

describe('P1 isolation and onboarding', () => {
  it('keeps saved records readable when an approved original source is removed', async () => {
    vi.mocked(externalEvidenceApi.check).mockResolvedValue({ status: 'NEEDS_ATTENTION', issues: ['SOURCE_LOCATION_UNAVAILABLE'], operator_configured: true, source_contents_checked: false, pins_verified: false, record_integrity_checked: false })
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    expect(wrapper.text()).toContain('已保存的健康记录仍可读取')
    expect(wrapper.get('[data-test=detail]').text()).toContain('5/5'); wrapper.unmount()
  })
  const corrupt = { identity: 'b'.repeat(64), status: 'CORRUPT' as const, error_code: 'EVIDENCE_RECORD_CORRUPT' as const, reason: 'Fixed integrity reason' }
  const available = { identity: detail.identity, status: 'AVAILABLE' as const, source_id: source.source_id, source_kind: source.source_kind, acceptance: 'VERIFIED_PASS' }
  const reject = (code: string, status = 409) => ({ response: { status, data: { error: { code, message: 'PRIVATE_EXCEPTION_NEVER_REFLECTED' } } } })
  it('unlocks mixed records and refuses corrupt detail without borrowing a verdict', async () => {
    vi.mocked(externalEvidenceApi.records).mockResolvedValue({ items: [available, corrupt] })
    const { wrapper, router } = await unlocked(`/external-runs/${detail.identity}`)
    expect(wrapper.get('[data-test=healthy-record]').text()).toContain('VERIFIED_PASS')
    expect(wrapper.get('[data-test=corrupt-record]').text()).toContain('EVIDENCE_RECORD_CORRUPT')
    expect(wrapper.get('[data-test=corrupt-record]').text()).not.toContain('VERIFIED_PASS')
    expect(wrapper.get('[data-test=detail]').text()).toContain('NOT_VERIFIED')
    vi.mocked(externalEvidenceApi.detail).mockRejectedValue(reject('EVIDENCE_INTEGRITY_ERROR'))
    await router.push(`/external-runs/${corrupt.identity}`); await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('EVIDENCE_INTEGRITY_ERROR')
    expect(wrapper.find('[data-test=detail]').exists()).toBe(false)
    expect(wrapper.find('[data-test=healthy-record]').exists()).toBe(true); wrapper.unmount()
  })
  it('shows all corrupt records rather than an empty or successful list', async () => {
    vi.mocked(externalEvidenceApi.records).mockResolvedValue({ items: [corrupt, { ...corrupt, identity: 'c'.repeat(64) }] })
    const { wrapper } = await unlocked()
    expect(wrapper.findAll('[data-test=corrupt-record]')).toHaveLength(2)
    expect(wrapper.text()).not.toContain('暂无记录')
    expect(wrapper.text()).not.toContain('VERIFIED_PASS'); wrapper.unmount()
  })
  it('allows known healthy detail after a transient concurrent list failure', async () => {
    vi.mocked(externalEvidenceApi.records).mockRejectedValue(reject('SERVER_UNAVAILABLE', 503))
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    expect(wrapper.get('[data-test=list-error]').text()).toContain('并非空列表')
    expect(wrapper.get('[data-test=detail]').text()).toContain('5/5')
    expect(wrapper.text()).not.toContain('PRIVATE_EXCEPTION'); wrapper.unmount()
  })
  it.each(['EVIDENCE_STORAGE_UNSAFE', 'EVIDENCE_POLICY_PERMISSION', 'LOCAL_OPERATOR_REQUIRED'])('keeps global %s failures closed', async code => {
    vi.mocked(externalEvidenceApi.records).mockRejectedValue(reject(code, 403))
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    expect(wrapper.get('[role=alert]').text()).toContain(code)
    expect(wrapper.find('[data-test=source]').exists()).toBe(false)
    expect(externalEvidenceApi.detail).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it.each(['EXTERNAL_EVIDENCE_DISABLED', 'EVIDENCE_POLICY_PERMISSION', 'EVIDENCE_POLICY_INVALID'])('explains configuration failure %s', async code => {
    vi.mocked(externalEvidenceApi.check).mockResolvedValue({ status: 'NOT_CONFIGURED', issues: [code], operator_configured: true, source_contents_checked: false, pins_verified: false, record_integrity_checked: false })
    const { wrapper } = await unlocked()
    expect(wrapper.get('[role=alert]').text()).toContain(code)
    expect(wrapper.get('[data-test=quickstart]').text()).toContain('external-evidence check')
    expect(externalEvidenceApi.sources).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('explains no approved sources without discovery', async () => {
    vi.mocked(externalEvidenceApi.sources).mockResolvedValue({ items: [] })
    vi.mocked(externalEvidenceApi.check).mockResolvedValue({ status: 'NO_APPROVED_SOURCES', issues: [], operator_configured: true, source_contents_checked: false, pins_verified: false, record_integrity_checked: false })
    const { wrapper } = await unlocked()
    expect(wrapper.text()).toContain('暂无批准来源')
    expect(wrapper.get('[data-test=configuration-check]').text()).toContain('NO_APPROVED_SOURCES')
    expect(wrapper.get('[data-test=import]').attributes('disabled')).toBeDefined(); wrapper.unmount()
  })
  it.each(['EVIDENCE_PIN_MISMATCH', 'EVIDENCE_SENSITIVE_INPUT'])('explains rejected import %s without a fake result', async code => {
    vi.mocked(externalEvidenceApi.ingest).mockRejectedValue(reject(code))
    const { wrapper } = await unlocked()
    await wrapper.get('[data-test=source]').setValue(source.source_id)
    await wrapper.get('[data-test=consent]').setValue(true)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain(code)
    expect(wrapper.text()).not.toContain('PRIVATE_EXCEPTION')
    expect(wrapper.find('[data-test=detail]').exists()).toBe(false); wrapper.unmount()
  })
  it('removes stale acceptance when export detects corruption', async () => {
    vi.mocked(externalEvidenceApi.export).mockRejectedValue(reject('EVIDENCE_INTEGRITY_ERROR'))
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    await wrapper.get('[data-test=export]').trigger('click'); await flushPromises()
    expect(wrapper.find('[data-test=detail]').exists()).toBe(false)
    expect(wrapper.get('[role=alert]').text()).toContain('EVIDENCE_INTEGRITY_ERROR'); wrapper.unmount()
  })
})
