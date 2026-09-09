import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AnalystView from '@/views/AnalystView.vue'
import router from '@/router'
import type { AnalystSession } from '@/types/analyst'
const api = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), create: vi.fn(), resume: vi.fn(), propose: vi.fn(), approve: vi.fn(), preflight: vi.fn() }))
const registry = vi.hoisted(() => ({ models: vi.fn() }))
const workbench = vi.hoisted(() => ({ listExperiments: vi.fn() }))
vi.mock('@/api/analyst', () => ({ analystApi: api }))
vi.mock('@/api/client', () => ({ workbenchApi: workbench, registryApi: registry }))
function fixture(update: Partial<AnalystSession> = {}): AnalystSession {
  return {
    spend_limits: null, session_id: 'analyst-saved', backend: 'fake', status: 'PAUSED', request: { experiment_id: 'experiment-one', question: 'Inspect failures' },
    scope: { experiment_id: 'experiment-one', plan_digest: 'plan-digest', task_ids: ['task'], cell_ids: ['cell'], run_ids: ['run'], ablation_ids: [] },
    scope_digest: 'scope-digest', profile_id: null, provider: null, model: null, route: null,
    decision_iterations: 2, tool_calls: 3, decision_limit: 8, tool_limit: 12, request_count: 0, request_budget_used: 0,
    max_output_tokens_per_request: null, request_timeout_seconds: null,
    totals: { input_tokens: null, output_tokens: null, total_tokens: null, cost_usd: null, latency_ms: null },
    evidence: [{ ref: { id: 'run:run' }, digest_bindings: ['digest'], data_by_tool: { query_runs: { status: 'failed_subject' } } }],
    completed_calls: [{ key: 'key', call: { name: 'query_runs' }, status: 'COMPLETED', evidence_refs: ['run:run'] }],
    report: null, error: null, proposed_plan: null, proposal_digest: null, approval: null, ...update,
  }
}
function button(wrapper: ReturnType<typeof mount>, text: string) {
  return wrapper.findAll('button').find(item => item.text() === text)!
}
beforeEach(() => {
  vi.resetAllMocks()
  workbench.listExperiments.mockResolvedValue({ items: [{ experiment_id: 'experiment-one', name: 'One' }] })
  registry.models.mockResolvedValue({ provider_profiles: [{ profile_id: 'registered-profile', enabled: true, automation_allowed: true }] })
  api.list.mockResolvedValue({ items: [fixture()] })
  api.get.mockResolvedValue(fixture())
})
describe('Analyst Workbench contracts', () => {
  it('keeps proposal references within the host limit and submits the visible selection', async () => {
    const evidence = Array.from({ length: 104 }, (_, index) => ({
      ref: { id: `run:${index}` }, digest_bindings: ['digest'], data_by_tool: {},
    }))
    api.list.mockResolvedValue({ items: [fixture({ evidence })] })
    api.propose.mockResolvedValue(fixture({ evidence }))
    const wrapper = mount(AnalystView); await flushPromises()
    const references = wrapper.get<HTMLSelectElement>('[aria-label="Proposal evidence references"]')
    expect(references.element.selectedOptions.length).toBe(100)
    await references.setValue(['run:103'])
    await button(wrapper, 'Save proposal').trigger('click'); await flushPromises()
    expect(api.propose.mock.calls[0]![1].evidence_refs).toEqual(['run:103'])
  })
  it('restores within Workbench without invoking a model', async () => {
    expect(router.getRoutes().some(route => route.path === '/analyst')).toBe(true)
    const wrapper = mount(AnalystView); await flushPromises()
    expect(api.list).toHaveBeenCalledWith('experiment-one')
    expect(wrapper.text()).toContain('Decisions 2/8')
    expect(wrapper.text()).toContain('Tools 3/12')
    expect(wrapper.text()).toContain('Unknown')
    expect(api.resume).not.toHaveBeenCalled()
  })
  it('creates Fake with frozen limits and no implicit resume', async () => {
    api.create.mockResolvedValue(fixture({ session_id: 'new', decision_iterations: 0, tool_calls: 0 }))
    const wrapper = mount(AnalystView); await flushPromises()
    await wrapper.get('[aria-label="Investigation goal"]').setValue('Inspect this evidence')
    await wrapper.get('[aria-label="Decision limit"]').setValue(3)
    await button(wrapper, 'Create investigation').trigger('click'); await flushPromises()
    expect(api.create).toHaveBeenCalledWith({ experiment_id: 'experiment-one', question: 'Inspect this evidence', backend: 'fake', provider_profile_id: null, decision_limit: 3, tool_limit: 12, spend_limits: null })
    expect(api.resume).not.toHaveBeenCalled()
  })
  it('renders authoritative terminal results after resume', async () => {
    api.resume.mockResolvedValue(fixture({ status: 'ABSTAINED', decision_iterations: 3, report: { summary: 'No conclusion', verified_facts: [], hypotheses: [], limitations: ['Insufficient evidence'] } }))
    const wrapper = mount(AnalystView); await flushPromises()
    await button(wrapper, 'Resume one step').trigger('click'); await flushPromises()
    expect(api.resume).toHaveBeenCalledWith('analyst-saved', false)
    expect(wrapper.text()).toContain('ABSTAINED')
    expect(wrapper.text()).toContain('Decisions 3/8')
    expect(button(wrapper, 'Resume one step').attributes('disabled')).toBeDefined()
  })
  it('requires real confirmation and never falls back after failure', async () => {
    api.list.mockResolvedValue({ items: [fixture({ backend: 'real', profile_id: 'registered-profile', provider: 'fixture-provider', model: 'fixture-model', request_count: 2 })] })
    api.resume.mockRejectedValue(new Error('Provider failure'))
    const wrapper = mount(AnalystView); await flushPromises()
    expect(button(wrapper, 'Resume one step').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="Confirm one real model decision"]').setValue(true)
    await button(wrapper, 'Resume one step').trigger('click'); await flushPromises()
    expect(api.resume).toHaveBeenCalledExactlyOnceWith('analyst-saved', true)
    expect(api.create).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('request failed')
    expect(wrapper.text()).toContain('fixture-model')
    expect(button(wrapper, 'Resume one step').attributes('disabled')).toBeDefined()
  })
  it('creates real only from the selected registry profile', async () => {
    api.create.mockResolvedValue(fixture({ backend: 'real', profile_id: 'registered-profile' }))
    const wrapper = mount(AnalystView); await flushPromises()
    await wrapper.get('[aria-label="Analyst backend"]').setValue('real')
    expect(button(wrapper, 'Create investigation').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="Cumulative token ceiling"]').setValue(24000)
    await button(wrapper, 'Create investigation').trigger('click'); await flushPromises()
    expect(api.create.mock.calls[0]![0].provider_profile_id).toBe('registered-profile')
    expect(api.create.mock.calls[0]![0].backend).toBe('real')
    expect(api.create.mock.calls[0]![0].spend_limits).toEqual({ provider_requests: 3, output_tokens_per_request: 1000, input_bytes_per_request: 64000, cumulative_tokens: 24000, timeout_seconds: 60, usd: null })
    expect(api.resume).not.toHaveBeenCalled()
  })
  it('binds approval to scope/content and clears approval on change', async () => {
    const proposed = fixture({ proposed_plan: { objective: 'Original', task_ids: ['task'], cell_ids: ['cell'], evidence_refs: ['run:run'], acceptance_criteria: ['Pass verification'], repeat_count: 1 }, proposal_digest: 'content-digest' })
    api.list.mockResolvedValue({ items: [proposed] })
    api.approve.mockResolvedValue({ ...proposed, approval: { reviewed_by: 'reviewer', execution_authorized: false, approved_at: 'now' } })
    const wrapper = mount(AnalystView); await flushPromises()
    await wrapper.get('[aria-label="Reviewer label"]').setValue('reviewer')
    await button(wrapper, 'Approve proposal only').trigger('click'); await flushPromises()
    expect(api.approve).toHaveBeenCalledWith('analyst-saved', { scope_digest: 'scope-digest', proposal_digest: 'content-digest', reviewed_by: 'reviewer' })
    expect(wrapper.text()).toContain('Execution is not authorized')
    await wrapper.get('[aria-label="Regression objective"]').setValue('Revised')
    expect(button(wrapper, 'Approve proposal only').attributes('disabled')).toBeDefined()
    api.propose.mockResolvedValue({ ...proposed, proposed_plan: { ...proposed.proposed_plan, objective: 'Revised' }, proposal_digest: 'new-digest', approval: null })
    await button(wrapper, 'Save proposal').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('Awaiting approval')
    expect(wrapper.text()).not.toContain('Approved by')
    expect(api.resume).not.toHaveBeenCalled()
  })
  it('refreshes persisted limits after a lost response without recreating', async () => {
    const wrapper = mount(AnalystView); await flushPromises()
    api.get.mockResolvedValue(fixture({ decision_iterations: 5, tool_calls: 7, status: 'FAILED', error: 'BACKEND_DECISION_FAILED' }))
    await button(wrapper, 'Refresh session').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('Decisions 5/8')
    expect(wrapper.text()).toContain('Tools 7/12')
    expect(api.create).not.toHaveBeenCalled()
    expect(api.resume).not.toHaveBeenCalled()
  })
  it('shows keyless blocked preflight without granting invocation consent', async () => {
    api.list.mockResolvedValue({ items: [fixture({ backend: 'real' })] })
    api.preflight.mockResolvedValue({ status: 'BLOCKED', reasons: ['SPEND_LIMITS_MISSING'], execution_authorized: false })
    const wrapper = mount(AnalystView); await flushPromises()
    await button(wrapper, 'Check smoke preflight').trigger('click'); await flushPromises()
    expect(api.preflight).toHaveBeenCalledExactlyOnceWith('analyst-saved')
    expect(wrapper.get('[aria-label="Smoke preflight"]').text()).toContain('SPEND_LIMITS_MISSING')
    expect(api.resume).not.toHaveBeenCalled()
    expect(button(wrapper, 'Resume one step').attributes('disabled')).toBeDefined()
  })

})
