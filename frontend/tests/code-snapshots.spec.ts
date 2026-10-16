import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CodeSnapshotPanel from '@/components/CodeSnapshotPanel.vue'
import { codeSnapshotsApi, type CodeSnapshot, type SnapshotReview } from '@/api/codeSnapshots'

vi.mock('@/api/codeSnapshots', () => ({ codeSnapshotsApi: { preview: vi.fn(), confirm: vi.fn(), detail: vi.fn() } }))
const manifest = {
  archive_sha256: 'sha256:archive', archive_bytes: 512, declared_tool: 'unknown',
  content_digest: 'sha256:source', directories: [],
  included: [{ path: 'main.py', bytes: 10, sha256: 'sha256:file' }],
  excluded: [{ path: '.venv/library.py', bytes: 20, sha256: 'sha256:excluded', reason: 'DEPENDENCY_DIRECTORY' }],
}
const review: Extract<SnapshotReview, { status: 'REVIEW_REQUIRED' }> = {
  status: 'REVIEW_REQUIRED', manifest, manifest_sha256: 'sha256:manifest', review_signature: 'signature',
}
const saved: CodeSnapshot = {
  identity: 'a'.repeat(64), kind: 'code-snapshot-v1', source_authenticity: 'NOT_ATTESTED',
  run_record: 'NO_RUN_RECORD', verification: 'NOT_VERIFIED', manifest,
  confirmation: { consent: 'SAVE_REVIEWED_SOURCE_SUBSET', archive_sha256: manifest.archive_sha256,
    manifest_sha256: 'sha256:manifest', excluded_subset_acknowledged: true },
}
async function setup(path = '/external-runs', token = 'operator-placeholder') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/external-runs', component: CodeSnapshotPanel },
    { path: '/code-snapshots/:snapshotIdentity', component: CodeSnapshotPanel },
  ] })
  await router.push(path); await router.isReady()
  const wrapper = mount(CodeSnapshotPanel, { props: { token }, global: { plugins: [router] } })
  await flushPromises(); return { wrapper, router }
}
async function choose(wrapper: Awaited<ReturnType<typeof setup>>['wrapper']) {
  const file = new File(['synthetic zip fixture'], 'source.zip', { type: 'application/zip' })
  Object.defineProperty(wrapper.get('[data-test=snapshot-file]').element, 'files', { value: [file], configurable: true })
  await wrapper.get('[data-test=snapshot-file]').trigger('change'); return file
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(codeSnapshotsApi.preview).mockResolvedValue(review)
  vi.mocked(codeSnapshotsApi.confirm).mockResolvedValue(saved)
  vi.mocked(codeSnapshotsApi.detail).mockResolvedValue(saved)
})
describe('independent source snapshot intake', () => {
  it('requires a file and memory-only operator token', async () => {
    const { wrapper } = await setup('/external-runs', '')
    await choose(wrapper)
    expect(wrapper.get('[data-test=snapshot-preview]').attributes('disabled')).toBeDefined()
    expect(codeSnapshotsApi.preview).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('previews the original archive and every exclusion before explicit subset consent', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem')
    const { wrapper, router } = await setup(); const file = await choose(wrapper)
    await wrapper.get('[data-test=snapshot-preview]').trigger('click'); await flushPromises()
    expect(codeSnapshotsApi.preview).toHaveBeenCalledWith(file, 'unknown', 'operator-placeholder')
    expect(wrapper.get('[data-test=snapshot-review]').text()).toContain('原始归档')
    expect(wrapper.text()).toContain('.venv/library.py'); expect(wrapper.text()).toContain('依赖目录')
    expect(wrapper.text()).toContain('不代表完整导入原始 ZIP')
    expect(wrapper.get('[data-test=snapshot-confirm]').attributes('disabled')).toBeDefined()
    expect(codeSnapshotsApi.confirm).not.toHaveBeenCalled()
    await wrapper.get('[data-test=snapshot-consent]').setValue(true)
    await wrapper.get('[data-test=snapshot-confirm]').trigger('click'); await flushPromises()
    expect(codeSnapshotsApi.confirm).toHaveBeenCalledWith(file, 'unknown', review, 'operator-placeholder')
    expect(router.currentRoute.value.path).toBe(`/code-snapshots/${saved.identity}`)
    const text = wrapper.get('[data-test=snapshot-detail]').text()
    for (const state of ['NOT_ATTESTED', 'NO_RUN_RECORD', 'NOT_VERIFIED', '未绑定任务', '可信任务', '.venv/library.py', 'sha256:file']) expect(text).toContain(state)
    expect(storage).not.toHaveBeenCalled(); storage.mockRestore(); wrapper.unmount()
  })
  it('shows whole-archive rejection with no confirmation or invented snapshot', async () => {
    vi.mocked(codeSnapshotsApi.preview).mockResolvedValue({ status: 'REJECTED', rejections: [{ reason: 'CREDENTIAL_CONTENT', entry: 2, path: 'config.py' }] })
    const { wrapper } = await setup(); await choose(wrapper)
    await wrapper.get('[data-test=snapshot-preview]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-test=snapshot-rejected]').text()).toContain('整包拒绝')
    expect(wrapper.text()).toContain('内容命中凭据规则')
    expect(wrapper.find('[data-test=snapshot-confirm]').exists()).toBe(false)
    expect(codeSnapshotsApi.confirm).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('shows upload limit as explicit whole-archive rejection with no snapshot', async () => {
    vi.mocked(codeSnapshotsApi.preview).mockRejectedValue({ response: { status: 413, data: { error: { code: 'ZIP_UPLOAD_LIMIT' } } } })
    const { wrapper } = await setup(); await choose(wrapper)
    await wrapper.get('[data-test=snapshot-preview]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-test=snapshot-rejected]').text()).toContain('整包拒绝')
    expect(wrapper.text()).toContain('8,000,000')
    expect(wrapper.find('[data-test=snapshot-confirm]').exists()).toBe(false)
    expect(codeSnapshotsApi.confirm).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('clears the reviewed subset and consent when file or declared tool changes', async () => {
    const { wrapper } = await setup(); await choose(wrapper)
    await wrapper.get('[data-test=snapshot-preview]').trigger('click'); await flushPromises()
    await wrapper.get('[data-test=snapshot-consent]').setValue(true)
    await wrapper.get('[data-test=snapshot-tool]').setValue('deepseek-harness-desktop')
    expect(wrapper.find('[data-test=snapshot-review]').exists()).toBe(false)
    await wrapper.get('[data-test=snapshot-preview]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-test=snapshot-confirm]').attributes('disabled')).toBeDefined()
    await choose(wrapper); expect(wrapper.find('[data-test=snapshot-review]').exists()).toBe(false); wrapper.unmount()
  })
  it('does not display a late review for changed selections', async () => {
    let resolve!: (value: SnapshotReview) => void
    vi.mocked(codeSnapshotsApi.preview).mockReturnValueOnce(new Promise(r => { resolve = r }))
    const { wrapper } = await setup(); await choose(wrapper)
    await wrapper.get('[data-test=snapshot-preview]').trigger('click')
    await wrapper.setProps({ token: 'new-placeholder' })
    resolve(review); await flushPromises()
    expect(wrapper.find('[data-test=snapshot-review]').exists()).toBe(false); wrapper.unmount()
  })
  it('rejects changed archive/manifest on confirm and clears consent for retry', async () => {
    vi.mocked(codeSnapshotsApi.confirm).mockRejectedValue({ response: { data: { error: { code: 'ZIP_REVIEW_MISMATCH' } } } })
    const { wrapper } = await setup(); await choose(wrapper)
    await wrapper.get('[data-test=snapshot-preview]').trigger('click'); await flushPromises()
    await wrapper.get('[data-test=snapshot-consent]').setValue(true)
    await wrapper.get('[data-test=snapshot-confirm]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-test=snapshot-error]').text()).toContain('ZIP_REVIEW_MISMATCH')
    expect(wrapper.find('[data-test=snapshot-detail]').exists()).toBe(false)
    expect(wrapper.get('[data-test=snapshot-confirm]').attributes('disabled')).toBeDefined(); wrapper.unmount()
  })
  it('refuses tampered snapshot details without presenting stale data', async () => {
    vi.mocked(codeSnapshotsApi.detail).mockRejectedValue({ response: { data: { error: { code: 'SNAPSHOT_INTEGRITY_ERROR' } } } })
    const { wrapper } = await setup(`/code-snapshots/${saved.identity}`)
    expect(wrapper.find('[data-test=snapshot-detail]').exists()).toBe(false)
    expect(wrapper.get('[data-test=snapshot-error]').text()).toContain('SNAPSHOT_INTEGRITY_ERROR'); wrapper.unmount()
  })
})
