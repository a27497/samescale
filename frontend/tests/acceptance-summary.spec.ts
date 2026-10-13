import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AcceptanceSummary from '@/components/AcceptanceSummary.vue'
import RunsHomeView from '@/views/RunsHomeView.vue'
import { externalAcceptanceRows, runAcceptanceRows } from '@/utils/acceptanceSummary'
import { workbenchApi } from '@/api/client'
import type { RunDetail } from '@/types/workbench'
import type { EvidenceDetail } from '@/api/externalEvidence'

vi.mock('@/api/client', () => ({ workbenchApi: { listExperiments: vi.fn(), getRuns: vi.fn(), getRun: vi.fn() } }))
const missing = { value: null, status: 'NOT_REPORTED' } as unknown as RunDetail['verifier_score']
const run = { run_id: 'r1', experiment_id: 'e1', cell_id: 'c', task_id: 't', task_version: '1', lane: 'H', repeat_index: 0, status: 'failed', provenance: 'UNVERIFIED_SOURCE', normalized_outcome: null, attempt: 1, duration_ms: missing, slot_id: 's', source_outcome: null, requested_model: null, observed_model: null, provider_route: null, harness: null, harness_version: null, trace_coverage: null, evidence_digest: null, artifact_name: null, verifier_passed: null, verifier_score: missing, summary: null, input_tokens: missing, output_tokens: missing, explicit_cost: missing, comparability: null, comparability_reason_codes: [] } as RunDetail
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div />' } }] })

describe('acceptance summary', () => {
  beforeEach(() => vi.resetAllMocks())
  it('never invents a pass when verifier data is missing', () => {
    const rows = runAcceptanceRows(run, null)
    expect(rows.map(r => r.key)).toEqual(['original', 'checked', 'unverified', 'replay'])
    expect(rows[1]!.status).toBe('NOT_VERIFIED')
    expect(rows[2]!.status).toBe('NOT_VERIFIED')
    expect(rows[3]!.status).toBe('NOT_REPORTED')
    expect(JSON.stringify(rows)).not.toContain('VERIFIED_PASS')
  })
  it('reports zero-check external runs as not verified and corrupt integrity as corrupt', () => {
    const detail = { identity: 'x', record: { source: {} as never, episode_identity: null, original_acceptance: 'NOT_VERIFIED', workspace_digest: 'd', workspace_files: {}, completeness: { status: 'PARTIAL', coverage: 'c', missing_fields: ['run_record', 'actual_model', 'usage', 'future_field'], integrity: 'RECORD_CORRUPT', origin: 'NOT_ATTESTED' }, trace: [] }, diagnosis: { original_episode_acceptance: 'NOT_RUN', workspace_acceptance: 'NOT_VERIFIED', independent_verification: { checks: 0, passed_checks: 0, reason: 'TRUSTED_TASK_OR_VERIFIER_MISSING' }, agent_self_reports: [], observed_failed_tools: [], file_changes: { status: 's', paths: [] }, infrastructure: { status: 'UNKNOWN', root_cause: null }, limits: [] } } as EvidenceDetail
    const rows = externalAcceptanceRows(detail)
    expect(rows[0]!.status).toBe('NOT_RUN'); expect(rows[1]!.status).toBe('NOT_VERIFIED'); expect(rows[3]!.status).toBe('CORRUPT')
    const wrapper = mount(AcceptanceSummary, { props: { rows } })
    expect(wrapper.findAll('.acceptance-row')).toHaveLength(4)
    expect(wrapper.text()).toContain('验收摘要')
    expect(wrapper.text()).toContain('运行记录、实际使用的模型、用量记录、其他未报告信息（见技术细节）')
    expect(wrapper.text()).toContain('缺少可信任务绑定或独立验收结果')
    expect(wrapper.text()).not.toMatch(/run_record|actual_model|usage|future_field|TRUSTED_TASK_OR_VERIFIER_MISSING/)
  })
  it('home separates personal empty state from explicitly labelled fixture entries', async () => {
    vi.mocked(workbenchApi.listExperiments).mockResolvedValue({ items: [{ experiment_id: 'f', name: 'Public Demo — offline fixture baseline', planned_run_count: 6, provenance: 'FIXTURE_OFFLINE' }], total: 1, limit: 20, offset: 0 } as never)
    vi.mocked(workbenchApi.getRuns).mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })
    const wrapper = mount(RunsHomeView, { global: { plugins: [router] } }); await flushPromises()
    expect(workbenchApi.getRuns).toHaveBeenCalledExactlyOnceWith('f', { limit: 50 })
    expect(wrapper.find('[data-test="runs-empty"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('导入运行记录')
    expect(wrapper.get('[data-test=example-entry]').text()).toContain('公开演示 · 基线')
    expect(wrapper.get('[data-test=example-entry] a').attributes('href')).toBe('/demo')
    expect(wrapper.find('[data-test=runs-table]').exists()).toBe(false)
  })
  it('backend unreachable is not reported as corruption', async () => {
    vi.mocked(workbenchApi.listExperiments).mockRejectedValue(new Error('network'))
    const wrapper = mount(RunsHomeView, { global: { plugins: [router] } }); await flushPromises()
    expect(wrapper.text()).toContain('不表示证据损坏')
  })
})
