<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { useRoute } from 'vue-router'
import { registryApi } from '@/api/client'
import ConnectionStates from '@/components/ConnectionStates.vue'
import { registryReason, runtimeProfileGroups } from '@/composables/registryPresentation'
import StatusBadge from '@/components/StatusBadge.vue'
import type {
  CapabilityAssessment, ProviderDefinition, RegistrySettings,
  ComparisonType,
  EvaluationMode,
  ExperimentBuilderRequest,
  ExperimentPreflight,
  ExperimentSnapshot,
  HarnessDefinition,
  MethodologyRegistryItem,
  ProviderModelProfile,
  TaskRegistryItem,
} from '@/types/registry'

const methodology = ref<MethodologyRegistryItem | null>(null)
const profiles = ref<ProviderModelProfile[]>([])
const harnesses = ref<HarnessDefinition[]>([])
const providers = ref<ProviderDefinition[]>([])
const capabilities = ref<CapabilityAssessment[]>([])
const settings = ref<RegistrySettings | null>(null)
const connectionError = ref(false)
// Retain identity for display only; availability always comes from the current catalog.
const selectedProfileIdentities = reactive<Record<string, string>>({})
const selectedHarnessIdentities = reactive<Record<string, string>>({})
let modelSelectionInitialized = false
const profileFor = (id: string) => profiles.value.find(p => p.profile_id === id)
const providerFor = (id: string) => providers.value.find(p => p.provider_id === profileFor(id)?.provider_id)
const harnessFor = (id: string) => harnesses.value.find(h => h.profiles.some(p => p.profile_id === id))
const capabilityFor = (profile: string, harness: string) => capabilities.value.find(c => c.provider_profile_id === profile && c.harness_profile_id === harness)
const tasks = ref<TaskRegistryItem[]>([])
const selectedTasks = ref<string[]>([])
const loading = ref(true)
const busy = ref(false)
const operation = ref<'preflight' | 'save' | null>(null)
const error = ref('')
const preflight = ref<ExperimentPreflight | null>(null)
const snapshot = ref<ExperimentSnapshot | null>(null)
const form = reactive({ name: t('工程能力评测'), mode: 'QUICK' as EvaluationMode, comparison: 'HARNESS_UPLIFT' as ComparisonType, scheduleSeed: 20260828, concurrency: 1, wallTime: 90, outputTokens: 2000, leftProfile: 'gpt56-relay-gpt56-responses', leftHarness: 'direct-gpt56-relay-gpt56-responses', rightProfile: 'gpt56-relay-gpt56-responses', rightHarness: 'codex-gpt56-medium' })
const repeatCount = computed(() => methodology.value?.repeat_counts[form.mode] ?? null)
const includesDirect = computed(() => harnesses.value.some(item => item.harness_id === 'direct-model'
  && item.profiles.some(profile => [form.leftHarness, form.rightHarness].includes(profile.profile_id))))
const harnessProfiles = computed(() => harnesses.value.flatMap((item) => item.profiles))
const harnessProfileFor = (id: string) => harnessProfiles.value.find(item => item.profile_id === id)
function harnessIssue(profileId: string, harnessId: string): string | null {
  const harness = harnessProfileFor(harnessId)
  if (!harness) return '执行方式已不可用，请显式选择有效配置。'
  // The Registry wire contract omits enabled when it is true.
  if (harness.enabled === false) return '执行方式已停用'
  if (!harness.supported_provider_profile_ids.includes(profileId)) return '执行方式与所选模型版本不兼容'
  return null
}

const route = useRoute()
watch(() => route.query.comparison, value => {
  if (value === 'MODEL_COMPARISON' || value === 'HARNESS_UPLIFT') form.comparison = value
}, { immediate: true })

async function load() {
  formGeneration++
  for (const id of [form.leftProfile, form.rightProfile]) {
    const identity = profileFor(id)?.profile_identity
    if (identity) selectedProfileIdentities[id] = identity
  }
  for (const id of [form.leftHarness, form.rightHarness]) {
    const identity = harnessProfileFor(id)?.harness_config_identity
    if (identity) selectedHarnessIdentities[id] = identity
  }
  loading.value = true; error.value = ''; preflight.value = null; snapshot.value = null
  profiles.value = []; harnesses.value = []; methodology.value = null; tasks.value = []; settings.value = null
  providers.value = []; capabilities.value = []; connectionError.value = false

  try {
    const [modelData, harnessData, taskData, methodologyData, settingData, connections] = await Promise.all([registryApi.models(), registryApi.harnesses(), registryApi.tasks(), registryApi.methodologies(), registryApi.settings(), Promise.allSettled([registryApi.providers(), registryApi.capabilities()])])
    settings.value = settingData
    if (connections[0].status === 'fulfilled') providers.value = connections[0].value.items; else connectionError.value = true
    if (connections[1].status === 'fulfilled') capabilities.value = connections[1].value.items; else connectionError.value = true
    profiles.value = modelData.provider_profiles.filter(p => !p.purpose || p.purpose === 'SUBJECT')
    harnesses.value = harnessData.items
    tasks.value = taskData.items
    methodology.value = methodologyData.items.find(item => item.active) ?? null
    form.mode = settingData.defaults.default_evaluation_mode
    form.scheduleSeed = settingData.defaults.default_schedule_seed
    form.concurrency = settingData.defaults.default_concurrency
    const defaultProfile = profiles.value.find(item => item.profile_id === settingData.defaults.default_provider_profile_id)?.profile_id ?? profiles.value[0]?.profile_id ?? ''
    if (!modelSelectionInitialized) {
      if (!profileFor(form.leftProfile)) form.leftProfile = defaultProfile
      if (!profileFor(form.rightProfile)) form.rightProfile = defaultProfile
      modelSelectionInitialized = true
    }
    // Keep the intended Harness identities, including on the first load. Never substitute an executor.
    selectedTasks.value = taskData.items.slice(0, 1).map((item) => item.task_id)
  } catch { error.value = '无法读取实验规划配置，请检查本地 API 后重试。' } finally { loading.value = false }
}
onMounted(load)

const outputTokenLimit = computed(() => {
  const limits = [form.leftProfile, form.rightProfile]
    .map(id => profileFor(id)?.max_output_tokens_limit)
    .filter((limit): limit is number => typeof limit === 'number')
  return limits.length ? Math.min(...limits) : null
})
const outputBudgetExceeded = computed(() => outputTokenLimit.value !== null && form.outputTokens > outputTokenLimit.value)
const formValid = computed(() => Boolean(methodology.value && form.name.trim() && form.name.length <= 200 && selectedTasks.value.length && selectedTasks.value.length <= 18 && profileFor(form.leftProfile) && profileFor(form.rightProfile) && !harnessIssue(form.leftProfile, form.leftHarness) && !harnessIssue(form.rightProfile, form.rightHarness))
  && Number.isInteger(form.concurrency) && form.concurrency >= 1 && form.concurrency <= 64
  && Number.isInteger(form.scheduleSeed) && Number.isInteger(form.wallTime) && form.wallTime > 0
  && Number.isInteger(form.outputTokens) && form.outputTokens > 0 && !outputBudgetExceeded.value)
let formGeneration = 0
watch([form, selectedTasks], () => { formGeneration++; preflight.value = null; snapshot.value = null }, { deep: true, flush: 'sync' })
function request(): ExperimentBuilderRequest {
  if (!methodology.value) throw new Error('Active methodology is unavailable')
  return {
    name: form.name, methodology_id: methodology.value.methodology_id, methodology_digest: methodology.value.methodology_digest, evaluation_mode: form.mode, comparison_type: form.comparison, task_ids: selectedTasks.value,
    cells: [
      { cell_id: 'left', provider_model_profile_id: form.leftProfile, harness_profile_id: form.leftHarness },
      { cell_id: 'right', provider_model_profile_id: form.rightProfile, harness_profile_id: form.rightHarness },
    ],
    budget: {
      max_wall_time: { status: 'ENFORCED', value: form.wallTime, unit: 'seconds', scopes: ['PER_LOGICAL_RUN'] }, max_output_tokens: { status: 'ENFORCED', value: form.outputTokens, unit: 'tokens', scopes: includesDirect.value ? ['PER_PROVIDER_REQUEST', 'PER_LOGICAL_RUN'] : ['PER_PROVIDER_REQUEST'] },
      max_model_turns: includesDirect.value ? { status: 'ENFORCED', value: 1, unit: 'turns', scopes: ['PER_LOGICAL_RUN'] } : { status: 'NOT_AVAILABLE', value: null, unit: 'turns', scopes: ['NOT_AVAILABLE'] }, max_tool_calls: includesDirect.value ? { status: 'ENFORCED', value: 0, unit: 'calls', scopes: ['PER_LOGICAL_RUN'] } : { status: 'NOT_AVAILABLE', value: null, unit: 'calls', scopes: ['NOT_AVAILABLE'] }, max_provider_requests: includesDirect.value ? { status: 'ENFORCED', value: 1, unit: 'requests', scopes: ['PER_LOGICAL_RUN'] } : { status: 'NOT_AVAILABLE', value: null, unit: 'requests', scopes: ['NOT_AVAILABLE'] }, max_cost: { status: 'NOT_AVAILABLE', value: null, unit: 'USD', scopes: ['NOT_AVAILABLE'] },
    },
    schedule_seed: form.scheduleSeed, max_parallel_runs: form.concurrency, billing_modes: {},
  }
}

async function runPreflight() {
  if (busy.value || !formValid.value) return
  const generation = formGeneration
  error.value = ''; preflight.value = null; snapshot.value = null; busy.value = true; operation.value = 'preflight'
  try { const result = await registryApi.preflight(request()); if (generation === formGeneration) preflight.value = result }
  catch { if (generation === formGeneration) error.value = '预检失败，请检查输入与本地服务后重试。' }
  finally { busy.value = false; operation.value = null }
}
async function freezeSnapshot() {
  if (busy.value || !formValid.value || !preflight.value || preflight.value.status === 'BLOCKED') return
  const generation = formGeneration
  error.value = ''; snapshot.value = null; busy.value = true; operation.value = 'save'
  try { const result = await registryApi.snapshot(request()); if (generation === formGeneration) snapshot.value = result }
  catch {
    if (generation === formGeneration) {
      preflight.value = null
      error.value = '快照未保存，请重新预检后重试。'
    }
  }
  finally { busy.value = false; operation.value = null }
}
</script>

<template>
  <section>
    <RouterLink class="table-link" to="/experiments#saved-plans">{{ t('查看已保存计划') }}</RouterLink>
    <div class="page-heading"><div><h2>{{ t('创建评测计划') }}</h2><p>{{ t('选择任务和运行配置。保存计划不会执行评测。') }}</p></div><StatusBadge :value="preflight?.status ?? 'NOT_REPORTED'" /></div>
    <button v-if="error && !loading" class="secondary-button retry-button" @click="load">{{ t('重新加载') }}</button>
    <div v-if="loading" class="loading-state">{{ t('正在读取规划配置…') }}</div>
    <div v-else class="builder-layout">
      <div class="panel builder-form">
        <div v-if="error" class="error-state">{{ t(error) }}</div>
        <div class="form-grid">
          <label>{{ t('实验名称') }}<input v-model="form.name" :aria-label="t('实验名称')" maxlength="200"></label>
          <label>{{ t('评测模式') }}<select v-model="form.mode" :aria-label="t('评测模式')"><option value="QUICK">{{ t('快速') }}</option><option value="INFORMAL">{{ t('非正式') }}</option><option value="FORMAL_EXHAUSTIVE">{{ t('正式穷举') }}</option></select></label>
          <label>{{ t('重复策略') }}<input :value="repeatCount === null ? 'UNKNOWN' : `n=${repeatCount} (服务端固定)`" :aria-label="t('重复策略')" disabled></label>
          <label>{{ t('对比类型') }}<select v-model="form.comparison" :aria-label="t('对比类型')"><option value="END_TO_END_SYSTEM_COMPARISON">{{ t('比较系统') }}</option><option value="MODEL_COMPARISON">{{ t('比较模型') }}</option><option value="HARNESS_UPLIFT">{{ t('直接调用 vs Agent') }}</option><option value="CONTROLLED_ABLATION">{{ t('受控消融') }}</option></select></label>
          <label>{{ t('调度种子') }}<input v-model.number="form.scheduleSeed" type="number" :aria-label="t('调度种子')"></label>
          <label>{{ t('并行运行上限') }}<input v-model.number="form.concurrency" type="number" min="1" max="64" :aria-label="t('并行运行上限')"></label>
          <label>{{ t('单次运行时限（秒）') }}<input v-model.number="form.wallTime" type="number" min="1" :aria-label="t('单次运行时限')"></label>
          <label>{{ t('输出 Token 上限') }}<input v-model.number="form.outputTokens" type="number" min="1" :aria-invalid="outputBudgetExceeded" :aria-describedby="outputBudgetExceeded ? 'output-budget-error' : undefined" :aria-label="t('输出 Token 上限')"></label>
        </div>
        <p v-if="outputBudgetExceeded" id="output-budget-error" class="error-state" role="alert">{{ t('输出预算超出所选配置上限：') }} {{ outputTokenLimit }} tokens</p>
        <div class="builder-section"><h3>{{ t('实验单元') }}</h3><div class="cell-grid"><div><strong>{{ t('左侧实验条件') }}</strong><label>{{ t('模型服务配置') }}<select v-model="form.leftProfile" :aria-label="t('左侧模型服务配置')"><option v-if="form.leftProfile && !profileFor(form.leftProfile)" :value="form.leftProfile" disabled>{{ t('已不可用') }}: {{ form.leftProfile }}</option><option v-for="item in profiles" :key="item.profile_id" :value="item.profile_id">{{ item.profile_id }}</option></select></label><label>{{ t('执行方式') }}<select v-model="form.leftHarness" :aria-label="t('左侧执行方式')"><option v-if="!harnessProfileFor(form.leftHarness)" :value="form.leftHarness" disabled>{{ t('已不可用') }}: {{ form.leftHarness }}</option><optgroup v-for="group in runtimeProfileGroups(harnesses)" :key="group.label" :label="t(group.label)"><option v-for="item in group.profiles" :key="item.profile_id" :value="item.profile_id">{{ item.profile_id }}{{ harnessIssue(form.leftProfile, item.profile_id) ? ' · ' + t(harnessIssue(form.leftProfile, item.profile_id)) : '' }}</option></optgroup></select></label></div><div><strong>{{ t('右侧实验条件') }}</strong><label>{{ t('模型服务配置') }}<select v-model="form.rightProfile" :aria-label="t('右侧模型服务配置')"><option v-if="form.rightProfile && !profileFor(form.rightProfile)" :value="form.rightProfile" disabled>{{ t('已不可用') }}: {{ form.rightProfile }}</option><option v-for="item in profiles" :key="item.profile_id" :value="item.profile_id">{{ item.profile_id }}</option></select></label><label>{{ t('执行方式') }}<select v-model="form.rightHarness" :aria-label="t('右侧执行方式')"><option v-if="!harnessProfileFor(form.rightHarness)" :value="form.rightHarness" disabled>{{ t('已不可用') }}: {{ form.rightHarness }}</option><optgroup v-for="group in runtimeProfileGroups(harnesses)" :key="group.label" :label="t(group.label)"><option v-for="item in group.profiles" :key="item.profile_id" :value="item.profile_id">{{ item.profile_id }}{{ harnessIssue(form.rightProfile, item.profile_id) ? ' · ' + t(harnessIssue(form.rightProfile, item.profile_id)) : '' }}</option></optgroup></select></label></div></div></div>
        <p v-if="connectionError" class="notice" role="status">{{ t('连接或兼容性信息未完整读取；以服务端预检为准。') }}</p>
        <div class="cell-grid planning-connections">
          <section v-for="cell in [{ name: '左侧实验条件', profile: form.leftProfile, harness: form.leftHarness }, { name: '右侧实验条件', profile: form.rightProfile, harness: form.rightHarness }]" :key="cell.name" class="planning-connection">
            <h4>{{ t(cell.name) }} · {{ t('组合兼容') }}</h4>
            <p v-if="cell.profile && !profileFor(cell.profile)" role="alert">{{ t('已选模型版本不可用，请显式选择有效版本后重新预检。') }} <code>{{ cell.profile }}</code><code>{{ selectedProfileIdentities[cell.profile] ?? 'NOT_REPORTED' }}</code></p>
            <p v-if="harnessIssue(cell.profile, cell.harness)" class="harness-eligibility" role="alert">{{ t(harnessIssue(cell.profile, cell.harness)) }}<code>{{ cell.harness }}</code><code>{{ harnessProfileFor(cell.harness)?.harness_config_identity ?? selectedHarnessIdentities[cell.harness] ?? 'NOT_REPORTED' }}</code></p>
            <StatusBadge :value="capabilityFor(cell.profile, cell.harness)?.status ?? 'NOT_VERIFIED'" />
            <ul v-if="capabilityFor(cell.profile, cell.harness)?.reason_codes.length"><li v-for="code in capabilityFor(cell.profile, cell.harness)?.reason_codes" :key="code">{{ t(registryReason(code)) }} <code>{{ code }}</code></li></ul>
            <p v-else-if="!capabilityFor(cell.profile, cell.harness)">{{ t('缺少此组合的兼容性结果。') }}</p>
            <details class="resource-disclosure"><summary>{{ t('凭据、连接与授权') }}</summary><ConnectionStates :profile="profileFor(cell.profile)" :provider="providerFor(cell.profile)" :harness="harnessFor(cell.harness)" :settings="settings" :capability="capabilityFor(cell.profile, cell.harness)" /><RouterLink class="table-link" :to="{ path: '/connections', query: { profile: cell.profile, harness: cell.harness } }">{{ t('连接总览') }}</RouterLink></details>
          </section>
        </div>
        <p v-if="includesDirect" class="notice">{{ t('直接调用每次运行限 1 次模型请求、1 轮决策、0 次工具调用；输出受请求和运行上限约束。此处只规划预算，适用条件由服务端预检确认。') }}</p>
        <div class="builder-section"><h3>{{ t('Tier-A 任务') }}</h3><div class="task-picker"><label v-for="task in tasks" :key="task.task_id"><input v-model="selectedTasks" type="checkbox" :value="task.task_id">{{ task.task_id }}</label></div></div>
        <div class="toolbar"><button class="primary-button" :disabled="busy || !formValid" @click="runPreflight">{{ t(operation === 'preflight' ? '正在预检…' : '运行无密钥预检') }}</button><button class="secondary-button" :disabled="busy || !formValid || !preflight || preflight.status === 'BLOCKED'" @click="freezeSnapshot">{{ t('保存计划') }}</button></div>
      </div>
      <aside class="panel preview-panel">
        <div class="panel-title"><h3>{{ t('规划预览') }}</h3><span class="status-pill neutral">{{ t('不执行实验') }}</span></div>
        <p v-if="busy" role="status" aria-live="polite">{{ t(operation === 'preflight' ? '正在运行无密钥预检，请等待结果。不会执行评测。' : '正在保存计划，请等待确认。不会执行评测。') }}</p>
        <div v-else-if="!preflight" class="empty-state">{{ t('先运行预检，查看服务端生成的调度与检查结果。') }}</div>
        <template v-if="preflight"><dl class="definition-list"><dt>{{ t('状态') }}</dt><dd><StatusBadge :value="preflight.status" /></dd><dt>{{ t('逻辑槽位') }}</dt><dd>{{ preflight.estimated_logical_slots }}</dd><dt>{{ t('模式 / 重复次数') }}</dt><dd>{{ preflight.evaluation_mode }} / {{ preflight.repeat_count }}</dd><dt>{{ t('最长运行时间上界') }}</dt><dd>{{ preflight.estimated_maximum_wall_time_seconds ?? 'NOT_AVAILABLE' }} {{ t('秒') }}</dd><dt>{{ t('费用估算') }}</dt><dd>{{ preflight.cost_estimate.status }}</dd><dt>{{ t('计划摘要') }}</dt><dd class="technical">{{ preflight.candidate_plan_digest }}</dd></dl><div class="check-list"><div v-for="check in preflight.checks" :key="`${check.key}:${check.reason_code}`" class="check-row"><StatusBadge :value="check.status" /><div><strong class="technical">{{ check.reason_code }}</strong><small>{{ check.detail }}</small></div></div></div><div v-for="block in preflight.schedule_preview.slice(0, 3)" :key="block.block_identity" class="schedule-block"><strong>{{ block.task_id }} / repeat={{ block.repeat_index }}</strong><span class="technical">{{ block.cell_execution_order.join(' → ') }}</span></div></template>
        <div v-if="snapshot" class="snapshot-confirmation"><strong>{{ t('不可变快照已保存') }}</strong><span class="technical">{{ snapshot.snapshot_id }}</span><span class="technical">{{ snapshot.snapshot_digest }}</span><RouterLink class="table-link" :to="{ path: '/experiments', query: { snapshot: snapshot.snapshot_id }, hash: '#saved-plans' }">{{ t('查看已保存计划') }}</RouterLink></div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.planning-connections { margin-top:16px; }.planning-connection { min-width:0; border-top:1px solid var(--line); padding-top:12px; }
.planning-connection h4 { font:var(--type-caption); margin:0 0 10px; }.planning-connection ul { padding-left:18px; }
.planning-connection li, .planning-connection p { font:var(--type-caption); color:var(--muted); overflow-wrap:anywhere; }
.planning-connection code { display:block; font-size:11px; overflow-wrap:anywhere; margin:4px 0 10px; }
.planning-connection :deep(.connection-states) { grid-template-columns:1fr; }
</style>
