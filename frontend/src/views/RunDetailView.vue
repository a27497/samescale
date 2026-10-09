<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { workbenchApi } from '@/api/client'
import TechnicalDetails from '@/components/TechnicalDetails.vue'
import { runName } from '@/utils/displayIdentity'
import EvidenceValue from '@/components/EvidenceValue.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import TraceTimeline from '@/components/TraceTimeline.vue'
import PageState from '@/components/PageState.vue'
import { copy as c } from '@/composables/visualLocale'
import { safeTrace, verifierStatus, downloadRun } from '@/utils/visualEvidence'
import type { RunDetail, TraceResponse } from '@/types/workbench'
const route = useRoute()
const router = useRouter()
const notFound = ref(false)
const denied = ref(false)
const failureCode = ref('')
const returnPath = computed(() => route.query.from === '/demo' ? '/demo' : typeof route.query.from === 'string' && run.value && route.query.from.split('?')[0] === `/experiments/${run.value.experiment_id}` ? route.query.from : run.value ? `/experiments/${run.value.experiment_id}?tab=runs${typeof route.query.candidate === 'string' ? `&candidate=${encodeURIComponent(route.query.candidate)}` : ''}` : '/experiments')
function goBack(event: MouseEvent) {
  if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  if (window.history.state?.back === returnPath.value) router.back()
  else void router.push(returnPath.value)
}
const run = ref<RunDetail | null>(null)
const trace = ref<TraceResponse | null>(null)
const loading = ref(true)
const error = ref(false)
const traceError = ref(false)
const publicArtifact = ref(false)
const artifactLoading = ref(false)
const runId = computed(() => String(route.params.runId))
const diagnosisLabel = computed(() => run.value?.verifier_passed === false ? c('查看失败诊断', 'View failure diagnosis') : run.value?.verifier_passed === true ? c('查看实验诊断', 'View experiment diagnosis') : c('查看诊断记录', 'View diagnosis records'))
const agentMessage = computed(() => trace.value?.events.find(event => event.type === 'AGENT_MESSAGE')?.summary ?? null)
const claimConflict = computed(() => run.value?.verifier_passed === false && !!agentMessage.value)
let sequence = 0
onUnmounted(() => { sequence++ })
async function load() {
  const request = ++sequence; const id = runId.value
  loading.value = true; error.value = false; notFound.value = false; denied.value = false; failureCode.value = ''; traceError.value = false; run.value = null; trace.value = null; publicArtifact.value = false; artifactLoading.value = false
  try {
    const value = await workbenchApi.getRun(id)
    if (request !== sequence) return
    run.value = value
  } catch (reason) {
    if (request !== sequence) return
    const failure = reason as { response?: { status?: number; data?: { error?: { code?: string } } } }
    error.value = true
    notFound.value = failure.response?.status === 404
    denied.value = failure.response?.status === 403
    failureCode.value = failure.response?.data?.error?.code ?? ''
    loading.value = false
    return // No trace/artifact probe follows a missing or denied run.
  }
  try {
    const value = await workbenchApi.getTrace(id)
    if (request !== sequence) return
    trace.value = value
  } catch { if (request === sequence) traceError.value = true }
  if (request !== sequence) return
  loading.value = false
  // A ready demo manifest supplies the supported artifact identity. The server remains the authority.
  if (run.value) {
    artifactLoading.value = true
    try {
      const demo = await workbenchApi.getPublicDemo()
      if (request !== sequence || !demo.public_demo_ready || ![demo.baseline_id, demo.candidate_id].includes(run.value?.experiment_id ?? '')) return
      const response = await fetch(`/api/workbench/runs/${encodeURIComponent(id)}/public-artifact`)
      // Consume the allowlisted response so the browser can finish the request.
      await response.arrayBuffer()
      if (request === sequence) publicArtifact.value = response.ok
    }
    catch { /* No artifact permission is inferred from a run ID or prefix. */ }
    finally { if (request === sequence) artifactLoading.value = false }
  }
}

watch(runId, load, { immediate: true })
</script>
<template>
  <section class="evidence-page run-page" :aria-busy="loading || artifactLoading">
    <div class="page-heading"><div><h2>{{ c('运行证据', 'Run evidence') }}</h2><p>{{ c('先看独立验收，再核对 Agent 自报与运行事件。', 'Start with independent verification, then inspect agent claims and trace events.') }}</p></div><StatusBadge value="READ_ONLY" localized /></div>
    <PageState v-if="loading" kind="loading">{{ c('正在读取已保存运行证据…', 'Loading saved run evidence…') }}</PageState>
    <PageState v-else-if="error || !run" kind="error"><span>{{ notFound ? c('运行记录不存在。请返回实验列表选择已有运行。', 'This run does not exist. Select a saved run from the experiment list.') : denied ? c('当前访问环境拒绝读取此运行，无法确认记录是否存在。请从已开放的实验中选择运行。', 'This environment denies access to this run. Its existence cannot be determined. Select a run from an available experiment.') : c('运行证据暂不可用或完整性校验未通过；未展示替代记录。', 'Run evidence is unavailable or failed integrity checks. No substitute record is shown.') }}</span><RouterLink v-if="notFound || denied" class="table-link" to="/experiments">{{ c('查看实验与运行', 'Browse experiments & runs') }}</RouterLink><button v-else class="secondary-button" @click="load">{{ c('重试', 'Retry') }}</button><TechnicalDetails :fields="[{ label: 'Run ID', value: runId }, { label: c('原始错误码', 'Original error code'), value: failureCode }]" /></PageState>
    <template v-else>
      <div class="panel run-toolbar toolbar"><a class="secondary-button" :href="returnPath" @click="goBack">{{ route.query.from === '/demo' ? c('返回演示', 'Back to demo') : c('返回实验运行', 'Back to experiment runs') }}</a><StatusBadge :value="run.provenance ?? 'UNVERIFIED_SOURCE'" localized /><button class="secondary-button" @click="downloadRun(run, trace)">{{ c('下载证据 JSON', 'Download safe evidence JSON') }}</button><a v-if="publicArtifact" class="secondary-button" :href="`/api/workbench/runs/${encodeURIComponent(run.run_id)}/public-artifact`" target="_blank" rel="noopener">{{ c('查看公开验收产物', 'View public verifier artifact') }}</a><RouterLink class="primary-button" :to="{ path: '/diagnosis', query: { experiment: run.experiment_id, candidate: route.query.candidate, run: run.run_id } }">{{ diagnosisLabel }}</RouterLink></div>
      <div class="run-id-strip run-context"><h3>{{ runName(run) }}</h3><span>{{ c('运行状态', 'Run lifecycle') }} <StatusBadge :value="run.status" context="run" localized /></span></div>
      <article class="panel outcome-panel"><div class="panel-header"><h3>{{ c('独立验收与 Agent 自报', 'Independent verification & agent claim') }}</h3><span class="muted">{{ c('两类记录，各自保留来源', 'Separate records with their own provenance') }}</span></div>
        <div v-if="claimConflict" class="conflict-banner">{{ c('独立任务验收未通过。Agent 消息保留原文，不能替代验收结论。', 'Independent task verification failed. The original agent message cannot replace the verdict.') }}</div>
        <div class="dual-evidence"><section class="verifier-column"><div class="panel-title"><h3>{{ c('独立验收（Verifier）', 'Independent verifier') }}</h3><StatusBadge :value="verifierStatus(run)" localized /></div><div class="verifier-score-box"><span>{{ c('已保存验收分数', 'Saved verifier score') }}</span><strong class="score-value" :class="{ 'fail-text': run.verifier_passed === false }"><EvidenceValue :evidence="run.verifier_score" localized /></strong></div><p>{{ run.verifier_passed === null ? c('当前记录不能确认任务已通过。', 'The current record does not establish a verified pass.') : c('任务结论依据已保存的独立验收记录。', 'The task verdict comes from the saved independent verification record.') }}</p><div class="source-box"><span class="original-label">{{ c('原始验收摘要', 'Original verifier summary') }}</span><p>{{ run.summary ?? c('未报告', 'Not reported') }}</p></div></section>
          <section class="agent-column"><div class="panel-title"><h3>{{ c('Agent 自报', 'Agent self-report') }}</h3><StatusBadge :value="agentMessage ? 'UNVERIFIED_CLAIM' : 'NOT_REPORTED'" localized /></div><div class="source-box"><span class="original-label">{{ c('原始 Agent 消息', 'Original agent message') }}</span><blockquote>{{ agentMessage ?? c('未报告', 'Not reported') }}</blockquote></div><p class="muted source-boundary">{{ run.provenance === 'FIXTURE_OFFLINE' ? c('固定 Fake 样例，不代表真实 Provider 或模型执行。', 'A fixed Fake fixture; no real provider or model execution is established.') : c('保存记录本身不认证 Provider 或模型来源。', 'A saved record alone does not authenticate provider or model provenance.') }}</p></section></div>
      </article>
      <div id="run-trace" class="panel"><div class="panel-header"><h3>{{ c('运行事件（Trace）与证据来源', 'Trace events & evidence provenance') }}</h3></div><p class="boundary-note">{{ c('文件变化事件（FILE_CHANGE）记录过程；最终工作区差异对照保存结果，两者含义不同。', 'FILE_CHANGE records a trace event; the final workspace diff compares saved content before and after the task. These have different meanings.') }}</p><PageState v-if="traceError" kind="error">{{ c('Trace 暂不可读取。独立验收记录仍保留；可重试读取事件。', 'Trace is unavailable. The verifier record is preserved; retry to load events.') }}<button class="secondary-button" @click="load">{{ c('重试', 'Retry') }}</button></PageState><TraceTimeline v-else-if="trace" :trace="trace" localized /></div>
      <details class="panel run-technical"><summary>{{ c('运行身份与配置', 'Run identity & configuration') }}</summary><TechnicalDetails :fields="[{ label: 'Run ID', value: run.run_id }, { label: 'Experiment ID', value: run.experiment_id }, { label: 'SHA256', value: run.evidence_digest }, { label: 'Slot ID', value: run.slot_id }]" /><div class="identity-grid">
        <dl><dt>{{ c('实验 / Cell / 任务版本', 'Experiment / Cell / task version') }}</dt><dd><RouterLink class="table-link" :to="`/experiments/${run.experiment_id}`">{{ run.experiment_id }}</RouterLink></dd><dd class="technical">{{ run.cell_id }} / {{ run.task_id }}@{{ run.task_version }}</dd><dt>{{ c('通道 / 重复 / 尝试', 'Lane / repeat / attempt') }}</dt><dd class="technical">{{ run.lane }} / {{ run.repeat_index }} / {{ run.attempt }}</dd></dl>
        <dl><dt>{{ c('请求模型', 'Requested model') }}</dt><dd>{{ run.requested_model ?? 'NOT_REPORTED' }}</dd><dt>{{ c('实际观察模型', 'Observed model') }}</dt><dd>{{ run.observed_model ?? 'NOT_REPORTED' }}</dd><dt>{{ c('Provider 路径', 'Provider route') }}</dt><dd>{{ run.provider_route ?? 'NOT_REPORTED' }}</dd></dl>
        <dl><dt>Harness / {{ c('版本', 'version') }}</dt><dd>{{ run.harness ?? 'NOT_REPORTED' }}@{{ run.harness_version ?? 'NOT_REPORTED' }}</dd><dt>{{ c('规范化 / 原始结果', 'Normalized / source outcome') }}</dt><dd><StatusBadge :value="run.normalized_outcome ?? 'NOT_REPORTED'" localized /></dd><dd>{{ run.source_outcome ?? 'NOT_REPORTED' }}</dd><dt>{{ c('可比性', 'Comparability') }}</dt><dd><StatusBadge :value="run.comparability ?? 'NOT_REPORTED'" localized /></dd></dl>
        <dl><dt>{{ c('Trace 覆盖', 'Trace coverage') }}</dt><dd><StatusBadge :value="run.trace_coverage ?? 'NOT_REPORTED'" localized /></dd><dt>{{ c('产物名称', 'Artifact name') }}</dt><dd>{{ run.artifact_name ?? 'NOT_REPORTED' }}</dd><dt>{{ c('证据摘要', 'Evidence digest') }}</dt><dd class="technical">{{ run.evidence_digest ?? 'NOT_REPORTED' }}</dd></dl>
      </div></details>
      <details class="panel"><summary>{{ c('已报告用量与配置限制', 'Reported usage & configuration limits') }}</summary><div class="metric-grid"><div v-for="(value, name) in { [c('耗时 · ms', 'Duration · ms')]: run.duration_ms, [c('输入 tokens', 'Input tokens')]: run.input_tokens, [c('输出 tokens', 'Output tokens')]: run.output_tokens, [c('已报告费用', 'Explicit cost')]: run.explicit_cost }" :key="name" class="metric-card"><span>{{ name }}</span><strong><EvidenceValue :evidence="value" localized /></strong></div></div><p class="muted">{{ c('缺失值不等于零。费用只展示已报告记录，不推算。', 'Missing values are not zero. Costs are reported as saved, never inferred.') }}</p><p class="technical">{{ run.comparability_reason_codes.join(' · ') || 'NOT_REPORTED' }}</p></details>
      <details class="panel"><summary>{{ c('查看标准化 API 证据原文', 'View normalized API source evidence') }}</summary><pre class="raw-evidence">{{ JSON.stringify({ run, trace: safeTrace(trace) }, null, 2) }}</pre><p class="muted">{{ c('下载仅包含安全 API 投影与标准化 Trace；私有路径与推理保留在服务端。', 'Downloads contain the safe API projection and normalized trace; private paths and reasoning stay server-side.') }}</p><a v-if="publicArtifact" class="secondary-button" :href="`/api/workbench/runs/${encodeURIComponent(run.run_id)}/public-artifact?download=true`">{{ c('下载原始验收产物', 'Download original verifier artifact') }}</a></details>
    </template>
  </section>
</template>
