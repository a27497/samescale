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
    expect(wrapper.find('[data-test=tool]').exists()).toBe(false)
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
    expect(wrapper.text()).toContain('tool_exit_codes'); expect(wrapper.text()).toContain('历史记录')
    wrapper.unmount()
  })
  it('keeps missing reliable task evidence unverified', async () => {
    vi.mocked(externalEvidenceApi.detail).mockResolvedValue({ ...detail, diagnosis: { ...detail.diagnosis, workspace_acceptance: 'NOT_VERIFIED', independent_verification: { checks: 0, passed_checks: 0 } } })
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    expect(wrapper.get('[data-test=acceptance]').text()).toContain('NOT_VERIFIED')
    expect(wrapper.get('[data-test=verification-next-step]').text()).toContain('仍为未验证'); wrapper.unmount()
  })
  it('shows permission and integrity errors without inventing records', async () => {
    vi.mocked(externalEvidenceApi.sources).mockRejectedValue({ response: { data: { error: { code: 'LOCAL_CONFIGURATION_DISABLED' } } } })
    const { wrapper } = await unlocked()
    expect(wrapper.get('[role=alert]').attributes('title')).toBe('LOCAL_CONFIGURATION_DISABLED')
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
    expect(wrapper.get('[data-test=healthy-record] .status-pill').text()).toBe('独立验收通过')
    expect(wrapper.get('[data-test=healthy-record] [data-test=record-technical-details]').text()).toContain('VERIFIED_PASS')
    expect(wrapper.get('[data-test=healthy-record] [data-test=record-technical-details]').attributes('open')).toBeUndefined()
    expect(wrapper.get('[data-test=corrupt-record] .status-pill').text()).toBe('记录损坏')
    expect(wrapper.get('[data-test=corrupt-record] [data-test=record-technical-details]').text()).toContain('CORRUPT')
    expect(wrapper.get('[data-test=corrupt-record] [data-test=record-technical-details]').text()).toContain('EVIDENCE_RECORD_CORRUPT')
    expect(wrapper.get('[data-test=corrupt-record]').text()).not.toContain('VERIFIED_PASS')
    expect(wrapper.get('[data-test=detail]').text()).toContain('NOT_VERIFIED')
    vi.mocked(externalEvidenceApi.detail).mockRejectedValue(reject('EVIDENCE_INTEGRITY_ERROR'))
    await router.push(`/external-runs/${corrupt.identity}`); await flushPromises()
    expect(wrapper.get('[role=alert]').attributes('title')).toBe('EVIDENCE_INTEGRITY_ERROR')
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
    expect(wrapper.get('[role=alert]').attributes('title')).toBe(code)
    expect(wrapper.find('[data-test=source]').exists()).toBe(false)
    expect(externalEvidenceApi.detail).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it.each(['EXTERNAL_EVIDENCE_DISABLED', 'EVIDENCE_POLICY_PERMISSION', 'EVIDENCE_POLICY_INVALID'])('explains configuration failure %s', async code => {
    vi.mocked(externalEvidenceApi.check).mockResolvedValue({ status: 'NOT_CONFIGURED', issues: [code], operator_configured: true, source_contents_checked: false, pins_verified: false, record_integrity_checked: false })
    const { wrapper } = await unlocked()
    expect(wrapper.get('[role=alert]').attributes('title')).toBe(code)
    expect(wrapper.get('[data-test=quickstart]').text()).toContain('external-evidence check')
    expect(externalEvidenceApi.sources).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('explains no approved sources without discovery', async () => {
    vi.mocked(externalEvidenceApi.sources).mockResolvedValue({ items: [] })
    vi.mocked(externalEvidenceApi.check).mockResolvedValue({ status: 'NO_APPROVED_SOURCES', issues: [], operator_configured: true, source_contents_checked: false, pins_verified: false, record_integrity_checked: false })
    const { wrapper } = await unlocked()
    expect(wrapper.text()).toContain('暂无批准来源')
    expect(wrapper.get('[data-test=configuration-check]').text()).toContain('暂无批准来源')
    expect(wrapper.get('[data-test=import]').attributes('disabled')).toBeDefined(); wrapper.unmount()
  })
  it.each(['EVIDENCE_PIN_MISMATCH', 'EVIDENCE_SENSITIVE_INPUT'])('explains rejected import %s without a fake result', async code => {
    vi.mocked(externalEvidenceApi.ingest).mockRejectedValue(reject(code))
    const { wrapper } = await unlocked()
    await wrapper.get('[data-test=source]').setValue(source.source_id)
    await wrapper.get('[data-test=consent]').setValue(true)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role=alert]').attributes('title')).toBe(code)
    expect(wrapper.text()).not.toContain('PRIVATE_EXCEPTION')
    expect(wrapper.find('[data-test=detail]').exists()).toBe(false); wrapper.unmount()
  })
  it('removes stale acceptance when export detects corruption', async () => {
    vi.mocked(externalEvidenceApi.export).mockRejectedValue(reject('EVIDENCE_INTEGRITY_ERROR'))
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    await wrapper.get('[data-test=export]').trigger('click'); await flushPromises()
    expect(wrapper.find('[data-test=detail]').exists()).toBe(false)
    expect(wrapper.get('[role=alert]').attributes('title')).toBe('EVIDENCE_INTEGRITY_ERROR'); wrapper.unmount()
  })
})

describe('tool-neutral intake', () => {
  const claude = { ...source, source_id: 'saved-claude', format: 'stream-json-v1', harness: { name: 'claude-code', version: 'synthetic-fixture' }, task_reference: 'custom:task/1', task_digest: 'sha256:task' }
  const code = { ...source, source_id: 'saved-code', format: 'code-only-v1', digest: null, task_reference: 'custom:task/1', task_digest: 'sha256:task' }
  it('filters approved inputs by tool and resets consent on a tool change', async () => {
    vi.mocked(externalEvidenceApi.sources).mockResolvedValue({ items: [source, claude, code] })
    const { wrapper } = await unlocked()
    expect(wrapper.get('h2').text()).toBe('导入运行记录')
    await wrapper.get('[data-test=tool]').setValue('claude-code')
    expect(wrapper.get('[data-test=source]').text()).toContain('saved-claude')
    expect(wrapper.get('[data-test=source]').text()).not.toContain('saved-real')
    await wrapper.get('[data-test=source]').setValue('saved-claude')
    expect(wrapper.get('[data-test=approved-inputs]').text()).toContain('sha256:b')
    expect(wrapper.get('[data-test=approved-inputs]').text()).toContain('custom:task/1')
    await wrapper.get('[data-test=consent]').setValue(true)
    await wrapper.get('[data-test=tool]').setValue('code-only')
    expect((wrapper.get('[data-test=consent]').element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.get('[data-test=import]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test=source]').setValue('saved-code')
    expect(wrapper.get('[data-test=approved-inputs]').text()).toContain('无运行记录')
    await wrapper.get('[data-test=consent]').setValue(true)
    vi.mocked(externalEvidenceApi.ingest).mockRejectedValue({ response: { data: { error: { code: 'EVIDENCE_PIN_MISMATCH' } } } })
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(externalEvidenceApi.ingest).toHaveBeenCalledWith('saved-code', 'operator-placeholder-only')
    expect(wrapper.find('[data-test=detail]').exists()).toBe(false)
    wrapper.unmount()
  })
  it.each([
    ['codex', 'SUPPLIED_EXEC_JSONL_ONLY', 'Codex'],
    ['claude-code', 'SUPPLIED_STREAM_JSON_ONLY', 'Claude Code'],
    ['code-only', 'NO_RUN_RECORD', '仅代码改动'],
  ])('shows truthful %s metadata without accepting a completion claim', async (name, coverage, label) => {
    const input = name === 'code-only' ? code : name === 'claude-code' ? claude : source
    vi.mocked(externalEvidenceApi.detail).mockResolvedValue({ ...detail, record: { ...detail.record, source: input, harness: name === 'code-only' ? null : { name, version: null }, episode_identity: null, completeness: { ...detail.record.completeness, coverage }, trace: [] }, diagnosis: { ...detail.diagnosis, workspace_acceptance: 'NOT_VERIFIED', independent_verification: { checks: 0, passed_checks: 0 }, agent_self_reports: [] } })
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    expect(wrapper.get('[data-test=harness]').text()).toContain(label)
    expect(wrapper.get('[data-test=acceptance]').text()).toContain('NOT_VERIFIED')
    expect(wrapper.get('[data-test=acceptance]').text()).toContain('0/0')
    expect(wrapper.get('[data-test=detail]').text()).not.toContain('VERIFIED_PASS')
    expect(wrapper.get('[data-test=technical-details]').attributes('open')).toBeUndefined()
    expect(wrapper.find('[data-test=technical-details] [data-test=acceptance]').exists()).toBe(true)
    if (name === 'code-only') {
      expect(wrapper.get('.acceptance-summary').text()).toContain('无运行记录')
      expect(wrapper.get('[data-test=verifier-command]').text()).toBe(`uv run --locked harnesslab external-evidence verify-workspace ${detail.identity} --confirm-independent-verifier`)
      expect(wrapper.find('[data-test=technical-details] [data-test=verifier-command]').exists()).toBe(true)
      expect(wrapper.get('[data-test=verifier-technical-guidance]').text()).toContain('HARNESSLAB_LOCAL_TASK_POLICY')
      expect(wrapper.get('[data-test=verification-next-step]').text()).not.toMatch(/TaskStore|oracle|baseline|HARNESSLAB_|Verifier|Workspace/)
      expect(wrapper.get('[data-test=verification-next-step]').text()).toContain('网页不能直接执行验收')
      expect(wrapper.get('[data-test=acceptance-original] .status-pill').attributes('data-status')).toBe('NOT_REPORTED')
    }
    wrapper.unmount()
  })
})

describe('source filtering and honest harness attribution', () => {
  it('labels the selector as all sources and retains unidentified auto inputs under both adapters', async () => {
    const auto = { ...source, source_id: 'auto-unidentified', format: 'auto-v1' }
    const declared = { ...auto, source_id: 'auto-declared-claude', harness: { name: 'claude-code', version: null } }
    vi.mocked(externalEvidenceApi.sources).mockResolvedValue({ items: [source, auto, declared] })
    const { wrapper } = await unlocked()
    expect(wrapper.get('[data-test=tool] option[value=all]').text()).toBe('全部来源')
    expect(wrapper.get('[data-test=source-filter]').text()).toContain('在点击导入后由后端识别')
    await wrapper.get('[data-test=tool]').setValue('codex')
    expect(wrapper.get('[data-test=source]').text()).toContain('auto-unidentified')
    expect(wrapper.get('[data-test=source]').text()).not.toContain('auto-declared-claude')
    await wrapper.get('[data-test=tool]').setValue('claude-code')
    expect(wrapper.get('[data-test=source]').text()).toContain('auto-unidentified')
    expect(wrapper.get('[data-test=source]').text()).toContain('auto-declared-claude')
    await wrapper.get('[data-test=source]').setValue('auto-unidentified')
    expect(wrapper.get('[data-test=approved-inputs]').text()).toContain('未报告')
    await wrapper.get('[data-test=consent]').setValue(true)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(externalEvidenceApi.ingest).toHaveBeenCalledWith('auto-unidentified', 'operator-placeholder-only')
    wrapper.unmount()
  })
  it.each([
    ['codex-jsonl-v1', 'Codex'], ['codex-h-lane-v1', 'Codex'],
    ['native-hook-v1', 'Codex'], ['verified-hook-v1', 'Codex'],
    ['auto-v1', '未报告'], ['hook-v1', '未报告'],
    ['h-lane-v1', '未报告'], ['stream-json-v1', '未报告'], ['future-v1', '未报告'],
  ])('attributes metadata-free %s honestly in input and saved detail', async (format, label) => {
    const input = { ...source, format }
    vi.mocked(externalEvidenceApi.sources).mockResolvedValue({ items: [input] })
    vi.mocked(externalEvidenceApi.detail).mockResolvedValue({ ...detail, record: { ...detail.record, source: input, harness: null } })
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    await wrapper.get('[data-test=source]').setValue(source.source_id)
    expect(wrapper.get('[data-test=approved-inputs]').text()).toContain(`${format} · ${label}`)
    expect(wrapper.get('[data-test=harness]').text()).toBe(`工具：${label} · 版本：未报告`)
    expect(wrapper.find('[data-test=verification-next-step]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('prefers reported record harness over legacy inference', async () => {
    vi.mocked(externalEvidenceApi.detail).mockResolvedValue({ ...detail, record: { ...detail.record, harness: { name: 'claude-code', version: 'fixture-only' } } })
    const { wrapper } = await unlocked(`/external-runs/${detail.identity}`)
    expect(wrapper.get('[data-test=harness]').text()).toBe('工具：Claude Code · 版本：fixture-only')
    wrapper.unmount()
  })
})

describe('Snapshot panel alongside existing record rows', () => {
  it('keeps one snapshot panel and preserves healthy versus corrupt record presentation', async () => {
    vi.mocked(externalEvidenceApi.records).mockResolvedValue({ items: [
      { identity: 'a'.repeat(64), status: 'AVAILABLE', source_id: 'healthy-original', source_kind: 'historical', acceptance: 'NOT_VERIFIED' },
      { identity: 'b'.repeat(64), status: 'CORRUPT', error_code: 'EVIDENCE_RECORD_CORRUPT', reason: 'Fixed integrity reason' },
    ] })
    const { wrapper } = await unlocked()
    expect(wrapper.findAll('[data-test=code-snapshot-panel]')).toHaveLength(1)
    expect(wrapper.get('[data-test=healthy-record]').text()).toContain('healthy-original')
    expect(wrapper.get('[data-test=healthy-record]').text()).not.toContain('损坏记录')
    expect(wrapper.get('[data-test=corrupt-record]').text()).toContain('损坏记录')
    wrapper.unmount()
  })
})
