<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { SavedPlan } from '@/api/localPlans'
import { localExecutionApi } from '@/api/localExecution'
import type { ExecutionState, ExecutionStatus } from '@/api/localExecution'
import { copy as c } from '@/composables/visualLocale'
import TechnicalDetails from './TechnicalDetails.vue'

const props = defineProps<{ plan: SavedPlan; token: string; stale: boolean }>()
const status = ref<ExecutionStatus | null>(null), state = ref<ExecutionState | null>(null)
const confirmed = ref(false), busy = ref(false), error = ref(''), key = ref('')
let generation = 0, alive = true
const terminal = ['VERIFIED_PASS', 'VERIFIED_FAIL', 'TIMEOUT', 'FAILED_INFRA', 'BLOCKED', 'INTERRUPTED', 'CANCELLED']
const active = computed(() => !!state.value?.attempt && !terminal.includes(state.value.status))
const names: Record<string, [string, string]> = {
  NOT_AUTHORIZED: ['未授权执行', 'Execution not authorized'], QUEUED: ['等待独立 Worker', 'Waiting for independent Worker'], CLAIMED: ['Worker 已领取', 'Claimed by Worker'], RUNNING: ['正在执行与独立验收', 'Running and independently verifying'],
  VERIFIED_PASS: ['独立验收通过 · Fake', 'Independent acceptance passed · Fake'], VERIFIED_FAIL: ['独立验收失败 · Fake', 'Independent acceptance failed · Fake'], TIMEOUT: ['运行超时 · 未验证', 'Timed out · not verified'], FAILED_INFRA: ['基础设施或证据失败 · 未验证', 'Infrastructure or evidence failure · not verified'], BLOCKED: ['执行前检查阻塞', 'Execution precheck blocked'], INTERRUPTED: ['Worker 中断 · 不会自动重跑', 'Worker interrupted · no automatic retry'], CANCELLED: ['已取消 · 不会自动重跑', 'Cancelled · no automatic retry'],
}
const label = (value: string) => names[value] ? c(...names[value]) : value
function message(e: unknown) { return (e as { response?: { data?: { error?: { code?: string } } } }).response?.data?.error?.code ?? c('读取失败，请刷新重试', 'Read failed; refresh to retry') }
async function load() {
  const current = ++generation
  confirmed.value = false; error.value = ''; busy.value = true; state.value = null; status.value = null
  try {
    const availability = await localExecutionApi.status(props.token)
    if (!alive || current !== generation) return
    status.value = availability
    // Read persisted attempts even when current execution policy is disabled.
    const data = await localExecutionApi.state(props.plan.plan_id, props.token)
    if (alive && current === generation) state.value = data
  } catch (e) { if (alive && current === generation) error.value = message(e) }
  finally { if (alive && current === generation) busy.value = false }
}
async function authorize() {
  if (!confirmed.value || busy.value || props.stale || !status.value?.enabled || state.value?.attempt) return
  if (!key.value) key.value = crypto.randomUUID()
  const current = generation, plan = props.plan, token = props.token
  busy.value = true; error.value = ''; confirmed.value = false
  try { const data = await localExecutionApi.authorize(plan, key.value, token); if (alive && current === generation) state.value = data }
  catch (e) { if (alive && current === generation) error.value = message(e) }
  finally { if (alive && current === generation) busy.value = false }
}
async function cancel() {
  if (busy.value || !active.value) return
  const current = generation
  busy.value = true; error.value = ''
  try { const data = await localExecutionApi.cancel(props.plan.plan_id, props.token); if (alive && current === generation) state.value = data }
  catch (e) { if (alive && current === generation) error.value = message(e) }
  finally { if (alive && current === generation) busy.value = false }
}
watch(() => [props.plan.plan_id, props.plan.plan_digest, props.token], () => { key.value = ''; load() }, { immediate: true })
watch(() => props.stale, () => { confirmed.value = false })
onBeforeUnmount(() => { alive = false; generation++; confirmed.value = false })
</script>

<template>
  <section class="execution-panel" data-test="execution-panel" aria-label="Execution authorization and result">
    <h4>{{ c('独立执行与验收', 'Independent execution and acceptance') }}</h4>
    <p>{{ c('计划确认不等于执行授权。当前仅开放无模型调用的隔离 Fake Codex；真实 Codex 订阅执行在本阶段关闭，不要求 API Key 或美元硬上限。', 'Plan confirmation does not authorize execution. Only isolated Fake Codex with zero model calls is available; real Codex subscription execution stays closed in this phase, with no API key or USD hard-cap requirement.') }}</p>
    <p v-if="error" role="alert" class="error-state" data-test="execution-error">{{ error }}</p>
    <p v-if="busy" role="status">{{ c('正在读取或提交…', 'Loading or submitting…') }}</p>
    <p v-if="state" data-test="execution-state"><strong>{{ label(state.status) }}</strong></p>
    <p v-if="state?.attempt?.cancellation_requested && active">{{ c('取消已请求；Worker 完成隔离清理后才确认终止。', 'Cancellation requested; termination is confirmed after Worker cleanup.') }}</p>
    <p v-if="!status?.enabled">{{ c('执行未启用，请检查独立 Worker 与操作员策略。', 'Execution is not enabled; check independent Worker and operator policy.') }}</p>
    <template v-if="status?.enabled && state?.status === 'NOT_AUTHORIZED'">
      <p>{{ c('授权仅适用于此计划的一次尝试，短时有效，实际到期时间保存在授权记录中。模型调用硬限制为 0、模型费用为 $0；时间限制由容器进程执行，token 与计划参考费用不是硬上限。', 'Authorization covers one attempt on this plan and is rechecked by the Worker. Zero model calls and $0 model cost are enforced; process timeout applies. Token and planning cost estimates are not hard caps.') }}</p>
      <p v-if="stale">{{ c('任务或配置已漂移，旧计划不能执行。请创建新计划。', 'The task or configuration drifted. Create a new plan before execution.') }}</p>
      <label class="execution-confirm"><input v-model="confirmed" data-test="execute-confirmation" type="checkbox" :disabled="stale || busy" />{{ c('我单独授权一次 Fake 尝试，并确认冻结预算及零模型调用；不授权真实或付费执行。', 'I separately authorize one Fake attempt and confirm frozen budgets and zero model calls; no real or paid execution is authorized.') }}</label>
      <button type="button" class="primary-button" data-test="authorize" :disabled="busy || stale || !confirmed" @click="authorize">{{ c('授权并提交给 Worker', 'Authorize and queue for Worker') }}</button>
    </template>
    <div v-if="state?.result" data-test="execution-result">
      <p>{{ c('失败分类 / 结果来源', 'Failure category / result source') }}: {{ state.result.reason_code }}</p>
      <p>{{ c('独立验收', 'Independent acceptance') }}: {{ state.result.acceptance }}</p>
      <p v-if="state.result.episode">{{ c('脱敏 Trace 事件', 'Sanitized trace events') }}: {{ state.result.episode.event_count }} · {{ c('实际修改文件', 'Actual changed files') }}: {{ state.result.episode.changed_file_count }} · {{ c('独立检查', 'Independent checks') }}: {{ state.result.episode.verifier_check_count }}</p>
      <p>{{ c('Fake 结果不能证明真实模型能力、真实任务准入或生产 Worker 已验证。', 'Fake results do not establish real model capability, real task admission or production Worker readiness.') }}</p>
      <TechnicalDetails :summary="c('结果与证据身份', 'Result and evidence identities')" :fields="[{ label: 'Run ID', value: state.result.run_id }, { label: 'Result SHA', value: state.result.digest }, { label: 'Episode SHA', value: state.result.episode_id }]"><pre>{{ JSON.stringify(state.result, null, 2) }}</pre></TechnicalDetails>
    </div>
    <div class="execution-actions">
      <button type="button" class="secondary-button" data-test="execution-refresh" :disabled="busy" @click="load">{{ c('刷新执行状态', 'Refresh execution state') }}</button>
      <button v-if="active" type="button" class="secondary-button" data-test="cancel-execution" :disabled="busy || state?.attempt?.cancellation_requested" @click="cancel">{{ c('取消此次尝试', 'Cancel this attempt') }}</button>
    </div>
  </section>
</template>
<style scoped>
.execution-panel { border-top: 1px solid var(--line); margin-top: 20px; padding-top: 16px; }
.execution-confirm { display: flex; align-items: start; gap: 10px; margin: 16px 0; }
.execution-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
