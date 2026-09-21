import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ExperimentBuilderView from '@/views/ExperimentBuilderView.vue'
import fixture from './fixtures/registry-connections.json'

const api = vi.hoisted(() => ({ models: vi.fn(), harnesses: vi.fn(), tasks: vi.fn(), methodologies: vi.fn(), settings: vi.fn(), preflight: vi.fn(), snapshot: vi.fn() }))
vi.mock('@/api/client', () => ({ registryApi: api }))
const model = { ...fixture.models.provider_profiles[0]!, profile_id: 'local-subject-v3', purpose: undefined, max_output_tokens_limit: 1000, reasoning_effort: 'high', request_timeout_seconds: 45, profile_identity: 'sha256:local-subject-v3' }
const runtime = { ...fixture.harnesses.items[0]!, version: 'runtime-v5', profiles: [{ ...fixture.harnesses.items[0]!.profiles[0]!, profile_id: 'local-harness-runtime-v2', enabled: true, supported_provider_profile_ids: [model.profile_id] }] }
const ready = { status: 'READY_WITH_WARNINGS', checks: [], estimated_logical_slots: 2, estimated_maximum_wall_time_seconds: 180, evaluation_mode: 'QUICK', repeat_count: 1, max_parallel_runs: 1, cost_estimate: { status: 'NOT_AVAILABLE', value: null }, schedule_preview: [], candidate_plan_digest: 'sha256:plan' }
const preflightButton = (w: ReturnType<typeof mount>) => w.get('.toolbar .primary-button')
const freezeButton = (w: ReturnType<typeof mount>) => w.get('.toolbar .secondary-button')
beforeEach(() => {
  vi.resetAllMocks()
  api.models.mockResolvedValue({ provider_profiles: [model, ...['ANALYST', 'JUDGE', 'UNKNOWN'].map(purpose => ({ ...model, profile_id: `local-${purpose}-v1`, purpose }))] })
  api.harnesses.mockResolvedValue({ items: [runtime] })
  api.tasks.mockResolvedValue({ items: [{ task_id: 'task-one' }] })
  api.methodologies.mockResolvedValue({ items: [{ active: false, methodology_id: 'inactive' }, { active: true, methodology_id: 'method', methodology_digest: 'sha256:method', repeat_counts: { QUICK: 1 } }] })
  api.settings.mockResolvedValue({ defaults: { default_provider_profile_id: model.profile_id, default_evaluation_mode: 'QUICK', default_schedule_seed: 9, default_concurrency: 1 } })
  api.preflight.mockResolvedValue(ready)
  api.snapshot.mockResolvedValue({ snapshot_id: 'snapshot-test', snapshot_digest: 'sha256:snapshot', provider_selections: [{ cell_id: 'left', provider_profile_id: model.profile_id, provider_profile_identity: model.profile_identity, harness_profile_id: runtime.profiles[0]!.profile_id, effective_runtime_profile_identity: 'sha256:actual-runtime', resource_envelope_identity: 'sha256:actual-budget' }] })
})
async function open() { const w = mount(ExperimentBuilderView); await flushPromises(); return w }
async function select(w: ReturnType<typeof mount>) {
  for (const side of ['Left', 'Right']) {
    await w.get(`[aria-label="${side} provider profile"]`).setValue(model.profile_id)
    await w.get(`[aria-label="${side} Harness profile"]`).setValue(runtime.profiles[0]!.profile_id)
  }
  await w.get('.task-picker input').setValue(true)
  await w.get('[aria-label="Max output tokens"]').setValue(800)
  await w.get('[aria-label="Comparison type"]').setValue('END_TO_END_SYSTEM_COMPARISON')
}
describe('local planning binding', () => {
  it('starts unconfigured even with a server default and excludes non-SUBJECT and unknown local roles', async () => {
    const w = await open()
    expect((w.get('[aria-label="Left provider profile"]').element as HTMLSelectElement).value).toBe('')
    expect((w.get('[aria-label="Left Harness profile"]').element as HTMLSelectElement).value).toBe('')
    expect((w.get('.task-picker input').element as HTMLInputElement).checked).toBe(false)
    expect(w.get('[aria-label="Left provider profile"]').text()).not.toMatch(/local-(ANALYST|JUDGE|UNKNOWN)/)
    expect(w.text()).toContain('UNKNOWN / unconfigured')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect(api.preflight).not.toHaveBeenCalled()
  })
  it('submits the displayed exact revisions and Direct resource contract, and shows server-frozen identities', async () => {
    const w = await open(); await select(w)
    expect(w.get('[data-cell="left"]').text()).toContain(model.profile_identity)
    expect(w.get('[data-cell="left"]').text()).toContain('runtime-v5')
    expect(w.get('[data-cell="left"]').text()).toContain('high')
    expect(w.text()).toContain('NOT_AVAILABLE')
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
    expect(w.get('[data-frozen-cell="left"]').text()).toContain('sha256:actual-runtime')
    expect(w.get('[data-frozen-cell="left"]').text()).toContain('sha256:actual-budget')
  })
  it('blocks an excessive configuration budget without clamping or sending it', async () => {
    const w = await open(); await select(w)
    await w.get('[aria-label="Max output tokens"]').setValue(1001)
    expect(w.get('[role="alert"]').text()).toContain('exceeds')
    expect((w.get('[aria-label="Max output tokens"]').element as HTMLInputElement).value).toBe('1001')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    await preflightButton(w).trigger('click'); expect(api.preflight).not.toHaveBeenCalled()
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
    await w.get('[aria-label="Max output tokens"]').setValue(700)
    expect(freezeButton(w).attributes('disabled')).toBeDefined()
    expect(w.text()).not.toContain('sha256:plan')
  })
  it('preserves a removed selection as unavailable and never selects the replacement revision', async () => {
    const w = await open(); await select(w)
    api.models.mockResolvedValue({ provider_profiles: [{ ...model, profile_id: 'local-subject-v4' }] })
    await w.get('button').trigger('click'); await flushPromises()
    expect((w.get('[aria-label="Left provider profile"]').element as HTMLSelectElement).value).toBe(model.profile_id)
    expect(w.get('[aria-label="Left provider profile"]').text()).toContain(`Unavailable: ${model.profile_id}`)
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
  })
  it('clears stale data on failed reload and retries without leaking errors or selecting defaults', async () => {
    const w = await open(); await select(w)
    api.models.mockRejectedValueOnce(new Error('private-endpoint'))
    await w.get('button').trigger('click'); await flushPromises()
    expect(w.text()).toContain('contracts are unavailable')
    expect(w.text()).not.toContain('private-endpoint')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    await w.get('button').trigger('click'); await flushPromises()
    expect(w.text()).not.toContain('contracts are unavailable')
    expect((w.get('[aria-label="Left provider profile"]').element as HTMLSelectElement).value).toBe(model.profile_id)
  })
  it('blocks disabled or incompatible Harness selections', async () => {
    api.harnesses.mockResolvedValue({ items: [{ ...runtime, profiles: [{ ...runtime.profiles[0]!, enabled: false }] }] })
    const w = await open(); await select(w)
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
    expect(api.preflight).not.toHaveBeenCalled()
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
    expect((w.get('[aria-label="Repeat policy"]').element as HTMLInputElement).value).toContain('UNKNOWN')
    expect(preflightButton(w).attributes('disabled')).toBeDefined()
  })
})
