<script setup lang="ts">
import PageState from '@/components/PageState.vue'
import { nextTick, onUnmounted } from 'vue'
import { copy as c } from '@/composables/visualLocale'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { BadCaseExport, DiagnosisReport, ExperimentSummary } from '@/types/workbench'
import { experimentDisplayName } from '@/utils/evidenceCopy'

const experiments = ref<ExperimentSummary[]>([])
const route = useRoute()
const router = useRouter()
const selectedExperiment = ref('')
const report = ref<DiagnosisReport | null>(null)
const exported = ref<BadCaseExport | null>(null)
const loading = ref(true)
const diagnosisLoading = ref(false)
const error = ref('')
const exportBusy = ref(false)
const selection = ref('')
const rawOpen = ref(false)
const referenceOrigin = ref<HTMLElement | null>(null)
const rawEvidence = ref<HTMLElement | null>(null)
const copyState = ref<'idle' | 'copied' | 'failed'>('idle')
let requestSequence = 0
onUnmounted(() => { requestSequence++ })
const groups = computed(() => (report.value?.cells ?? []).flatMap(cell => cell.task_families.flatMap(family => family.clusters.map(cluster => ({ cell: cell.cell_id, family: family.task_family, cluster, key: `${cell.cell_id}:${family.task_family}:${cluster.cluster_id}` })))))
const selectedGroup = computed(() => groups.value.find(group => group.cluster.runs.some(run => run.run_id === selection.value)))
const selectedRun = computed(() => selectedGroup.value?.cluster.runs.find(run => run.run_id === selection.value))
const unmatchedRun = computed(() => typeof route.query.run === 'string' && !groups.value.some(group => group.cluster.runs.some(run => run.run_id === route.query.run)))
function reconcileSelection() {
 const requested = typeof route.query.run === 'string' ? route.query.run : ''
 selection.value = groups.value.some(group => group.cluster.runs.some(run => run.run_id === requested)) ? requested : requested ? '' : groups.value[0]?.cluster.runs[0]?.run_id ?? ''
 rawOpen.value = false; copyState.value = 'idle'; referenceOrigin.value = null
}
watch(() => route.query.run, reconcileSelection)
function selectRun(id: string) { selection.value = id; rawOpen.value = false; copyState.value = 'idle'; referenceOrigin.value = null; void router.push({ query: { ...route.query, experiment: selectedExperiment.value, run: id } }) }
async function locateReference(event: Event) { referenceOrigin.value = event.currentTarget as HTMLElement; rawOpen.value = true; await nextTick(); rawEvidence.value?.focus(); rawEvidence.value?.scrollIntoView?.({ block: 'center' }) }
function returnReference() { referenceOrigin.value?.focus(); referenceOrigin.value?.scrollIntoView?.({ block: 'center' }) }
async function copyId() { try { await navigator.clipboard.writeText(selection.value); copyState.value = 'copied' } catch { copyState.value = 'failed' } }

const selectedProvenance = computed(() => experiments.value.find(item => item.experiment_id === selectedExperiment.value)?.provenance ?? 'UNVERIFIED_SOURCE')
watch(() => route.query.experiment, async value => {
  if (typeof value !== 'string' || value === selectedExperiment.value) return
  selectedExperiment.value = value
  report.value = null; exported.value = null; selection.value = ''; rawOpen.value = false
  error.value = ''; diagnosisLoading.value = true
  const request = ++requestSequence
  if (!experiments.value.some(item => item.experiment_id === value)) {
    try {
      const linked = await workbenchApi.getExperiment(value)
      if (request !== requestSequence) return
      experiments.value.unshift(linked)
    } catch {
      if (request === requestSequence) { error.value = 'linked'; diagnosisLoading.value = false }
      return
    }
  }
  if (request === requestSequence) await loadDiagnosis()
})

async function loadDiagnosis() {
  if (!selectedExperiment.value) return
  const request = ++requestSequence
  diagnosisLoading.value = true
  report.value = null; selection.value = ''; rawOpen.value = false
  error.value = ''
  exported.value = null
  try { const loaded = await workbenchApi.getDiagnosis(selectedExperiment.value); if (request === requestSequence) { report.value = loaded; reconcileSelection() } }
  catch { if (request === requestSequence) { report.value = null; error.value = 'diagnosis' } }
  finally { if (request === requestSequence) diagnosisLoading.value = false }
}

async function exportBadCases() {
  if (!report.value || report.value.failure_run_count === 0 || diagnosisLoading.value || exportBusy.value) return
  const snapshot = report.value
  const provenance = selectedProvenance.value
  const request = requestSequence
  exportBusy.value = true
  try {
    const received = await workbenchApi.exportBadCases(snapshot.experiment_id)
    if (request !== requestSequence) return
    exported.value = received
    const safeExport = {
      experiment_id: exported.value.experiment_id,
      source_report_digest: snapshot.report_digest,
      backend_export_digest: exported.value.export_digest,
      experiment_provenance: provenance,
      persisted_case_count: exported.value.real_case_count,
      in_memory_synthetic_qualification_count: exported.value.synthetic_qualification_case_count,
      interpretation: provenance === 'FIXTURE_OFFLINE'
        ? 'Persisted keyless Fake fixture cases. No real Provider or model execution is established.'
        : 'Persisted, verified experiment records. Provider authenticity is a separate claim.',
      cases: exported.value.cases.map(item => ({
        ...item,
        origin: item.origin === 'IMMUTABLE_EXPERIMENT' ? 'PERSISTED_EXPERIMENT_RECORD' : item.origin,
        experiment_provenance: provenance,
      })),
    }
    const blob = new Blob([JSON.stringify(safeExport, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `samescale-badcases-${snapshot.experiment_id}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }
  catch { if (request === requestSequence) error.value = 'export' }
  finally { exportBusy.value = false }
}

onMounted(async () => {
  try {
    const response = await workbenchApi.listExperiments({ limit: 100 })
    experiments.value = response.items
    const requested = typeof route.query.experiment === 'string' ? route.query.experiment : ''
    if (requested && !response.items.some(item => item.experiment_id === requested)) {
      try { experiments.value.unshift(await workbenchApi.getExperiment(requested)) }
      catch { error.value = 'linked'; return }
    }
    selectedExperiment.value = requested || response.items[0]?.experiment_id || ''
    if (selectedExperiment.value) await loadDiagnosis()
  } catch { error.value = 'list' }
  finally { loading.value = false }
})
</script>

<template>
  <section class="evidence-page diagnosis-page">
    <div class="page-heading"><div><h2>{{ c('失败诊断', 'Failure diagnosis') }}</h2><p>{{ c('从失败模式定位到具体运行，区分已观察事实、待验证假设和证据限制。', 'Trace failure patterns to individual runs, separating observed facts, hypotheses, and evidence limits.') }}</p></div><StatusBadge value="READ_ONLY" localized /></div>
    <div class="diagnosis-toolbar panel"><label><span>{{ c('选择实验', 'Select experiment') }}</span><select v-model="selectedExperiment" :disabled="loading || exportBusy" :aria-label="c('诊断实验', 'Diagnosis experiment')" data-test="diagnosis-experiment" @change="router.push({ query: { ...route.query, experiment: selectedExperiment, run: undefined } }); loadDiagnosis()"><option v-for="experiment in experiments" :key="experiment.experiment_id" :value="experiment.experiment_id">{{ experimentDisplayName(experiment.name, experiment.provenance) }} · {{ experiment.experiment_id }}</option></select></label><RouterLink v-if="report && typeof route.query.candidate === 'string'" class="secondary-button" :to="{ path: '/regression', query: { baseline: report.experiment_id, candidate: route.query.candidate, run: selection || undefined } }">{{ c('查看候选对比', 'View comparison') }}</RouterLink><button class="primary-button" :disabled="!report || report.failure_run_count === 0 || diagnosisLoading || exportBusy" @click="exportBadCases">{{ exportBusy ? c('正在导出…', 'Exporting…') : c('下载失败案例 JSON', 'Download failure cases JSON') }}</button></div>
    <PageState v-if="loading || diagnosisLoading" kind="loading">{{ c('正在读取确定性诊断与失败簇…', 'Loading deterministic diagnosis and failure patterns…') }}</PageState>
    <PageState v-else-if="error && !report" kind="error">{{ c('诊断证据暂不可用或完整性校验未通过。未生成替代分析。', 'Diagnosis evidence is unavailable or failed integrity checks. No substitute analysis was generated.') }}<button class="secondary-button" @click="selectedExperiment ? loadDiagnosis() : router.go(0)">{{ c('重试', 'Retry') }}</button></PageState>
    <PageState v-else-if="!report" kind="empty">{{ c('暂无可读取的实验证据。请选择已有的已完成实验。', 'No experiment evidence is available. Select an existing completed experiment.') }}<RouterLink class="table-link" to="/experiments">{{ c('查看实验与运行', 'Browse experiments & runs') }}</RouterLink></PageState>
    <template v-else>
      <div class="diagnosis-summary"><StatusBadge :value="selectedProvenance" localized /><span>{{ c('失败运行', 'Failure runs') }} <strong>{{ report.failure_run_count }}</strong></span><span>{{ c('失败簇', 'Clusters') }} <strong>{{ groups.length }}</strong></span><span>{{ c('持久化运行记录', 'Persisted run records') }} <strong>{{ report.real_run_count }}</strong></span><span>{{ c('内存合成资格检查', 'Synthetic qualification') }} <strong>{{ report.synthetic_run_count }}</strong></span></div>
      <p class="boundary-note">{{ c('失败分类用于定位线索，不等于根因已被证明。保存记录不自动认证真实 Provider 调用。', 'Classification identifies leads; it does not establish root cause. Saved records do not automatically authenticate real provider execution.') }}</p>
      <p v-if="exported" class="notice diagnosis-export-result" role="status">{{ c('已下载持久化案例 / 合成资格案例', 'Downloaded persisted / synthetic qualification cases') }}: {{ exported.real_case_count }} / {{ exported.synthetic_qualification_case_count }}</p><PageState v-if="error" kind="error">{{ c('失败案例导出未通过后端校验。可以重试。', 'Failure-case export failed backend validation. You can retry.') }}</PageState>
      <PageState v-if="!report.failure_run_count" kind="empty">{{ c('当前实验没有已分类的失败运行；这不证明所有任务通过。', 'No classified failed runs were found. This does not prove that every task passed.') }}<RouterLink class="table-link" :to="`/experiments/${encodeURIComponent(selectedExperiment)}?tab=runs`">{{ c('查看实验运行', 'Inspect experiment runs') }}</RouterLink></PageState>
      <div v-else class="diagnosis-master-detail">
        <aside class="diagnosis-master"><div class="panel"><div class="panel-header"><h3>{{ c('失败模式', 'Failure patterns') }}</h3><small>{{ groups.length }}</small></div><div v-for="group in groups" :key="group.key" class="cluster-entry"><p class="technical cluster-context">{{ group.cell }} / {{ group.family }}</p><button class="cluster-button" :class="{ selected: selectedGroup?.key === group.key }" :aria-pressed="selectedGroup?.key === group.key" @click="selectRun(group.cluster.runs[0]?.run_id ?? '')"><strong>{{ group.cluster.failure_class }}</strong><span><StatusBadge :value="group.cluster.failure_scope" localized /><small>{{ group.cluster.run_count }} {{ c('条运行', 'runs') }}</small></span><code :title="group.cluster.cluster_id">{{ group.cluster.cluster_id }}</code></button></div></div>
          <div v-if="selectedGroup" class="panel"><div class="panel-header"><h3>{{ c('运行记录', 'Run records') }}</h3><small>{{ selectedGroup.cluster.runs.length }}</small></div><button v-for="item in selectedGroup.cluster.runs" :key="item.run_id" class="run-selection" :class="{ selected: selection === item.run_id }" :aria-pressed="selection === item.run_id" @click="selectRun(item.run_id)"><strong class="technical" :title="item.run_id">{{ item.run_id }}</strong><span>{{ item.task_id }}@{{ item.task_version }}</span><span><StatusBadge :value="item.verifier.status" localized /><code>{{ item.verifier.score === null ? 'NOT_REPORTED' : item.verifier.score.toFixed(2) }}</code></span></button></div>
          <div class="boundary-note"><strong>{{ c('分类与根因保持分离', 'Keep classification and cause separate') }}</strong><p>{{ c('聚类是定位线索；归因需要额外证据，不展示推测概率。', 'Clusters identify leads. Attribution needs further evidence; no invented probabilities are shown.') }}</p></div>
        </aside>
        <main class="diagnosis-detail"><PageState v-if="!selectedRun" kind="empty">{{ unmatchedRun ? c('链接中的运行不在当前诊断中。请在左侧选择已有记录。', 'The linked run is absent from this diagnosis. Select a saved record on the left.') : c('在左侧选择失败簇或运行，查看已有证据。', 'Select a failure pattern or run to inspect its saved evidence.') }}</PageState>
          <template v-else>
            <div class="panel selected-run-identity"><div class="panel-title"><h3>{{ c('当前运行的证据', 'Evidence for selected run') }}</h3><StatusBadge :value="selectedRun.verifier.status" localized /></div><code>{{ selectedRun.run_id }}</code><div class="toolbar"><button class="secondary-button" @click="copyId">{{ copyState === 'copied' ? c('已复制', 'Copied') : c('复制 ID', 'Copy ID') }}</button><RouterLink class="secondary-button" :to="{ path: `/runs/${selectedRun.run_id}`, query: { candidate: route.query.candidate } }">{{ c('打开运行证据', 'Open run evidence') }}</RouterLink></div><p v-if="copyState === 'failed'" role="status">{{ c('复制失败，请手动选取 ID。', 'Copy failed. Select the ID manually.') }}</p><small>{{ selectedRun.task_family }} · {{ selectedRun.harness }} · {{ selectedRun.origin }}</small></div>
            <article class="panel facts-panel"><div class="panel-header"><h3>{{ c('已观察事实', 'Observed facts') }}</h3><StatusBadge value="VERIFIED_FACT" localized /></div><div class="diagnosis-observations"><div><span>Verifier</span><strong>{{ selectedRun.verifier.status }} · {{ selectedRun.verifier.score === null ? 'NOT_REPORTED' : selectedRun.verifier.score.toFixed(2) }}</strong><small>{{ selectedRun.verifier.failure_subtype ?? selectedRun.verifier.sandbox_status ?? 'NOT_REPORTED' }}</small></div><div><span>{{ c('最终工作区差异', 'Final workspace diff') }}</span><strong>{{ selectedRun.workspace_diff.pattern === 'no-modification' ? c('未观察到最终工作区修改', 'No persisted workspace modification') : selectedRun.workspace_diff.pattern }}</strong><small>{{ selectedRun.workspace_diff.status }} · {{ selectedRun.workspace_diff.changed_paths.length }} {{ c('条路径记录', 'reported paths') }}</small></div><div><span>Trace</span><strong>{{ selectedRun.trace.pattern }}</strong><small>{{ selectedRun.trace.status }} · {{ selectedRun.trace.coverage ?? 'NOT_REPORTED' }}</small></div><div><span>{{ c('工具调用', 'Tool calls') }}</span><strong>{{ selectedRun.tool_calls.pattern }}</strong><small>{{ selectedRun.tool_calls.status }} · {{ selectedRun.tool_calls.count ?? 'NOT_REPORTED' }}</small></div></div>
              <p v-if="selectedRun.trace.events.some(event => event.type === 'FILE_CHANGE')" class="boundary-note">{{ c('已记录 FILE_CHANGE 事件；这不单独证明最终工作区已修改。', 'A FILE_CHANGE event was recorded; it does not itself prove a persisted workspace change.') }}</p>
              <article v-for="(attribution, index) in selectedRun.attributions.filter(item => item.kind === 'VERIFIED_FACT')" :key="index" class="attribution"><p class="original-label">{{ c('原始事实记录', 'Original fact record') }}</p><p>{{ attribution.statement }}</p><div class="evidence-references"><button v-for="reference in attribution.evidence_references" :key="reference" class="evidence-reference" @click="locateReference($event)">{{ reference }}</button></div><p v-if="attribution.caveat">{{ attribution.caveat }}</p><small class="technical">{{ attribution.causal_strength }}</small></article>
            </article>
            <article class="panel hypotheses-panel"><div class="panel-header"><h3>{{ c('待验证假设', 'Hypotheses to verify') }}</h3><StatusBadge value="HYPOTHESIS" localized /></div><p class="muted">{{ c('以下归因保留后端原文和相关性边界。', 'Attributions below preserve backend source text and correlation limits.') }}</p><article v-for="(attribution, index) in selectedRun.attributions.filter(item => item.kind === 'HYPOTHESIS')" :key="index" class="attribution"><p>{{ attribution.statement }}</p><p v-if="attribution.caveat" class="boundary-note">{{ attribution.caveat }}</p><small class="technical">{{ attribution.causal_strength }}</small><div class="evidence-references"><button v-for="reference in attribution.evidence_references" :key="reference" class="evidence-reference" @click="locateReference($event)">{{ reference }}</button></div></article><p v-if="!selectedRun.attributions.some(item => item.kind === 'HYPOTHESIS')">{{ c('当前运行未报告诊断假设。', 'No diagnostic hypothesis is reported for this run.') }}</p></article>
            <article class="panel"><div class="panel-header"><h3>{{ c('证据限制', 'Evidence limitations') }}</h3></div><div class="limitations-grid"><div class="boundary-note"><strong>{{ c('相关性边界 · 原文', 'Correlation boundary · source') }}</strong><p>{{ report.correlation_warning }}</p></div><div v-for="limitation in report.classification_limitations" :key="limitation" class="boundary-note"><p>{{ limitation }}</p></div></div></article>
            <details class="panel" :open="rawOpen" @toggle="rawOpen = ($event.target as HTMLDetailsElement).open"><summary>{{ c('引用来源与原始证据', 'Reference sources & raw evidence') }}</summary><div ref="rawEvidence" tabindex="-1"><p>{{ c('引用绑定于以下当前运行、Trace 摘要与原始聚类维度。', 'References are bound to the selected run, trace digest and original cluster dimensions below.') }}</p><button v-if="referenceOrigin" class="secondary-button" @click="returnReference">{{ c('返回引用处', 'Return to citation') }}</button><pre class="raw-evidence">{{ JSON.stringify({ experiment_id: report.experiment_id, report_digest: report.report_digest, cell: selectedGroup?.cell, task_family: selectedGroup?.family, cluster_id: selectedGroup?.cluster.cluster_id, dimensions: selectedGroup?.cluster.dimensions, run: selectedRun }, null, 2) }}</pre></div></details>
          </template>
        </main>
      </div>
      <details class="panel"><summary>{{ c('诊断报告身份', 'Diagnosis report identity') }}</summary><dl class="definition-list"><dt>{{ c('实验身份', 'Experiment identity') }}</dt><dd>{{ report.experiment_id }}</dd><dt>{{ c('计划摘要', 'Plan digest') }}</dt><dd class="technical">{{ report.plan_digest }}</dd><dt>{{ c('报告摘要', 'Report digest') }}</dt><dd class="technical">{{ report.report_digest }}</dd><dt>{{ c('聚类维度', 'Cluster dimensions') }}</dt><dd class="technical">{{ report.cluster_dimensions.join(', ') }}</dd></dl></details>
    </template>
  </section>
</template>
