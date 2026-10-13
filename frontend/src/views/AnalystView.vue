<script setup lang="ts">
import StatusBadge from '@/components/StatusBadge.vue'
import { statusLabel } from '@/utils/statusLabels'
import { experimentOption } from '@/utils/displayIdentity'
import { computed, onMounted, ref } from 'vue'
import PublicAnalystNotice from '@/components/PublicAnalystNotice.vue'
import { useAnalystAccess } from '@/composables/analystAccess'
import InvestigationReport from '@/components/InvestigationReport.vue'

import { analystApi } from '@/api/analyst'
import { registryApi, workbenchApi } from '@/api/client'
import type { AnalystSession, AnalystPreflight } from '@/types/analyst'
import type { ProviderModelProfile } from '@/types/registry'
import type { ExperimentSummary } from '@/types/workbench'

const { access, loadAccess } = useAnalystAccess()
const experiments = ref<ExperimentSummary[]>([])
const profiles = ref<ProviderModelProfile[]>([])
const experimentId = ref('')
const backend = ref<'fake' | 'real'>(new URLSearchParams(window.location.search).get('backend') === 'real' ? 'real' : 'fake')
const profileId = ref('')
const goal = ref('解释已观察到的失败，并提出范围受限的回归检查。')
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
const objective = ref('')
const criteria = ref('')
const reviewedBy = ref('')
const reviewerValid = computed(() => reviewedBy.value.trim().length > 0 && /^[A-Za-z0-9 ._@-]+$/.test(reviewedBy.value))
const proposalEvidence = ref<string[]>([])
const canResume = computed(() => current.value && ['PAUSED', 'RUNNING', 'FAILED'].includes(current.value.status)
  && (current.value.backend === 'fake' || confirmReal.value))
const proposalDirty = computed(() => objective.value !== current.value?.proposed_plan?.objective
  || criteria.value !== current.value?.proposed_plan?.acceptance_criteria.join('\n')
  || JSON.stringify(proposalEvidence.value) !== JSON.stringify(current.value?.proposed_plan?.evidence_refs))

function display(value: AnalystSession) {
  preflight.value = null
  current.value = value
  setupOpen.value = false
  selectedId.value = value.session_id
  const index = sessions.value.findIndex(item => item.session_id === value.session_id)
  if (index >= 0) sessions.value[index] = value
  objective.value = value.proposed_plan?.objective ?? value.request.question
  criteria.value = value.proposed_plan?.acceptance_criteria.join('\n') ?? '使用确定性证据核验所选案例。'
  const cited = [...new Set(value.report?.verified_facts.flatMap(fact => fact.evidence_refs) ?? [])]
  proposalEvidence.value = value.proposed_plan?.evidence_refs.slice()
    ?? (cited.length ? cited : value.evidence.map(item => item.ref.id)).slice(0, 100)
  confirmReal.value = false
}
async function action(work: () => Promise<void>) {
  busy.value = true; error.value = ''
  try { await work() }
  catch { error.value = '调查请求失败。请先刷新已保存会话，再尝试继续；预算限制仍保留。' }
  finally { busy.value = false }
}
async function loadSessions() {
  setupOpen.value = true
  current.value = null; selectedId.value = ''; sessions.value = []; confirmReal.value = false; preflight.value = null
  sessions.value = (await analystApi.list(experimentId.value)).items
  if (sessions.value[0]) display(sessions.value[0])
}
async function selectSaved() {
  const id = selectedId.value
  current.value = null; confirmReal.value = false; preflight.value = null
  await action(async () => display(await analystApi.get(id)))
}
async function create() {
  await action(async () => {
    const value = await analystApi.create({ experiment_id: experimentId.value, question: goal.value,
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
onMounted(async () => {
  await loadAccess()
  if (access.value !== 'private') return
  busy.value = true
  const results = await Promise.allSettled([
    workbenchApi.listExperiments({ limit: 100 }), registryApi.models(),
  ])
  const [runs, models] = results
  if (models.status === 'fulfilled') {
    profiles.value = models.value.provider_profiles.filter(p => p.enabled && p.automation_allowed)
    profileId.value = profiles.value[0]?.profile_id ?? ''
  }
  if (runs.status === 'fulfilled') {
    experiments.value = runs.value.items
    experimentId.value = runs.value.items[0]?.experiment_id ?? ''
    if (experimentId.value) await action(loadSessions)
    if (backend.value === 'real') setupOpen.value = true
  } else {
    error.value = '当前实验无法加载，数据库或历史计划校验可能不可用。可返回首页运行独立的离线演示。'
  }
  if (models.status === 'rejected') error.value += ' 注册表读取失败；真实模型调查暂不可用，离线 Fake 仍可使用。'
  busy.value = false
})
</script>

<template>
  <section v-if="access !== 'private'" class="sessions-workspace">
    <h2>已保存调查</h2>
    <PublicAnalystNotice v-if="access === 'public'" />
    <p v-else-if="access === 'loading'" role="status">正在检查工作区权限…</p>
    <p v-else role="alert">工作区权限暂时无法读取，请重新加载页面后重试。 <RouterLink to="/analyst">打开调查工作区 →</RouterLink></p>
  </section>
  <section v-else class="sessions-workspace">
    <div class="page-heading"><div><span class="eyebrow">调查工作区</span><h2>继续追踪一个工程问题</h2><p>选择已有证据，继续调查，或审阅下一步回归方案。</p></div></div>
    <p><a href="/analyst">← 开始调查：离线演示 / 历史真实记录</a></p>
    <p v-if="!busy && !experiments.length">当前没有可用实验。离线演示无需导入历史数据库；Real 调查需要先提供可验证的实验记录。</p>
    <p>当前数据库会话会保存调查进度。Fake 使用固定决策；Real 需要启用模型与逐步确认。审批方案只记录审阅结果。</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <fieldset :disabled="busy"><legend>1 · 选择调查范围与会话</legend>
      <label>实验 <select v-model="experimentId" aria-label="调查实验" @change="action(loadSessions)"><option v-for="item in experiments" :key="item.experiment_id" :value="item.experiment_id">{{ experimentOption(item, experiments) }}</option></select></label>
      <label>已保存调查<select v-model="selectedId" aria-label="已保存调查" @change="selectSaved"><option v-for="value in sessions" :key="value.session_id" :value="value.session_id">{{ value.backend.toUpperCase() }} · {{ statusLabel(value.status, 'session') }} · {{ value.request.question }} · {{ value.session_id }}</option></select></label>
      <button :disabled="!selectedId" @click="action(async () => display(await analystApi.get(selectedId)))">刷新会话</button>
      <p v-if="!busy && experimentId && !sessions.length">此实验还没有已保存调查。展开下方表单开始。</p>
    </fieldset>
    <details :open="setupOpen" class="setup-panel" @toggle="setupOpen = ($event.target as HTMLDetailsElement).open">
      <summary>新建调查 <span>选择问题、模式与预算</span></summary>
    <fieldset :disabled="busy">
      <legend>新建调查</legend>
      <label>调查问题 <textarea v-model="goal" aria-label="调查问题" maxlength="2000" /></label>
      <label>调查模式 <select v-model="backend" aria-label="调查模式"><option value="fake">Fake · 无需密钥</option><option value="real">真实模型驱动</option></select></label>
      <label v-if="backend === 'real'">注册表配置 <select v-model="profileId" aria-label="调查模型配置"><option v-for="profile in profiles" :key="profile.profile_id" :value="profile.profile_id">{{ profile.profile_id }}</option></select></label>
      <label>最大决策次数 <input v-model.number="decisionLimit" aria-label="最大决策次数" type="number" min="1" max="8" /></label>
      <label>最大工具调用次数 <input v-model.number="toolLimit" aria-label="最大工具调用次数" type="number" min="1" max="12" /></label>
      <template v-if="backend === 'real'">
        <label>最大模型请求次数 <input v-model.number="requestCeiling" aria-label="最大模型请求次数" type="number" min="1" :max="decisionLimit" /></label>
        <label>单次请求输出 token 上限 <input v-model.number="outputCeiling" aria-label="输出 token 上限" type="number" min="1" /></label>
        <label>单次请求输入字节上限 <input v-model.number="inputCeiling" aria-label="输入字节上限" type="number" min="1" max="256000" /></label>
        <label>累计 token 上限 <input v-model.number="tokenCeiling" aria-label="累计 token 上限" type="number" min="1" /></label>
        <label>单次请求超时（秒） <input v-model.number="timeoutCeiling" aria-label="超时上限" type="number" min="1" max="600" /></label>
        <label>可选费用上限（美元） <input v-model="usdCeiling" aria-label="费用上限" type="number" min="0.000001" step="any" /></label>
        <p>请明确填写累计 token 预算。预检为下一次请求预留已知上下文上限与输出上限；费用上限需要已知且匹配路由的价格依据。</p>
      </template>
      <button :disabled="!experimentId || !goal.trim() || (backend === 'real' && (!profileId || tokenCeiling <= 0 || requestCeiling > decisionLimit))" @click="create">创建调查</button>
    </fieldset>
    </details>
    <p v-if="busy" role="status">正在读取或保存调查状态…</p>
    <article v-if="current" class="session-detail" aria-label="调查详情">
      <span class="eyebrow">2 · 调查进度与结果</span>
      <p class="session-origin">{{ current.backend === 'fake' ? 'FAKE · 当前数据库会话 · 固定决策，不调用真实模型' : 'REAL · 当前数据库会话 · 模型调用需要逐步确认' }}</p>
      <h3>{{ current.request.question }}</h3>
      <p><StatusBadge :value="current.status" context="session" /></p>
      <p class="session-guidance">{{ current.report ? '报告已生成。核对引用与限制后，审阅回归方案。' : current.status === 'FAILED' ? '调查失败。先刷新已保存状态，再按剩余预算决定是否继续。' : ['PAUSED', 'RUNNING'].includes(current.status) ? '调查尚未完成。每次继续一步，状态与已消耗预算都会保存。' : '调查已停止，当前没有可用报告。请检查状态与限制。' }}</p>
      <p>决策次数 {{ current.decision_iterations }}/{{ current.decision_limit }} · 工具调用次数 {{ current.tool_calls }}/{{ current.tool_limit }} · 模型请求次数 {{ current.request_count ?? '未知' }} · 已消耗请求预算 {{ current.request_budget_used }}</p>
      <div v-if="current.error" role="alert"><p>调查发生错误。请先刷新保存状态，再检查配置与剩余预算。</p><details><summary>查看原始错误</summary><p>{{ current.error }}</p></details></div>
      <label v-if="current.backend === 'real'"><input v-model="confirmReal" type="checkbox" aria-label="确认一次真实模型决策" />我允许使用此配置与剩余预算执行一次真实模型决策 ({{ current.max_output_tokens_per_request }} 输出 token / 请求；{{ current.request_timeout_seconds }} 秒）。</label>
      <button :disabled="busy || !canResume" @click="resumeCurrent">继续一步</button>
      <template v-if="current.backend === 'real'">
        <details><summary>固定费用与用量限制</summary><pre>{{ current.spend_limits ?? '缺少预算记录，此会话不能调用模型服务。' }}</pre></details>
        <button :disabled="busy" @click="action(async () => { preflight = await analystApi.preflight(current!.session_id) })">检查烟测预检</button>
        <div v-if="preflight" aria-label="烟测预检"><StatusBadge :value="preflight.status" /><details><summary>查看原始预检记录</summary><pre>{{ preflight }}</pre></details><p>仅为无需密钥的检查快照；就绪不代表已授权执行。</p></div>
      </template>
      <details class="session-metadata"><summary>会话来源与用量</summary>
      <p>{{ current.session_id }} · {{ current.backend }}</p>
      <p>{{ current.provider ?? (current.backend === 'fake' ? 'Fake' : '服务商未知') }} / {{ current.model ?? (current.backend === 'fake' ? '固定决策' : '模型未知') }} · {{ current.profile_id ?? '未配置服务商模型' }}</p><p v-if="current.route">路由：{{ current.route }}</p>
      <p>输入 token {{ current.totals.input_tokens ?? '未知' }} · 输出 token {{ current.totals.output_tokens ?? '未知' }} · 费用（美元） {{ current.totals.cost_usd ?? '未知' }} · 延迟 {{ current.totals.latency_ms ?? '未知' }} ms</p>
      </details>
      <details><summary>调查过程与已完成工具（{{ current.completed_calls.length }}）</summary><ul><li v-for="call in current.completed_calls" :key="call.key">{{ call.call.name }} · {{ statusLabel(call.status) }}</li></ul></details>
      <InvestigationReport v-if="current.report" :key="current.session_id" :report="current.report" :evidence="current.evidence" />
      <p v-else>尚未形成结论。恢复一步以查询证据；失败后先刷新状态，已消耗预算不会重置。</p>
      <details class="proposal-panel">
        <summary>3 · 审阅回归方案 <span>{{ current.approval ? '已有审阅记录' : current.proposed_plan ? '待审阅' : '准备下一步' }}</span></summary>
        <p>先核对报告证据，再保存方案和审阅记录。实验执行需要另行授权。</p>
      <fieldset :disabled="busy || !current.evidence.length"><legend>仅审阅回归方案</legend>
        <label>目标 <textarea v-model="objective" aria-label="回归目标" maxlength="2000" /></label>
        <label>验收条件（每行一项） <textarea v-model="criteria" aria-label="回归验收条件" /></label>
        <p>任务：{{ (current.proposed_plan?.task_ids ?? current.scope.task_ids).join(', ') }} · 配置：{{ (current.proposed_plan?.cell_ids ?? current.scope.cell_ids).join(', ') }}</p>
        <label>证据引用 ({{ proposalEvidence.length }}/100)
          <select v-model="proposalEvidence" multiple aria-label="方案证据引用">
            <option v-for="entry in current.evidence" :key="entry.ref.id" :value="entry.ref.id"
              :disabled="proposalEvidence.length >= 100 && !proposalEvidence.includes(entry.ref.id)">{{ entry.ref.id }}</option>
          </select>
        </label>
        <button :disabled="!proposalEvidence.length || proposalEvidence.length > 100" @click="saveProposal">保存方案</button>
        <p>方案摘要： {{ current.proposal_digest ?? '尚未提出方案' }}</p>
        <p>审阅标签 是本地审阅标签，不是已认证身份。审批仅保存方案，不授权执行。</p>
        <label>审阅标签 <input v-model="reviewedBy" aria-label="审阅标签" maxlength="100" :aria-invalid="reviewedBy.length > 0 && !reviewerValid" aria-describedby="reviewer-format" /></label>
        <p id="reviewer-format">审阅标签支持英文字母、数字、空格及 . _ @ -；例如 local-reviewer。</p>
        <button :disabled="!current.proposal_digest || proposalDirty || !reviewerValid" @click="action(async () => display(await analystApi.approve(current!.session_id, { scope_digest: current!.scope_digest, proposal_digest: current!.proposal_digest!, reviewed_by: reviewedBy })))">仅批准方案</button>
        <p v-if="current.approval">审阅人 {{ current.approval.reviewed_by }} · {{ current.approval.approved_at }}. 尚未授权执行。</p>
        <p v-else>等待审阅。修改后保存会使此前审批失效。</p>
      </fieldset>
      </details>
    </article>
  </section>
</template>

<style scoped>
.setup-panel, .proposal-panel, .session-detail { padding: 22px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); margin: 18px 0; }
.setup-panel > summary, .proposal-panel > summary { font-weight: 600; }
summary > span { font-size: 12px; color: var(--muted); margin-left: 12px; font-weight: 400; }
.session-guidance { padding: 14px; border-left: 3px solid var(--accent); background: var(--accent-soft); }
.session-metadata { margin: 20px 0 12px; }
.session-origin { color: var(--accent); font-size: 12px; }
@media (max-width: 600px) { .setup-panel, .proposal-panel, .session-detail { padding: 14px; } }
section, article, fieldset { min-width: 0; max-width: 100%; }
section { font-size: 14px; line-height: 1.5; overflow-wrap: anywhere; }
fieldset { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr)); gap: 14px; margin: 20px 0; padding: 16px 0; border: 0; border-top: 1px solid var(--line); }
legend { padding: 0 10px 0 0; font-weight: 600; }
label { display: grid; align-content: start; gap: 6px; min-width: 0; color: var(--muted); font-size: 12px; }
input, select, textarea { width: 100%; min-width: 0; max-width: 100%; border: 1px solid #ccd3da; border-radius: 4px; padding: 8px; background: var(--panel); color: var(--ink); font: inherit; }
input, select { min-height: 36px; }
input[type="checkbox"] { width: 18px; min-height: 18px; }
textarea { min-height: 72px; resize: vertical; }
select[multiple] { min-height: 112px; }
button { align-self: end; justify-self: start; min-height: 36px; max-width: 100%; padding: 7px 12px; border: 1px solid #b6c6c4; border-radius: 4px; background: var(--panel); color: var(--accent); cursor: pointer; white-space: normal; }
button:disabled { cursor: default; opacity: .55; }
button:not(:disabled):hover { background: var(--accent-soft); }
fieldset > p { grid-column: 1 / -1; margin: 0; }
pre { min-width: 0; max-width: 100%; max-height: 420px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; }
h3 { margin: 22px 0 10px; font-size: 17px; }
h4 { margin: 16px 0 8px; font-size: 14px; }
li { margin: 8px 0; }
.evidence-catalog { margin: 20px 0; border-block: 1px solid var(--line); padding: 12px 0; }
summary { cursor: pointer; }
:is(button, input, select, textarea, summary):focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
