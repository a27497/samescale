import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { localPlansApi } from '@/api/localPlans'
import type { PlanDetail, PlanMaterial, PreflightReceipt, TaskInspection } from '@/api/localPlans'
import LocalPlansView from '@/views/LocalPlansView.vue'
import { preferences } from '@/composables/preferences'

vi.mock('@/api/localPlans', () => ({ localPlansApi: Object.fromEntries(['status', 'sources', 'tasks', 'importTask', 'inspect', 'configurations', 'preflight', 'save', 'plans', 'plan'].map(k => [k, vi.fn()])) }))
const digest = 'sha256:'+'a'.repeat(64)
const task: TaskInspection = { reference: 'local-task@1.0.0', task_owner: 'Developer', task_category: 'engineering', task_identity: digest, workspace_identity: digest, verifier_identity: digest, oracle_identity: digest, managed_snapshot_identity: digest, source_root_id: 'trusted', source_relative_path: 'local-task/1.0.0', source_identity: digest, structural_validation: 'PASS', behavioral_validation: 'TRUSTED_PRIOR_RESULT', qualification_identity: digest, eligible_for_planning: true, reason_codes: [], verifier_executed: false }
const material: PlanMaterial = { request: { name: 'Engineering task', task_reference: task.reference, provider_profile_id: 'provider-model', harness_profile_id: 'codex-high', budget: { wall_time_seconds: 90, output_tokens_estimate: 1000, cost_budget_usd: 1 } }, task, material_digest: digest, policy_identity: digest, configuration: { application_version: '0.1.0', application_code_identity: digest, image_identity: digest, configuration_identity: digest, model: { requested_model: 'gpt-5.6-sol', credential_reference: 'LOCAL_KEY_REFERENCE' }, harness: { version: '0.149.0' }, harness_profile: { reasoning_effort: 'high' } }, custom_plan: { tasks: [task], targets: ['codex'], run_slots: ['one-planned-attempt'], repeat_count: 1 }, budget_semantics: {}, workspace_policy: 'ISOLATED_COPY_REQUIRED_HIDDEN_ASSETS_EXCLUDED' }
const receipt: PreflightReceipt = { receipt_id: 'preflight-1', receipt_digest: digest, status: 'READY_TO_SAVE', checks: [{ code: 'TASK_INTEGRITY_AND_SOURCE', passed: true }], material, created_at: '2026-10-10T00:00:00Z', expires_at: '2026-10-10T00:15:00Z', execution_authorized: false, provider_calls: 0, verifier_calls: 0 }
const detail: PlanDetail = { plan: { plan_id: 'plan-1', plan_digest: digest, created_at: receipt.created_at, preflight: receipt, status: 'SAVED_PLAN_ONLY', execution_authorized: false, runs_created: 0, episodes_created: 0 }, current_status: 'UNCHANGED_RECHECK_REQUIRED', checks: receipt.checks, execution_enabled: false }

beforeEach(() => {
  vi.resetAllMocks(); preferences.language = 'zh-CN'
  vi.mocked(localPlansApi.status).mockResolvedValue({ enabled: true, execution_enabled: false })
  vi.mocked(localPlansApi.sources).mockResolvedValue({ root_ids: ['trusted'], candidates: [{ root_id: 'trusted', relative_path: 'local-task/1.0.0' }] })
  vi.mocked(localPlansApi.tasks).mockResolvedValue({ items: [task] })
  vi.mocked(localPlansApi.configurations).mockResolvedValue({ items: [{ provider_profile_id: 'provider-model', harness_profile_id: 'codex-high', requested_model: 'gpt-5.6-sol', reasoning_effort: 'high', runtime_version: '0.149.0', image_reference: 'pinned-image', enabled: true, configuration_label: 'Codex gpt-5.6-sol high' }] })
  vi.mocked(localPlansApi.importTask).mockResolvedValue(task); vi.mocked(localPlansApi.inspect).mockResolvedValue(task)
  vi.mocked(localPlansApi.preflight).mockResolvedValue(receipt); vi.mocked(localPlansApi.save).mockResolvedValue(detail.plan)
  vi.mocked(localPlansApi.plans).mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 }); vi.mocked(localPlansApi.plan).mockResolvedValue(detail)
})
async function screen(path = '/plans') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/plans', component: LocalPlansView }, { path: '/plans/:planId', component: LocalPlansView }] })
  await router.push(path); await router.isReady()
  const wrapper = mount(LocalPlansView, { global: { plugins: [router] } }); await flushPromises()
  return { wrapper, router }
}
async function unlocked(path = '/plans') {
  const result = await screen(path)
  await result.wrapper.get('[data-test="operator"]').setValue('local-operator-placeholder')
  await result.wrapper.get('form').trigger('submit'); await flushPromises()
  return result
}
async function selected() {
  const result = await unlocked()
  await result.wrapper.get('[data-test="task"]').setValue(task.reference)
  await result.wrapper.get('[data-test="configuration"]').setValue('0')
  await result.wrapper.get('[data-test="name"]').setValue('Engineering task')
  return result
}
async function checked() {
  const result = await selected(); await result.wrapper.get('form').trigger('submit'); await flushPromises(); return result
}

describe('Private Phase-1 local planning', () => {
  it('requires operator access, never persists the token, and disables public workflow', async () => {
    const write = vi.spyOn(Storage.prototype, 'setItem')
    const { wrapper } = await screen()
    expect(localPlansApi.sources).not.toHaveBeenCalled()
    await wrapper.get('[data-test="operator"]').setValue('local-operator-placeholder')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(localPlansApi.sources).toHaveBeenCalledWith('local-operator-placeholder')
    expect(write.mock.calls.some(call => String(call).includes('local-operator-placeholder'))).toBe(false)
    write.mockRestore()
    vi.mocked(localPlansApi.status).mockResolvedValue({ enabled: false, execution_enabled: false })
    const disabled = await screen(); expect(disabled.wrapper.text()).toContain('本地计划功能未启用')
    expect(disabled.wrapper.find('[data-test="preflight"]').exists()).toBe(false)
  })
  it('imports a bounded source and distinguishes structure from historical acceptance', async () => {
    const { wrapper } = await unlocked(); await wrapper.get('[data-test="source"]').setValue('0')
    await wrapper.get('[data-test="import"]').trigger('click'); await flushPromises()
    expect(localPlansApi.importTask).toHaveBeenCalledWith('trusted', 'local-task/1.0.0', 'local-operator-placeholder')
    expect(wrapper.text()).toContain('本轮未执行 Verifier'); expect(wrapper.text()).toContain('摘要不认证来源')
  })
  it('saves exactly one plan only after explicit confirmation and reads its persisted detail', async () => {
    const { wrapper, router } = await checked()
    expect(wrapper.get('[data-test="save"]').attributes('disabled')).toBeDefined()
    expect(localPlansApi.save).not.toHaveBeenCalled()
    await wrapper.get('[data-test="confirmation"]').setValue(true)
    await wrapper.get('[data-test="save"]').trigger('click'); await flushPromises()
    expect(localPlansApi.save).toHaveBeenCalledWith(receipt, expect.any(String), 'local-operator-placeholder')
    expect(router.currentRoute.value.path).toBe('/plans/plan-1')
    expect(wrapper.get('[data-test="saved-plan"]').text()).toContain('0 Run · 0 Episode')
    expect(wrapper.get('[data-test="saved-plan"] button').attributes('disabled')).toBeDefined()
  })
  it('never offers save for blocked or unqualified tasks', async () => {
    vi.mocked(localPlansApi.tasks).mockResolvedValue({ items: [{ ...task, eligible_for_planning: false, behavioral_validation: 'NOT_VERIFIED', reason_codes: ['TRUSTED_PRIOR_QUALIFICATION_REQUIRED'] }] })
    vi.mocked(localPlansApi.preflight).mockResolvedValue({ ...receipt, status: 'BLOCKED', material: null, checks: [{ code: 'TRUSTED_PRIOR_QUALIFICATION', passed: false }] })
    const { wrapper } = await checked()
    expect(wrapper.text()).toContain('结构检查不能替代验收'); expect(wrapper.text()).toContain('不能保存计划')
    expect(wrapper.find('[data-test="save"]').exists()).toBe(false); expect(localPlansApi.save).not.toHaveBeenCalled()
  })
  it.each(['name', 'wall-time', 'tokens', 'cost'])('invalidates confirmation when %s changes', async field => {
    const { wrapper } = await checked(); await wrapper.get('[data-test="confirmation"]').setValue(true)
    await wrapper.get(`[data-test="${field}"]`).setValue(field === 'name' ? 'Changed plan' : 2)
    expect(wrapper.find('[data-test="preflight-result"]').exists()).toBe(false)
    expect(localPlansApi.save).not.toHaveBeenCalled()
  })
  it('discards an in-flight preflight after form drift', async () => {
    let resolve!: (r: PreflightReceipt) => void
    vi.mocked(localPlansApi.preflight).mockReturnValue(new Promise(r => { resolve = r }))
    const { wrapper } = await selected(); await wrapper.get('form').trigger('submit')
    await wrapper.get('[data-test="name"]').setValue('Changed during preflight'); resolve(receipt); await flushPromises()
    expect(wrapper.find('[data-test="save"]').exists()).toBe(false)
  })
  it('requires a fresh check after a backend drift rejection', async () => {
    vi.mocked(localPlansApi.save).mockRejectedValue({ response: { data: { error: { code: 'PREFLIGHT_STALE' } } } })
    const { wrapper } = await checked(); await wrapper.get('[data-test="confirmation"]').setValue(true)
    await wrapper.get('[data-test="save"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('请重新预检'); expect(wrapper.find('[data-test="save"]').exists()).toBe(false)
  })
  it('retries a lost save response with the same idempotency key', async () => {
    vi.mocked(localPlansApi.save).mockRejectedValueOnce(new Error('network response lost'))
    const { wrapper } = await checked(); await wrapper.get('[data-test="confirmation"]').setValue(true)
    await wrapper.get('[data-test="save"]').trigger('click'); await flushPromises()
    await wrapper.get('[data-test="confirmation"]').setValue(true)
    await wrapper.get('[data-test="save"]').trigger('click'); await flushPromises()
    const calls = vi.mocked(localPlansApi.save).mock.calls; expect(calls).toHaveLength(2); expect(calls[0]?.[1]).toBe(calls[1]?.[1])
  })
  it('reads saved plans after refreshing and displays current drift without rewriting the plan', async () => {
    vi.mocked(localPlansApi.plan).mockResolvedValue({ ...detail, current_status: 'STALE' })
    const { wrapper } = await unlocked('/plans/plan-1')
    expect(localPlansApi.plan).toHaveBeenCalledWith('plan-1', 'local-operator-placeholder')
    expect(wrapper.get('[data-test="current-status"]').text()).toContain('原计划保留')
    expect(localPlansApi.save).not.toHaveBeenCalled()
  })
  it('rejects missing budget in the form and clearly labels unenforced limits', async () => {
    const { wrapper } = await selected(); await wrapper.get('[data-test="cost"]').setValue('')
    expect(wrapper.get('[data-test="preflight"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('非硬上限'); expect(wrapper.text()).toContain('非强制限制')
  })
  it('keeps persisted plans readable when the source task list has drifted', async () => {
    vi.mocked(localPlansApi.tasks).mockRejectedValue({ response: { data: { error: { code: 'TASK_SOURCE_DRIFT' } } } })
    vi.mocked(localPlansApi.plan).mockResolvedValue({ ...detail, current_status: 'STALE' })
    const { wrapper } = await unlocked('/plans/plan-1')
    expect(wrapper.get('[data-test="saved-plan"]').text()).toContain('0 Run · 0 Episode')
    expect(wrapper.text()).toContain('旧预检已失效')
    expect(wrapper.get('[data-test="current-status"]').text()).toContain('原计划保留')
  })
  it('retains the same plan-only boundary in English', async () => {
    preferences.language = 'en-US'; const { wrapper } = await unlocked('/plans/plan-1')
    expect(wrapper.text()).toContain('execution not authorized'); expect(wrapper.text()).toContain('not a hard cap')
  })
})
