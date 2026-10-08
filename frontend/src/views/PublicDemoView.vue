<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { workbenchApi } from '@/api/client'
import PageState from '@/components/PageState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import EvidenceValue from '@/components/EvidenceValue.vue'
import { copy as c } from '@/composables/visualLocale'
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
  <section class="public-demo visual-demo"><div class="demo-intro"><span class="guide-badge">{{ c('只读证据导览', 'READ-ONLY EVIDENCE WALKTHROUGH') }}</span><h2>{{ c('Agent 说完成了，独立验收怎么说？', "The agent says it's done. What does verification show?") }}</h2><p>{{ c('沿一组保存的离线样例，逐步查看声明、验收、失败诊断与候选对比。', 'Follow a saved offline fixture through claims, verification, diagnosis, and comparison.') }}</p></div>
    <PageState v-if="loading" kind="loading">{{ c('正在核对演示证据完整性…', 'Checking demo evidence integrity…') }}</PageState><PageState v-else-if="error" kind="error">{{ error === 'configuration' ? c('此工作区尚未配置公开演示。', 'No public demo is configured for this workspace.') : c('演示证据暂不可用，完整性校验未通过。未展示替代结果。', 'Demo evidence is unavailable: integrity checks failed. No substitute results were shown.') }}<button class="secondary-button" @click="load">{{ c('重试', 'Retry') }}</button><RouterLink class="table-link" to="/analyst?example=offline">{{ c('查看离线调查案例', 'View offline investigation') }}</RouterLink></PageState>
    <template v-else-if="demo"><div class="demo-scope-bar"><div class="toolbar"><StatusBadge :value="demo.provenance" localized /><StatusBadge value="READ_ONLY" localized /><span>{{ c('这里展示已保存的证据，不会启动 Agent 或调用真实模型。', 'This walkthrough uses saved evidence; it does not start an agent or call a real model.') }}</span></div><div class="toolbar"><a class="secondary-button" href="#demo-step-1">{{ c('从第 1 步阅读', 'Start at step 1') }}</a><a class="primary-button" href="#demo-step-2">{{ c('直接查看声明与验收', 'Jump to claim & verification') }}</a></div></div>
      <p v-if="supplementLoading" role="status" class="muted">{{ c('正在读取各阶段的保存证据…', 'Loading saved evidence for each step…') }}</p><p v-if="supplementErrors.length" role="status" class="notice">{{ c('部分阶段证据暂不可用。详情入口仍保留，可稍后重试。', 'Some step evidence is unavailable. Detail links remain available; retry later.') }}<button class="secondary-button" :disabled="supplementLoading" @click="loadDetails()">{{ c('重试阶段证据', 'Retry step evidence') }}</button></p>
      <ol class="demo-walkthrough" :aria-label="c('公开演示证据路径', 'Public demo evidence journey')">
        <li id="demo-step-1"><span class="step-number">01</span><article class="panel demo-step-card"><div class="step-heading"><span class="evidence-label">{{ c('来源与身份', 'PROVENANCE & IDENTITY') }}</span><StatusBadge :value="demo.provenance" localized /></div><h3>{{ c('确认证据来源', 'Check evidence provenance') }}</h3><p>{{ c('核对基线实验、运行身份与保存摘要。完整性检查绑定保存身份，不认证模型来源。', 'Review the baseline experiment, run identity, and saved digest. Integrity checks bind saved identities; they do not authenticate model provenance.') }}</p><dl class="demo-source-grid"><div><dt>{{ c('基线实验', 'Baseline experiment') }}</dt><dd>{{ demo.baseline_id }}</dd></div><div><dt>Run ID</dt><dd>{{ demo.failed_run_id }}</dd></div><div><dt>{{ c('已保存运行 / 文件', 'Saved runs / files') }}</dt><dd>{{ demo.run_count }} / {{ demo.artifact_file_count }}</dd></div><div><dt>{{ c('生成时间', 'Generated at') }}</dt><dd>{{ demo.generated_at }}</dd></div></dl><div class="step-footer"><code class="technical">{{ demo.manifest_digest }}</code><RouterLink class="table-link" :to="{ path: `/experiments/${demo.baseline_id}`, query: { tab: 'runs', candidate: demo.candidate_id } }">{{ c('查看基线实验', 'View baseline experiment') }} →</RouterLink></div></article></li>
        <li id="demo-step-2" class="core-step"><span class="step-number">02</span><article class="panel demo-step-card"><div class="step-heading"><span class="evidence-label">{{ c('两侧原始记录', 'CLAIM & VERIFICATION') }}</span><StatusBadge v-if="run" :value="verifierStatus(run)" localized /></div><h3>{{ c('对照 Agent 自报与独立验收', 'Compare agent claim and verification') }}</h3><p>{{ c('并列阅读两侧原始记录；Agent 自报并不等于验收通过。', 'Read both source records side by side. An agent claim is not a verified pass.') }}</p><div class="demo-verdict-grid"><div class="source-box"><span class="original-label">{{ c('原始 Agent 消息', 'Original agent message') }}</span><blockquote v-if="trace">{{ agentMessage ?? 'NOT_REPORTED' }}</blockquote><p v-else>{{ stageLoading('trace') ? c('读取中…', 'Loading…') : c('这一阶段的证据暂不可用，请打开详情核对或稍后重试。', 'Evidence for this step is unavailable. Open the detailed view or retry later.') }}</p><small>{{ c('消息原文 · 不作为验收依据', 'Source message · not verification evidence') }}</small></div><div class="source-box"><span class="original-label">{{ c('独立 Verifier · 保存的结果', 'Independent verifier · saved result') }}</span><template v-if="run"><strong class="demo-score" :class="{ 'fail-text': run.verifier_passed === false }"><EvidenceValue :evidence="run.verifier_score" localized /></strong><p>{{ run.summary ?? 'NOT_REPORTED' }}</p></template><p v-else>{{ stageLoading('run') ? c('读取中…', 'Loading…') : c('这一阶段的证据暂不可用，请打开详情核对或稍后重试。', 'Evidence for this step is unavailable. Open the detailed view or retry later.') }}</p></div></div><div class="step-footer"><span class="muted">{{ c('状态来自保存的 Verifier；不从 Agent 文字推断。', 'The verdict comes from saved verification, not agent text.') }}</span><RouterLink class="primary-button" :to="{ path: `/runs/${demo.failed_run_id}`, query: { candidate: demo.candidate_id } }">{{ c('查看完整运行', 'View run details') }} →</RouterLink></div></article></li>
        <li id="demo-step-3"><span class="step-number">03</span><article class="panel demo-step-card"><div class="step-heading"><span class="evidence-label">{{ c('事实与假设', 'FACTS & HYPOTHESES') }}</span></div><h3>{{ c('追溯失败证据', 'Trace failure evidence') }}</h3><p>{{ c('查看已有失败分类及证据引用，保留根因的不确定性。', 'Inspect recorded failure classifications and references without overstating root cause.') }}</p><div v-if="diagnosis" class="source-box"><div class="toolbar"><strong>{{ c('失败运行 / 簇', 'Failure runs / clusters') }}: {{ diagnosis.failure_run_count }} / {{ clusters.length }}</strong><span v-for="cluster in clusters" :key="cluster.cluster_id">{{ cluster.failure_class }} · {{ cluster.run_count }}</span></div><p class="original-label">{{ c('原始相关性限制', 'Original correlation limitation') }}</p><p>{{ diagnosis.correlation_warning }}</p></div><p v-else>{{ stageLoading('diagnosis') ? c('读取中…', 'Loading…') : c('这一阶段的证据暂不可用，请打开详情核对或稍后重试。', 'Evidence for this step is unavailable. Open the detailed view or retry later.') }}</p><div class="step-footer"><span>{{ c('失败分类不等于根因证明', 'Failure classification does not establish root cause') }}</span><RouterLink class="table-link" :to="{ path: '/diagnosis', query: { experiment: demo.baseline_id, candidate: demo.candidate_id, run: demo.failed_run_id } }">{{ c('阅读诊断', 'Open diagnosis') }} →</RouterLink></div></article></li>
        <li id="demo-step-4"><span class="step-number">04</span><article class="panel demo-step-card"><div class="step-heading"><span class="evidence-label">{{ c('可比性与边界', 'COMPARABILITY & LIMITS') }}</span><StatusBadge v-if="comparison?.comparisons[0]" :value="comparison.comparisons[0].comparability" localized /></div><h3>{{ c('检查候选可比性', 'Check comparison conditions') }}</h3><p>{{ c('先看可比性和缺失原因，再理解描述性差异。', 'Review comparability and missing conditions before interpreting descriptive differences.') }}</p><div v-if="comparison" class="source-box"><div v-for="item in comparison.comparisons" :key="`${item.baseline_cell_id}:${item.candidate_cell_id}`"><div class="toolbar"><StatusBadge :value="item.comparability" localized /><strong>{{ c('可比配对', 'Eligible pairs') }}: {{ item.eligible_paired_observations }} / {{ item.paired_observations }}</strong><code>{{ eligibleDirection(item) }}</code></div><p class="technical">{{ item.reason_codes.join(' · ') || 'NOT_REPORTED' }}</p></div><p v-if="!comparison.comparisons.length">{{ c('未报告 Cell 配对', 'No cell pairs reported') }}</p></div><p v-else>{{ stageLoading('comparison') ? c('读取中…', 'Loading…') : c('这一阶段的证据暂不可用，请打开详情核对或稍后重试。', 'Evidence for this step is unavailable. Open the detailed view or retry later.') }}</p><div class="step-footer"><span>{{ c('不可比时不判断候选胜出', 'Incomparable evidence does not establish a winner') }}</span><RouterLink class="table-link" :to="{ path: '/regression', query: { baseline: demo.baseline_id, candidate: demo.candidate_id, run: demo.failed_run_id } }">{{ c('查看候选对比', 'View comparison') }} →</RouterLink></div></article></li>
        <li id="demo-step-5"><span class="step-number">05</span><article class="panel demo-step-card"><div class="step-heading"><span class="evidence-label">{{ c('产物与公开边界', 'ARTIFACTS & PUBLIC BOUNDARY') }}</span><StatusBadge value="READ_ONLY" localized /></div><h3>{{ c('查看公开验收产物', 'View public verifier artifacts') }}</h3><p>{{ c('仅提供已校验、获准公开的产物；私有原始记录不会公开。', 'Only verified, allowlisted artifacts are public; private native records remain withheld.') }}</p><div class="source-box"><p>{{ c('公开产物由服务端白名单和摘要检查控制。下载安全 JSON 只包含标准化 API 投影。', 'The server enforces artifact allowlists and digest checks. Safe JSON downloads contain normalized API projections only.') }}</p><p class="technical">{{ run?.evidence_digest ?? 'NOT_REPORTED' }}</p></div><div class="step-footer"><button class="secondary-button" :disabled="!run || supplementLoading" @click="run && downloadRun(run, trace)">{{ c('下载安全证据 JSON', 'Download safe evidence JSON') }}</button><a class="table-link" :href="`/api/workbench/runs/${encodeURIComponent(demo.failed_run_id)}/public-artifact`" target="_blank" rel="noopener">{{ c('打开公开产物', 'Open public artifact') }} ↗</a><a class="secondary-button" :href="`/api/workbench/runs/${encodeURIComponent(demo.failed_run_id)}/public-artifact?download=true`">{{ c('下载原始验收产物', 'Download original verifier artifact') }}</a></div></article></li>
      </ol>
      <details class="panel demo-identity" :aria-label="c('演示证据来源', 'Demo evidence provenance')"><summary>{{ c('完整来源与证据限制', 'Full provenance & evidence limits') }}</summary><dl class="definition-list"><dt>Demo ID</dt><dd class="technical">{{ demo.demo_id }}</dd><dt>{{ c('清单摘要', 'Manifest digest') }}</dt><dd class="technical">{{ demo.manifest_digest }}</dd><dt>{{ c('原始来源限制', 'Original provenance limitation') }}</dt><dd>{{ demo.limitation }}</dd></dl><p>{{ c('公共实例只读：配置修改与执行已禁用；无需账号或 Provider 凭据。', 'Public browsing is read-only: configuration and execution are disabled; no account or provider credential is required.') }}</p></details>
      <details v-if="demo.historical_integrity_failures.length" class="panel historical-unavailable"><summary>{{ c('历史 QA 证据不可用', 'Historical QA evidence unavailable') }}</summary><p>{{ c('原 QA 记录及摘要仍保留，原产物未恢复。本演示使用独立的新证据身份，不替换历史失败结果。', 'Historical QA records and digests remain preserved; their artifacts have not been restored. This demo has a separate identity and does not replace historical failures.') }}</p><ul><li v-for="id in demo.historical_integrity_failures" :key="id"><RouterLink :to="`/experiments/${id}`">{{ id }}</RouterLink></li></ul></details>
    </template>
  </section>
</template>
