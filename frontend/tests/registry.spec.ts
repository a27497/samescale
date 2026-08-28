import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import router from '@/router'
import CapabilitiesView from '@/views/CapabilitiesView.vue'
import ExperimentBuilderView from '@/views/ExperimentBuilderView.vue'
import ProvidersView from '@/views/ProvidersView.vue'
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
    expect(paths).toEqual(expect.arrayContaining(['/models', '/providers', '/harnesses', '/capabilities', '/settings', '/experiments/new']))
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
    const wrapper = mount(SettingsView)
    await flushPromises()
    expect(wrapper.text()).toContain('HARNESSLAB_ALIBABA_BAILIAN_API_KEY')
    expect(wrapper.text()).toContain('MISSING')
    expect(wrapper.text()).toContain('Secret editing is intentionally unavailable')
  })

  it('renders fail-closed capability reason codes', async () => {
    const wrapper = mount(CapabilitiesView)
    await flushPromises()
    expect(wrapper.text()).toContain('UNSUPPORTED')
    expect(wrapper.text()).toContain('PROVIDER_MODEL_PROFILE_UNSUPPORTED_BY_HARNESS')
  })

  it('keeps repeat count backend-derived and previews blocked interleaving', async () => {
    const wrapper = mount(ExperimentBuilderView)
    await flushPromises()
    await wrapper.get('[aria-label="Evaluation mode"]').setValue('INFORMAL')
    expect((wrapper.get('[aria-label="Repeat policy"]').element as HTMLInputElement).value).toContain('n=3')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const request = api.preflight.mock.calls[0][0]
    expect(request.evaluation_mode).toBe('INFORMAL')
    expect(request).not.toHaveProperty('repeat_count')
    expect(wrapper.text()).toContain('right → left')
    expect(wrapper.text()).toContain('PRICING_NOT_AVAILABLE')
    expect(wrapper.text()).toContain('NO EXECUTION')
  })
})
