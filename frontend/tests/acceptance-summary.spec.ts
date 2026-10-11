import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AcceptanceSummary from '@/components/AcceptanceSummary.vue'
import RunsHomeView from '@/views/RunsHomeView.vue'
import { externalAcceptanceRows, runAcceptanceRows } from '@/utils/acceptanceSummary'
import { workbenchApi } from '@/api/client'
import type { RunDetail } from '@/types/workbench'
import type { EvidenceDetail } from '@/api/externalEvidence'

vi.mock('@/api/client', () => ({ workbenchApi: { listExperiments: vi.fn(), getRuns: vi.fn() } }))
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
    const detail = { identity: 'x', record: { source: {} as never, episode_identity: null, original_acceptance: 'NOT_VERIFIED', workspace_digest: 'd', workspace_files: {}, completeness: { status: 'PARTIAL', coverage: 'c', missing_fields: ['usage'], integrity: 'RECORD_CORRUPT', origin: 'NOT_ATTESTED' }, trace: [] }, diagnosis: { original_episode_acceptance: 'NOT_RUN', workspace_acceptance: 'NOT_VERIFIED', independent_verification: { checks: 0, passed_checks: 0 }, agent_self_reports: [], observed_failed_tools: [], file_changes: { status: 's', paths: [] }, infrastructure: { status: 'UNKNOWN', root_cause: null }, limits: [] } } as EvidenceDetail
    const rows = externalAcceptanceRows(detail)
    expect(rows[0]!.status).toBe('NOT_RUN'); expect(rows[1]!.status).toBe('NOT_VERIFIED'); expect(rows[3]!.status).toBe('CORRUPT')
    const wrapper = mount(AcceptanceSummary, { props: { rows } })
    expect(wrapper.findAll('.acceptance-row')).toHaveLength(4)
    expect(wrapper.text()).toContain('验收摘要')
  })
  it('home empty state guides to import, not demo, and hides fixtures', async () => {
    vi.mocked(workbenchApi.listExperiments).mockResolvedValue({ items: [{ experiment_id: 'f', provenance: 'FIXTURE_OFFLINE' }], total: 1, limit: 20, offset: 0 } as never)
    const wrapper = mount(RunsHomeView, { global: { plugins: [router] } }); await flushPromises()
    expect(workbenchApi.getRuns).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="runs-empty"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('导入运行记录')
    expect(wrapper.text()).not.toContain('演示')
  })
  it('backend unreachable is not reported as corruption', async () => {
    vi.mocked(workbenchApi.listExperiments).mockRejectedValue(new Error('network'))
    const wrapper = mount(RunsHomeView, { global: { plugins: [router] } }); await flushPromises()
    expect(wrapper.text()).toContain('不表示证据损坏')
  })
})
