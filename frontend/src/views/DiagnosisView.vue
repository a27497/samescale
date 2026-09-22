<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'

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

let generation = 0
const exporting = ref(false)
onBeforeUnmount(() => { generation++ })
async function loadDiagnosis() {
  const ownGeneration = ++generation
  report.value = null
  if (!selectedExperiment.value) return
  diagnosisLoading.value = true
  error.value = ''
  exported.value = null
  try { const value = await workbenchApi.getDiagnosis(selectedExperiment.value); if (ownGeneration === generation) report.value = value }
  catch { if (ownGeneration !== generation) return; report.value = null; error.value = '诊断证据不可用或未通过完整性校验。' }
  finally { if (ownGeneration === generation) diagnosisLoading.value = false }
}

async function exportBadCases() {
  if (!report.value || exporting.value || diagnosisLoading.value) return
  const ownGeneration = generation
  exporting.value = true; error.value = ''; exported.value = null
  try { const value = await workbenchApi.exportBadCases(report.value.experiment_id); if (ownGeneration === generation) exported.value = value }
  catch { if (ownGeneration === generation) error.value = '失败案例导出未通过校验，请重试。' }
  finally { exporting.value = false }
}

async function load() {
  loading.value = true; error.value = ''
  try {
    const response = await workbenchApi.listExperiments({ limit: 100 })
    experiments.value = response.items
    selectedExperiment.value = response.items[0]?.experiment_id ?? ''
    if (selectedExperiment.value) await loadDiagnosis()
  } catch { error.value = '实验列表暂不可用，请检查完整服务。' }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <h2>{{ t('失败诊断') }}</h2>
        <p>{{ t('根据已保存证据查看服务端生成的失败聚类。') }}</p>
      </div>
      <span class="status-pill neutral">{{ t('无模型调用') }}</span>
    </div>

    <div class="diagnosis-warning">
      <strong>{{ t('归因边界') }}</strong>
      <span>{{ report?.correlation_warning ?? t('轨迹相关性不等于因果；归因需要受控消融证据。') }}</span>
    </div>
    <ul v-if="report" class="diagnosis-limitations" :aria-label="t('诊断限制')">
      <li v-for="limitation in report.classification_limitations" :key="limitation">{{ limitation }}</li>
    </ul>

    <div class="diagnosis-toolbar">
      <label>
        {{ t('实验') }}
        <select v-model="selectedExperiment" :aria-label="t('选择诊断实验')" @change="loadDiagnosis">
          <option v-for="experiment in experiments" :key="experiment.experiment_id" :value="experiment.experiment_id">
            {{ experiment.name }} · {{ experiment.experiment_id }}
          </option>
        </select>
      </label>
      <button class="primary-button" :disabled="!report || diagnosisLoading || exporting" @click="exportBadCases">{{ t('导出真实失败案例') }}</button>
    </div>

    <div v-if="loading || diagnosisLoading" class="loading-state">{{ t('正在读取确定性聚类…') }}</div>
    <div v-else-if="error && !report" role="alert" class="error-state"><p>{{ t(error) }}</p><button class="secondary-button" @click="load">{{ t('重新加载') }}</button></div>
    <div v-else-if="!report" class="empty-state">{{ t('尚无可用的实验证据。') }}</div>
    <template v-else>
      <div class="metric-grid diagnosis-metrics">
        <div class="metric-card"><span>{{ t('失败运行') }}</span><strong class="value">{{ report.failure_run_count }}</strong></div>
        <div class="metric-card"><span>{{ t('聚类数') }}</span><strong class="value">{{ clusterCount }}</strong></div>
        <div class="metric-card"><span>{{ t('真实证据') }}</span><strong class="value">{{ report.real_run_count }}</strong></div>
        <div class="metric-card"><span>{{ t('合成证据') }}</span><strong class="value">{{ report.synthetic_run_count }}</strong></div>
      </div>

      <div v-if="exported" class="notice diagnosis-export-result">
        {{ t('已导出') }} {{ exported.real_case_count }} {{ t('个真实失败案例与') }} {{ exported.synthetic_qualification_case_count }} {{ t('个合成案例。') }}
        {{ exported.limitation }}
      </div>
      <div v-if="error" class="error-state">{{ t(error) }}</div>

      <div class="diagnosis-tree">
        <details v-for="cell in report.cells" :key="cell.cell_id" open class="diagnosis-level diagnosis-cell">
          <summary><span>{{ t('实验 → 单元') }}</span><strong>{{ cell.cell_id }}</strong></summary>
          <details v-for="family in cell.task_families" :key="family.task_family" open class="diagnosis-level">
            <summary><span>{{ t('任务类别') }}</span><strong>{{ family.task_family }}</strong></summary>
            <details v-for="cluster in family.clusters" :key="cluster.cluster_id" class="diagnosis-level diagnosis-cluster">
              <summary>
                <span>{{ t('失败聚类') }}</span>
                <strong>{{ cluster.failure_class }}</strong>
                <StatusBadge :value="cluster.failure_scope" />
                <small>{{ cluster.run_count }} {{ t('次运行') }}</small>
              </summary>
              <div class="cluster-dimensions">
                <code v-for="(value, key) in cluster.dimensions" :key="key">{{ key }}={{ value }}</code>
              </div>
              <article v-for="run in cluster.runs" :key="run.run_id" class="diagnosis-run">
                <header><strong>{{ t('运行 ·') }} {{ run.run_id }}</strong><RouterLink :to="`/runs/${run.run_id}`">{{ t('查看证据 →') }}</RouterLink></header>
                <div class="diagnosis-drilldown">
                  <div><span>{{ t('轨迹') }}</span><strong>{{ run.trace.pattern }}</strong><small>{{ run.trace.status }} · {{ run.trace.coverage ?? 'NOT_REPORTED' }}</small></div>
                  <div><span>{{ t('工作区差异') }}</span><strong>{{ run.workspace_diff.pattern }}</strong><small>{{ t('已记录') }} {{ run.workspace_diff.changed_paths.length }} {{ t('个路径') }}</small></div>
                  <div><span>{{ t('工具调用') }}</span><strong>{{ run.tool_calls.pattern }}</strong><small>{{ run.tool_calls.status }}</small></div>
                  <div><span>{{ t('校验器') }}</span><strong>{{ run.verifier.status }}</strong><small>{{ run.verifier.failure_subtype ?? run.verifier.sandbox_status ?? 'NOT_REPORTED' }}</small></div>
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
