import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import router from '@/router'
import DiagnosisView from '@/views/DiagnosisView.vue'

const api = vi.hoisted(() => ({
  listExperiments: vi.fn(),
  getDiagnosis: vi.fn(),
  exportBadCases: vi.fn(),
}))

vi.mock('@/api/client', () => ({ workbenchApi: api }))

const report = {
  schema_version: 1 as const,
  experiment_id: 'diagnosis-fixture',
  plan_digest: `sha256:${'1'.repeat(64)}`,
  report_digest: `sha256:${'2'.repeat(64)}`,
  cluster_dimensions: ['model', 'harness', 'task', 'language', 'task_family', 'failure_class', 'trace_pattern', 'tool_pattern', 'workspace_diff_pattern'],
  correlation_warning: '轨迹相关性不等于因果；归因需要受控消融证据。',
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

beforeEach(() => {
  vi.clearAllMocks()
  api.listExperiments.mockResolvedValue({ items: [{ experiment_id: 'diagnosis-fixture', name: 'Diagnosis fixture' }], total: 1, limit: 100, offset: 0 })
  api.getDiagnosis.mockResolvedValue(report)
  api.exportBadCases.mockResolvedValue({
    experiment_id: 'diagnosis-fixture', export_digest: `sha256:${'5'.repeat(64)}`,
    real_case_count: 1, synthetic_qualification_case_count: 0,
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
    expect(text).toContain('实验 → 单元')
    expect(text).toContain('codex-low')
    expect(text).toContain('targeted-bug-fix')
    expect(text).toContain('Test Failure')
    expect(text).toContain('轨迹')
    expect(text).toContain('工作区差异')
    expect(text).toContain('工具调用')
    expect(text).toContain('校验器')
    expect(text).toContain('已验证事实')
    expect(text).toContain('HYPOTHESIS')
    expect(text).toContain('Trace correlation is not causality')
    expect(api.getDiagnosis).toHaveBeenCalledWith('diagnosis-fixture')
  })

  it('exports only backend-selected real BadCases', async () => {
    const wrapper = mount(DiagnosisView, { global: { plugins: [router] } })
    await flushPromises()
    await wrapper.get('button.primary-button').trigger('click')
    await flushPromises()

    expect(api.exportBadCases).toHaveBeenCalledWith('diagnosis-fixture')
    expect(wrapper.text()).toContain('已导出 1 个真实失败案例与 0 个合成案例')
    expect(wrapper.text()).toContain('never counted as real BadCases')
  })
})
