<script setup lang="ts">
import { statusLabel, metadataLabel } from '@/utils/statusLabels'
import PageState from '@/components/PageState.vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { registryApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type {
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
const tasks = ref<TaskRegistryItem[]>([])
const selectedTasks = ref<string[]>([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const preflight = ref<ExperimentPreflight | null>(null)
const snapshot = ref<ExperimentSnapshot | null>(null)
const form = reactive({ name: '费用受控评测', mode: 'QUICK' as EvaluationMode, comparison: 'HARNESS_UPLIFT' as ComparisonType, scheduleSeed: 20260828, concurrency: 1, wallTime: 90, outputTokens: 2000, leftProfile: '', leftHarness: '', rightProfile: '', rightHarness: '' })
const repeatCount = computed(() => methodology.value?.repeat_counts[form.mode] ?? statusLabel('UNKNOWN'))
const harnessProfiles = computed(() => harnesses.value.flatMap((item) => item.profiles))
const profileFor = (id: string) => profiles.value.find(p => p.profile_id === id)
const harnessProfileFor = (id: string) => harnessProfiles.value.find(p => p.profile_id === id)
const harnessFor = (id: string) => harnesses.value.find(h => h.profiles.some(p => p.profile_id === id))
const cells = computed(() => [
  { id: 'left', profile: form.leftProfile, harness: form.leftHarness },
  { id: 'right', profile: form.rightProfile, harness: form.rightHarness },
])
const includesDirect = computed(() => cells.value.some(c => harnessFor(c.harness)?.harness_id === 'direct-model'))
// Registry wire contract omits purpose when its value is SUBJECT, including local profiles.
const isSubject = (p: ProviderModelProfile) => p.purpose === undefined || p.purpose === 'SUBJECT'
const compatible = (profile: string, harness: string) => {
  const p = profileFor(profile); const h = harnessProfileFor(harness)
  return p?.enabled === true && isSubject(p) && h !== undefined && h.enabled !== false
    && h.supported_provider_profile_ids.includes(profile)
}
const formValid = computed(() => !loading.value && Boolean(methodology.value?.active && form.name.trim()
  && form.name.length <= 200 && selectedTasks.value.length && selectedTasks.value.length <= 18)
  && selectedTasks.value.every(id => tasks.value.some(t => t.task_id === id))
  && cells.value.every(c => compatible(c.profile, c.harness))
  && Number.isInteger(form.concurrency) && form.concurrency >= 1 && form.concurrency <= 64
  && Number.isInteger(form.scheduleSeed) && Number.isInteger(form.wallTime) && form.wallTime > 0
  && Number.isInteger(form.outputTokens) && form.outputTokens > 0
  && cells.value.every(c => profileFor(c.profile)?.max_output_tokens_limit == null
    || form.outputTokens <= profileFor(c.profile)!.max_output_tokens_limit!))
let generation = 0
let loadGeneration = 0
let alive = true
watch([form, selectedTasks], () => { generation++; preflight.value = null; snapshot.value = null }, { deep: true, flush: 'sync' })
async function load() {
  const current = ++loadGeneration; generation++
  loading.value = true; error.value = ''; preflight.value = null; snapshot.value = null
  profiles.value = []; harnesses.value = []; methodology.value = null; tasks.value = []
  try {
    const [modelData, harnessData, taskData, methodologyData, settingData] = await Promise.all([registryApi.models(), registryApi.harnesses(), registryApi.tasks(), registryApi.methodologies(), registryApi.settings()])
    if (!alive || current !== loadGeneration) return
    profiles.value = modelData.provider_profiles.filter(isSubject)
    harnesses.value = harnessData.items
    tasks.value = taskData.items
    methodology.value = methodologyData.items.find(item => item.active) ?? null
    form.mode = settingData.defaults.default_evaluation_mode
    form.scheduleSeed = settingData.defaults.default_schedule_seed
    form.concurrency = settingData.defaults.default_concurrency
    // Model, Harness and task choices are explicit. Never substitute another identity on reload.
  } catch { if (alive && current === loadGeneration) error.value = '实验规划配置暂时无法读取。请重新加载配置后重试。' }
  finally { if (alive && current === loadGeneration) loading.value = false }
}
onMounted(load)
onBeforeUnmount(() => { alive = false; generation++; loadGeneration++ })

function request(): ExperimentBuilderRequest {
  if (!methodology.value) throw new Error('暂无启用的评测方法')
  return {
    name: form.name, methodology_id: methodology.value.methodology_id, methodology_digest: methodology.value.methodology_digest, evaluation_mode: form.mode, comparison_type: form.comparison, task_ids: [...selectedTasks.value],
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
  const current = generation
  error.value = ''; preflight.value = null; snapshot.value = null; busy.value = true
  try { const result = await registryApi.preflight(request()); if (alive && current === generation) preflight.value = result }
  catch { if (alive && current === generation) error.value = '预检请求失败。请检查配置和后端服务后重试。' }
  finally { if (alive) busy.value = false }
}
async function freezeSnapshot() {
  if (busy.value || !formValid.value || !preflight.value || preflight.value.status === 'BLOCKED') return
  const current = generation
  error.value = ''; snapshot.value = null; busy.value = true
  try { const result = await registryApi.snapshot(request()); if (alive && current === generation) snapshot.value = result }
  catch { if (alive && current === generation) { preflight.value = null; error.value = '未能保存固定快照。请重新读取配置，再次预检。' } }
  finally { if (alive) busy.value = false }
}
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>实验规划</h2><p>由服务端验证实验计划。此处不会调用模型或创建运行。</p></div><StatusBadge :value="preflight?.status ?? 'NOT_REPORTED'" context="preflight" /></div>
    <div class="notice">已登记配置可以用于规划；执行还需凭据、可用运行环境和通过预检。执行前请查看 <RouterLink to="/providers">服务商运行环境</RouterLink> 。</div>
    <button class="secondary-button" :disabled="loading || busy" @click="load">重新读取规划配置</button>
    <PageState v-if="loading" kind="loading">正在读取规划配置…</PageState>
    <div v-else class="builder-layout">
      <div class="panel builder-form">
        <PageState v-if="error" kind="error">{{ error }}</PageState>
        <div class="form-grid">
          <label>实验名称<input v-model="form.name" aria-label="实验名称" maxlength="200"></label>
          <label>评测模式<select v-model="form.mode" aria-label="评测模式"><option value="QUICK">{{ statusLabel('QUICK') }}</option><option value="INFORMAL">{{ statusLabel('INFORMAL') }}</option><option value="FORMAL_EXHAUSTIVE">{{ statusLabel('FORMAL_EXHAUSTIVE') }}</option></select></label>
          <label>重复策略<input :value="`重复 ${repeatCount} 次（服务端固定）`" aria-label="重复策略" disabled></label>
          <label>对比类型<select v-model="form.comparison" aria-label="对比类型"><option value="END_TO_END_SYSTEM_COMPARISON">{{ statusLabel('END_TO_END_SYSTEM_COMPARISON') }}</option><option value="MODEL_COMPARISON">{{ statusLabel('MODEL_COMPARISON') }}</option><option value="HARNESS_UPLIFT">{{ statusLabel('HARNESS_UPLIFT') }}</option><option value="CONTROLLED_ABLATION">{{ statusLabel('CONTROLLED_ABLATION') }}</option></select></label>
          <label>调度随机种子<input v-model.number="form.scheduleSeed" type="number" aria-label="调度随机种子"></label>
          <label>最大并发运行数<input v-model.number="form.concurrency" type="number" min="1" max="64" aria-label="最大并发运行数"></label>
          <label>单次运行最长时间（秒）<input v-model.number="form.wallTime" type="number" min="1" aria-label="最长运行时间"></label>
          <label>最大输出 token 数<input v-model.number="form.outputTokens" type="number" min="1" aria-label="最大输出 token 数"></label>
        </div>
        <div class="builder-section"><h3>实验组合 · 明确选择被测模型</h3><div class="cell-grid">
          <div v-for="side in (['left', 'right'] as const)" :key="side" :data-cell="side">
            <strong>{{ side === 'left' ? '左侧' : '右侧' }}组合</strong>
            <label>服务商模型配置<select v-model="form[`${side}Profile`]" :aria-label="`${side === 'left' ? '左侧' : '右侧'}模型配置`">
              <option disabled value="">未配置 · 请选择被测模型</option>
              <option v-if="form[`${side}Profile`] && !profileFor(form[`${side}Profile`])" :value="form[`${side}Profile`]" disabled>不可用： {{ form[`${side}Profile`] }}</option>
              <option v-for="item in profiles" :key="item.profile_id" :value="item.profile_id" :disabled="!item.enabled">{{ item.profile_id }}{{ !item.enabled ? '（不可用）' : '' }}</option>
            </select></label>
            <label>Harness 配置<select v-model="form[`${side}Harness`]" :aria-label="`${side === 'left' ? '左侧' : '右侧'} Harness 配置`">
              <option disabled value="">未配置 · 请选择 Harness 版本</option>
              <option v-if="form[`${side}Harness`] && !harnessProfileFor(form[`${side}Harness`])" :value="form[`${side}Harness`]" disabled>不可用： {{ form[`${side}Harness`] }}</option>
              <option v-for="item in harnessProfiles" :key="item.profile_id" :value="item.profile_id" :disabled="!compatible(form[`${side}Profile`], item.profile_id)">{{ item.profile_id }} · {{ harnessFor(item.profile_id)?.version ?? statusLabel('UNKNOWN') }}</option>
            </select></label>
            <dl class="definition-list selection-details">
              <dt>模型用途</dt><dd>{{ metadataLabel(profileFor(form[`${side}Profile`]) ? 'SUBJECT' : 'UNKNOWN') }}</dd>
              <dt>模型配置 / 版本</dt><dd>{{ profileFor(form[`${side}Profile`])?.profile_id ?? statusLabel('NOT_CONFIGURED') }}</dd>
              <dt>配置身份</dt><dd>{{ profileFor(form[`${side}Profile`])?.profile_identity ?? statusLabel('UNKNOWN') }}</dd>
              <dt>请求模型 / 服务商</dt><dd>{{ profileFor(form[`${side}Profile`])?.requested_model ?? statusLabel('UNKNOWN') }} / {{ profileFor(form[`${side}Profile`])?.provider_id ?? statusLabel('UNKNOWN') }}</dd>
              <dt>Harness 配置 / 运行版本</dt><dd>{{ harnessProfileFor(form[`${side}Harness`])?.profile_id ?? statusLabel('NOT_CONFIGURED') }} / {{ harnessFor(form[`${side}Harness`])?.version ?? statusLabel('UNKNOWN') }}</dd>
              <dt>Harness 配置身份</dt><dd>{{ harnessProfileFor(form[`${side}Harness`])?.harness_config_identity ?? statusLabel('UNKNOWN') }}</dd>
              <dt>有效推理强度</dt><dd>{{ metadataLabel(harnessFor(form[`${side}Harness`])?.harness_id === 'direct-model' ? profileFor(form[`${side}Profile`])?.reasoning_effort : harnessProfileFor(form[`${side}Harness`])?.reasoning_effort ?? profileFor(form[`${side}Profile`])?.reasoning_effort) }}</dd>
              <dt>配置输出上限</dt><dd>{{ profileFor(form[`${side}Profile`])?.max_output_tokens_limit ?? statusLabel('NOT_CONFIGURED') }}</dd>
              <dt>请求超时（秒）</dt><dd>{{ profileFor(form[`${side}Profile`])?.request_timeout_seconds ?? statusLabel('UNKNOWN') }}</dd>
              <dt>运行环境状态</dt><dd><StatusBadge :value="harnessFor(form[`${side}Harness`])?.runtime_health ?? 'UNKNOWN'" /></dd>
            </dl>
            <p v-if="!compatible(form[`${side}Profile`], form[`${side}Harness`])" role="status">请选择可用被测模型及兼容的 Harness 版本。未知或过期选择不会自动替换。</p>
          </div>
        </div></div>
        <p v-if="cells.some(c => profileFor(c.profile)?.max_output_tokens_limit != null && form.outputTokens > profileFor(c.profile)!.max_output_tokens_limit!)" role="alert">输出预算超出所选模型配置上限。请调整预算或明确选择其他配置。</p>
        <p v-if="includesDirect" class="notice">直接调用约定：每次运行最多 1 次模型服务请求、1 个模型回合、0 次工具调用。输出限制同时约束单次请求与运行；服务端验证两个组合共用的预算。</p>
        <p v-else class="notice">暂无模型回合、工具调用与模型请求次数限制。输出 token 仅限制每次模型服务请求。</p>
        <p>暂无费用上限依据。配置与规划不代表凭据、连接或执行环境已核验。</p>
        <div class="builder-section"><h3>基础任务</h3><div class="task-picker"><label v-for="task in tasks" :key="task.task_id"><input v-model="selectedTasks" type="checkbox" :value="task.task_id">{{ task.task_id }}</label></div></div>
        <div class="toolbar"><button class="primary-button" :disabled="busy || !formValid" @click="runPreflight">运行无需密钥的预检</button><button class="secondary-button" :disabled="busy || !formValid || !preflight || preflight.status === 'BLOCKED'" @click="freezeSnapshot">保存固定快照</button></div>
      </div>
      <aside class="panel preview-panel">
        <div class="panel-title"><h3>规划预览</h3><span class="status-pill neutral">尚未执行</span></div>
        <PageState v-if="!preflight" kind="empty">选择任务、模型和 Harness 后运行预检，即可查看服务端调度预览。</PageState>
        <template v-else><dl class="definition-list"><dt>状态</dt><dd><StatusBadge :value="preflight.status" context="preflight" /></dd><dt>计划运行单元</dt><dd>{{ preflight.estimated_logical_slots }}</dd><dt>模式 / 重复次数</dt><dd>{{ statusLabel(preflight.evaluation_mode) }} / {{ preflight.repeat_count }}</dd><dt>最长运行时限</dt><dd>{{ preflight.estimated_maximum_wall_time_seconds ?? statusLabel('NOT_AVAILABLE') }} 秒</dd><dt>费用估算</dt><dd><StatusBadge :value="preflight.cost_estimate.status" /></dd><dt>计划摘要</dt><dd class="technical">{{ preflight.candidate_plan_digest }}</dd></dl><div class="check-list"><div v-for="check in preflight.checks" :key="`${check.key}:${check.reason_code}`" class="check-row"><StatusBadge :value="check.status" context="preflight" /><div><strong :title="check.reason_code">{{ statusLabel(check.reason_code) }}</strong><details><summary>查看原始检查说明</summary><p>{{ check.detail }}</p><code>{{ check.reason_code }}</code></details></div></div></div><div v-for="block in preflight.schedule_preview.slice(0, 3)" :key="block.block_identity" class="schedule-block"><strong>{{ block.task_id }} · 第 {{ block.repeat_index + 1 }} 次</strong><span class="technical">{{ block.cell_execution_order.map(side => side === 'left' ? '左侧' : side === 'right' ? '右侧' : side).join(' → ') }}</span></div></template>
        <div v-if="snapshot" class="snapshot-confirmation"><strong>固定快照已保存</strong><span class="technical">{{ snapshot.snapshot_id }}</span><span class="technical">{{ snapshot.snapshot_digest }}</span>
          <div v-for="selection in snapshot.provider_selections" :key="selection.cell_id" class="frozen-selection" :data-frozen-cell="selection.cell_id">
            <strong>{{ selection.cell_id }} · 已保存选择</strong>
            <div>{{ selection.provider_profile_id }} / {{ selection.harness_profile_id }}</div>
            <div>{{ selection.provider_profile_identity }}</div>
            <div>有效运行环境： {{ selection.effective_runtime_profile_identity ?? statusLabel('NOT_AVAILABLE') }}</div>
            <div>资源约束： {{ selection.resource_envelope_identity ?? statusLabel('NOT_AVAILABLE') }}</div>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
/* Keep exact configuration identities readable inside the existing planning layout. */
.selection-details dd, .preview-panel { overflow-wrap: anywhere; }
.check-row > div { min-width: 0; }
</style>
