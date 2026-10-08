<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { workbenchApi } from '@/api/client'
import EvidenceValue from '@/components/EvidenceValue.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import TraceTimeline from '@/components/TraceTimeline.vue'
import PageState from '@/components/PageState.vue'
import { copy as c } from '@/composables/visualLocale'
import { safeTrace, verifierStatus, downloadRun } from '@/utils/visualEvidence'
import type { RunDetail, TraceResponse } from '@/types/workbench'
const route = useRoute()
const run = ref<RunDetail | null>(null)
const trace = ref<TraceResponse | null>(null)
const loading = ref(true)
const error = ref(false)
const traceError = ref(false)
const publicArtifact = ref(false)
const copyState = ref<'idle' | 'copied' | 'failed'>('idle')
const runId = computed(() => String(route.params.runId))
const diagnosisLabel = computed(() => run.value?.verifier_passed === false ? c('查看失败诊断', 'View failure diagnosis') : run.value?.verifier_passed === true ? c('查看实验诊断', 'View experiment diagnosis') : c('查看诊断记录', 'View diagnosis records'))
const agentMessage = computed(() => trace.value?.events.find(event => event.type === 'AGENT_MESSAGE')?.summary ?? null)
// This is a reading hint, not a semantic validation of the agent's free text.
const claimConflict = computed(() => run.value?.verifier_passed === false && !!agentMessage.value && /success|pass|done|implement/i.test(agentMessage.value))
let sequence = 0
onUnmounted(() => { sequence++ })
async function load() {
  const request = ++sequence; const id = runId.value
  loading.value = true; error.value = false; traceError.value = false; run.value = null; trace.value = null; publicArtifact.value = false; copyState.value = 'idle'
  const records = await Promise.allSettled([workbenchApi.getRun(id), workbenchApi.getTrace(id)])
  if (request !== sequence) return
  const [runResult, traceResult] = records
  if (runResult.status === 'fulfilled') run.value = runResult.value
  else error.value = true
  if (traceResult.status === 'fulfilled') trace.value = traceResult.value
  else traceError.value = true
  loading.value = false
  // A ready demo manifest supplies the supported artifact identity. The server remains the authority.
  if (run.value) {
    try {
      const demo = await workbenchApi.getPublicDemo()
      if (request !== sequence || !demo.public_demo_ready || ![demo.baseline_id, demo.candidate_id].includes(run.value?.experiment_id ?? '')) return
      const response = await fetch(`/api/workbench/runs/${encodeURIComponent(id)}/public-artifact`)
      // Consume the allowlisted response so the browser can finish the request.
      await response.arrayBuffer()
      if (request === sequence) publicArtifact.value = response.ok
    }
    catch { /* No artifact permission is inferred from a run ID or prefix. */ }
  }
}
async function copyId() { try { await navigator.clipboard.writeText(runId.value); copyState.value = 'copied' } catch { copyState.value = 'failed' } }
watch(runId, load, { immediate: true })
</script>
<template>
  <section class="evidence-page run-page">
    <div class="page-heading"><div><h2>{{ c('运行证据', 'Run evidence') }}</h2><p>{{ c('先看独立验收，再核对 Agent 自报与运行事件。', 'Start with independent verification, then inspect agent claims and trace events.') }}</p></div><StatusBadge value="READ_ONLY" localized /></div>
    <PageState v-if="loading" kind="loading">{{ c('正在读取已保存运行证据…', 'Loading saved run evidence…') }}</PageState>
    <PageState v-else-if="error || !run" kind="error"><span>{{ c('运行证据暂不可用或完整性校验未通过；未展示替代记录。', 'Run evidence is unavailable or failed integrity checks. No substitute record is shown.') }}</span><button class="secondary-button" @click="load">{{ c('重试', 'Retry') }}</button></PageState>
    <template v-else>
      <div class="panel run-toolbar toolbar"><RouterLink class="secondary-button" :to="{ path: `/experiments/${run.experiment_id}`, query: { tab: 'runs' } }">{{ c('返回实验运行', 'Back to experiment runs') }}</RouterLink><StatusBadge :value="run.provenance ?? 'UNVERIFIED_SOURCE'" localized /><button class="secondary-button" @click="downloadRun(run, trace)">{{ c('下载安全证据 JSON', 'Download safe evidence JSON') }}</button><a v-if="publicArtifact" class="secondary-button" :href="`/api/workbench/runs/${encodeURIComponent(run.run_id)}/public-artifact`" target="_blank" rel="noopener">{{ c('查看公开验收产物', 'View public verifier artifact') }}</a><RouterLink class="primary-button" :to="{ path: '/diagnosis', query: { experiment: run.experiment_id, candidate: route.query.candidate, run: run.run_id } }">{{ diagnosisLabel }}</RouterLink></div>
      <div class="run-id-strip panel"><span class="evidence-label">RUN_ID</span><code>{{ run.run_id }}</code><button class="secondary-button" @click="copyId">{{ copyState === 'copied' ? c('已复制', 'Copied') : c('复制 ID', 'Copy ID') }}</button><span v-if="copyState === 'failed'" role="status">{{ c('复制失败，请选取上方 ID 手动复制。', 'Copy failed. Select the ID above and copy it manually.') }}</span><StatusBadge :value="run.status" localized /></div>
      <article class="panel outcome-panel"><div class="panel-header"><h3>{{ c('独立验收与 Agent 自报', 'Independent verification & agent claim') }}</h3><span class="muted">{{ c('两类记录，各自保留来源', 'Separate records with their own provenance') }}</span></div>
        <div v-if="claimConflict" class="conflict-banner">{{ c('Agent 消息可能声称成功，但独立验收未通过。请对照原文，不将关键词提示当作语义验证。', 'The agent message may claim success, while independent verification failed. Inspect the source text; keyword hints are not semantic validation.') }}</div>
        <div class="dual-evidence"><section class="verifier-column"><div class="panel-title"><h3>{{ c('独立验收（Verifier）', 'Independent verifier') }}</h3><StatusBadge :value="verifierStatus(run)" localized /></div><div class="verifier-score-box"><span>{{ c('已保存验收分数', 'Saved verifier score') }}</span><strong class="score-value" :class="{ 'fail-text': run.verifier_passed === false }"><EvidenceValue :evidence="run.verifier_score" localized /></strong></div><p>{{ run.verifier_passed === false ? c('最终工作区未通过独立任务验收。', 'The final workspace failed independent task verification.') : run.verifier_passed === true ? c('已保存的独立任务验收结果为通过。', 'The saved independent task verdict is a pass.') : c('当前记录不能确认任务已通过。', 'The current record does not establish a verified pass.') }}</p><div class="source-box"><span class="original-label">{{ c('原始验收摘要', 'Original verifier summary') }}</span><p>{{ run.summary ?? 'NOT_REPORTED' }}</p></div></section>
          <section class="agent-column"><div class="panel-title"><h3>{{ c('Agent 自报', 'Agent self-report') }}</h3><StatusBadge :value="agentMessage ? 'UNVERIFIED_CLAIM' : 'NOT_REPORTED'" localized /></div><div class="source-box"><span class="original-label">{{ c('原始 Agent 消息', 'Original agent message') }}</span><blockquote>{{ agentMessage ?? 'NOT_REPORTED' }}</blockquote></div><div class="boundary-note"><strong>{{ c('自报不能替代任务验收', 'A claim cannot replace verification') }}</strong><p>{{ c('消息是运行事件中的原文；独立验收结果由保存的 Verifier 记录决定。', 'The message is source text from a trace event. The saved verifier record determines the independent verdict.') }}</p></div><p class="muted">{{ run.provenance === 'FIXTURE_OFFLINE' ? c('固定 Fake 样例，不代表真实 Provider 或模型执行。', 'A fixed Fake fixture; no real provider or model execution is established.') : c('保存记录本身不认证 Provider 或模型来源。', 'A saved record alone does not authenticate provider or model provenance.') }}</p></section></div>
      </article>
      <div id="run-trace" class="panel"><div class="panel-header"><h3>{{ c('运行事件（Trace）与证据来源', 'Trace events & evidence provenance') }}</h3><a href="#run-trace" class="table-link">Trace</a></div><p class="boundary-note">{{ c('FILE_CHANGE 仅表示文件变化事件，不单独证明最终工作区已修改。私有原生记录与推理内容不公开。', 'FILE_CHANGE records an event; it does not establish a persisted workspace change. Private native records and reasoning are withheld.') }}</p><PageState v-if="traceError" kind="error">{{ c('Trace 暂不可读取。独立验收记录仍保留；可重试读取事件。', 'Trace is unavailable. The verifier record is preserved; retry to load events.') }}<button class="secondary-button" @click="load">{{ c('重试', 'Retry') }}</button></PageState><TraceTimeline v-else-if="trace" :trace="trace" localized /></div>
      <div class="panel"><div class="panel-header"><h3>{{ c('运行身份与来源', 'Run identity & provenance') }}</h3></div><div class="identity-grid">
        <dl><dt>{{ c('实验 / Cell / 任务版本', 'Experiment / Cell / task version') }}</dt><dd><RouterLink class="table-link" :to="`/experiments/${run.experiment_id}`">{{ run.experiment_id }}</RouterLink></dd><dd class="technical">{{ run.cell_id }} / {{ run.task_id }}@{{ run.task_version }}</dd><dt>{{ c('通道 / 重复 / 尝试', 'Lane / repeat / attempt') }}</dt><dd class="technical">{{ run.lane }} / {{ run.repeat_index }} / {{ run.attempt }}</dd></dl>
        <dl><dt>{{ c('请求模型', 'Requested model') }}</dt><dd>{{ run.requested_model ?? 'NOT_REPORTED' }}</dd><dt>{{ c('实际观察模型', 'Observed model') }}</dt><dd>{{ run.observed_model ?? 'NOT_REPORTED' }}</dd><dt>{{ c('Provider 路径', 'Provider route') }}</dt><dd>{{ run.provider_route ?? 'NOT_REPORTED' }}</dd></dl>
        <dl><dt>Harness / {{ c('版本', 'version') }}</dt><dd>{{ run.harness ?? 'NOT_REPORTED' }}@{{ run.harness_version ?? 'NOT_REPORTED' }}</dd><dt>{{ c('规范化 / 原始结果', 'Normalized / source outcome') }}</dt><dd><StatusBadge :value="run.normalized_outcome ?? 'NOT_REPORTED'" localized /></dd><dd>{{ run.source_outcome ?? 'NOT_REPORTED' }}</dd><dt>{{ c('可比性', 'Comparability') }}</dt><dd><StatusBadge :value="run.comparability ?? 'NOT_REPORTED'" localized /></dd></dl>
        <dl><dt>{{ c('Trace 覆盖', 'Trace coverage') }}</dt><dd><StatusBadge :value="run.trace_coverage ?? 'NOT_REPORTED'" localized /></dd><dt>{{ c('产物名称', 'Artifact name') }}</dt><dd>{{ run.artifact_name ?? 'NOT_REPORTED' }}</dd><dt>{{ c('证据摘要', 'Evidence digest') }}</dt><dd class="technical">{{ run.evidence_digest ?? 'NOT_REPORTED' }}</dd></dl>
      </div></div>
      <details class="panel"><summary>{{ c('已报告用量与配置限制', 'Reported usage & configuration limits') }}</summary><div class="metric-grid"><div v-for="(value, name) in { [c('耗时 · ms', 'Duration · ms')]: run.duration_ms, [c('输入 tokens', 'Input tokens')]: run.input_tokens, [c('输出 tokens', 'Output tokens')]: run.output_tokens, [c('已报告费用', 'Explicit cost')]: run.explicit_cost }" :key="name" class="metric-card"><span>{{ name }}</span><strong><EvidenceValue :evidence="value" localized /></strong></div></div><p class="muted">{{ c('缺失值不等于零。费用只展示已报告记录，不推算。', 'Missing values are not zero. Costs are reported as saved, never inferred.') }}</p><p class="technical">{{ run.comparability_reason_codes.join(' · ') || 'NOT_REPORTED' }}</p></details>
      <details class="panel"><summary>{{ c('查看标准化 API 证据原文', 'View normalized API source evidence') }}</summary><pre class="raw-evidence">{{ JSON.stringify({ run, trace: safeTrace(trace) }, null, 2) }}</pre><p class="muted">{{ c('下载仅包含安全 API 投影与标准化 Trace；私有路径与推理保留在服务端。', 'Downloads contain the safe API projection and normalized trace; private paths and reasoning stay server-side.') }}</p><a v-if="publicArtifact" class="secondary-button" :href="`/api/workbench/runs/${encodeURIComponent(run.run_id)}/public-artifact?download=true`">{{ c('下载原始验收产物', 'Download original verifier artifact') }}</a></details>
    </template>
  </section>
</template>
