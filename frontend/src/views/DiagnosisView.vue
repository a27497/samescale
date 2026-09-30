<script setup lang="ts">
import PageState from '@/components/PageState.vue'
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

const clusterCount = computed(() => report.value?.cells.reduce(
  (cellTotal, cell) => cellTotal + cell.task_families.reduce(
    (familyTotal, family) => familyTotal + family.clusters.length,
    0,
  ),
  0,
) ?? 0)
const crossCellPatterns = computed(() => {
  const grouped = new Map<string, { failure: string; task: string; verifier: string; cells: Set<string>; runs: number }>()
  for (const cell of report.value?.cells ?? []) for (const family of cell.task_families) for (const cluster of family.clusters) {
    const current = grouped.get(cluster.cluster_id) ?? { failure: cluster.failure_class, task: cluster.dimensions.task ?? 'UNKNOWN', verifier: cluster.dimensions.verifier_signature ?? 'NOT_REPORTED', cells: new Set<string>(), runs: 0 }
    current.cells.add(cell.cell_id); current.runs += cluster.run_count; grouped.set(cluster.cluster_id, current)
  }
  return [...grouped.values()].sort((a, b) => b.runs - a.runs)
})
const selectedProvenance = computed(() => experiments.value.find(item => item.experiment_id === selectedExperiment.value)?.provenance ?? 'UNVERIFIED_SOURCE')
watch(() => route.query.experiment, value => {
  if (typeof value === 'string' && value !== selectedExperiment.value && experiments.value.some(item => item.experiment_id === value)) {
    selectedExperiment.value = value
    void loadDiagnosis()
  }
})

async function loadDiagnosis() {
  if (!selectedExperiment.value) return
  diagnosisLoading.value = true
  error.value = ''
  exported.value = null
  try { report.value = await workbenchApi.getDiagnosis(selectedExperiment.value) }
  catch { report.value = null; error.value = 'Diagnosis evidence is unavailable or failed integrity validation.' }
  finally { diagnosisLoading.value = false }
}

async function exportBadCases() {
  if (!report.value) return
  try {
    exported.value = await workbenchApi.exportBadCases(report.value.experiment_id)
    const safeExport = {
      experiment_id: exported.value.experiment_id,
      source_report_digest: report.value.report_digest,
      backend_export_digest: exported.value.export_digest,
      experiment_provenance: selectedProvenance.value,
      persisted_case_count: exported.value.real_case_count,
      in_memory_synthetic_qualification_count: exported.value.synthetic_qualification_case_count,
      interpretation: selectedProvenance.value === 'FIXTURE_OFFLINE'
        ? 'Persisted keyless Fake fixture cases. No real Provider or model execution is established.'
        : 'Persisted, verified experiment records. Provider authenticity is a separate claim.',
      cases: exported.value.cases.map(item => ({
        ...item,
        origin: item.origin === 'IMMUTABLE_EXPERIMENT' ? 'PERSISTED_EXPERIMENT_RECORD' : item.origin,
        experiment_provenance: selectedProvenance.value,
      })),
    }
    const blob = new Blob([JSON.stringify(safeExport, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `samescale-badcases-${report.value.experiment_id}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }
  catch { error.value = 'BadCase export failed backend validation.' }
}

onMounted(async () => {
  try {
    const response = await workbenchApi.listExperiments({ limit: 100 })
    experiments.value = response.items
    const requested = typeof route.query.experiment === 'string' ? route.query.experiment : ''
    if (requested && !response.items.some(item => item.experiment_id === requested)) {
      try { experiments.value.unshift(await workbenchApi.getExperiment(requested)) }
      catch { error.value = 'The linked experiment is unavailable or failed integrity validation.'; return }
    }
    selectedExperiment.value = requested || response.items[0]?.experiment_id || ''
    if (selectedExperiment.value) await loadDiagnosis()
  } catch { error.value = 'Experiments are unavailable.' }
  finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <h2>Failure Diagnosis</h2>
        <p>Backend-derived clusters over immutable evidence. The browser does not infer failures.</p>
      </div>
      <span class="status-pill neutral">Saved evidence analysis</span>
    </div>

    <div class="diagnosis-warning">
      <strong>Correlation boundary</strong>
      <span>{{ report?.correlation_warning ?? 'Trace correlation is not causality; only controlled ablation can strengthen attribution.' }}</span>
    </div>
    <ul v-if="report" class="diagnosis-limitations" aria-label="Diagnosis limitations">
      <li v-for="limitation in report.classification_limitations" :key="limitation">{{ limitation }}</li>
    </ul>

    <div class="diagnosis-toolbar">
      <label>
        Experiment
        <select v-model="selectedExperiment" aria-label="Diagnosis experiment" @change="router.push({ query: { experiment: selectedExperiment } }); loadDiagnosis()">
          <option v-for="experiment in experiments" :key="experiment.experiment_id" :value="experiment.experiment_id">
            {{ experimentDisplayName(experiment.name, experiment.provenance) }} · {{ experiment.experiment_id }}
          </option>
        </select>
      </label>
      <RouterLink v-if="report && typeof route?.query?.candidate === 'string'" class="secondary-button" :to="{ path: '/regression', query: { baseline: report.experiment_id, candidate: route.query.candidate, run: route.query.run } }">Compare candidate →</RouterLink>
      <button class="primary-button" :disabled="!report || report.failure_run_count === 0" @click="exportBadCases">Download BadCases JSON</button>
    </div>

    <PageState v-if="loading || diagnosisLoading" kind="loading">Building deterministic clusters…</PageState>
    <PageState v-else-if="error && !report" kind="error">{{ error }}</PageState>
    <PageState v-else-if="!report" kind="empty">No experiment evidence is available. Create or select a completed experiment to inspect failure evidence.</PageState>
    <template v-else>
      <div class="notice">Source: {{ selectedProvenance }}. {{ selectedProvenance === 'FIXTURE_OFFLINE' ? 'This is a keyless Fake fixture run, not a real Provider or model execution.' : 'Persisted evidence does not by itself authenticate the Provider or model.' }}</div>
      <div class="metric-grid diagnosis-metrics">
        <div class="metric-card"><span>Failure runs</span><strong class="value">{{ report.failure_run_count }}</strong></div>
        <div class="metric-card"><span>Clusters</span><strong class="value">{{ clusterCount }}</strong></div>
        <div class="metric-card"><span>Persisted run records</span><strong class="value">{{ report.real_run_count }}</strong></div>
        <div class="metric-card"><span>In-memory synthetic qualification</span><strong class="value">{{ report.synthetic_run_count }}</strong></div>
      </div>

      <div v-if="exported" class="notice diagnosis-export-result">
        Downloaded {{ exported.real_case_count }} persisted BadCases and {{ exported.synthetic_qualification_case_count }} synthetic qualification cases.
        Saved records remain subject to the experiment provenance above; a persisted case is not automatically a real Provider run.
      </div>
      <PageState v-if="error" kind="error">{{ error }}</PageState>

      <div v-if="crossCellPatterns.length" class="panel"><div class="panel-title"><h3>Failure patterns across cells</h3><span class="muted">Grouped by task, verifier signature, final workspace, trace and tool pattern; correlation only.</span></div><div class="diagnosis-pattern-grid"><article v-for="pattern in crossCellPatterns" :key="`${pattern.task}:${pattern.verifier}:${pattern.failure}`" class="panel"><strong>{{ pattern.failure }}</strong><p>{{ pattern.task }} · {{ pattern.verifier }}</p><small>{{ pattern.runs }} runs across {{ [...pattern.cells].join(', ') }}</small></article></div></div>
      <PageState v-if="!report.failure_run_count" kind="empty">No failed runs in this experiment. Open a run to inspect its verified outcome, or choose another experiment.</PageState>
      <div class="diagnosis-tree">
        <details v-for="cell in report.cells" :key="cell.cell_id" open class="diagnosis-level diagnosis-cell">
          <summary><span>Experiment → Cell</span><strong>{{ cell.cell_id }}</strong></summary>
          <details v-for="family in cell.task_families" :key="family.task_family" open class="diagnosis-level">
            <summary><span>Task family</span><strong>{{ family.task_family }}</strong></summary>
            <details v-for="cluster in family.clusters" :key="cluster.cluster_id" class="diagnosis-level diagnosis-cluster">
              <summary>
                <span>Failure cluster</span>
                <strong>{{ cluster.failure_class }}</strong>
                <StatusBadge :value="cluster.failure_scope" />
                <small>{{ cluster.run_count }} runs</small>
              </summary>
              <div class="cluster-dimensions">
                <code v-for="(value, key) in cluster.dimensions" :key="key">{{ key }}={{ value }}</code>
              </div>
              <article v-for="run in cluster.runs" :key="run.run_id" class="diagnosis-run">
                <header><strong>Run · {{ run.run_id }}</strong><RouterLink :to="`/runs/${run.run_id}`">Open evidence →</RouterLink></header>
                <div class="diagnosis-drilldown">
                  <div><span>Trace</span><strong>{{ run.trace.pattern }}</strong><small>{{ run.trace.status }} · {{ run.trace.coverage ?? 'NOT_REPORTED' }}</small></div>
                  <div><span>Final workspace diff</span><strong>{{ run.workspace_diff.pattern === 'no-modification' ? 'No persisted workspace modification' : run.workspace_diff.pattern }}</strong><small>{{ run.workspace_diff.changed_paths.length }} paths reported</small></div>
                  <div v-if="run.trace.events.some(event => event.type === 'FILE_CHANGE')"><span>Trace event</span><strong>File-change event observed</strong><small>This does not prove a final workspace diff.</small></div>
                  <div><span>Tool calls</span><strong>{{ run.tool_calls.pattern }}</strong><small>{{ run.tool_calls.status }}</small></div>
                  <div><span>Verifier</span><strong>{{ run.verifier.status }}</strong><small>{{ run.verifier.failure_subtype ?? run.verifier.sandbox_status ?? 'NOT_REPORTED' }}</small></div>
                </div>
                <p class="notice">Next: inspect the linked run and verifier evidence; check the task contract and final workspace before proposing a fix.</p>
                <div class="attribution-list">
                  <div v-for="attribution in run.attributions" :key="attribution.kind" :class="['attribution', attribution.kind.toLowerCase()]">
                    <StatusBadge :value="attribution.kind" />
                    <p>{{ attribution.statement }}</p>
                    <small v-if="attribution.caveat">{{ attribution.caveat }}</small>
                  </div>
                </div>
              </article>
            </details>
          </details>
        </details>
      </div>
    </template>
  </section>
</template>
<style scoped>.diagnosis-pattern-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 10px; min-width: 0; }.diagnosis-pattern-grid article { min-width: 0; margin: 0; overflow-wrap: anywhere; }</style>
