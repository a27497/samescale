import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import router from '@/router'
import type { DiagnosisReport } from '@/types/workbench'
import DiagnosisView from '@/views/DiagnosisView.vue'

const api = vi.hoisted(() => ({
  listExperiments: vi.fn(),
  getDiagnosis: vi.fn(),
  getExperiment: vi.fn(),
  exportBadCases: vi.fn(),
}))

vi.mock('@/api/client', () => ({ workbenchApi: api }))

const report: DiagnosisReport = {
  schema_version: 1 as const,
  experiment_id: 'diagnosis-fixture',
  plan_digest: `sha256:${'1'.repeat(64)}`,
  report_digest: `sha256:${'2'.repeat(64)}`,
  cluster_dimensions: ['model', 'harness', 'task', 'language', 'task_family', 'failure_class', 'trace_pattern', 'tool_pattern', 'workspace_diff_pattern'],
  correlation_warning: 'Trace correlation is not causality; only controlled ablation can strengthen attribution.',
  classification_limitations: ['Free-form output is never guessed into a taxonomy.'],
  failure_run_count: 1,
  real_run_count: 1,
  synthetic_run_count: 0,
  cells: [{
    cell_id: 'codex-low',
    task_families: [{
      task_family: 'targeted-bug-fix',
      clusters: [{
        cluster_id: `sha256:${'3'.repeat(64)}`,
        dimensions: { model: 'fixture-model', harness: 'codex', failure_class: 'Test Failure' },
        failure_class: 'Test Failure',
        failure_scope: 'CAPABILITY' as const,
        run_count: 1,
        real_run_count: 1,
        synthetic_run_count: 0,
        runs: [{
          run_id: 'fixture-run', origin: 'IMMUTABLE_EXPERIMENT' as const,
          task_id: 'micro-python-clamp', task_version: '1.0.0', model: 'fixture-model',
          harness: 'codex', language: 'python', task_family: 'targeted-bug-fix',
          failure_class: 'Test Failure', failure_scope: 'CAPABILITY' as const,
          artifact_verified: true, evidence_identity: `sha256:${'6'.repeat(64)}`,
          trace: { status: 'REPORTED' as const, coverage: 'FULL_STREAM', digest: `sha256:${'4'.repeat(64)}`, pattern: 'COMMAND_EXECUTION:1', events: [] },
          workspace_diff: { status: 'REPORTED' as const, input_digest: null, output_digest: null, pattern: 'paths=1', changed_paths: [{ path: 'solution.py', status: 'modified' }], protected_paths_changed: [] },
          tool_calls: { status: 'REPORTED' as const, count: 1, pattern: 'count=1;failed=0', failed_exit_codes: [] },
          verifier: { status: 'FAILED' as const, score: 0, sandbox_status: 'succeeded', failure_subtype: null },
          attributions: [
            { kind: 'VERIFIED_FACT' as const, statement: 'Structured evidence classifies this run.', evidence_references: ['run:fixture-run'], causal_strength: 'NOT_APPLICABLE' as const, caveat: null },
            { kind: 'HYPOTHESIS' as const, statement: 'Patterns may explain the cluster.', evidence_references: [], causal_strength: 'CORRELATION_ONLY' as const, caveat: 'Trace correlation is not causality.' },
          ],
        }],
      }],
    }],
  }],
}

beforeEach(async () => {
  vi.resetAllMocks()
  await router.push('/diagnosis')
  api.listExperiments.mockResolvedValue({ items: [{ experiment_id: 'diagnosis-fixture', name: 'Diagnosis fixture' }], total: 1, limit: 100, offset: 0 })
  api.getDiagnosis.mockResolvedValue(report)
  api.exportBadCases.mockResolvedValue({
    experiment_id: 'diagnosis-fixture', export_digest: `sha256:${'5'.repeat(64)}`,
    real_case_count: 1, synthetic_qualification_case_count: 0,
    cases: [{ run_id: 'fixture-run', origin: 'IMMUTABLE_EXPERIMENT' }],
    limitation: 'Real BadCases require verified immutable evidence; synthetic qualification cases are labeled and never counted as real BadCases.',
  })
})

describe('Diagnosis Workbench', () => {
  it('registers Diagnosis before the productized catch-all route', () => {
    const paths = router.getRoutes().map((item) => item.path)
    expect(paths).toContain('/diagnosis')
    expect(paths).toContain('/:pathMatch(.*)*')
  })

  it('renders the backend drill-down and explicit attribution boundary', async () => {
    const wrapper = mount(DiagnosisView, { global: { plugins: [router] } })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('失败模式')
    expect(text).toContain('codex-low')
    expect(text).toContain('targeted-bug-fix')
    expect(text).toContain('Test Failure')
    expect(text).toContain('Trace')
    expect(text).toContain('最终工作区差异')
    expect(text).toContain('工具调用')
    expect(text).toContain('Verifier')
    expect(text).toContain('VERIFIED_FACT')
    expect(text).toContain('HYPOTHESIS')
    expect(text).toContain('Trace correlation is not causality')
    expect(api.getDiagnosis).toHaveBeenCalledWith('diagnosis-fixture')
  })

  it('exports only backend-selected real BadCases', async () => {
    const createObjectURL = vi.fn(() => 'blob:fixture')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const wrapper = mount(DiagnosisView, { global: { plugins: [router] } })
    await flushPromises()
    await wrapper.get('[data-test="export-failures"]').trigger('click')
    await flushPromises()

    expect(api.exportBadCases).toHaveBeenCalledWith('diagnosis-fixture')
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fixture')
    expect(wrapper.text()).toContain('已下载持久化案例 / 合成资格案例: 1 / 0')
    expect(wrapper.find('[data-status="UNVERIFIED_SOURCE"]').exists()).toBe(true)
    click.mockRestore()
  })

  it('loads a linked experiment outside the first list page', async () => {
    api.getExperiment.mockResolvedValue({ experiment_id: 'outside-first-page', name: 'Older run', provenance: 'FIXTURE_OFFLINE' })
    await router.push('/diagnosis?experiment=outside-first-page')
    const wrapper = mount(DiagnosisView, { global: { plugins: [router] } })
    await flushPromises()
    expect(api.getExperiment).toHaveBeenCalledWith('outside-first-page')
    expect(api.getDiagnosis).toHaveBeenCalledWith('outside-first-page')
    expect(wrapper.find('[data-status="FIXTURE_OFFLINE"]').exists()).toBe(true)
  })
})

it('offers an executable runs link when diagnosis has no failures', async () => {
  api.getDiagnosis.mockResolvedValue({ ...report, failure_run_count: 0, cells: [] })
  const wrapper = mount(DiagnosisView, { global: { plugins: [router] } }); await flushPromises()
  expect(wrapper.get('a[href="/experiments/diagnosis-fixture?tab=runs"]').text()).toBe('查看实验运行')
  expect(wrapper.text()).not.toContain('Open a run to inspect')
})


it('updates a same-page experiment deep link outside the bounded list without keeping the old report', async () => {
  await router.push('/diagnosis?experiment=diagnosis-fixture')
  const wrapper = mount(DiagnosisView, { global: { plugins: [router] } })
  await flushPromises()
  api.getExperiment.mockResolvedValue({ experiment_id: 'older-linked', name: 'Older record', provenance: 'FIXTURE_OFFLINE' })
  api.getDiagnosis.mockResolvedValue({ ...report, experiment_id: 'older-linked', failure_run_count: 0, cells: [] })
  await router.push('/diagnosis?experiment=older-linked'); await flushPromises()
  expect(api.getExperiment).toHaveBeenCalledWith('older-linked')
  expect(api.getDiagnosis).toHaveBeenLastCalledWith('older-linked')
  expect(wrapper.find('.selected-run-identity').exists()).toBe(false)
  expect((wrapper.get('[data-test="diagnosis-experiment"]').element as HTMLSelectElement).value).toBe('older-linked')
  expect(wrapper.text()).toContain('这不证明所有任务通过')
})


it('separates a succeeded verifier process from the failed task verdict', async () => {
  const wrapper = mount(DiagnosisView, { global: { plugins: [router] } }); await flushPromises()
  const verifier = wrapper.get('.diagnosis-verifier')
  expect(verifier.text()).toContain('任务验收结论')
  expect(verifier.get('[data-status="FAILED"]').classes()).toContain('bad')
  expect(verifier.get('[data-status="succeeded"]').classes()).toContain('neutral')
  expect(verifier.get('[data-status="succeeded"]').attributes('data-status')).toBe('succeeded')
  expect(verifier.text()).toContain('Verifier 进程')
  expect(verifier.find('[data-status="PASSED"]').exists()).toBe(false)
  wrapper.unmount()
})

it('explains FILE_CHANGE separately from a digest-only final workspace without inventing changed paths', async () => {
  const source = structuredClone(report)
  const selected = source.cells[0]!.task_families[0]!.clusters[0]!.runs[0]!
  selected.workspace_diff = { status: 'DIGEST_ONLY', input_digest: 'same', output_digest: 'same', pattern: 'no-modification', changed_paths: [], protected_paths_changed: [] }
  selected.trace.events = [{ ordinal: 1, type: 'FILE_CHANGE', status: 'completed', exit_code: null }]
  api.getDiagnosis.mockResolvedValueOnce(source)
  const wrapper = mount(DiagnosisView, { global: { plugins: [router] } }); await flushPromises()
  const facts = wrapper.get('.facts-panel')
  expect(facts.text()).toContain('最终工作区无修改')
  expect(facts.text()).toContain('仅有摘要对照')
  expect(facts.text()).not.toContain('0 条路径记录')
  expect(facts.text()).toContain('FILE_CHANGE 是事件记录')
  expect(facts.text()).toContain('进程执行完成也不代表任务验收通过')
  expect(wrapper.get('.raw-evidence').text()).toContain('"pattern": "no-modification"')
  expect(wrapper.get('.raw-evidence').text()).toContain('"type": "FILE_CHANGE"')
  expect(selected.workspace_diff.changed_paths).toEqual([])
  wrapper.unmount()
})
