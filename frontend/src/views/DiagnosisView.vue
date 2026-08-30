<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { BadCaseExport, DiagnosisReport, ExperimentSummary } from '@/types/workbench'

const experiments = ref<ExperimentSummary[]>([])
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
  try { exported.value = await workbenchApi.exportBadCases(report.value.experiment_id) }
  catch { error.value = 'BadCase export failed backend validation.' }
}

onMounted(async () => {
  try {
    const response = await workbenchApi.listExperiments({ limit: 100 })
    experiments.value = response.items
    selectedExperiment.value = response.items[0]?.experiment_id ?? ''
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
      <span class="status-pill neutral">KEYLESS ANALYSIS</span>
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
        <select v-model="selectedExperiment" aria-label="Diagnosis experiment" @change="loadDiagnosis">
          <option v-for="experiment in experiments" :key="experiment.experiment_id" :value="experiment.experiment_id">
            {{ experiment.name }} · {{ experiment.experiment_id }}
          </option>
        </select>
      </label>
      <button class="primary-button" :disabled="!report" @click="exportBadCases">Export real BadCases</button>
    </div>

    <div v-if="loading || diagnosisLoading" class="loading-state">Building deterministic clusters…</div>
    <div v-else-if="error && !report" class="error-state">{{ error }}</div>
    <div v-else-if="!report" class="empty-state">No experiment evidence is available.</div>
    <template v-else>
      <div class="metric-grid diagnosis-metrics">
        <div class="metric-card"><span>Failure runs</span><strong class="value">{{ report.failure_run_count }}</strong></div>
        <div class="metric-card"><span>Clusters</span><strong class="value">{{ clusterCount }}</strong></div>
        <div class="metric-card"><span>Real evidence</span><strong class="value">{{ report.real_run_count }}</strong></div>
        <div class="metric-card"><span>Synthetic</span><strong class="value">{{ report.synthetic_run_count }}</strong></div>
      </div>

      <div v-if="exported" class="notice diagnosis-export-result">
        Exported {{ exported.real_case_count }} real BadCases and {{ exported.synthetic_qualification_case_count }} synthetic cases.
        {{ exported.limitation }}
      </div>
      <div v-if="error" class="error-state">{{ error }}</div>

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
                  <div><span>Workspace diff</span><strong>{{ run.workspace_diff.pattern }}</strong><small>{{ run.workspace_diff.changed_paths.length }} paths reported</small></div>
                  <div><span>Tool calls</span><strong>{{ run.tool_calls.pattern }}</strong><small>{{ run.tool_calls.status }}</small></div>
                  <div><span>Verifier</span><strong>{{ run.verifier.status }}</strong><small>{{ run.verifier.failure_subtype ?? run.verifier.sandbox_status ?? 'NOT_REPORTED' }}</small></div>
                </div>
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
