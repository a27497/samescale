<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { localPlansApi } from '@/api/localPlans'
import type { CodexConfiguration, PlanDetail, PlanRequest, PlanSummary, PreflightReceipt, TaskInspection } from '@/api/localPlans'
import { copy as c } from '@/composables/visualLocale'
import TechnicalDetails from '@/components/TechnicalDetails.vue'

const route = useRoute(), router = useRouter()
const enabled = ref<boolean | null>(null), token = ref(''), unlocked = ref(false), busy = ref(false)
const error = ref(''), tasks = ref<TaskInspection[]>([]), configurations = ref<CodexConfiguration[]>([])
const source = ref(''), sources = ref<{ root_id: string; relative_path: string }[]>([])
const taskReference = ref(''), configurationIndex = ref(''), name = ref('')
const wallTime = ref(90), outputTokens = ref(1000), costBudget = ref(1)
const receipt = ref<PreflightReceipt | null>(null), confirmed = ref(false), detail = ref<PlanDetail | null>(null)
const plans = ref<PlanSummary[]>([]), total = ref(0), offset = ref(0), requestKey = ref('')
let revision = 0, alive = true, loadGeneration = 0
const selectedTask = computed(() => tasks.value.find(t => t.reference === taskReference.value))
const selectedConfiguration = computed(() => configurations.value[Number(configurationIndex.value)])
const canPreflight = computed(() => unlocked.value && !!selectedTask.value && !!configurationIndex.value && name.value.trim() && [wallTime.value, outputTokens.value, costBudget.value].every(n => Number.isFinite(n) && n > 0))
const checkLabels: Record<string, [string, string]> = {
  TASK_INTEGRITY_AND_SOURCE: ['任务与来源完整性', 'Task and source integrity'],
  TRUSTED_PRIOR_QUALIFICATION: ['可信历史行为验收与准入', 'Trusted prior validation and admission'],
  ONE_CODEX_SUBJECT_CONFIGURATION: ['单 Codex 主体配置', 'One Codex subject configuration'],
  MODEL_HARNESS_COMPATIBLE: ['模型与 Harness 兼容性', 'Model and Harness compatibility'],
  CREDENTIAL_REFERENCE_PRESENT: ['本地凭据引用已配置', 'Local credential reference configured'],
  PROVIDER_ROUTE_VALID: ['Provider 路由配置有效', 'Provider route configuration valid'],
  PROVIDER_NOT_KNOWN_BLOCKED: ['无已知服务阻塞', 'No known service block'],
  PINNED_LOCAL_IMAGE_PRESENT: ['固定版本本地镜像存在', 'Pinned local image exists'],
  LOCAL_RUNTIME_IMAGE_APPROVED: ['本地运行镜像身份经操作员准入', 'Local runtime image identity approved by operator'],
  EXPLICIT_BUDGET_REQUIRED: ['已填写计划预算', 'Planning budget provided'],
  TASK_WALL_TIME_LIMIT: ['时间限制符合任务契约', 'Wall time fits task contract'],
  OUTPUT_ESTIMATE_WITHIN_PROFILE: ['输出估计符合配置范围', 'Output estimate fits profile'],
}
const reasonLabels: Record<string, [string, string]> = {
  TRUSTED_PRIOR_QUALIFICATION_REQUIRED: ['缺少可信历史行为验收与准入记录', 'Trusted prior admission evidence is missing'],
  TRUSTED_PRIOR_QUALIFICATION_INVALID: ['准入记录与任务身份不一致或无效', 'Admission evidence is invalid or has drifted'],
  HARNESS_LANE_REQUIRED: ['该任务不支持 Harness 工作区', 'Task does not support the Harness lane'],
  PREFLIGHT_STALE: ['任务、配置、运行版本或准入已变化，请重新预检', 'Task, configuration, runtime or admission changed; preflight again'],
  PREFLIGHT_EXPIRED: ['预检已过期，请重新预检', 'Preflight expired; preflight again'],
  TASK_SOURCE_DRIFT: ['源任务已变化，旧预检已失效', 'Source task changed; previous preflight is stale'],
  PHASE1_EXECUTION_DISABLED: ['本阶段执行入口关闭', 'Execution is disabled in this phase'],
  LOCAL_OPERATOR_REQUIRED: ['请检查本地操作员凭据', 'Check the local operator credential'],
  LOCAL_TASK_POLICY_INVALID: ['本地任务准入配置缺失或无效', 'Trusted local task policy is missing or invalid'],
}
function label(code: string) { const pair = checkLabels[code] ?? reasonLabels[code]; return pair ? c(...pair) : code }
function reportError(e: unknown) {
  const response = (e as { response?: { data?: { error?: { code?: string; message?: string } } } }).response
  const code = response?.data?.error?.code
  error.value = code ? label(code) : c('信息读取失败，请重试。', 'Could not load information. Retry.')
}
function invalidate() { revision++; receipt.value = null; confirmed.value = false; requestKey.value = '' }
watch([taskReference, configurationIndex, name, wallTime, outputTokens, costBudget, token], invalidate)
watch(token, () => { unlocked.value = false; busy.value = false; detail.value = null; plans.value = []; tasks.value = []; configurations.value = []; sources.value = []; loadGeneration++ })
async function loadPlans() { const current = loadGeneration; const data = await localPlansApi.plans(token.value, offset.value); if (alive && current === loadGeneration) { plans.value = data.items; total.value = data.total } }
async function loadDetail() {
  if (!route.params.planId) { detail.value = null; return }
  const current = loadGeneration, id = String(route.params.planId)
  const data = await localPlansApi.plan(id, token.value)
  if (alive && current === loadGeneration && id === String(route.params.planId)) detail.value = data
}
async function unlock() {
  const current = ++loadGeneration, operator = token.value
  busy.value = true; error.value = ''
  try {
    // Authenticate using the persisted plan index first, so task drift cannot hide saved plans.
    await loadPlans()
    const data = await Promise.allSettled([localPlansApi.sources(operator), localPlansApi.configurations(operator), localPlansApi.tasks(operator)])
    if (!alive || current !== loadGeneration) return
    if (data[0].status === 'fulfilled') sources.value = data[0].value.candidates
    if (data[1].status === 'fulfilled') configurations.value = data[1].value.items
    if (data[2].status === 'fulfilled') tasks.value = data[2].value.items
    for (const result of data) if (result.status === 'rejected') reportError(result.reason)
    unlocked.value = true
    await loadDetail()
  } catch (e) { if (alive && current === loadGeneration) reportError(e) }
  finally { if (alive && current === loadGeneration) busy.value = false }
}
async function importSource() {
  const selected = sources.value[Number(source.value)]; if (!selected || !source.value) return
  busy.value = true; error.value = ''; invalidate()
  try {
    const item = await localPlansApi.importTask(selected.root_id, selected.relative_path, token.value)
    tasks.value = [...tasks.value.filter(t => t.reference !== item.reference), item]; taskReference.value = item.reference
  } catch (e) { reportError(e) } finally { busy.value = false }
}
async function inspectSelected() {
  if (!taskReference.value) return
  busy.value = true; error.value = ''; invalidate()
  try { const item = await localPlansApi.inspect(taskReference.value, token.value); tasks.value = tasks.value.map(t => t.reference === item.reference ? item : t) }
  catch (e) { reportError(e) } finally { busy.value = false }
}
async function preflight() {
  const config = selectedConfiguration.value; if (!config || !canPreflight.value) return
  busy.value = true; error.value = ''; invalidate(); const current = revision
  const payload: PlanRequest = { name: name.value, task_reference: taskReference.value, provider_profile_id: config.provider_profile_id, harness_profile_id: config.harness_profile_id, budget: { wall_time_seconds: wallTime.value, output_tokens_estimate: outputTokens.value, cost_budget_usd: costBudget.value } }
  try { const data = await localPlansApi.preflight(payload, token.value); if (alive && current === revision) { receipt.value = data; requestKey.value = crypto.randomUUID() } }
  catch (e) { reportError(e) } finally { busy.value = false }
}
async function save() {
  if (!receipt.value || receipt.value.status !== 'READY_TO_SAVE' || !confirmed.value || busy.value) return
  busy.value = true; error.value = ''
  try { const plan = await localPlansApi.save(receipt.value, requestKey.value, token.value); offset.value = 0; await router.push(`/plans/${plan.plan_id}`); await Promise.all([loadPlans(), loadDetail()]); invalidate() }
  catch (e) {
    const code = (e as { response?: { data?: { error?: { code?: string } } } }).response?.data?.error?.code
    if (['PREFLIGHT_STALE', 'PREFLIGHT_EXPIRED', 'PREFLIGHT_INTEGRITY_ERROR', 'IDEMPOTENCY_CONFLICT'].includes(code ?? '')) invalidate()
    confirmed.value = false; reportError(e)
  } finally { busy.value = false }
}
async function page(delta: number) { offset.value += delta; try { await loadPlans() } catch (e) { reportError(e) } }
watch(() => route.params.planId, () => { if (unlocked.value) loadDetail().catch(reportError) })
onMounted(async () => { try { enabled.value = (await localPlansApi.status()).enabled } catch (e) { reportError(e); enabled.value = false } })
onBeforeUnmount(() => { alive = false; loadGeneration++; token.value = '' })
</script>

<template>
  <section class="local-plans-page">
    <div class="page-heading"><div><h2>{{ c('本地评测计划', 'Local evaluation plans') }}</h2><p>{{ c('可信任务 → 单 Codex 配置 → 预检 → 确认保存', 'Trusted task → one Codex configuration → preflight → confirm and save') }}</p></div><RouterLink class="secondary-button" to="/plans">{{ c('创建计划', 'New plan') }}</RouterLink></div>
    <p class="plan-boundary">{{ c('本阶段仅保存一次尝试的计划。不会创建 Run/Episode；确认计划不授权付费执行。', 'This phase saves one planned attempt. It creates no Run/Episode; confirmation does not authorize paid execution.') }}</p>
    <p v-if="error" class="error-state" role="alert">{{ error }}</p>
    <p v-if="enabled === null" class="loading-state" role="status">{{ c('正在检查本地工作区…', 'Checking the local workspace…') }}</p>
    <div v-else-if="!enabled" class="panel"><h3>{{ c('本地计划功能未启用', 'Local planning is not enabled') }}</h3><p>{{ c('请在私有本地工作区配置操作员权限、可信任务根目录和独立准入记录。公开 Demo 不支持此操作。', 'Configure operator access, trusted task roots and separate admission evidence in a private local workspace. Public Demo does not support this workflow.') }}</p><RouterLink to="/connections">{{ c('查看连接与配置', 'Connections and configuration') }}</RouterLink></div>
    <form v-else-if="!unlocked" class="panel builder-form" @submit.prevent="unlock"><h3>{{ c('解锁本地工作区', 'Unlock the local workspace') }}</h3><label>{{ c('本地操作员凭据', 'Local operator credential') }}<input v-model="token" data-test="operator" type="password" autocomplete="off" required /></label><p>{{ c('凭据只用于当前页面，不写入浏览器存储。刷新后可重新解锁并读取已保存计划。', 'The credential stays on this page and is not stored. After refreshing, unlock again to read saved plans.') }}</p><button class="primary-button" :disabled="busy || !token">{{ busy ? c('正在读取…', 'Loading…') : c('解锁并读取', 'Unlock and load') }}</button></form>
    <template v-else>
      <div v-if="detail" class="panel" data-test="saved-plan">
        <div class="panel-title"><h3>{{ detail.plan.preflight.material?.request.name }}</h3><strong>{{ c('已保存 · 未授权执行', 'Saved · execution not authorized') }}</strong></div>
        <p>{{ detail.plan.preflight.material?.task.reference }} · {{ detail.plan.preflight.material?.configuration.model.requested_model }} · Codex {{ detail.plan.preflight.material?.configuration.harness.version }}</p>
        <p data-test="current-status">{{ detail.current_status === 'STALE' ? c('任务或配置已变化。原计划保留，但须重新预检。', 'Task or configuration changed. The original plan remains; preflight again.') : c('当前身份未变；未来执行仍须重新预检和单独授权。', 'Current identities are unchanged; future execution still needs preflight and separate authorization.') }}</p>
        <p>{{ c('一次计划尝试 · 0 Run · 0 Episode · 执行入口关闭', 'One planned attempt · 0 Run · 0 Episode · execution disabled') }}</p>
        <button class="secondary-button" disabled>{{ c('执行暂未开放', 'Execution unavailable') }}</button>
        <TechnicalDetails :summary="c('计划身份与原始配置', 'Plan identity and original configuration')" :fields="[{ label: 'Plan ID', value: detail.plan.plan_id }, { label: 'Plan SHA', value: detail.plan.plan_digest }]"><pre>{{ JSON.stringify(detail.plan, null, 2) }}</pre></TechnicalDetails>
      </div>
      <form class="panel builder-form" @submit.prevent="preflight">
        <h3>{{ c('1. 选择与检查可信本地任务', '1. Select and inspect a trusted local task') }}</h3>
        <div class="form-grid"><label>{{ c('可导入任务包', 'Local package to import') }}<select v-model="source" data-test="source"><option value="">{{ c('选择可信根目录中的任务', 'Choose a task under a trusted root') }}</option><option v-for="(item, i) in sources" :key="`${item.root_id}/${item.relative_path}`" :value="String(i)">{{ item.root_id }} / {{ item.relative_path }}</option></select></label><div class="plan-action"><button class="secondary-button" type="button" data-test="import" :disabled="busy || !source" @click="importSource">{{ c('导入并检查', 'Import and inspect') }}</button></div></div>
        <div class="form-grid"><label>{{ c('已接入任务', 'Managed task') }}<select v-model="taskReference" data-test="task"><option value="">{{ c('选择任务', 'Choose a task') }}</option><option v-for="task in tasks" :key="task.reference" :value="task.reference">{{ task.reference }} · {{ task.task_category }}</option></select></label><div class="plan-action"><button type="button" class="secondary-button" :disabled="busy || !taskReference" @click="inspectSelected">{{ c('重新检查任务', 'Reinspect task') }}</button></div></div>
        <div v-if="selectedTask" class="task-admission" data-test="task-inspection"><strong>{{ selectedTask.eligible_for_planning ? c('可用于创建计划', 'Eligible for planning') : c('准入阻塞', 'Admission blocked') }}</strong><p>{{ c('结构与摘要检查通过；本轮未执行 Verifier。', 'Structure and digests checked; no Verifier executed in this phase.') }} {{ selectedTask.behavioral_validation === 'TRUSTED_PRIOR_RESULT' ? c('已绑定操作员信任的历史行为验收；摘要不认证来源。', 'Bound to operator-trusted prior validation; digests do not attest origin.') : c('行为验收未核验，结构检查不能替代验收。', 'Behavior is not verified. Structure cannot substitute for acceptance.') }}</p><p v-for="reason in selectedTask.reason_codes" :key="reason">{{ label(reason) }}</p><TechnicalDetails :summary="c('任务与 Workspace 身份', 'Task and workspace identities')" :fields="[{ label: 'Task SHA', value: selectedTask.task_identity }, { label: 'Workspace SHA', value: selectedTask.workspace_identity }]"><pre>{{ JSON.stringify(selectedTask, null, 2) }}</pre></TechnicalDetails></div>
        <h3>{{ c('2. 选择一个 Codex 配置与预算', '2. Choose one Codex configuration and budget') }}</h3>
        <div class="form-grid"><label>{{ c('计划名称', 'Plan name') }}<input v-model="name" data-test="name" maxlength="100" required /></label><label>{{ c('Codex 配置', 'Codex configuration') }}<select v-model="configurationIndex" data-test="configuration" required><option value="">{{ c('选择配置', 'Choose a configuration') }}</option><option v-for="(config, i) in configurations" :key="`${config.provider_profile_id}/${config.harness_profile_id}`" :value="String(i)" :disabled="!config.enabled">{{ config.configuration_label }}</option></select></label></div>
        <div class="form-grid"><label>{{ c('每次尝试时间限制（秒）', 'Attempt wall time limit (seconds)') }}<input v-model.number="wallTime" data-test="wall-time" type="number" min="1" max="3600" required /></label><label>{{ c('参考费用预算（USD，非硬上限）', 'Reference cost budget (USD, not a hard cap)') }}<input v-model.number="costBudget" data-test="cost" type="number" min="0.001" max="1000" step="0.001" required /></label><label>{{ c('输出 token 估计（非强制限制）', 'Output token estimate (not enforced)') }}<input v-model.number="outputTokens" data-test="tokens" type="number" min="1" required /></label></div>
        <p>{{ c('现有 Codex runner 支持超时终止，Phase 2 Worker 必须应用它。本阶段没有生效的执行预算；费用和输出 token 仅供参考，未保留额度，服务连通性未探测。', 'The existing Codex runner supports timeout termination; the Phase 2 worker must apply it. No execution budget is active here. Cost and output tokens are estimates, with no reservation or live service probe.') }}</p>
        <button class="primary-button" data-test="preflight" :disabled="busy || !canPreflight">{{ busy ? c('正在检查…', 'Checking…') : c('3. 执行本地预检', '3. Run local preflight') }}</button>
      </form>
      <div v-if="receipt" class="panel" data-test="preflight-result"><h3>{{ receipt.status === 'READY_TO_SAVE' ? c('预检完成，可确认保存', 'Preflight complete; confirm to save') : c('预检阻塞，不能保存计划', 'Preflight blocked; plan cannot be saved') }}</h3><ul class="plan-checks"><li v-for="check in receipt.checks" :key="check.code"><strong>{{ check.passed ? c('通过', 'Checked') : c('阻塞', 'Blocked') }}</strong> {{ label(check.code) }}</li></ul><template v-if="receipt.status === 'READY_TO_SAVE'"><p>{{ c('预检有效期 15 分钟；参数、任务或配置变化后须重新预检。', 'Preflight expires in 15 minutes. Changes to parameters, task or configuration require another preflight.') }}</p><label class="plan-confirmation"><input v-model="confirmed" data-test="confirmation" type="checkbox" />{{ c('我确认仅保存此计划；不授权执行、不产生付费调用。', 'I confirm saving this plan only; I do not authorize execution or paid calls.') }}</label><button type="button" class="primary-button" data-test="save" :disabled="busy || !confirmed" @click="save">{{ c('4. 确认并保存计划', '4. Confirm and save plan') }}</button></template></div>
      <div class="panel"><div class="panel-title"><h3>{{ c('已保存计划', 'Saved plans') }} · {{ total }}</h3><button type="button" class="secondary-button" :disabled="busy" @click="loadPlans().catch(reportError)">{{ c('刷新列表', 'Refresh list') }}</button></div><p v-if="!plans.length">{{ c('尚未保存计划。完成预检并确认后，计划会保留在本地数据库中。', 'No saved plans. After preflight and confirmation, plans remain in the local database.') }}</p><ul class="saved-plan-list"><li v-for="plan in plans" :key="plan.plan_id"><RouterLink :to="`/plans/${plan.plan_id}`">{{ plan.name }}</RouterLink><span>{{ plan.task_reference }} · {{ c('仅计划', 'Plan only') }}</span></li></ul><div class="plan-pagination"><button class="secondary-button" :disabled="offset === 0 || busy" @click="page(-25)">{{ c('上一页', 'Previous') }}</button><button class="secondary-button" :disabled="offset + 25 >= total || busy" @click="page(25)">{{ c('下一页', 'Next') }}</button></div></div>
    </template>
  </section>
</template>

<style scoped>
.plan-boundary { border-left: 3px solid var(--accent); padding: 10px 14px; background: #f3f7fd; }
.builder-form h3 { margin-top: 22px; }.builder-form h3:first-child { margin-top: 0; }
.builder-form .form-grid { margin-bottom: 14px; }.builder-form p { color: var(--muted); line-height: 1.65; }
.plan-action { display: flex; align-items: end; }.task-admission { border: 1px solid var(--line); padding: 16px; border-radius: 6px; }
.plan-checks { padding-left: 20px; line-height: 2; }.plan-confirmation { display: flex; gap: 8px; align-items: center; margin: 16px 0; }
.saved-plan-list { list-style: none; padding: 0; }.saved-plan-list li { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--line); }
.saved-plan-list span { color: var(--muted); }.plan-pagination { display: flex; gap: 10px; margin-top: 16px; }
pre { overflow-wrap: anywhere; white-space: pre-wrap; max-width: 100%; }
@media (max-width: 700px) { .form-grid { grid-template-columns: 1fr; } }
</style>
