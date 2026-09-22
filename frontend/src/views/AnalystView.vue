<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, nextTick, onMounted, onBeforeUnmount, ref } from 'vue'
import { statusLabel } from '@/composables/labels'
import InvestigationReport from '@/components/InvestigationReport.vue'

import { analystApi } from '@/api/analyst'
import { registryApi, workbenchApi } from '@/api/client'
import type { AnalystSession, AnalystPreflight } from '@/types/analyst'
import type { ProviderModelProfile } from '@/types/registry'
import type { ExperimentSummary } from '@/types/workbench'

const search = ref('')
const statusFilter = ref('all')
const workspaceUnavailable = ref(false)
const sessionsUnavailable = ref(false)
const detailRoot = ref<HTMLElement | null>(null)
const filteredSessions = computed(() => sessions.value.filter(value =>
  (statusFilter.value === 'all' || value.status === statusFilter.value)
  && `${value.request.question} ${value.session_id} ${value.backend}`.toLowerCase().includes(search.value.toLowerCase())))
const experiments = ref<ExperimentSummary[]>([])
const profiles = ref<ProviderModelProfile[]>([])
const experimentId = ref('')
const backend = ref<'fake' | 'real'>(new URLSearchParams(window.location.search).get('backend') === 'real' ? 'real' : 'fake')
const profileId = ref('')
const selectedProfile = computed(() => profiles.value.find(p => p.profile_id === profileId.value))
const localProfile = computed(() => selectedProfile.value?.profile_id.startsWith('local-') ? selectedProfile.value : null)
const incomingQuestion = typeof window.history.state?.investigationQuestion === 'string'
  ? window.history.state.investigationQuestion.trim().slice(0, 2000) : ''
const goal = ref(incomingQuestion || t('解释观察到的失败，并提出有界的回归验证方案。'))
const decisionLimit = ref(8)
const toolLimit = ref(12)
const requestCeiling = ref(3)
const outputCeiling = ref(1000)
const inputCeiling = ref(64000)
const tokenCeiling = ref(0)
const timeoutCeiling = ref(60)
const usdCeiling = ref('')
const preflight = ref<AnalystPreflight | null>(null)
const sessions = ref<AnalystSession[]>([])
const selectedId = ref('')
const current = ref<AnalystSession | null>(null)
const busy = ref(false)
const setupOpen = ref(true)
const error = ref('')
const confirmReal = ref(false)
let active = true
onBeforeUnmount(() => { active = false })
const objective = ref('')
const criteria = ref('')
const reviewedBy = ref('')
const reviewerValid = computed(() => reviewedBy.value.trim().length > 0 && /^[A-Za-z0-9 ._@-]+$/.test(reviewedBy.value))
const proposalEvidence = ref<string[]>([])
const boundedInteger = (value: number, min: number, max: number) => Number.isInteger(value) && value >= min && value <= max
const createValid = computed(() => Boolean(experimentId.value && goal.value.trim() && goal.value.length <= 2000)
  && boundedInteger(decisionLimit.value, 1, 8) && boundedInteger(toolLimit.value, 1, 12)
  && (backend.value === 'fake' || (Boolean(selectedProfile.value) && boundedInteger(requestCeiling.value, 1, decisionLimit.value)
    && (!localProfile.value || (outputCeiling.value <= Math.min(localProfile.value.max_output_tokens, localProfile.value.max_output_tokens_limit ?? localProfile.value.max_output_tokens)
      && timeoutCeiling.value <= localProfile.value.request_timeout_seconds))
    && boundedInteger(outputCeiling.value, 1, Number.MAX_SAFE_INTEGER) && boundedInteger(inputCeiling.value, 1, 256000)
    && boundedInteger(tokenCeiling.value, 1, Number.MAX_SAFE_INTEGER) && (Number.isFinite(timeoutCeiling.value) && timeoutCeiling.value > 0 && timeoutCeiling.value <= 600)
    && (!usdCeiling.value.trim() || (Number.isFinite(Number(usdCeiling.value)) && Number(usdCeiling.value) > 0)))))
const canResume = computed(() => current.value && ['PAUSED', 'RUNNING', 'FAILED'].includes(current.value.status)
  && (current.value.backend === 'fake' || confirmReal.value))
const proposalDirty = computed(() => objective.value !== current.value?.proposed_plan?.objective
  || criteria.value !== current.value?.proposed_plan?.acceptance_criteria.join('\n')
  || JSON.stringify(proposalEvidence.value) !== JSON.stringify(current.value?.proposed_plan?.evidence_refs))

function display(value: AnalystSession) {
  if (!active) return
  preflight.value = null
  current.value = value
  setupOpen.value = false
  selectedId.value = value.session_id
  window.history.replaceState({ ...window.history.state, investigationSelection: {
    experimentId: value.request.experiment_id, sessionId: value.session_id,
  } }, '')
  const index = sessions.value.findIndex(item => item.session_id === value.session_id)
  if (index >= 0) sessions.value[index] = value
  objective.value = value.proposed_plan?.objective ?? value.request.question
  criteria.value = value.proposed_plan?.acceptance_criteria.join('\n') ?? t('使用确定性证据验证所选案例。')
  const cited = [...new Set(value.report?.verified_facts.flatMap(fact => fact.evidence_refs) ?? [])]
  proposalEvidence.value = value.proposed_plan?.evidence_refs.slice()
    ?? (cited.length ? cited : value.evidence.map(item => item.ref.id)).slice(0, 100)
  confirmReal.value = false
}
async function action(work: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await work() }
  catch { error.value = '调查请求失败。请刷新已保存状态后重试；已消耗预算不会重置。' }
  finally { busy.value = false }
}
async function loadSessions(restoreId = '') {
  setupOpen.value = true
  search.value = ''; statusFilter.value = 'all'
  current.value = null; selectedId.value = ''; sessions.value = []; confirmReal.value = false; preflight.value = null
  sessionsUnavailable.value = false
  try { sessions.value = (await analystApi.list(experimentId.value)).items }
  catch (cause) { sessionsUnavailable.value = true; throw cause }
  if (restoreId) {
    const restored = sessions.value.find(item => item.session_id === restoreId)
    if (!restored) throw new Error('Saved selection is unavailable')
    display(restored)
  } else {
    window.history.replaceState({ ...window.history.state, investigationSelection: {
      experimentId: experimentId.value, sessionId: null,
    } }, '')
    if (sessions.value[0] && !incomingQuestion) display(sessions.value[0])
  }
}
async function selectSaved(id = selectedId.value) {
  if (busy.value || !id) return
  selectedId.value = id
  current.value = null; confirmReal.value = false; preflight.value = null
  await action(async () => display(await analystApi.get(id)))
  await nextTick()
  detailRoot.value?.focus({ preventScroll: true })
  detailRoot.value?.scrollIntoView?.({ block: 'start' })
}
async function returnToList() {
  if (busy.value) return
  const previous = selectedId.value
  current.value = null; selectedId.value = ''; confirmReal.value = false; preflight.value = null
  await nextTick()
  const row = [...document.querySelectorAll<HTMLButtonElement>('.investigation-row')].find(item => item.dataset.sessionId === previous)
  row?.focus(); row?.scrollIntoView({ block: 'center' })
}
async function create() {
  if (!createValid.value) return
  await action(async () => {
    const value = await analystApi.create({ experiment_id: experimentId.value, question: goal.value.trim(),
      backend: backend.value, provider_profile_id: backend.value === 'real' ? profileId.value : null,
      decision_limit: decisionLimit.value, tool_limit: toolLimit.value,
      spend_limits: backend.value === 'real' ? { provider_requests: requestCeiling.value,
        output_tokens_per_request: outputCeiling.value, input_bytes_per_request: inputCeiling.value,
        cumulative_tokens: tokenCeiling.value, timeout_seconds: timeoutCeiling.value,
        usd: usdCeiling.value.trim() || null } : null })
    sessions.value.unshift(value); display(value)
  })
}
async function resumeCurrent() {
  const value = current.value
  if (!value) return
  const confirmed = confirmReal.value
  confirmReal.value = false
  await action(async () => display(await analystApi.resume(value.session_id, confirmed)))
}
async function saveProposal() {
  const value = current.value
  if (!value) return
  await action(async () => display(await analystApi.propose(value.session_id, {
    objective: objective.value, acceptance_criteria: criteria.value.split('\n').filter(Boolean),
    task_ids: value.proposed_plan?.task_ids ?? value.scope.task_ids,
    cell_ids: value.proposed_plan?.cell_ids ?? value.scope.cell_ids,
    evidence_refs: proposalEvidence.value,
    repeat_count: value.proposed_plan?.repeat_count ?? 1,
  })))
}
async function loadWorkspace() {
  busy.value = true
  error.value = ''; workspaceUnavailable.value = false
  const results = await Promise.allSettled([
    workbenchApi.listExperiments({ limit: 100 }), registryApi.models(),
  ])
  const [runs, models] = results
  if (models.status === 'fulfilled') {
    profiles.value = models.value.provider_profiles.filter(p => p.enabled && p.automation_allowed
      && (!p.profile_id.startsWith('local-') || p.purpose === 'ANALYST'))
    profileId.value = profiles.value[0]?.profile_id ?? ''
  }
  if (runs.status === 'fulfilled') {
    experiments.value = runs.value.items
    const selection = window.history.state?.investigationSelection
    const selectedExperiment = typeof selection?.experimentId === 'string' ? selection.experimentId : ''
    const restoreId = typeof selection?.sessionId === 'string' ? selection.sessionId : ''
    experimentId.value = selectedExperiment
      ? runs.value.items.find(item => item.experiment_id === selectedExperiment)?.experiment_id ?? ''
      : runs.value.items[0]?.experiment_id ?? ''
    if (selectedExperiment && !experimentId.value) {
      current.value = null; sessions.value = []; selectedId.value = ''
      error.value = '上次查看的实验不在当前可用列表中，请重新选择调查范围。'
    }
    if (experimentId.value) {
      try { await loadSessions(restoreId) } catch { error.value = '无法读取此实验的调查记录，请重试。' }
    }
    if (!current.value && (backend.value === 'real' || incomingQuestion)) setupOpen.value = true
  } else {
    workspaceUnavailable.value = true
    const code = runs.reason?.response?.data?.code ?? runs.reason?.response?.data?.error?.code
    error.value = code === 'FULL_WORKSPACE_REQUIRED'
      ? '当前是演示模式，不提供已保存调查。请在服务机器上停止演示并运行 samescale up，再打开完整工作区。'
      : code === 'WORKSPACE_NOT_CONFIGURED'
        ? '完整工作区尚未配置。请在服务机器上运行 samescale up，再重新连接。'
        : '当前实验无法加载，数据库或历史计划校验可能不可用。可返回首页运行独立的离线演示。'
  }
  if (models.status === 'rejected') { profiles.value = []; profileId.value = '' }
  if (models.status === 'rejected') error.value += ' Registry 加载失败；Real 暂不可用，Fake 仍可使用。'
  busy.value = false
}
onMounted(loadWorkspace)
</script>

<template>
  <section class="sessions-workspace">
    <div class="page-heading"><div><span class="eyebrow">{{ t('本地工作区') }}</span><h2>{{ t('已保存调查') }}</h2><p>{{ t('围绕一个工程问题，核对证据，追踪下一步。') }}</p></div><RouterLink to="/analyst?example=offline" class="sample-link">{{ t('打开 Sample') }}</RouterLink></div>
    <div v-if="incomingQuestion && !current" class="question-handoff"><span>{{ t('待调查的问题') }}</span><p>{{ incomingQuestion }}</p><small>{{ t('选择已有实验后创建调查；此时尚未调用模型。') }}</small></div>
    <p class="workspace-note">{{ t('当前数据库会话会保存调查进度。Fake 使用固定决策；Real 需要启用模型与逐步确认。审批方案只记录审阅结果。') }}</p>
    <div v-if="error" role="alert" class="workspace-error"><strong>{{ t('工作区连接需要检查') }}</strong><p>{{ t(error) }}</p><button v-if="workspaceUnavailable" :disabled="busy" @click="loadWorkspace">{{ t('重新连接') }}</button></div>
    <div v-if="!busy && !experiments.length" class="workspace-empty">
      <span class="eyebrow">{{ workspaceUnavailable ? t('工作区暂不可用') : t('尚无实验') }}</span>
      <h3>{{ workspaceUnavailable ? t('暂时无法读取本地调查') : t('从已有实验开始第一份调查') }}</h3>
      <p>{{ workspaceUnavailable ? t('连接恢复后才能确认已保存记录。你可以先打开无需数据库的 Sample。') : t('当前没有可用实验。离线演示无需导入历史数据库；Real 调查需要先提供可验证的实验记录。') }}</p>
      <RouterLink to="/analyst?example=offline" class="sample-link">{{ t('运行离线演示') }}</RouterLink><RouterLink to="/experiments" class="sample-link">{{ t('查看实验') }}</RouterLink>
    </div>
    <fieldset v-if="experiments.length" :disabled="busy" class="scope-toolbar"><legend>{{ t('调查范围') }}</legend>
      <label>{{ t('实验') }} <select v-model="experimentId" :aria-label="t('调查所属实验')" @change="action(loadSessions)"><option v-for="item in experiments" :key="item.experiment_id" :value="item.experiment_id">{{ item.name }}</option></select></label>
      <label>{{ t('快速切换') }}<select v-model="selectedId" :aria-label="t('已保存调查')" @change="selectSaved()"><option v-if="!selectedId" disabled value="">{{ t('选择已保存调查') }}</option><option v-for="value in sessions" :key="value.session_id" :value="value.session_id">{{ value.backend.toUpperCase() }} · {{ value.request.question }}</option></select></label>
      <button :disabled="!selectedId" @click="action(async () => display(await analystApi.get(selectedId)))">{{ t('刷新调查') }}</button>
    </fieldset>
    <section v-if="experimentId" class="investigation-list" :aria-label="t('已保存调查列表')">
      <div class="list-toolbar"><span>{{ t('调查') }} <b>{{ sessionsUnavailable ? t('不可用') : sessions.length }}</b></span><div><input v-model="search" :aria-label="t('搜索调查')" :placeholder="t('搜索问题或会话 ID')" type="search" /><select v-model="statusFilter" :aria-label="t('筛选调查状态')"><option value="all">{{ t('全部状态') }}</option><option v-for="status in [...new Set(sessions.map(item => item.status))]" :key="status" :value="status">{{ statusLabel(status) }}</option></select></div></div>
      <div class="list-columns"><span>{{ t('工程问题') }}</span><span>{{ t('来源 / 状态') }}</span><span>{{ t('证据') }}</span></div>
      <button v-for="value in filteredSessions" :key="value.session_id" class="investigation-row" :data-session-id="value.session_id" :class="{ selected: value.session_id === selectedId }" :aria-pressed="value.session_id === selectedId" :disabled="busy" @click="selectSaved(value.session_id)">
        <span class="row-question"><strong>{{ value.request.question }}</strong><code>{{ value.session_id }}</code></span><span class="row-status"><span>{{ value.backend.toUpperCase() }}</span><span class="status-pill neutral">{{ statusLabel(value.status) }}</span></span><span class="row-evidence">{{ value.evidence.length }}</span>
      </button>
      <p v-if="sessionsUnavailable" class="list-empty">{{ t('无法读取此实验的调查记录。') }}<button :disabled="busy" @click="action(loadSessions)">{{ t('重试读取调查') }}</button></p>
      <p v-else-if="!busy && !sessions.length" class="list-empty">{{ t('此实验还没有已保存调查。展开下方表单开始。') }}</p>
      <p v-else-if="!filteredSessions.length" class="list-empty">{{ t('没有符合筛选条件的调查。') }}<button @click="search = ''; statusFilter = 'all'">{{ t('清除筛选') }}</button></p>
    </section>
    <details v-if="experiments.length" :open="setupOpen" class="setup-panel" @toggle="setupOpen = ($event.target as HTMLDetailsElement).open">
      <summary>{{ t('新建调查') }} <span>{{ t('选择问题、模式与预算') }}</span></summary>
    <fieldset :disabled="busy">
      <legend>{{ t('新建调查') }}</legend>
      <label>{{ t('调查问题') }} <textarea v-model="goal" :aria-label="t('调查问题')" maxlength="2000" /></label>
      <label>{{ t('运行模式') }} <select v-model="backend" :aria-label="t('调查运行模式')"><option value="fake">{{ t('Fake · 固定决策，无模型调用') }}</option><option value="real">{{ t('Real · 真实模型调查') }}</option></select></label>
      <label v-if="backend === 'real'">{{ t('模型服务配置') }} <select v-model="profileId" :aria-label="t('调查模型配置')"><option v-for="profile in profiles" :key="profile.profile_id" :value="profile.profile_id">{{ profile.profile_id }}</option></select></label>
      <p v-if="backend === 'real' && localProfile" class="binding-selection">{{ t('本地 Analyst 配置：保存后固定此版本。') }} {{ t('输出 Token 上限') }} {{ Math.min(localProfile.max_output_tokens, localProfile.max_output_tokens_limit ?? localProfile.max_output_tokens) }} · {{ t('超时上限') }} {{ localProfile.request_timeout_seconds }} {{ t('秒') }}。{{ t('创建调查不调用模型。配置或凭据变更后，请新建调查。') }}</p>
      <label>{{ t('决策步数上限') }} <input v-model.number="decisionLimit" :aria-label="t('决策步数上限')" type="number" min="1" max="8" /></label>
      <label>{{ t('工具调用上限') }} <input v-model.number="toolLimit" :aria-label="t('工具调用上限')" type="number" min="1" max="12" /></label>
      <template v-if="backend === 'real'">
        <label>{{ t('模型请求上限') }} <input v-model.number="requestCeiling" :aria-label="t('模型请求上限')" type="number" min="1" :max="decisionLimit" /></label>
        <label>{{ t('每次请求输出 Token 上限') }} <input v-model.number="outputCeiling" :aria-label="t('输出 Token 上限')" type="number" min="1" /></label>
        <label>{{ t('每次请求输入字节上限') }} <input v-model.number="inputCeiling" :aria-label="t('输入字节上限')" type="number" min="1" max="256000" /></label>
        <label>{{ t('累计 Token 预算') }} <input v-model.number="tokenCeiling" :aria-label="t('累计 Token 上限')" type="number" min="1" /></label>
        <label>{{ t('每次请求超时（秒）') }} <input v-model.number="timeoutCeiling" :aria-label="t('超时上限')" type="number" min="1" max="600" /></label>
        <label>{{ t('费用上限（美元，可选）') }} <input v-model="usdCeiling" :aria-label="t('美元预算上限')" type="number" min="0.000001" step="any" /></label>
        <p>{{ t('请输入累计 Token 预算。预检会为下一次请求预留已知上下文与输出上限；费用上限需要已知且匹配当前路由的价格依据。') }}</p>
      </template>
      <button :disabled="!createValid" @click="create">{{ t('创建调查') }}</button>
    </fieldset>
    </details>
    <p v-if="busy" role="status">{{ t('正在读取或保存调查状态…') }}</p>
    <article v-if="current" ref="detailRoot" tabindex="-1" class="session-detail" :aria-label="t('调查详情')">
      <button class="return-list" @click="returnToList">{{ t('返回调查列表') }}</button>
      <span class="eyebrow">{{ t('调查详情') }}</span>
      <p class="session-origin">{{ current.backend === 'fake' ? t('FAKE · 当前数据库会话 · 固定决策，不调用真实模型') : t('REAL · 当前数据库会话 · 模型调用需要逐步确认') }}</p>
      <p v-if="current.model_binding" class="frozen-binding">{{ t('已绑定 Analyst 模型') }} · {{ current.model_binding.configuration_id }} · v{{ current.model_binding.configuration_revision }}<template v-if="current.model_binding.connection_id"> · {{ t('服务连接') }} {{ current.model_binding.connection_id }} · v{{ current.model_binding.connection_revision }}</template></p>
      <h3>{{ current.request.question }}</h3>
      <p><span class="status-pill" :class="current.status === 'COMPLETED' ? 'good' : current.status === 'FAILED' ? 'bad' : 'neutral'">{{ statusLabel(current.status) }}</span></p>
      <p class="session-guidance">{{ current.report ? t('报告已生成。核对引用与限制后，审阅回归方案。') : current.status === 'FAILED' ? t('调查失败。先刷新已保存状态，再按剩余预算决定是否继续。') : ['PAUSED', 'RUNNING'].includes(current.status) ? t('调查尚未完成。每次继续一步，状态与已消耗预算都会保存。') : t('调查已停止，当前没有可用报告。请检查状态与限制。') }}</p>
      <p>{{ t('决策') }} {{ current.decision_iterations }}/{{ current.decision_limit }} {{ t('· 工具') }} {{ current.tool_calls }}/{{ current.tool_limit }} {{ t('· 模型请求') }} {{ current.request_count ?? t('未知') }} {{ t('· 已用请求预算') }} {{ current.request_budget_used }}</p>
      <p v-if="current.error" role="alert">{{ current.error }}</p>
      <label v-if="current.backend === 'real'"><input v-model="confirmReal" type="checkbox" :aria-label="t('确认一次真实模型决策')" />{{ t('确认使用此配置与剩余预算进行一次真实模型决策（') }}{{ current.max_output_tokens_per_request }} {{ t('输出 Token / 次；') }}{{ current.request_timeout_seconds }} {{ t('秒）。') }}</label>
      <button :disabled="busy || !canResume" @click="resumeCurrent">{{ t('继续一步') }}</button>
      <template v-if="current.backend === 'real'">
        <p>{{ t('已冻结预算') }}</p><pre>{{ current.spend_limits ?? t('缺少预算：此调查无法调用模型。') }}</pre>
        <button :disabled="busy" @click="action(async () => { preflight = await analystApi.preflight(current!.session_id) })">{{ t('检查调用前置条件') }}</button>
        <div v-if="preflight" :aria-label="t('调用前置检查')"><strong>{{ preflight.status }}</strong><p v-if="current.model_binding && preflight.reasons.some(reason => ['MODEL_BINDING_STALE_OR_UNAVAILABLE', 'PROFILE_DRIFT_OR_UNAVAILABLE'].includes(reason))">{{ t('绑定的配置或凭据已变更或不可用。历史记录保留，请选择当前版本新建调查。') }}</p><pre>{{ preflight }}</pre><p>{{ t('检查不调用模型。就绪状态不代表授权执行。') }}</p></div>
      </template>
      <details class="session-metadata"><summary>{{ t('会话来源与用量') }}</summary>
      <p>{{ current.session_id }} · {{ current.backend }}</p>
      <p>{{ current.provider ?? (current.backend === 'fake' ? 'Fake' : t('未知服务')) }} / {{ current.model ?? (current.backend === 'fake' ? t('固定决策') : t('未知模型')) }} · {{ current.profile_id ?? t('无模型服务配置') }}</p><p v-if="current.route">{{ t('路由：') }}{{ current.route }}</p>
      <p>{{ t('输入 Token') }} {{ current.totals.input_tokens ?? t('未知') }} {{ t('· 输出 Token') }} {{ current.totals.output_tokens ?? t('未知') }} {{ t('· 费用（美元）') }}{{ current.totals.cost_usd ?? t('未知') }} {{ t('· 耗时') }} {{ current.totals.latency_ms ?? t('未知') }} ms</p>
      </details>
      <details><summary>{{ t('调查过程与已完成工具（') }}{{ current.completed_calls.length }}）</summary><ul><li v-for="call in current.completed_calls" :key="call.key">{{ call.call.name }} · {{ call.status }}</li></ul></details>
      <InvestigationReport v-if="current.report" :key="current.session_id" :report="current.report" :evidence="current.evidence" />
      <p v-else>{{ t('尚未形成结论。恢复一步以查询证据；失败后先刷新状态，已消耗预算不会重置。') }}</p>
      <details class="proposal-panel">
        <summary>{{ t('3 · 审阅回归方案') }} <span>{{ current.approval ? t('已有审阅记录') : current.proposed_plan ? t('待审阅') : t('准备下一步') }}</span></summary>
        <p>{{ t('先核对报告证据，再保存方案和审阅记录。实验执行需要另行授权。') }}</p>
      <fieldset :disabled="busy || !current.evidence.length"><legend>{{ t('回归方案审阅') }}</legend>
        <label>{{ t('目标') }} <textarea v-model="objective" :aria-label="t('回归目标')" maxlength="2000" /></label>
        <label>{{ t('验收标准，每行一项') }} <textarea v-model="criteria" :aria-label="t('回归验收标准')" /></label>
        <p>{{ t('任务：') }}{{ (current.proposed_plan?.task_ids ?? current.scope.task_ids).join(', ') }} {{ t('· 单元：') }}{{ (current.proposed_plan?.cell_ids ?? current.scope.cell_ids).join(', ') }}</p>
        <label>{{ t('证据引用（') }}{{ proposalEvidence.length }}/100）
          <select v-model="proposalEvidence" multiple :aria-label="t('方案证据引用')">
            <option v-for="entry in current.evidence" :key="entry.ref.id" :value="entry.ref.id"
              :disabled="proposalEvidence.length >= 100 && !proposalEvidence.includes(entry.ref.id)">{{ entry.ref.id }}</option>
          </select>
        </label>
        <button :disabled="!proposalEvidence.length || proposalEvidence.length > 100 || !objective.trim() || !criteria.trim()" @click="saveProposal">{{ t('保存方案') }}</button>
        <p>{{ t('方案摘要：') }} {{ current.proposal_digest ?? t('尚未提出方案') }}</p>
        <p>{{ t('审阅标签是本地审阅标签，不是已认证身份。审批仅保存方案，不授权执行。') }}</p>
        <label>{{ t('审阅标签') }} <input v-model="reviewedBy" :aria-label="t('审阅标签')" maxlength="100" :aria-invalid="reviewedBy.length > 0 && !reviewerValid" aria-describedby="reviewer-format" /></label>
        <p id="reviewer-format">{{ t('审阅标签支持英文字母、数字、空格及 . _ @ -；例如 local-reviewer。') }}</p>
        <button :disabled="!current.proposal_digest || proposalDirty || !reviewerValid" @click="action(async () => display(await analystApi.approve(current!.session_id, { scope_digest: current!.scope_digest, proposal_digest: current!.proposal_digest!, reviewed_by: reviewedBy })))">{{ t('确认审阅方案') }}</button>
        <p v-if="current.approval">{{ t('已由') }} {{ current.approval.reviewed_by }} · {{ current.approval.approved_at }} {{ t('审阅。未授权执行。') }}</p>
        <p v-else>{{ t('等待审阅确认。保存修改后的内容会使旧审批失效。') }}</p>
      </fieldset>
      </details>
    </article>
  </section>
</template>

<style scoped>
.setup-panel, .proposal-panel, .session-detail { padding: 22px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); margin: 18px 0; }
.setup-panel > summary, .proposal-panel > summary { font-weight: 600; }
summary > span { font-size: 13px; color: var(--muted); margin-left: 12px; font-weight: 400; }
.session-guidance { padding: 14px; border-left: 3px solid var(--accent); background: var(--accent-soft); }
.session-metadata { margin: 20px 0 12px; }
.session-origin { color: var(--accent); font-size: 13px; }
@media (max-width: 600px) { .setup-panel, .proposal-panel, .session-detail { padding: 14px; } }
section, article, fieldset { min-width: 0; max-width: 100%; }
section { font-size: 14px; line-height: 24px; overflow-wrap: anywhere; }
fieldset { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr)); gap: 14px; margin: 20px 0; padding: 16px 0; border: 0; border-top: 1px solid var(--line); }
legend { padding: 0 10px 0 0; font-weight: 600; }
label { display: grid; align-content: start; gap: 6px; min-width: 0; color: var(--muted); font-size: 13px; }
input, select, textarea { width: 100%; min-width: 0; max-width: 100%; border: 1px solid #ccd3da; border-radius: 4px; padding: 8px; background: var(--panel); color: var(--ink); font: inherit; }
input, select { min-height: 40px; }
input[type="checkbox"] { width: 18px; min-height: 18px; }
textarea { min-height: 72px; resize: vertical; }
select[multiple] { min-height: 112px; }
button { align-self: end; justify-self: start; min-height: 40px; max-width: 100%; padding: 7px 12px; border: 1px solid #b6c6c4; border-radius: 4px; background: var(--panel); color: var(--accent); cursor: pointer; white-space: normal; }
button:disabled { cursor: default; opacity: .55; }
button:not(:disabled):hover { background: var(--accent-soft); }
fieldset > p { grid-column: 1 / -1; margin: 0; }
pre { min-width: 0; max-width: 100%; max-height: 420px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 13px; }
h3 { margin: 22px 0 10px; font-size: 17px; }
h4 { margin: 16px 0 8px; font-size: 14px; }
li { margin: 8px 0; }
.evidence-catalog { margin: 20px 0; border-block: 1px solid var(--line); padding: 12px 0; }
summary { cursor: pointer; }
:is(button, input, select, textarea, summary):focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.question-handoff { margin: 24px 0; padding: 18px 20px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }.question-handoff > span, .question-handoff small { color: var(--muted); font: var(--type-caption); }.question-handoff p { font: var(--type-body); margin: 8px 0; }
.sessions-workspace { width: 100%; margin: 0; }
.page-heading { align-items: center; }
.page-heading { padding: 22px 24px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); }.page-heading h2 { font: var(--type-title); margin: 6px 0 8px; }
.page-heading h2 span { font-size: 13px; font-weight: 400; color: var(--muted); margin-left: 10px; }
.sample-link { color: var(--accent); font-size: 13px; text-underline-offset: 4px; display: inline-block; margin-right: 18px; }
.workspace-note { color: var(--muted); font-size: 13px; padding: 14px 18px; background: var(--accent-soft); border: 1px solid var(--line); border-radius: 8px; }
.workspace-error { padding: 16px 18px; border: 1px solid #d7c6be; border-radius: 6px; background: #f6f2ef; font-size: 13px; margin: 24px 0; color: #705d52; }
.workspace-error strong { font-weight: 500; }
.workspace-error p { margin: 6px 0 12px; }
.workspace-empty { padding: 28px; text-align: left; border: 1px solid var(--line); border-radius: 8px; background: #fff; margin-top: 24px; }
.workspace-empty h3 { font-size: 18px; font-weight: 500; }
.workspace-empty p { max-width: 520px; margin: 12px 0 24px; color: var(--muted); font-size: 13px; }
.scope-toolbar { border: 0; padding: 12px 0; margin: 24px 0; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; align-items: end; }
.scope-toolbar legend { font-size: 13px; color: var(--muted); font-weight: 400; }
.investigation-list { border: 1px solid var(--line); border-radius: 7px; background: #fff; overflow: hidden; }
.list-toolbar, .list-toolbar > div { display: flex; gap: 12px; align-items: center; }.list-toolbar { padding: 14px 18px; justify-content: space-between; font-size: 13px; }
.list-toolbar b { font-weight: 400; color: var(--muted); margin-left: 6px; }
.list-toolbar input { width: 220px; }.list-toolbar select { width: auto; }
.list-columns, button.investigation-row { display: grid; grid-template-columns: minmax(0, 1fr) 210px 45px; gap: 18px; padding: 12px 18px; width: 100%; }
.list-columns { background: #f7f7f6; border-block: 1px solid var(--line); color: var(--muted); font-size: 13px; }
button.investigation-row { border: 0; border-bottom: 1px solid #eceeec; border-radius: 0; color: var(--ink); text-align: left; align-items: center; background: #fff; padding-block: 18px; }
button.investigation-row.selected { background: #f0f2f4; box-shadow: inset 2px 0 #79899b; }
.row-question { min-width: 0; display: grid; gap: 7px; }.row-question strong { font-size: 14px; font-weight: 500; }.row-question code { font-size: 13px; color: #7c848e; }
.row-status { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; font: var(--type-caption); color: var(--muted); }.row-evidence { color: var(--muted); font: var(--type-caption); }
.list-empty { text-align: center; padding: 28px; color: var(--muted); font-size: 13px; }
.setup-panel, .proposal-panel { border-radius: 7px; padding: 18px 20px; }
.session-detail { border: 0; border-top: 1px solid var(--line); border-radius: 0; background: transparent; padding: 30px 0 0; margin-top: 32px; scroll-margin-top: 80px; }
.session-detail:focus { outline: none; }
.session-detail > h3 { font: var(--type-title); margin: 12px 0; }
.session-detail > p { font: var(--type-body); color: var(--muted); }.session-origin { margin: 12px 0; }
.session-guidance { padding: 10px 14px; border-left-width: 2px; background: #eef0f2; }
.session-detail > details:not(.proposal-panel) { font-size: 13px; color: var(--muted); margin: 14px 0; }
button { border-color: #d1d7de; border-radius: 5px; }input, select, textarea { border-color: #d6dadd; border-radius: 5px; }
@media (max-width: 1050px) { .list-toolbar { align-items: flex-start; flex-direction: column; }.list-toolbar > div { width: 100%; }.list-toolbar input { flex: 1; width: 120px; }.scope-toolbar { grid-template-columns: 1fr 1fr; } }
@media (max-width: 600px) { .list-columns { display: none; }button.investigation-row { grid-template-columns: minmax(0, 1fr) auto; gap: 12px; }.row-status { grid-row: 2; }.row-evidence { grid-column: 2; grid-row: 1; }.scope-toolbar { grid-template-columns: 1fr; }.page-heading { align-items: flex-start; }.page-heading h2 span { display: block; margin: 8px 0 0; }.workspace-empty { padding: 36px 18px; } }

.setup-panel > summary, .proposal-panel > summary { font: var(--type-control); font-weight: 500; }
.scope-toolbar select, .list-toolbar input, .list-toolbar select, fieldset input, fieldset select, fieldset textarea, button { font: var(--type-control); }
.list-columns { font: var(--type-caption); }
.session-detail .proposal-panel { margin-top: 28px; }
@media (max-width: 600px) { .list-toolbar > div { flex-wrap: wrap; }.list-toolbar input { min-width: 160px; }.list-toolbar select { flex: 1; }.row-status { gap: 8px; } }
</style>
