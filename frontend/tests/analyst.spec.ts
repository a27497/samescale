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
  window.history.replaceState(null, '')
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
    const references = wrapper.get<HTMLSelectElement>('[aria-label="方案证据引用"]')
    expect(references.element.selectedOptions.length).toBe(100)
    await references.setValue(['run:103'])
    await button(wrapper, '保存方案').trigger('click'); await flushPromises()
    expect(api.propose.mock.calls[0]![1].evidence_refs).toEqual(['run:103'])
  })
  it('restores within Workbench without invoking a model', async () => {
    expect(router.getRoutes().some(route => route.path === '/analyst')).toBe(true)
    const wrapper = mount(AnalystView); await flushPromises()
    expect(api.list).toHaveBeenCalledWith('experiment-one')
    expect(wrapper.text()).toContain('决策 2/8')
    expect(wrapper.text()).toContain('工具 3/12')
    expect(wrapper.text()).toContain('未知')
    expect(api.resume).not.toHaveBeenCalled()
  })
  it('creates Fake with frozen limits and no implicit resume', async () => {
    api.create.mockResolvedValue(fixture({ session_id: 'new', decision_iterations: 0, tool_calls: 0 }))
    const wrapper = mount(AnalystView); await flushPromises()
    await wrapper.get('[aria-label="调查问题"]').setValue('Inspect this evidence')
    await wrapper.get('[aria-label="决策步数上限"]').setValue(3)
    await button(wrapper, '创建调查').trigger('click'); await flushPromises()
    expect(api.create).toHaveBeenCalledWith({ experiment_id: 'experiment-one', question: 'Inspect this evidence', backend: 'fake', provider_profile_id: null, decision_limit: 3, tool_limit: 12, spend_limits: null })
    expect(api.resume).not.toHaveBeenCalled()
  })
  it('renders authoritative terminal results after resume', async () => {
    api.resume.mockResolvedValue(fixture({ status: 'ABSTAINED', decision_iterations: 3, report: { summary: 'No conclusion', verified_facts: [], hypotheses: [], limitations: ['Insufficient evidence'] } }))
    const wrapper = mount(AnalystView); await flushPromises()
    await button(wrapper, '继续一步').trigger('click'); await flushPromises()
    expect(api.resume).toHaveBeenCalledWith('analyst-saved', false)
    expect(wrapper.text()).toContain('ABSTAINED')
    expect(wrapper.text()).toContain('决策 3/8')
    expect(button(wrapper, '继续一步').attributes('disabled')).toBeDefined()
  })
  it('requires real confirmation and never falls back after failure', async () => {
    api.list.mockResolvedValue({ items: [fixture({ backend: 'real', profile_id: 'registered-profile', provider: 'fixture-provider', model: 'fixture-model', request_count: 2 })] })
    api.resume.mockRejectedValue(new Error('Provider failure'))
    const wrapper = mount(AnalystView); await flushPromises()
    expect(button(wrapper, '继续一步').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="确认一次真实模型决策"]').setValue(true)
    await button(wrapper, '继续一步').trigger('click'); await flushPromises()
    expect(api.resume).toHaveBeenCalledExactlyOnceWith('analyst-saved', true)
    expect(api.create).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('调查请求失败')
    expect(wrapper.text()).toContain('fixture-model')
    expect(button(wrapper, '继续一步').attributes('disabled')).toBeDefined()
  })
  it('creates real only from the selected registry profile', async () => {
    api.create.mockResolvedValue(fixture({ backend: 'real', profile_id: 'registered-profile' }))
    const wrapper = mount(AnalystView); await flushPromises()
    await wrapper.get('[aria-label="调查运行模式"]').setValue('real')
    expect(button(wrapper, '创建调查').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="累计 Token 上限"]').setValue(24000)
    await button(wrapper, '创建调查').trigger('click'); await flushPromises()
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
    await wrapper.get('[aria-label="审阅标签"]').setValue('reviewer')
    await button(wrapper, '确认审阅方案').trigger('click'); await flushPromises()
    expect(api.approve).toHaveBeenCalledWith('analyst-saved', { scope_digest: 'scope-digest', proposal_digest: 'content-digest', reviewed_by: 'reviewer' })
    expect(wrapper.text()).toContain('未授权执行')
    await wrapper.get('[aria-label="回归目标"]').setValue('Revised')
    expect(button(wrapper, '确认审阅方案').attributes('disabled')).toBeDefined()
    api.propose.mockResolvedValue({ ...proposed, proposed_plan: { ...proposed.proposed_plan, objective: 'Revised' }, proposal_digest: 'new-digest', approval: null })
    await button(wrapper, '保存方案').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('等待审阅确认')
    expect(wrapper.text()).not.toContain('Approved by')
    expect(api.resume).not.toHaveBeenCalled()
  })
  it('refreshes persisted limits after a lost response without recreating', async () => {
    const wrapper = mount(AnalystView); await flushPromises()
    api.get.mockResolvedValue(fixture({ decision_iterations: 5, tool_calls: 7, status: 'FAILED', error: 'BACKEND_DECISION_FAILED' }))
    await button(wrapper, '刷新调查').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('决策 5/8')
    expect(wrapper.text()).toContain('工具 7/12')
    expect(api.create).not.toHaveBeenCalled()
    expect(api.resume).not.toHaveBeenCalled()
  })
  it('shows keyless blocked preflight without granting invocation consent', async () => {
    api.list.mockResolvedValue({ items: [fixture({ backend: 'real' })] })
    api.preflight.mockResolvedValue({ status: 'BLOCKED', reasons: ['SPEND_LIMITS_MISSING'], execution_authorized: false })
    const wrapper = mount(AnalystView); await flushPromises()
    await button(wrapper, '检查调用前置条件').trigger('click'); await flushPromises()
    expect(api.preflight).toHaveBeenCalledExactlyOnceWith('analyst-saved')
    expect(wrapper.get('[aria-label="调用前置检查"]').text()).toContain('SPEND_LIMITS_MISSING')
    expect(api.resume).not.toHaveBeenCalled()
    expect(button(wrapper, '继续一步').attributes('disabled')).toBeDefined()
  })

})

it('keeps Fake sessions usable when Registry loading fails', async () => {
  registry.models.mockRejectedValue(new Error('Registry unavailable'))
  const wrapper = mount(AnalystView); await flushPromises()
  expect(api.list).toHaveBeenCalledWith('experiment-one')
  expect(wrapper.text()).toContain('Registry 加载失败')
  expect(wrapper.text()).toContain('analyst-saved')
  expect(button(wrapper, '继续一步').attributes('disabled')).toBeUndefined()
})

it('clears stale sessions and confirmation when experiment loading fails', async () => {
  workbench.listExperiments.mockResolvedValue({ items: [{ experiment_id: 'experiment-one', name: 'One' }, { experiment_id: 'experiment-two', name: 'Two' }] })
  const wrapper = mount(AnalystView); await flushPromises()
  api.list.mockRejectedValue(new Error('Invalid plan'))
  await wrapper.get('[aria-label="调查所属实验"]').setValue('experiment-two'); await flushPromises()
  expect(wrapper.find('[aria-label="调查详情"]').exists()).toBe(false)
  expect(wrapper.get('[aria-label="已保存调查"]').findAll('option:not([disabled])')).toHaveLength(0)
  expect(api.resume).not.toHaveBeenCalled()
})

it('does not show an old Fake session under a newly selected Real session after read failure', async () => {
  api.list.mockResolvedValue({ items: [fixture(), fixture({ session_id: 'real-session', backend: 'real' })] })
  const wrapper = mount(AnalystView); await flushPromises()
  api.get.mockRejectedValue(new Error('Missing session'))
  await wrapper.get('[aria-label="已保存调查"]').setValue('real-session'); await flushPromises()
  expect(wrapper.find('[aria-label="调查详情"]').exists()).toBe(false)
  expect(api.resume).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('调查请求失败')
})

it('prioritizes saved results and keeps new setup available when the scope is empty', async () => {
  workbench.listExperiments.mockResolvedValue({ items: [{ experiment_id: 'experiment-one', name: 'One' }, { experiment_id: 'empty', name: 'Empty' }] })
  const wrapper = mount(AnalystView); await flushPromises()
  expect(wrapper.get('.setup-panel').attributes('open')).toBeUndefined()
  expect(wrapper.get('.proposal-panel').attributes('open')).toBeUndefined()
  api.list.mockResolvedValue({ items: [] })
  await wrapper.get('[aria-label="调查所属实验"]').setValue('empty'); await flushPromises()
  expect(wrapper.get('.setup-panel').attributes('open')).toBeDefined()
  expect(wrapper.find('[aria-label="调查详情"]').exists()).toBe(false)
  expect(wrapper.text()).toContain('此实验还没有已保存调查')
  expect(api.resume).not.toHaveBeenCalled()
})

it('rejects reviewer labels outside the existing backend contract before approval', async () => {
  api.list.mockResolvedValue({ items: [fixture({ proposed_plan: { objective: 'Original', task_ids: ['task'], cell_ids: ['cell'], evidence_refs: ['run:run'], acceptance_criteria: ['Pass'], repeat_count: 1 }, proposal_digest: 'digest' })] })
  const wrapper = mount(AnalystView); await flushPromises()
  await wrapper.get('[aria-label="审阅标签"]').setValue('reviewer (local)')
  expect(wrapper.get('[aria-label="审阅标签"]').attributes('aria-invalid')).toBe('true')
  expect(button(wrapper, '确认审阅方案').attributes('disabled')).toBeDefined()
  expect(api.approve).not.toHaveBeenCalled()
  await wrapper.get('[aria-label="审阅标签"]').setValue('local-reviewer')
  expect(button(wrapper, '确认审阅方案').attributes('disabled')).toBeUndefined()
})


it('filters persisted investigation rows and clears the filter without invoking a model', async () => {
  api.list.mockResolvedValue({ items: [fixture(), fixture({ session_id: 'other', status: 'COMPLETED', request: { experiment_id: 'experiment-one', question: 'Review order mismatch' } })] })
  const wrapper = mount(AnalystView); await flushPromises()
  expect(wrapper.findAll('.investigation-row')).toHaveLength(2)
  await wrapper.get('[aria-label="搜索调查"]').setValue('order')
  expect(wrapper.findAll('.investigation-row')).toHaveLength(1)
  expect(wrapper.get('.investigation-row').text()).toContain('Review order mismatch')
  await wrapper.get('[aria-label="筛选调查状态"]').setValue('PAUSED')
  expect(wrapper.findAll('.investigation-row')).toHaveLength(0)
  await button(wrapper, '清除筛选').trigger('click')
  expect(wrapper.findAll('.investigation-row')).toHaveLength(2)
  expect(api.resume).not.toHaveBeenCalled()
})

it('distinguishes an unavailable database from an empty workspace and retries reads', async () => {
  workbench.listExperiments.mockRejectedValueOnce(new Error('Offline'))
  const wrapper = mount(AnalystView); await flushPromises()
  expect(wrapper.text()).toContain('暂时无法读取本地调查')
  expect(wrapper.find('.setup-panel').exists()).toBe(false)
  expect(wrapper.find('.scope-toolbar').exists()).toBe(false)
  await button(wrapper, '重新连接').trigger('click'); await flushPromises()
  expect(wrapper.findAll('.investigation-row')).toHaveLength(1)
  expect(wrapper.find('.workspace-empty').exists()).toBe(false)
  expect(api.create).not.toHaveBeenCalled()
})


it('prefills the incoming question and opens setup without showing an unrelated saved result', async () => {
  window.history.replaceState({ investigationQuestion: '检查输入顺序边界' }, '')
  const wrapper = mount(AnalystView); await flushPromises()
  expect(wrapper.get<HTMLTextAreaElement>('[aria-label="调查问题"]').element.value).toBe('检查输入顺序边界')
  expect(wrapper.get('.setup-panel').attributes('open')).toBeDefined()
  expect(wrapper.find('.session-detail').exists()).toBe(false)
  expect(wrapper.get('.question-handoff').text()).toContain('检查输入顺序边界')
  expect(api.create).not.toHaveBeenCalled()
  expect(api.resume).not.toHaveBeenCalled()
})

it('restores the exact saved selection on reload after creating from a homepage question', async () => {
  const saved = fixture({ session_id: 'created-from-home' })
  window.history.replaceState({ investigationQuestion: 'New question', investigationSelection: {
    experimentId: 'experiment-one', sessionId: saved.session_id,
  } }, '')
  api.list.mockResolvedValue({ items: [fixture({ session_id: 'unrelated-first' }), saved] })
  const wrapper = mount(AnalystView); await flushPromises()
  expect(wrapper.get('.session-detail').text()).toContain('created-from-home')
  expect(wrapper.get('.setup-panel').attributes('open')).toBeUndefined()
  expect(api.create).not.toHaveBeenCalled()
  expect(api.resume).not.toHaveBeenCalled()
})

it('does not substitute another report when the previous saved selection disappears', async () => {
  window.history.replaceState({ investigationSelection: {
    experimentId: 'experiment-one', sessionId: 'missing-session',
  } }, '')
  const wrapper = mount(AnalystView); await flushPromises()
  expect(wrapper.find('.session-detail').exists()).toBe(false)
  expect(wrapper.text()).toContain('无法读取此实验的调查记录')
  expect(api.resume).not.toHaveBeenCalled()
})

it('selects only local Analyst roles and freezes the visible version without invoking', async () => {
  const local = { profile_id: 'local-analysis-v2', purpose: 'ANALYST', enabled: true, automation_allowed: true, max_output_tokens: 4096, max_output_tokens_limit: 800, request_timeout_seconds: 30 }
  registry.models.mockResolvedValue({ provider_profiles: [local, { ...local, profile_id: 'local-subject-v1', purpose: 'SUBJECT' }, { ...local, profile_id: 'local-judge-v1', purpose: 'JUDGE' }] })
  const model_binding = { purpose: 'ANALYST' as const, configuration_id: 'analysis', configuration_revision: 2, connection_id: 'service', connection_revision: 1, binding_digest: 'sha256:frozen' }
  api.create.mockResolvedValue(fixture({ backend: 'real', profile_id: local.profile_id, model_binding }))
  const wrapper = mount(AnalystView); await flushPromises()
  await wrapper.get('[aria-label="调查运行模式"]').setValue('real')
  expect(wrapper.get('[aria-label="调查模型配置"]').findAll('option').map(o => o.element.value)).toEqual(['local-analysis-v2'])
  await wrapper.get('[aria-label="累计 Token 上限"]').setValue(3000000)
  expect(button(wrapper, '创建调查').attributes('disabled')).toBeDefined()
  await wrapper.get('[aria-label="输出 Token 上限"]').setValue(800)
  await wrapper.get('[aria-label="超时上限"]').setValue(30)
  expect(button(wrapper, '创建调查').attributes('disabled')).toBeUndefined()
  await button(wrapper, '创建调查').trigger('click'); await flushPromises()
  expect(api.create.mock.calls[0]![0].provider_profile_id).toBe('local-analysis-v2')
  expect(wrapper.get('.frozen-binding').text()).toContain('analysis · v2')
  expect(wrapper.get('.frozen-binding').text()).toContain('service · v1')
  expect(api.resume).not.toHaveBeenCalled()
})

it('restores frozen bindings and explains stale preflight without replacing the session', async () => {
  const model_binding = { purpose: 'ANALYST' as const, configuration_id: 'analysis', configuration_revision: 1, connection_id: null, connection_revision: null, binding_digest: 'sha256:old' }
  api.list.mockResolvedValue({ items: [fixture({ backend: 'real', model_binding })] })
  api.preflight.mockResolvedValue({ status: 'BLOCKED', reasons: ['MODEL_BINDING_STALE_OR_UNAVAILABLE'], execution_authorized: false })
  const wrapper = mount(AnalystView); await flushPromises()
  await button(wrapper, '检查调用前置条件').trigger('click'); await flushPromises()
  expect(wrapper.get('.frozen-binding').text()).toContain('analysis · v1')
  expect(wrapper.text()).toContain('历史记录保留，请选择当前版本新建调查')
  expect(api.create).not.toHaveBeenCalled()
  expect(api.resume).not.toHaveBeenCalled()
})
