<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { workbenchApi } from '@/api/client'
import TechnicalDetails from '@/components/TechnicalDetails.vue'
import { identityKey, runName } from '@/utils/displayIdentity'
import PageState from '@/components/PageState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import EvidenceValue from '@/components/EvidenceValue.vue'
import { copy as c } from '@/composables/visualLocale'
import { evidenceLabel } from '@/utils/evidenceLabels'
import { verifierStatus, downloadRun, eligibleDirection } from '@/utils/visualEvidence'
import type { PublicDemo, RunDetail, TraceResponse, DiagnosisReport, RegressionResponse } from '@/types/workbench'
const demo = ref<PublicDemo | null>(null)
const run = ref<RunDetail | null>(null)
const trace = ref<TraceResponse | null>(null)
const diagnosis = ref<DiagnosisReport | null>(null)
const comparison = ref<RegressionResponse | null>(null)
const loading = ref(true)
const supplementLoading = ref(false)
const error = ref('')
const supplementErrors = ref<string[]>([])
const agentMessage = computed(() => trace.value?.events.find(event => event.type === 'AGENT_MESSAGE')?.summary ?? null)
const clusters = computed(() => diagnosis.value?.cells.flatMap(cell => cell.task_families.flatMap(family => family.clusters)) ?? [])
let sequence = 0
onUnmounted(() => { sequence++ })
async function loadDetails(request?: number) {
  if (!demo.value || supplementLoading.value) return
  const version = request ?? ++sequence
  const identity = demo.value
  supplementLoading.value = true; supplementErrors.value = []
  // Every re-read invalidates its old result; each fresh stage settles independently.
  run.value = null; trace.value = null; diagnosis.value = null; comparison.value = null
  async function read<T>(stage: string, fetchRecord: () => Promise<T>, store: (value: T | null) => void) {
    try {
      const value = await fetchRecord()
      if (version === sequence) store(value)
    } catch {
      if (version === sequence) { store(null); supplementErrors.value.push(stage) }
    }
  }
  await Promise.all([
    read('run', () => workbenchApi.getRun(identity.failed_run_id), value => { run.value = value }),
    read('trace', () => workbenchApi.getTrace(identity.failed_run_id), value => { trace.value = value }),
    read('diagnosis', () => workbenchApi.getDiagnosis(identity.baseline_id), value => { diagnosis.value = value }),
    read('comparison', () => workbenchApi.compare(identity.baseline_id, identity.candidate_id, 'MODEL_COMPARISON'), value => { comparison.value = value }),
  ])
  if (version === sequence) supplementLoading.value = false
}
const stageLoading = (stage: string) => supplementLoading.value && !supplementErrors.value.includes(stage)
async function load() {
  const request = ++sequence
  loading.value = true; error.value = ''; demo.value = null; run.value = null; trace.value = null; diagnosis.value = null; comparison.value = null; supplementLoading.value = false; supplementErrors.value = []
  try {
    const result = await workbenchApi.getPublicDemo()
    if (request !== sequence) return
    if (!result.public_demo_ready) error.value = 'integrity'
    else demo.value = result
  } catch (failure) {
    if (request !== sequence) return
    const code = (failure as { response?: { data?: { error?: { code?: string } } } })?.response?.data?.error?.code
    error.value = code === 'DEMO_NOT_CONFIGURED' ? 'configuration' : 'integrity'
  } finally { if (request === sequence) loading.value = false }
  if (demo.value) void loadDetails(request)
}
onMounted(load)
</script>
<template>
  <section class="public-demo visual-demo" :aria-busy="loading || supplementLoading">
    <div class="demo-intro"><span class="guide-badge">{{ c('只读证据导览', 'READ-ONLY EVIDENCE WALKTHROUGH') }}</span><h2>{{ c('Agent 说完成了，独立验收怎么说？', "The agent says it's done. What does verification show?") }}</h2><p>{{ c('从交付结果出发，沿证据、诊断和候选对比继续调查。', 'Start with the outcome, then follow evidence, diagnosis and comparison.') }}</p></div>
    <PageState v-if="loading" kind="loading">{{ c('正在核对演示证据完整性…', 'Checking demo evidence integrity…') }}</PageState>
    <PageState v-else-if="error" kind="error">{{ error === 'configuration' ? c('此工作区尚未配置公开演示。', 'No public demo is configured for this workspace.') : c('演示证据暂不可用，完整性校验未通过。未展示替代结果。', 'Demo evidence is unavailable: integrity checks failed. No substitute results were shown.') }}<button class="secondary-button" @click="load">{{ c('重试', 'Retry') }}</button><RouterLink class="table-link" to="/analyst?example=offline">{{ c('查看离线调查案例', 'View offline investigation') }}</RouterLink></PageState>
    <template v-else-if="demo">
      <div class="demo-context"><StatusBadge :value="demo.provenance" localized /><span>{{ c('不启动 Agent 或调用模型', 'No agent starts or model calls') }}</span><span>{{ run ? runName(run) : c('公开演示 · 已保存运行', 'Public demo · Saved run') }}</span></div>
      <p v-if="supplementLoading" role="status" class="muted">{{ c('正在读取保存证据…', 'Loading saved evidence…') }}</p>
      <p v-if="supplementErrors.length" role="status" class="notice">{{ c('部分证据暂不可用，可重试读取。', 'Some evidence is unavailable. Retry to read it.') }}<button class="secondary-button" :disabled="supplementLoading" @click="loadDetails()">{{ c('重试阶段证据', 'Retry step evidence') }}</button></p>
      <ol class="demo-walkthrough" :aria-label="c('公开演示证据路径', 'Public demo evidence journey')">
        <li id="demo-step-2" class="core-step"><span class="step-number">01</span><article class="panel demo-step-card"><div class="step-heading"><h3>{{ c('Agent 自报与独立验收', 'Agent claim & independent verification') }}</h3><StatusBadge v-if="run" :value="verifierStatus(run)" localized /></div><div class="demo-verdict-grid">
          <div class="source-box"><span class="original-label">{{ c('Agent 消息 · 原文', 'Agent message · source') }}</span><blockquote v-if="trace">{{ agentMessage ?? c('未报告', 'Not reported') }}</blockquote><p v-else>{{ stageLoading('trace') ? c('读取中…', 'Loading…') : c('证据暂不可用，可打开详情或重试。', 'Evidence for this step is unavailable. Open the detailed view or retry later.') }}</p><small>{{ c('自报不作为验收依据', 'A claim is not verification evidence') }}</small></div>
          <div class="source-box"><span class="original-label">{{ c('独立 Verifier · 保存结果', 'Independent verifier · saved result') }}</span><template v-if="run"><strong class="demo-score" :class="{ 'fail-text': run.verifier_passed === false }"><EvidenceValue :evidence="run.verifier_score" localized /></strong><p>{{ run.summary ?? c('未报告', 'Not reported') }}</p></template><p v-else>{{ stageLoading('run') ? c('读取中…', 'Loading…') : c('证据暂不可用，可打开详情或重试。', 'Evidence for this step is unavailable. Open the detailed view or retry later.') }}</p></div>
        </div><div class="step-footer"><span class="muted">{{ c('结论依据保存的验收结果', 'Verdict from saved verification') }}</span><RouterLink class="primary-button" :to="{ path: `/runs/${demo.failed_run_id}`, query: { candidate: demo.candidate_id, from: '/demo' } }">{{ c('查看完整运行', 'View run details') }} →</RouterLink></div></article></li>
        <li id="demo-step-3"><span class="step-number">02</span><article class="panel demo-step-card"><div class="step-heading"><h3>{{ c('追溯失败证据', 'Trace failure evidence') }}</h3><RouterLink class="table-link" :to="{ path: '/diagnosis', query: { experiment: demo.baseline_id, candidate: demo.candidate_id, run: demo.failed_run_id } }">{{ c('阅读诊断', 'Open diagnosis') }} →</RouterLink></div><div v-if="diagnosis" class="demo-facts"><strong>{{ diagnosis.failure_run_count }} {{ c('条失败运行', 'failed runs') }}</strong><span v-for="cluster in clusters" :key="cluster.cluster_id">{{ evidenceLabel(cluster.failure_class) }} · {{ cluster.run_count }}</span><details><summary>{{ c('分类边界 · 原文', 'Classification boundary · source') }}</summary><p>{{ diagnosis.correlation_warning }}</p></details></div><p v-else>{{ stageLoading('diagnosis') ? c('读取中…', 'Loading…') : c('证据暂不可用，可打开详情或重试。', 'Evidence for this step is unavailable. Open the detailed view or retry later.') }}</p><p class="muted">{{ c('分类用于定位线索，不能单独证明根因。', 'Classification identifies leads; it does not establish root cause.') }}</p></article></li>
        <li id="demo-step-4"><span class="step-number">03</span><article class="panel demo-step-card"><div class="step-heading"><h3>{{ c('检查候选可比性', 'Check candidate comparability') }}</h3><RouterLink class="table-link" :to="{ path: '/regression', query: { baseline: demo.baseline_id, candidate: demo.candidate_id, run: demo.failed_run_id } }">{{ c('查看候选对比', 'View comparison') }} →</RouterLink></div><div v-if="comparison"><div v-for="item in comparison.comparisons" :key="`${item.baseline_cell_id}:${item.candidate_cell_id}`"><div class="toolbar"><StatusBadge :value="item.comparability" localized /><strong>{{ c('可比配对', 'Eligible pairs') }} {{ item.eligible_paired_observations }} / {{ item.paired_observations }}</strong><StatusBadge v-if="eligibleDirection(item) !== 'NOT_REPORTED'" :value="eligibleDirection(item)" localized /><span v-else>{{ c('暂不判断方向', 'No direction concluded') }}</span></div><ul class="compact-reasons"><li v-for="reason in item.reason_codes" :key="reason">{{ evidenceLabel(reason) === reason ? c('未分类约束，见技术详情', 'Unclassified constraint; see technical details') : evidenceLabel(reason) }}</li></ul><TechnicalDetails :fields="item.reason_codes.map(reason => ({ label: c('可比性原因', 'Comparability reason'), value: reason }))" /></div><p v-if="!comparison.comparisons.length">{{ c('未报告配置配对', 'No configuration pairs reported') }}</p></div><p v-else>{{ stageLoading('comparison') ? c('读取中…', 'Loading…') : c('证据暂不可用，可打开详情或重试。', 'Evidence for this step is unavailable. Open the detailed view or retry later.') }}</p></article></li>
      </ol>
      <div id="demo-step-5" class="panel demo-artifacts"><h3>{{ c('证据文件', 'Evidence files') }}</h3><div class="toolbar"><button class="secondary-button" :disabled="!run || supplementLoading" @click="run && downloadRun(run, trace)">{{ c('下载证据 JSON', 'Download safe evidence JSON') }}</button><a class="table-link" :href="`/api/workbench/runs/${encodeURIComponent(demo.failed_run_id)}/public-artifact`" target="_blank" rel="noopener">{{ c('查看公开验收产物', 'View public verifier artifact') }} ↗</a><a class="table-link" :href="`/api/workbench/runs/${encodeURIComponent(demo.failed_run_id)}/public-artifact?download=true`">{{ c('下载原始产物', 'Download original artifact') }}</a></div></div>
      <details id="demo-step-1" class="panel demo-identity"><summary>{{ c('来源、身份与公开边界', 'Provenance, identity & public boundaries') }}</summary><p>{{ c('固定 Fake 样例。摘要绑定核对内容一致性，不认证模型来源；仅公开获准的标准化证据和验收产物。', 'Fixed Fake evidence. Digests check content consistency, not model authenticity. Only allowlisted normalized evidence and artifacts are public.') }}</p><p>{{ demo.limitation }}</p><TechnicalDetails :fields="[{ label: 'Demo ID', value: demo.demo_id }, { label: 'Run ID', value: demo.failed_run_id }, { label: c('基线 Experiment ID', 'Baseline experiment ID'), value: demo.baseline_id }, { label: c('候选 Experiment ID', 'Candidate experiment ID'), value: demo.candidate_id }, { label: 'SHA256', value: demo.manifest_digest }, { label: c('生成时间', 'Generated at'), value: demo.generated_at }, { label: c('已保存运行 / 文件', 'Saved runs / files'), value: `${demo.run_count} / ${demo.artifact_file_count}` }]" /><RouterLink class="table-link" :to="{ path: `/experiments/${demo.baseline_id}`, query: { tab: 'runs', candidate: demo.candidate_id } }">{{ c('查看基线实验', 'View baseline experiment') }} →</RouterLink></details>
      <details v-if="demo.historical_integrity_failures.length" class="panel historical-unavailable"><summary>{{ c('历史 QA 证据不可用', 'Historical QA evidence unavailable') }}</summary><p>{{ c('历史原产物未恢复，原身份与失败结果仍保留；此演示不替换历史证据。', 'Historical artifacts remain unavailable. Original identities and failures are preserved; this demo does not replace them.') }}</p><ul><li v-for="id in demo.historical_integrity_failures" :key="id"><RouterLink :to="`/experiments/${id}`">{{ c('历史 QA 记录', 'Historical QA record') }} · {{ identityKey(id, demo.historical_integrity_failures) }}</RouterLink><TechnicalDetails :fields="[{ label: 'Experiment ID', value: id }]" /></li></ul></details>
    </template>
  </section>
</template>
