import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import router from '@/router'
import { preferences } from '@/composables/preferences'
import CapabilitiesView from '@/views/CapabilitiesView.vue'
import ExperimentBuilderView from '@/views/ExperimentBuilderView.vue'
import HarnessesView from '@/views/HarnessesView.vue'
import ModelsView from '@/views/ModelsView.vue'
import ProvidersView from '@/views/ProvidersView.vue'
import ConnectionsView from '@/views/ConnectionsView.vue'
import SettingsView from '@/views/SettingsView.vue'

const api = vi.hoisted(() => ({
  providers: vi.fn(), models: vi.fn(), harnesses: vi.fn(), capabilities: vi.fn(),
  settings: vi.fn(), tasks: vi.fn(), methodologies: vi.fn(), preflight: vi.fn(), snapshot: vi.fn(),
}))

vi.mock('@/api/client', () => ({ registryApi: api }))

const providerProfile = {
  profile_id: 'gpt56-relay-gpt56-responses', model_id: 'gpt-5.6-sol', provider_id: 'gpt56-relay',
  requested_model: 'gpt-5.6-sol', protocol: 'responses', route: '/responses',
  provider_route_identity: 'gpt56-relay|responses|env:HARNESSLAB_GPT56_RELAY_BASE_URL/responses',
  credential_ref: 'HARNESSLAB_GPT56_RELAY_API_KEY', reasoning_effort: 'medium',
  max_output_tokens: 2000, request_timeout_seconds: 180, observed_model_capability: 'RUN_EVIDENCE_ONLY',
  automation_allowed: true, enabled: true, pricing_snapshot_reference: null,
  runtime_endpoint_fingerprint: 'sha256:fingerprint', profile_identity: 'sha256:profile',
}

const directProfile = {
  profile_id: 'direct-gpt56-relay-gpt56-responses',
  profile_reference: 'builtin:registry.direct.gpt56-relay-gpt56-responses',
  supported_provider_profile_ids: ['gpt56-relay-gpt56-responses'], reasoning_effort: 'medium',
  harness_config_identity: 'sha256:direct',
}
const codexProfile = {
  profile_id: 'codex-gpt56-medium', profile_reference: 'builtin:registry.codex-gpt56',
  supported_provider_profile_ids: ['gpt56-relay-gpt56-responses'], reasoning_effort: 'medium',
  harness_config_identity: 'sha256:codex',
}

beforeEach(() => {
  vi.clearAllMocks()
  api.providers.mockResolvedValue({ items: [{
    provider_id: 'alibaba-bailian', display_name: 'Alibaba Bailian', provider_family: 'Alibaba Cloud',
    region: 'cn-beijing', protocols: ['chat_completions', 'responses'], endpoint_class: 'WORKSPACE_DEDICATED',
    base_url_reference: 'HARNESSLAB_ALIBABA_BAILIAN_BASE_URL', credential_ref: 'HARNESSLAB_ALIBABA_BAILIAN_API_KEY',
    billing_mode: 'PAY_AS_YOU_GO', automation_allowed: true, enabled: true, health_status: 'UNKNOWN',
    capabilities: ['openai-compatible'], pricing_snapshot_reference: null, runtime_endpoint_fingerprint: null,
    configuration_reason_codes: ['CONFIGURED_MODEL_ID_REQUIRED'],
  }] })
  api.models.mockResolvedValue({ models: [], provider_profiles: [providerProfile] })
  api.harnesses.mockResolvedValue({ items: [
    { harness_id: 'direct-model', display_name: 'Direct model', version: '1', image_reference: 'image', image_digest: null, cli_runtime_identity: 'direct', profiles: [directProfile], supported_protocols: ['responses'], tool_surface: [], trace_coverage: 'FINAL_OUTPUT_ONLY', observed_model_exposure: 'RUN_EVIDENCE_ONLY', network_capability: 'PROVIDER_ALLOWLIST', mcp_capability: false, workspace_mutation: true, native_tools: false, runtime_health: 'UNKNOWN', runner_contract: 'direct-model-v1' },
    { harness_id: 'codex', display_name: 'Codex', version: '0.149.0', image_reference: 'codex-image', image_digest: null, cli_runtime_identity: 'codex', profiles: [codexProfile], supported_protocols: ['responses'], tool_surface: ['shell'], trace_coverage: 'FULL_STREAM', observed_model_exposure: 'RUN_EVIDENCE_ONLY', network_capability: 'PROVIDER_ALLOWLIST', mcp_capability: true, workspace_mutation: true, native_tools: true, runtime_health: 'UNKNOWN', runner_contract: 'codex-harness-v1' },
  ] })
  api.tasks.mockResolvedValue({ items: [{ task_id: 'core-python-deduplicate', task_version: '1.0.0', task_digest: 'sha256:task', package_path: 'tasks/core-python-deduplicate/1.0.0', tier: 'TIER_A_MICRO_CONTRACT' }] })
  api.methodologies.mockResolvedValue({ items: [{ methodology_id: 'harnesslab-evaluation-methodology-v2', methodology_digest: 'sha256:methodology', active: true, evaluation_modes: ['QUICK', 'INFORMAL', 'FORMAL_EXHAUSTIVE'], repeat_counts: { QUICK: 1, INFORMAL: 3, FORMAL_EXHAUSTIVE: 5 }, scheduling_policy: 'BLOCKED_INTERLEAVED_SCHEDULING' }] })
  api.settings.mockResolvedValue({ defaults: { default_provider_profile_id: providerProfile.profile_id, default_evaluation_mode: 'QUICK', default_schedule_seed: 7, default_concurrency: 1, default_cost_budget: null }, credentials: [{ credential_ref: 'HARNESSLAB_ALIBABA_BAILIAN_API_KEY', status: 'MISSING' }], provider_enabled: { 'alibaba-bailian': true }, secret_editing_supported: false })
  api.capabilities.mockResolvedValue({ items: [{ provider_profile_id: providerProfile.profile_id, harness_profile_id: 'unsupported-harness', status: 'UNSUPPORTED', reason_codes: ['PROVIDER_MODEL_PROFILE_UNSUPPORTED_BY_HARNESS'], protocol_compatible: false, model_provider_compatible: false, observed_model: 'NOT_AVAILABLE', trace_coverage: 'NOT_AVAILABLE', native_tools: false, workspace_mutation: false, network_requirement: 'DENY', reasoning_control_supported: false, harness_uplift_eligible: false, judge_eligible: false }] })
  api.preflight.mockResolvedValue({ status: 'READY_WITH_WARNINGS', checks: [{ key: 'pricing', status: 'WARNING', reason_code: 'PRICING_NOT_AVAILABLE', detail: 'No immutable price evidence' }], estimated_logical_slots: 6, estimated_maximum_wall_time_seconds: 540, evaluation_mode: 'INFORMAL', repeat_count: 3, max_parallel_runs: 1, cost_estimate: { status: 'NOT_AVAILABLE', value: null, currency: 'USD', evidence_reference: null }, schedule_preview: [{ block_identity: 'sha256:block', task_id: 'core-python-deduplicate', repeat_index: 0, cell_execution_order: ['right', 'left'], provider_status: 'AVAILABLE' }], candidate_experiment_id: 'registry-id', candidate_plan_digest: 'sha256:plan' })
})

describe('Unified Registry Lite Workbench', () => {
  it('registers every Registry Lite route', () => {
    const paths = router.getRoutes().map((item) => item.path)
    expect(paths).toEqual(expect.arrayContaining(['/models', '/providers', '/harnesses', '/capabilities', '/settings', '/experiments/new', '/run-control']))
  })

  it('renders only safe Alibaba references and configured-model state', async () => {
    const wrapper = mount(ProvidersView)
    await flushPromises()
    expect(wrapper.text()).toContain('HARNESSLAB_ALIBABA_BAILIAN_API_KEY')
    expect(wrapper.text()).toContain('CONFIGURED_MODEL_ID_REQUIRED')
    expect(wrapper.text()).not.toContain('WorkspaceId')
    expect(wrapper.text()).not.toContain('sk-sentinel')
  })

  it('shows credential presence without browser secret editing', async () => {
    await router.push('/connections')
    const wrapper = mount(ConnectionsView, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('HARNESSLAB_ALIBABA_BAILIAN_API_KEY')
    expect(wrapper.find('[data-status="MISSING"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('当前网页不编辑 API Key 或服务端配置。')
  })

  it('renders fail-closed capability reason codes', async () => {
    const wrapper = mount(CapabilitiesView)
    await flushPromises()
    expect(wrapper.find('[data-status="UNSUPPORTED"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('PROVIDER_MODEL_PROFILE_UNSUPPORTED_BY_HARNESS')
    await wrapper.get('.compatibility-toggle').trigger('click')
    expect(wrapper.text()).toContain('PROVIDER_MODEL_PROFILE_UNSUPPORTED_BY_HARNESS')
    expect(wrapper.text()).toContain('NOT_SUPPORTED')
  })

  it('exposes provider-model identity and routing metadata without credential values', async () => {
    api.models.mockResolvedValueOnce({
      models: [{
        model_id: 'gpt-5.6-sol', display_name: 'GPT 5.6', model_family: 'gpt-5.6',
        capabilities: ['reasoning'], context_window_tokens: 128000, context_metadata_status: 'REPORTED',
        reasoning_controls: { effort: true, temperature: false, thinking_toggle: false },
        supported_protocols: ['responses'],
      }],
      provider_profiles: [providerProfile],
    })
    const wrapper = mount(ModelsView)
    await flushPromises()
    expect(wrapper.text()).toContain('gpt56-relay-gpt56-responses')
    expect(wrapper.text()).toContain('gpt56-relay|responses|env:HARNESSLAB_GPT56_RELAY_BASE_URL/responses')
    expect(wrapper.text()).toContain('RUN_EVIDENCE_ONLY')
    expect(wrapper.text()).toContain('sha256:profile')
    expect(wrapper.text()).not.toContain('sk-sentinel')
  })

  it('exposes Harness image, tools, network, observed-model surface, and supported profiles', async () => {
    const wrapper = mount(HarnessesView)
    await flushPromises()
    expect(wrapper.text()).not.toContain('codex-image')
    await wrapper.findAll('.resource-list button').find(item => item.text().includes('Codex'))!.trigger('click')
    const text = wrapper.text()
    expect(text).toContain('codex-image')
    expect(text).toContain('shell')
    expect(text).toContain('PROVIDER_ALLOWLIST')
    expect(text).toContain('RUN_EVIDENCE_ONLY')
    expect(text).toContain('gpt56-relay-gpt56-responses')
  })

  it('keeps repeat count backend-derived and previews blocked interleaving', async () => {
    const wrapper = mount(ExperimentBuilderView, { global: { plugins: [router] } })
    await flushPromises()
    await wrapper.get('[aria-label="评测模式"]').setValue('INFORMAL')
    expect((wrapper.get('[aria-label="重复策略"]').element as HTMLInputElement).value).toContain('n=3')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const request = api.preflight.mock.calls[0][0]
    expect(request.evaluation_mode).toBe('INFORMAL')
    expect(request).not.toHaveProperty('repeat_count')
    expect(request.budget.max_output_tokens.scopes).toEqual(['PER_PROVIDER_REQUEST', 'PER_LOGICAL_RUN'])
    expect(request.budget.max_model_turns).toMatchObject({ status: 'ENFORCED', value: 1 })
    expect(request.budget.max_tool_calls).toMatchObject({ status: 'ENFORCED', value: 0 })
    expect(request.budget.max_provider_requests).toMatchObject({ status: 'ENFORCED', value: 1 })
    expect(wrapper.text()).toContain('right → left')
    expect(wrapper.text()).toContain('PRICING_NOT_AVAILABLE')
    expect(wrapper.text()).toContain('不执行实验')
  })
})

it('invalidates a preflight and frozen snapshot when the form changes', async () => {
  const wrapper = mount(ExperimentBuilderView, { global: { plugins: [router] } }); await flushPromises()
  const preflightButton = () => wrapper.findAll('button').find(item => item.text() === '运行无密钥预检')!
  const snapshotButton = () => wrapper.findAll('button').find(item => item.text() === '保存计划')!
  await preflightButton().trigger('click'); await flushPromises()
  expect(snapshotButton().attributes('disabled')).toBeUndefined()
  await wrapper.get('[aria-label="实验名称"]').setValue('Changed plan')
  expect(snapshotButton().attributes('disabled')).toBeDefined()
  expect(wrapper.text()).not.toContain('PRICING_NOT_AVAILABLE')
  expect(api.snapshot).not.toHaveBeenCalled()
})

it('discards a preflight that finishes after a budget edit', async () => {
  let finish!: (value: unknown) => void
  api.preflight.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const wrapper = mount(ExperimentBuilderView, { global: { plugins: [router] } }); await flushPromises()
  await wrapper.findAll('button').find(item => item.text() === '运行无密钥预检')!.trigger('click')
  await wrapper.get('[aria-label="输出 Token 上限"]').setValue(999)
  finish({ status: 'READY', checks: [], schedule_preview: [], candidate_plan_digest: 'stale-plan' })
  await flushPromises()
  expect(wrapper.text()).not.toContain('stale-plan')
  expect(wrapper.findAll('button').find(item => item.text() === '保存计划')!.attributes('disabled')).toBeDefined()
})

it('keeps browser preferences independent of server configuration reads', async () => {
  localStorage.clear()
  const wrapper = mount(SettingsView); await flushPromises()
  expect(api.settings).not.toHaveBeenCalled()
  await wrapper.get('#text-size').setValue('large')
  expect(document.documentElement.dataset.textSize).toBe('large')
  expect(JSON.parse(localStorage.getItem('samescale.ui.preferences.v1')!).textSize).toBe('large')
  await wrapper.findAll('button').find(item => item.text() === '恢复默认显示')!.trigger('click')
  expect(document.documentElement.dataset.textSize).toBe('standard')
  expect(api.preflight).not.toHaveBeenCalled()
})


it('paginates compatibility and resets the page and disclosure after filtering', async () => {
  const item = (await api.capabilities()).items[0]
  api.capabilities.mockResolvedValueOnce({ items: Array.from({ length: 23 }, (_, index) => ({ ...item, provider_profile_id: `profile-${index}` })) })
  const wrapper = mount(CapabilitiesView); await flushPromises()
  expect(wrapper.findAll('.compatibility-toggle')).toHaveLength(10)
  await wrapper.findAll('button').find(item => item.text() === '下一页')!.trigger('click')
  expect(wrapper.findAll('.compatibility-toggle')[0]!.text()).toContain('profile-10')
  await wrapper.get('.compatibility-toggle').trigger('click')
  await wrapper.get('[aria-label="搜索兼容性"]').setValue('profile-22')
  expect(wrapper.findAll('.compatibility-toggle')).toHaveLength(1)
  expect(wrapper.get('.compatibility-toggle').attributes('aria-expanded')).toBe('false')
  expect(wrapper.get('.pagination').text()).toContain('1–1 / 1')
})

it('searches resources without leaving an unrelated detail visible', async () => {
  const wrapper = mount(HarnessesView); await flushPromises()
  await wrapper.get('[aria-label="搜索资源"]').setValue('codex')
  expect(wrapper.findAll('.resource-list button')).toHaveLength(1)
  expect(wrapper.get('.resource-detail').text()).toContain('codex-image')
  await wrapper.get('[aria-label="搜索资源"]').setValue('not-a-resource')
  expect(wrapper.get('.resource-detail').text()).not.toContain('codex-image')
})

it('persists interface language, updates mounted UI and preserves raw registry identities', async () => {
  localStorage.clear()
  const wrapper = mount(SettingsView); await flushPromises()
  await wrapper.get('#interface-language').setValue('en')
  expect(wrapper.text()).toContain('Interface language')
  expect(api.settings).not.toHaveBeenCalled()
  expect(document.documentElement.lang).toBe('en')
  expect(JSON.parse(localStorage.getItem('samescale.ui.preferences.v1')!).language).toBe('en')
  const other = mount(SettingsView); await flushPromises()
  expect(other.text()).toContain('Interface language')
  await other.get('#interface-language').setValue('zh-CN')
  expect(wrapper.text()).toContain('界面语言')
  localStorage.clear()
})


it('restores a valid comparison URL and invalidates preflight when the URL choice changes', async () => {
  await router.push('/experiments/new?comparison=MODEL_COMPARISON')
  const wrapper = mount(ExperimentBuilderView, { global: { plugins: [router] } }); await flushPromises()
  const comparison = () => (wrapper.get('[aria-label="对比类型"]').element as HTMLSelectElement).value
  expect(comparison()).toBe('MODEL_COMPARISON')
  await wrapper.findAll('button').find(item => item.text() === '运行无密钥预检')!.trigger('click'); await flushPromises()
  expect(api.preflight.mock.calls.at(-1)?.[0].comparison_type).toBe('MODEL_COMPARISON')
  await router.push('/experiments/new?comparison=HARNESS_UPLIFT'); await flushPromises()
  expect(comparison()).toBe('HARNESS_UPLIFT')
  expect(wrapper.findAll('button').find(item => item.text() === '保存计划')!.attributes('disabled')).toBeDefined()
  await router.push('/experiments/new?comparison=invalid'); await flushPromises()
  expect(comparison()).toBe('HARNESS_UPLIFT')
  expect(api.snapshot).not.toHaveBeenCalled()
})


it('shows server compatibility and its reasons beside each planning selection', async () => {
  const unsupported = (await api.capabilities()).items[0]
  api.capabilities.mockResolvedValue({ items: [
    { ...unsupported, harness_profile_id: directProfile.profile_id, status: 'PARTIALLY_SUPPORTED', reason_codes: ['TRACE_COVERAGE_LIMITED'] },
    { ...unsupported, harness_profile_id: codexProfile.profile_id },
  ] })
  const wrapper = mount(ExperimentBuilderView, { global: { plugins: [router] } }); await flushPromises()
  expect(wrapper.findAll('.planning-connection')[0]!.text()).toContain('轨迹覆盖有限')
  expect(wrapper.findAll('.planning-connection')[1]!.text()).toContain('此执行方式未声明支持该模型服务配置')
  expect(wrapper.findAll('.planning-connection')[1]!.find('[data-status="UNSUPPORTED"]').exists()).toBe(true)
  await wrapper.get('[aria-label="右侧执行方式"]').setValue(directProfile.profile_id)
  expect(wrapper.findAll('.planning-connection')[1]!.find('[data-status="PARTIALLY_SUPPORTED"]').exists()).toBe(true)
  expect(api.preflight).not.toHaveBeenCalled()
  expect(api.snapshot).not.toHaveBeenCalled()
})

it('keeps missing compatibility unknown and allows explicit authoritative preflight', async () => {
  api.capabilities.mockRejectedValue(new Error('offline'))
  const wrapper = mount(ExperimentBuilderView, { global: { plugins: [router] } }); await flushPromises()
  expect(wrapper.get('[role="status"]').text()).toContain('以服务端预检为准')
  expect(wrapper.findAll('.planning-connection > [data-status="NOT_VERIFIED"]')).toHaveLength(2)
  expect(api.preflight).not.toHaveBeenCalled()
  await wrapper.findAll('button').find(b => b.text() === '运行无密钥预检')!.trigger('click'); await flushPromises()
  expect(api.preflight).toHaveBeenCalledTimes(1)
  expect(api.snapshot).not.toHaveBeenCalled()
})

it('announces pending preflight and removes the unsubmitted prompt until success or failure', async () => {
  const wrapper = mount(ExperimentBuilderView, { global: { plugins: [router] } }); await flushPromises()
  let finish!: (value: unknown) => void
  api.preflight.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  await wrapper.findAll('button').find(b => b.text() === '运行无密钥预检')!.trigger('click')
  expect(wrapper.get('[role="status"]').text()).toContain('正在运行无密钥预检')
  expect(wrapper.text()).not.toContain('先运行预检')
  expect(wrapper.findAll('button').find(b => b.text() === '正在预检…')!.attributes('disabled')).toBeDefined()
  finish({ status: 'BLOCKED', checks: [], estimated_logical_slots: 2, cost_estimate: { status: 'NOT_AVAILABLE' }, schedule_preview: [] }); await flushPromises()
  expect(wrapper.text()).not.toContain('正在运行无密钥预检')
  expect(wrapper.findAll('button').find(b => b.text() === '保存计划')!.attributes('disabled')).toBeDefined()
  api.preflight.mockRejectedValueOnce(new Error('private failure'))
  await wrapper.findAll('button').find(b => b.text() === '运行无密钥预检')!.trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('预检失败'); expect(wrapper.text()).not.toContain('正在运行无密钥预检')
})

it('links a saved snapshot to a reloadable read-only entry', async () => {
  api.snapshot.mockResolvedValue({ snapshot_id: 'snapshot-test', snapshot_digest: 'sha256:saved' })
  const wrapper = mount(ExperimentBuilderView, { global: { plugins: [router] } }); await flushPromises()
  await wrapper.findAll('button').find(b => b.text() === '运行无密钥预检')!.trigger('click'); await flushPromises()
  await wrapper.findAll('button').find(b => b.text() === '保存计划')!.trigger('click'); await flushPromises()
  expect(wrapper.get('.snapshot-confirmation a').attributes('href')).toBe('/experiments?snapshot=snapshot-test#saved-plans')
})

it('translates the product footer after switching language and reconstructing settings', async () => {
  localStorage.clear()
  const wrapper = mount(SettingsView); await flushPromises()
  await wrapper.get('#interface-language').setValue('en')
  expect(wrapper.get('.settings-about').text()).toContain('Conclusions are limited to the available evidence.')
  wrapper.unmount()
  const again = mount(SettingsView); await flushPromises()
  expect(again.get('.settings-about').text()).not.toMatch(/[\u4e00-\u9fff]/)
})


it('invalidates failed snapshot preflight and requires a successful new preflight before saving again', async () => {
  preferences.language = 'zh-CN'
  await router.push('/experiments/new')
  const wrapper = mount(ExperimentBuilderView, { global: { plugins: [router] } }); await flushPromises()
  const preflightButton = () => wrapper.findAll('button').find(b => b.text() === '运行无密钥预检')!
  const saveButton = () => wrapper.findAll('button').find(b => b.text() === '保存计划')!
  await preflightButton().trigger('click'); await flushPromises()
  expect(saveButton().attributes('disabled')).toBeUndefined()
  expect(wrapper.text()).toContain('sha256:plan')
  api.snapshot.mockRejectedValueOnce(new Error('private-save-failure'))
  await saveButton().trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('快照未保存，请重新预检后重试。')
  expect(wrapper.text()).not.toContain('private-save-failure')
  expect(wrapper.text()).not.toContain('sha256:plan')
  expect(wrapper.find('.snapshot-confirmation').exists()).toBe(false)
  expect(saveButton().attributes('disabled')).toBeDefined()
  await saveButton().trigger('click'); expect(api.snapshot).toHaveBeenCalledTimes(1)
  api.preflight.mockRejectedValueOnce(new Error('preflight-unavailable'))
  await preflightButton().trigger('click'); await flushPromises()
  expect(saveButton().attributes('disabled')).toBeDefined()
  api.preflight.mockResolvedValueOnce({ status: 'BLOCKED', checks: [], schedule_preview: [], cost_estimate: { status: 'NOT_AVAILABLE' } })
  await preflightButton().trigger('click'); await flushPromises()
  expect(saveButton().attributes('disabled')).toBeDefined()
  let complete!: (value: unknown) => void
  const ready = await api.preflight.mock.results[0]!.value
  api.preflight.mockReturnValueOnce(new Promise(resolve => { complete = resolve }))
  await preflightButton().trigger('click')
  expect(saveButton().attributes('disabled')).toBeDefined()
  complete({ ...ready, candidate_plan_digest: 'sha256:renewed-plan' }); await flushPromises()
  expect(saveButton().attributes('disabled')).toBeUndefined()
  api.snapshot.mockResolvedValueOnce({ snapshot_id: 'snapshot-recovered', snapshot_digest: 'sha256:recovered' })
  await saveButton().trigger('click'); await flushPromises()
  expect(api.snapshot).toHaveBeenCalledTimes(2)
  expect(wrapper.get('.snapshot-confirmation').text()).toContain('snapshot-recovered')
})
