<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import InvestigationReport from '@/components/InvestigationReport.vue'

import { analystApi } from '@/api/analyst'
import { registryApi, workbenchApi } from '@/api/client'
import type { AnalystSession, AnalystPreflight } from '@/types/analyst'
import type { ProviderModelProfile } from '@/types/registry'
import type { ExperimentSummary } from '@/types/workbench'

const experiments = ref<ExperimentSummary[]>([])
const profiles = ref<ProviderModelProfile[]>([])
const experimentId = ref('')
const backend = ref<'fake' | 'real'>(new URLSearchParams(window.location.search).get('backend') === 'real' ? 'real' : 'fake')
const profileId = ref('')
const goal = ref('Explain the observed failures and propose a bounded regression check.')
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
const error = ref('')
const confirmReal = ref(false)
const objective = ref('')
const criteria = ref('')
const reviewedBy = ref('')
const proposalEvidence = ref<string[]>([])
const canResume = computed(() => current.value && ['PAUSED', 'RUNNING', 'FAILED'].includes(current.value.status)
  && (current.value.backend === 'fake' || confirmReal.value))
const proposalDirty = computed(() => objective.value !== current.value?.proposed_plan?.objective
  || criteria.value !== current.value?.proposed_plan?.acceptance_criteria.join('\n')
  || JSON.stringify(proposalEvidence.value) !== JSON.stringify(current.value?.proposed_plan?.evidence_refs))

function display(value: AnalystSession) {
  preflight.value = null
  current.value = value
  selectedId.value = value.session_id
  const index = sessions.value.findIndex(item => item.session_id === value.session_id)
  if (index >= 0) sessions.value[index] = value
  objective.value = value.proposed_plan?.objective ?? value.request.question
  criteria.value = value.proposed_plan?.acceptance_criteria.join('\n') ?? 'Verify the selected cases using deterministic evidence.'
  const cited = [...new Set(value.report?.verified_facts.flatMap(fact => fact.evidence_refs) ?? [])]
  proposalEvidence.value = value.proposed_plan?.evidence_refs.slice()
    ?? (cited.length ? cited : value.evidence.map(item => item.ref.id)).slice(0, 100)
  confirmReal.value = false
}
async function action(work: () => Promise<void>) {
  busy.value = true; error.value = ''
  try { await work() }
  catch { error.value = 'The Analyst request failed. Refresh the persisted session before retrying; limits are retained.' }
  finally { busy.value = false }
}
async function loadSessions() {
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
  } else {
    error.value = '当前实验无法加载，数据库或历史计划校验可能不可用。可返回首页运行独立的离线演示。'
  }
  if (models.status === 'rejected') error.value += ' Registry 加载失败；Real 暂不可用，Fake 仍可使用。'
  busy.value = false
})
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>当前数据库调查会话</h2><p>Inspect existing evidence, resume a bounded investigation, and review a regression proposal.</p></div></div>
    <p><a href="/analyst">返回 Analyst 首页：离线演示 / 历史真实记录</a></p>
    <p v-if="!busy && !experiments.length">当前没有可用实验。离线演示无需导入历史数据库；Real 调查需要先提供可验证的实验记录。</p>
    <p>Fake is deterministic and keyless. Real uses the selected Registry profile and requires server enablement. Approving a proposal never starts an experiment.</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <fieldset :disabled="busy">
      <legend>New investigation</legend>
      <label>Experiment <select v-model="experimentId" aria-label="Analyst experiment" @change="action(loadSessions)"><option v-for="item in experiments" :key="item.experiment_id" :value="item.experiment_id">{{ item.name }}</option></select></label>
      <label>Goal <textarea v-model="goal" aria-label="Investigation goal" maxlength="2000" /></label>
      <label>Backend <select v-model="backend" aria-label="Analyst backend"><option value="fake">Fake — keyless</option><option value="real">Real — model driven</option></select></label>
      <label v-if="backend === 'real'">Registry profile <select v-model="profileId" aria-label="Analyst profile"><option v-for="profile in profiles" :key="profile.profile_id" :value="profile.profile_id">{{ profile.profile_id }}</option></select></label>
      <label>Decision limit <input v-model.number="decisionLimit" aria-label="Decision limit" type="number" min="1" max="8" /></label>
      <label>Tool limit <input v-model.number="toolLimit" aria-label="Tool limit" type="number" min="1" max="12" /></label>
      <template v-if="backend === 'real'">
        <label>Provider request ceiling <input v-model.number="requestCeiling" aria-label="Provider request ceiling" type="number" min="1" :max="decisionLimit" /></label>
        <label>Output tokens/request <input v-model.number="outputCeiling" aria-label="Output token ceiling" type="number" min="1" /></label>
        <label>Input bytes/request <input v-model.number="inputCeiling" aria-label="Input byte ceiling" type="number" min="1" max="256000" /></label>
        <label>Cumulative tokens <input v-model.number="tokenCeiling" aria-label="Cumulative token ceiling" type="number" min="1" /></label>
        <label>Timeout seconds/request <input v-model.number="timeoutCeiling" aria-label="Timeout ceiling" type="number" min="1" max="600" /></label>
        <label>Optional USD ceiling <input v-model="usdCeiling" aria-label="USD ceiling" type="number" min="0.000001" step="any" /></label>
        <p>Enter an explicit cumulative token budget. Preflight reserves the KNOWN Registry context bound plus output cap for the next request. A USD ceiling requires KNOWN route-matched pricing.</p>
      </template>
      <button :disabled="!experimentId || !goal.trim() || (backend === 'real' && (!profileId || tokenCeiling <= 0 || requestCeiling > decisionLimit))" @click="create">Create investigation</button>
    </fieldset>
    <fieldset :disabled="busy"><legend>Saved investigations</legend>
      <select v-model="selectedId" aria-label="Saved investigation" @change="selectSaved"><option v-for="value in sessions" :key="value.session_id" :value="value.session_id">{{ value.backend.toUpperCase() }} · {{ value.status }} · {{ value.session_id }}</option></select>
      <button :disabled="!selectedId" @click="action(async () => display(await analystApi.get(selectedId)))">Refresh session</button>
    </fieldset>
    <article v-if="current" aria-label="Investigation details">
      <p class="session-origin">{{ current.backend === 'fake' ? 'FAKE · 当前数据库会话 · 固定决策，不调用真实模型' : 'REAL · 当前数据库会话 · 模型调用需要逐步确认' }}</p>
      <h3>{{ current.request.question }}</h3><p>{{ current.session_id }} · {{ current.status }} · {{ current.backend }}</p>
      <p>{{ current.provider ?? (current.backend === 'fake' ? 'Fake' : 'Unknown provider') }} / {{ current.model ?? (current.backend === 'fake' ? 'Deterministic' : 'Unknown model') }} · {{ current.profile_id ?? 'No provider profile' }}</p><p v-if="current.route">Route: {{ current.route }}</p>
      <p>Decisions {{ current.decision_iterations }}/{{ current.decision_limit }} · Tools {{ current.tool_calls }}/{{ current.tool_limit }} · Provider invocations {{ current.request_count ?? 'Unknown' }} · Request budget used {{ current.request_budget_used }}</p>
      <p>Input tokens {{ current.totals.input_tokens ?? 'Unknown' }} · Output tokens {{ current.totals.output_tokens ?? 'Unknown' }} · Cost USD {{ current.totals.cost_usd ?? 'Unknown' }} · Latency {{ current.totals.latency_ms ?? 'Unknown' }} ms</p>
      <p v-if="current.error" role="alert">{{ current.error }}</p>
      <label v-if="current.backend === 'real'"><input v-model="confirmReal" type="checkbox" aria-label="Confirm one real model decision" />Allow one real model decision with this profile and remaining limits ({{ current.max_output_tokens_per_request }} output tokens/request; {{ current.request_timeout_seconds }} seconds).</label>
      <button :disabled="busy || !canResume" @click="resumeCurrent">Resume one step</button>
      <template v-if="current.backend === 'real'">
        <p>Frozen spend limits</p><pre>{{ current.spend_limits ?? 'Missing: this session cannot invoke a provider.' }}</pre>
        <button :disabled="busy" @click="action(async () => { preflight = await analystApi.preflight(current!.session_id) })">Check smoke preflight</button>
        <div v-if="preflight" aria-label="Smoke preflight"><strong>{{ preflight.status }}</strong><pre>{{ preflight }}</pre><p>Keyless snapshot only. READY is not execution authorization.</p></div>
      </template>
      <details><summary>调查过程与已完成工具（{{ current.completed_calls.length }}）</summary><ul><li v-for="call in current.completed_calls" :key="call.key">{{ call.call.name }} · {{ call.status }}</li></ul></details>
      <InvestigationReport v-if="current.report" :key="current.session_id" :report="current.report" :evidence="current.evidence" />
      <p v-else>尚未形成结论。恢复一步以查询证据；失败后先刷新状态，已消耗预算不会重置。</p>
      <fieldset :disabled="busy || !current.evidence.length"><legend>Review-only regression proposal</legend>
        <label>Objective <textarea v-model="objective" aria-label="Regression objective" maxlength="2000" /></label>
        <label>Acceptance criteria, one per line <textarea v-model="criteria" aria-label="Regression acceptance criteria" /></label>
        <p>Tasks: {{ (current.proposed_plan?.task_ids ?? current.scope.task_ids).join(', ') }} · Cells: {{ (current.proposed_plan?.cell_ids ?? current.scope.cell_ids).join(', ') }}</p>
        <label>Evidence references ({{ proposalEvidence.length }}/100)
          <select v-model="proposalEvidence" multiple aria-label="Proposal evidence references">
            <option v-for="entry in current.evidence" :key="entry.ref.id" :value="entry.ref.id"
              :disabled="proposalEvidence.length >= 100 && !proposalEvidence.includes(entry.ref.id)">{{ entry.ref.id }}</option>
          </select>
        </label>
        <button :disabled="!proposalEvidence.length || proposalEvidence.length > 100" @click="saveProposal">Save proposal</button>
        <p>Proposal digest: {{ current.proposal_digest ?? 'Not proposed' }}</p>
        <p>Reviewer label 是本地审阅标签，不是已认证身份。审批仅保存方案，不授权执行。</p>
        <label>Reviewer label <input v-model="reviewedBy" aria-label="Reviewer label" maxlength="100" /></label>
        <button :disabled="!current.proposal_digest || proposalDirty || !reviewedBy.trim()" @click="action(async () => display(await analystApi.approve(current!.session_id, { scope_digest: current!.scope_digest, proposal_digest: current!.proposal_digest!, reviewed_by: reviewedBy })))">Approve proposal only</button>
        <p v-if="current.approval">Approved by {{ current.approval.reviewed_by }} · {{ current.approval.approved_at }}. Execution is not authorized.</p>
        <p v-else>Awaiting approval. Saving changed content invalidates previous approval.</p>
      </fieldset>
    </article>
  </section>
</template>

<style scoped>
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
