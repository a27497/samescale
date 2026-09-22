import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { preferences } from '@/composables/preferences'
import ExperimentBuilderView from '@/views/ExperimentBuilderView.vue'
import ModelsView from '@/views/ModelsView.vue'
import HarnessesView from '@/views/HarnessesView.vue'
import SavedPlans from '@/components/SavedPlans.vue'
import fixture from './fixtures/registry-connections.json'

const api = vi.hoisted(() => ({ models: vi.fn(), providers: vi.fn(), capabilities: vi.fn(), harnesses: vi.fn(), tasks: vi.fn(), methodologies: vi.fn(), settings: vi.fn(), preflight: vi.fn(), snapshot: vi.fn(), snapshots: vi.fn(), getSnapshot: vi.fn() }))
vi.mock('@/api/client', () => ({ registryApi: api }))
const model = { ...fixture.models.provider_profiles[0]!, profile_id: 'local-subject-v3', purpose: undefined, max_output_tokens_limit: 1000, reasoning_effort: 'high', request_timeout_seconds: 45, profile_identity: 'sha256:local-subject-v3' }
const runtime = { ...fixture.harnesses.items[0]!, version: 'runtime-v5', profiles: [{ ...fixture.harnesses.items[0]!.profiles[0]!, profile_id: 'local-harness-runtime-v2', enabled: true, supported_provider_profile_ids: [model.profile_id] }] }
const ready = { status: 'READY_WITH_WARNINGS', checks: [], estimated_logical_slots: 2, estimated_maximum_wall_time_seconds: 180, evaluation_mode: 'QUICK', repeat_count: 1, max_parallel_runs: 1, cost_estimate: { status: 'NOT_AVAILABLE', value: null }, schedule_preview: [], candidate_plan_digest: 'sha256:plan' }
const preflightButton = (w: ReturnType<typeof mount>) => w.get('.toolbar .primary-button')
const freezeButton = (w: ReturnType<typeof mount>) => w.get('.toolbar .secondary-button')
beforeEach(() => {
  vi.resetAllMocks(); preferences.language = 'zh-CN'
  api.providers.mockResolvedValue(structuredClone(fixture.providers))
  api.capabilities.mockResolvedValue(structuredClone(fixture.capabilities))
  api.models.mockResolvedValue({ models: fixture.models.models, provider_profiles: [model, ...['ANALYST', 'JUDGE', 'UNKNOWN'].map(purpose => ({ ...model, profile_id: `local-${purpose}-v1`, purpose }))] })
  api.harnesses.mockResolvedValue({ items: [runtime] })
  api.tasks.mockResolvedValue({ items: [{ task_id: 'task-one' }] })
  api.methodologies.mockResolvedValue({ items: [{ active: false, methodology_id: 'inactive' }, { active: true, methodology_id: 'method', methodology_digest: 'sha256:method', repeat_counts: { QUICK: 1 } }] })
  api.settings.mockResolvedValue({ defaults: { default_provider_profile_id: model.profile_id, default_evaluation_mode: 'QUICK', default_schedule_seed: 9, default_concurrency: 1 }, credentials: [], provider_enabled: {} })
  api.preflight.mockResolvedValue(ready)
  const saved = { plan: { name: 'Planning binding fixture', evaluation_mode: 'QUICK' }, preflight: ready, snapshot_id: 'snapshot-test', snapshot_digest: 'sha256:snapshot', provider_selections: [{ cell_id: 'left', provider_profile_id: model.profile_id, provider_profile_identity: model.profile_identity, harness_profile_id: runtime.profiles[0]!.profile_id, effective_runtime_profile_identity: 'sha256:actual-runtime', resource_envelope_identity: 'sha256:actual-budget' }] }
  api.snapshot.mockResolvedValue(saved)
  api.getSnapshot.mockResolvedValue(saved)
  api.snapshots.mockResolvedValue({ items: [{ ...saved, name: saved.plan.name }], total: 1, offset: 0, limit: 25 })
})
async function open(url = '/experiments/new') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/experiments/new', component: ExperimentBuilderView }, { path: '/experiments', component: SavedPlans }, { path: '/models', component: ModelsView }, { path: '/harnesses', component: HarnessesView }, { path: '/connections', component: { template: '<div />' } }] })
  await router.push(url); await router.isReady()
  const w = mount({ template: '<RouterView />' }, { global: { plugins: [router] } }); await flushPromises(); return w
}
async function select(w: ReturnType<typeof mount>) {
  for (const side of ['左侧', '右侧']) {
    await w.get(`[aria-label="${side}模型服务配置"]`).setValue(model.profile_id)
    await w.get(`[aria-label="${side}执行方式"]`).setValue(runtime.profiles[0]!.profile_id)
  }
  await w.get('.task-picker input').setValue(true)
  await w.get('[aria-label="输出 Token 上限"]').setValue(800)
  await w.get('[aria-label="对比类型"]').setValue('END_TO_END_SYSTEM_COMPARISON')
}
describe('local planning binding', () => {
  it('uses initial server defaults without running preflight and excludes non-SUBJECT and unknown local roles', async () => {
    const w = await open()
    expect((w.get('[aria-label="左侧模型服务配置"]').element as HTMLSelectElement).value).toBe(model.profile_id)
    expect((w.get('[aria-label="左侧执行方式"]').element as HTMLSelectElement).value).toBe('direct-gpt56-relay-gpt56-responses')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect((w.get('.task-picker input').element as HTMLInputElement).checked).toBe(true)
    expect(w.get('[aria-label="左侧模型服务配置"]').text()).not.toMatch(/local-(ANALYST|JUDGE|UNKNOWN)/)
    expect(w.find('[aria-label="右侧模型服务配置"]').text()).not.toMatch(/local-(ANALYST|JUDGE|UNKNOWN)/)
    await select(w)
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    expect(api.preflight).not.toHaveBeenCalled()
  })
  it('submits the displayed exact revisions and Direct resource contract, and shows server-frozen identities', async () => {
    // Registry metadata lives in resource detail pages; saved identities live in the read-only plan.
    const w = await open('/models')
    const profile = w.findAll('.provider-profile').find(p => p.text().includes(model.profile_id))!
    expect(profile.text()).toContain(model.profile_identity)
    expect(profile.text()).toContain('high')
    expect(w.text()).toContain('NOT_AVAILABLE')
    await w.vm.$router.push('/harnesses'); await flushPromises()
    expect(w.get('.harness-card').text()).toContain('runtime-v5')
    await w.vm.$router.push('/experiments/new'); await flushPromises(); await select(w)
    expect((w.get('[aria-label="左侧模型服务配置"]').element as HTMLSelectElement).value).toBe(model.profile_id)
    expect((w.get('[aria-label="左侧执行方式"]').element as HTMLSelectElement).value).toBe(runtime.profiles[0]!.profile_id)
    await preflightButton(w).trigger('click'); await flushPromises()
    const payload = api.preflight.mock.calls[0]![0]
    expect(payload.cells).toEqual(['left', 'right'].map(cell_id => ({ cell_id, provider_model_profile_id: model.profile_id, harness_profile_id: runtime.profiles[0]!.profile_id })))
    expect(payload.methodology_id).toBe('method')
    expect(payload.budget.max_output_tokens).toEqual({ status: 'ENFORCED', value: 800, unit: 'tokens', scopes: ['PER_PROVIDER_REQUEST', 'PER_LOGICAL_RUN'] })
    expect(payload.budget.max_model_turns.value).toBe(1)
    expect(payload.budget.max_provider_requests.value).toBe(1)
    expect(payload.budget.max_tool_calls.value).toBe(0)
    expect(payload.budget.max_cost).toMatchObject({ status: 'NOT_AVAILABLE', value: null })
    await freezeButton(w).trigger('click'); await flushPromises()
    expect(api.snapshot).toHaveBeenCalledWith(payload)
    await w.get('.snapshot-confirmation a').trigger('click'); await flushPromises()
    expect(api.getSnapshot).toHaveBeenCalledWith('snapshot-test')
    const frozen = w.get('.saved-plan-detail pre').text()
    expect(frozen).toContain(model.profile_identity)
    expect(frozen).toContain('sha256:actual-runtime')
    expect(frozen).toContain('sha256:actual-budget')
  })
  it('blocks an excessive configuration budget without clamping or sending it', async () => {
    const w = await open(); await select(w)
    await w.get('[aria-label="输出 Token 上限"]').setValue(1001)
    expect((w.get('[aria-label="输出 Token 上限"]').element as HTMLInputElement).value).toBe('1001')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect(w.get('[role="alert"]').text()).toContain('输出预算超出所选配置上限')
    expect(w.get('[role="alert"]').text()).toContain('1000')
    await preflightButton(w).trigger('click'); expect(api.preflight).not.toHaveBeenCalled()
  })
  it.each([999, 1000])('allows a budget of %i under the server limit and sends the unchanged value', async budget => {
    const w = await open(); await select(w)
    await w.get('[aria-label="输出 Token 上限"]').setValue(budget)
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
    expect(w.find('[role="alert"]').exists()).toBe(false)
    await preflightButton(w).trigger('click'); await flushPromises()
    expect(api.preflight.mock.calls[0]![0].budget.max_output_tokens.value).toBe(budget)
    expect(freezeButton(w).attributes('disabled')).toBeUndefined()
  })
  it('invalidates the old preflight when exceeding the limit and requires a fresh preflight after correction', async () => {
    const w = await open(); await select(w)
    await w.get('[aria-label="输出 Token 上限"]').setValue(1000)
    await preflightButton(w).trigger('click'); await flushPromises()
    expect(freezeButton(w).attributes('disabled')).toBeUndefined()
    await w.get('[aria-label="输出 Token 上限"]').setValue(1001)
    expect((w.get('[aria-label="输出 Token 上限"]').element as HTMLInputElement).value).toBe('1001')
    expect(w.get('[role="alert"]').text()).toContain('1000')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    expect(w.text()).not.toContain('sha256:plan')
    await preflightButton(w).trigger('click'); await freezeButton(w).trigger('click')
    expect(api.preflight).toHaveBeenCalledTimes(1); expect(api.snapshot).not.toHaveBeenCalled()
    await w.get('[aria-label="输出 Token 上限"]').setValue(999)
    expect(w.find('[role="alert"]').exists()).toBe(false)
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    await preflightButton(w).trigger('click'); await flushPromises()
    expect(api.preflight).toHaveBeenCalledTimes(2)
    expect(api.preflight.mock.calls[1]![0].budget.max_output_tokens.value).toBe(999)
    expect(freezeButton(w).attributes('disabled')).toBeUndefined()
  })
  it.each(['左侧', '右侧'])('recalculates the budget limit and invalidates preflight when %s switches to a stricter configuration', async side => {
    const strict = { ...model, profile_id: 'local-strict-v1', max_output_tokens_limit: 500 }
    api.models.mockResolvedValue({ models: fixture.models.models, provider_profiles: [model, strict] })
    api.harnesses.mockResolvedValue({ items: [{ ...runtime, profiles: [{ ...runtime.profiles[0]!, supported_provider_profile_ids: [model.profile_id, strict.profile_id] }] }] })
    const w = await open(); await select(w)
    await preflightButton(w).trigger('click'); await flushPromises()
    expect(freezeButton(w).attributes('disabled')).toBeUndefined()
    await w.get(`[aria-label="${side}模型服务配置"]`).setValue(strict.profile_id)
    expect((w.get('[aria-label="输出 Token 上限"]').element as HTMLInputElement).value).toBe('800')
    expect(w.get('[role="alert"]').text()).toContain('500')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    await preflightButton(w).trigger('click'); expect(api.preflight).toHaveBeenCalledTimes(1)
    await w.get('[aria-label="输出 Token 上限"]').setValue(500)
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    await preflightButton(w).trigger('click'); await flushPromises()
    expect(api.preflight.mock.calls[1]![0].budget.max_output_tokens.value).toBe(500)
    await w.get(`[aria-label="${side}模型服务配置"]`).setValue(model.profile_id)
    await w.get('[aria-label="输出 Token 上限"]').setValue(1000)
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
  })
  it('does not invent a budget limit when the server omits it', async () => {
    api.models.mockResolvedValue({ models: fixture.models.models, provider_profiles: [{ ...model, max_output_tokens_limit: null }] })
    const w = await open(); await select(w)
    await w.get('[aria-label="输出 Token 上限"]').setValue(2001)
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })
  it('ignores a late preflight response after an over-limit budget edit', async () => {
    const w = await open(); await select(w)
    let done!: (value: unknown) => void
    api.preflight.mockReturnValueOnce(new Promise(resolve => { done = resolve }))
    await preflightButton(w).trigger('click')
    await w.get('[aria-label="输出 Token 上限"]').setValue(1001)
    done(ready); await flushPromises()
    expect(w.text()).not.toContain('sha256:plan')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    await w.get('[aria-label="输出 Token 上限"]').setValue(1000)
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
  })
  it('invalidates preflight after budget or task edits and ignores late responses', async () => {
    const w = await open(); await select(w)
    let done!: (value: unknown) => void
    api.preflight.mockReturnValueOnce(new Promise(resolve => { done = resolve }))
    await preflightButton(w).trigger('click')
    await w.get('.task-picker input').setValue(false)
    expect(api.preflight.mock.calls[0]![0].task_ids).toEqual(['task-one'])
    done(ready); await flushPromises()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    await w.get('.task-picker input').setValue(true)
    await preflightButton(w).trigger('click'); await flushPromises()
    await w.get('[aria-label="输出 Token 上限"]').setValue(700)
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    expect(w.text()).not.toContain('sha256:plan')
  })
  it('preserves a removed selection as unavailable and never selects the replacement revision', async () => {
    const w = await open(); await select(w)
    // A stale selection is reported by preflight; use the visible catalog recovery action.
    api.preflight.mockRejectedValueOnce(new Error('stale-profile'))
    await preflightButton(w).trigger('click'); await flushPromises()
    api.models.mockResolvedValue({ models: fixture.models.models, provider_profiles: [{ ...model, profile_id: 'local-subject-v4', profile_identity: 'sha256:local-subject-v4' }] })
    api.harnesses.mockResolvedValue({ items: [{ ...runtime, profiles: [{ ...runtime.profiles[0]!, supported_provider_profile_ids: ['local-subject-v4'] }] }] })
    await w.get('.retry-button').trigger('click'); await flushPromises()
    expect(api.models).toHaveBeenCalledTimes(2)
    expect((w.get('[aria-label="左侧模型服务配置"]').element as HTMLSelectElement).value).toBe(model.profile_id)
    expect(w.get('[aria-label="左侧模型服务配置"]').text()).toContain(`已不可用: ${model.profile_id}`)
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect((w.get('[aria-label="右侧模型服务配置"]').element as HTMLSelectElement).value).toBe(model.profile_id)
    expect(w.get('[aria-label="右侧模型服务配置"]').text()).toContain(`已不可用: ${model.profile_id}`)
    expect(w.text()).toContain(model.profile_identity)
    expect(w.text()).not.toContain('sha256:plan')
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    const calls = api.preflight.mock.calls.length
    await preflightButton(w).trigger('click'); await freezeButton(w).trigger('click')
    expect(api.preflight).toHaveBeenCalledTimes(calls); expect(api.snapshot).not.toHaveBeenCalled()
    await w.get('[aria-label="左侧模型服务配置"]').setValue('local-subject-v4')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    await w.get('[aria-label="右侧模型服务配置"]').setValue('local-subject-v4')
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    await preflightButton(w).trigger('click'); await flushPromises()
    expect(api.preflight.mock.calls.at(-1)![0].cells.map((cell: { provider_model_profile_id: string }) => cell.provider_model_profile_id)).toEqual(['local-subject-v4', 'local-subject-v4'])
    expect(freezeButton(w).attributes('disabled')).toBeUndefined()
    api.snapshot.mockResolvedValueOnce({ snapshot_id: 'snapshot-v4', snapshot_digest: 'sha256:snapshot-v4' })
    await freezeButton(w).trigger('click'); await flushPromises()
    expect(api.snapshot.mock.calls.at(-1)![0].cells.map((cell: { provider_model_profile_id: string }) => cell.provider_model_profile_id)).toEqual(['local-subject-v4', 'local-subject-v4'])
    expect(w.get('.snapshot-confirmation').text()).toContain('snapshot-v4')
  })
  it('applies initial defaults after an initial catalog failure', async () => {
    api.models.mockRejectedValueOnce(new Error('catalog unavailable'))
    const w = await open()
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    await w.get('.retry-button').trigger('click'); await flushPromises()
    for (const side of ['左侧', '右侧']) {
      expect((w.get(`[aria-label="${side}模型服务配置"]`).element as HTMLSelectElement).value).toBe(model.profile_id)
    }
    expect(api.preflight).not.toHaveBeenCalled()
  })
  it('ignores a late preflight for the previous model selection on either side', async () => {
    api.models.mockResolvedValue({ models: fixture.models.models, provider_profiles: [model, { ...model, profile_id: 'local-subject-v4' }] })
    for (const side of ['左侧', '右侧']) {
      const w = await open(); await select(w)
      let done!: (value: unknown) => void
      api.preflight.mockReturnValueOnce(new Promise(resolve => { done = resolve }))
      await preflightButton(w).trigger('click')
      await w.get(`[aria-label="${side}模型服务配置"]`).setValue('local-subject-v4')
      done(ready); await flushPromises()
      expect(w.text()).not.toContain('sha256:plan')
      expect(freezeButton(w).attributes('disabled')).toBeDefined()
      w.unmount()
    }
  })
  it('clears stale data on failed reload and retries without leaking errors or selecting defaults', async () => {
    const w = await open(); await select(w)
    // Catalog reload is now exposed after a request error, not as the first button.
    api.preflight.mockRejectedValueOnce(new Error('preflight-unavailable'))
    await preflightButton(w).trigger('click'); await flushPromises()
    api.models.mockRejectedValueOnce(new Error('private-endpoint'))
    await w.get('.retry-button').trigger('click'); await flushPromises()
    expect(api.models).toHaveBeenCalledTimes(2)
    expect(w.text()).toContain('无法读取实验规划配置，请检查本地 API 后重试。')
    expect(w.text()).not.toContain('private-endpoint')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    await w.get('.retry-button').trigger('click'); await flushPromises()
    expect(api.models).toHaveBeenCalledTimes(3)
    expect(w.text()).not.toContain('无法读取实验规划配置，请检查本地 API 后重试。')
    expect((w.get('[aria-label="左侧模型服务配置"]').element as HTMLSelectElement).value).toBe(model.profile_id)
  })
  it.each(['disabled', 'incompatible'])('blocks disabled or incompatible Harness selections (%s)', async state => {
    // Keep the supported alternative revision present in the catalog: only the selected pair is incompatible.
    api.models.mockResolvedValue({ models: fixture.models.models, provider_profiles: [model, { ...model, profile_id: 'other-model-revision' }] })
    api.harnesses.mockResolvedValue({ items: [{ ...runtime, profiles: [{ ...runtime.profiles[0]!, enabled: state !== 'disabled', supported_provider_profile_ids: state === 'incompatible' ? ['other-model-revision'] : [model.profile_id] }] }] })
    const w = await open(); await select(w)
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    await preflightButton(w).trigger('click'); await freezeButton(w).trigger('click')
    expect(api.preflight).not.toHaveBeenCalled(); expect(api.snapshot).not.toHaveBeenCalled()
  })
  it.each(['左侧', '右侧'])('blocks one invalid %s Harness and recovers only after explicit selection and new preflight', async side => {
    const valid = runtime.profiles[0]!
    const disabled = { ...valid, profile_id: 'disabled-runtime', enabled: false }
    api.harnesses.mockResolvedValue({ items: [{ ...runtime, profiles: [valid, disabled] }] })
    const w = await open(); await select(w)
    await preflightButton(w).trigger('click'); await flushPromises()
    expect(freezeButton(w).attributes('disabled')).toBeUndefined()
    await w.get(`[aria-label="${side}执行方式"]`).setValue(disabled.profile_id)
    expect((w.get(`[aria-label="${side}执行方式"]`).element as HTMLSelectElement).value).toBe(disabled.profile_id)
    expect(w.text()).toContain('执行方式已停用')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    expect(w.text()).not.toContain('sha256:plan')
    await preflightButton(w).trigger('click'); await freezeButton(w).trigger('click')
    expect(api.preflight).toHaveBeenCalledTimes(1); expect(api.snapshot).not.toHaveBeenCalled()
    await w.get(`[aria-label="${side}执行方式"]`).setValue(valid.profile_id)
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    await preflightButton(w).trigger('click'); await flushPromises()
    expect(api.preflight).toHaveBeenCalledTimes(2)
    expect(freezeButton(w).attributes('disabled')).toBeUndefined()
  })
  it.each(['左侧', '右侧'])('preserves %s Harness identity when a model change makes it incompatible and rejects a late response', async side => {
    const nextModel = { ...model, profile_id: 'other-model-revision' }
    const nextRuntime = { ...runtime.profiles[0]!, profile_id: 'other-runtime', supported_provider_profile_ids: [nextModel.profile_id] }
    api.models.mockResolvedValue({ models: fixture.models.models, provider_profiles: [model, nextModel] })
    api.harnesses.mockResolvedValue({ items: [{ ...runtime, profiles: [...runtime.profiles, nextRuntime] }] })
    const w = await open(); await select(w)
    let done!: (value: unknown) => void
    api.preflight.mockReturnValueOnce(new Promise(resolve => { done = resolve }))
    await preflightButton(w).trigger('click')
    await w.get(`[aria-label="${side}模型服务配置"]`).setValue(nextModel.profile_id)
    done(ready); await flushPromises()
    expect((w.get(`[aria-label="${side}执行方式"]`).element as HTMLSelectElement).value).toBe(runtime.profiles[0]!.profile_id)
    expect(w.text()).toContain('执行方式与所选模型版本不兼容')
    expect(w.text()).not.toContain('sha256:plan')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    await preflightButton(w).trigger('click'); expect(api.preflight).toHaveBeenCalledTimes(1)
    await w.get(`[aria-label="${side}执行方式"]`).setValue(nextRuntime.profile_id)
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    await preflightButton(w).trigger('click'); await flushPromises()
    expect(freezeButton(w).attributes('disabled')).toBeUndefined()
  })
  it.each(['disabled', 'removed', 'incompatible'])('keeps the selected Harness on catalog reload when it becomes %s', async state => {
    const valid = runtime.profiles[0]!
    const w = await open(); await select(w)
    api.preflight.mockRejectedValueOnce(new Error('catalog changed'))
    await preflightButton(w).trigger('click'); await flushPromises()
    const replacement = { ...valid, profile_id: 'replacement-runtime' }
    const changed = { ...valid, enabled: state !== 'disabled', supported_provider_profile_ids: state === 'incompatible' ? [] : valid.supported_provider_profile_ids }
    api.harnesses.mockResolvedValue({ items: [{ ...runtime, profiles: state === 'removed' ? [replacement] : [changed, replacement] }] })
    await w.get('.retry-button').trigger('click'); await flushPromises()
    for (const side of ['左侧', '右侧']) {
      expect((w.get(`[aria-label="${side}执行方式"]`).element as HTMLSelectElement).value).toBe(valid.profile_id)
    }
    expect(w.text()).toContain(valid.harness_config_identity)
    expect(w.text()).toContain(state === 'removed' ? '已不可用' : state === 'disabled' ? '执行方式已停用' : '执行方式与所选模型版本不兼容')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    await preflightButton(w).trigger('click'); expect(api.preflight).toHaveBeenCalledTimes(1)
    for (const side of ['左侧', '右侧']) await w.get(`[aria-label="${side}执行方式"]`).setValue(replacement.profile_id)
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
  })
  it.each(['disabled', 'incompatible', 'missing'])('does not replace an invalid initial Harness (%s) with another executor', async state => {
    const preferred = { ...runtime.profiles[0]!, profile_id: 'direct-gpt56-relay-gpt56-responses', enabled: state !== 'disabled', supported_provider_profile_ids: state === 'incompatible' ? [] : [model.profile_id] }
    api.harnesses.mockResolvedValue({ items: [{ ...runtime, profiles: state === 'missing' ? runtime.profiles : [preferred, ...runtime.profiles] }] })
    const w = await open()
    expect((w.get('[aria-label="左侧执行方式"]').element as HTMLSelectElement).value).toBe(preferred.profile_id)
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect(api.preflight).not.toHaveBeenCalled()
    expect(w.get('[aria-label="左侧执行方式"]').text()).toContain(runtime.profiles[0]!.profile_id)
    await select(w)
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
  })
  it('does not persist a BLOCKED preflight or reuse preflight after a rejected snapshot', async () => {
    const w = await open(); await select(w)
    api.preflight.mockResolvedValueOnce({ ...ready, status: 'BLOCKED' })
    await preflightButton(w).trigger('click'); await flushPromises()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    await preflightButton(w).trigger('click'); await flushPromises()
    api.snapshot.mockRejectedValueOnce(new Error('private-secret'))
    await freezeButton(w).trigger('click'); await flushPromises()
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    expect(w.text()).not.toContain('private-secret')
  })
  it('does not turn an inactive methodology into an active default', async () => {
    api.methodologies.mockResolvedValue({ items: [{ active: false }] })
    const w = await open(); await select(w)
    expect((w.get('[aria-label="重复策略"]').element as HTMLInputElement).value).toContain('UNKNOWN')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
  })
})


it('keeps an empty methodology catalog unknown and blocks preflight and saving', async () => {
  api.methodologies.mockResolvedValue({ items: [] })
  const w = await open(); await select(w)
  expect((w.get('[aria-label="重复策略"]').element as HTMLInputElement).value).toBe('UNKNOWN')
  expect(preflightButton(w).attributes('disabled')).toBeDefined()
  expect(freezeButton(w).attributes('disabled')).toBeDefined()
  await preflightButton(w).trigger('click'); await freezeButton(w).trigger('click')
  expect(api.preflight).not.toHaveBeenCalled(); expect(api.snapshot).not.toHaveBeenCalled()
})

it('displays the active server methodology repeat counts for every mode without a local default', async () => {
  api.methodologies.mockResolvedValue({ items: [
    { methodology_id: 'inactive', active: false, repeat_counts: { QUICK: 99, INFORMAL: 99, FORMAL_EXHAUSTIVE: 99 } },
    { methodology_id: 'active', methodology_digest: 'sha256:active', active: true, repeat_counts: { QUICK: 1, INFORMAL: 3, FORMAL_EXHAUSTIVE: 5 } },
  ] })
  const w = await open(); await select(w)
  for (const [mode, count] of [['QUICK', 1], ['INFORMAL', 3], ['FORMAL_EXHAUSTIVE', 5]] as const) {
    await w.get('[aria-label="评测模式"]').setValue(mode)
    expect((w.get('[aria-label="重复策略"]').element as HTMLInputElement).value).toBe(`n=${count} (服务端固定)`)
    expect(preflightButton(w).attributes('disabled')).toBeUndefined()
  }
  expect(api.preflight).not.toHaveBeenCalled(); expect(api.snapshot).not.toHaveBeenCalled()
})
