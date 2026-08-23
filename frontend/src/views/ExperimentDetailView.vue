<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import MatrixHeatmap from '@/components/MatrixHeatmap.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useExperimentStore } from '@/stores/experiments'
import type { MatrixMetricKey } from '@/types/workbench'

const route = useRoute()
const store = useExperimentStore()
const tab = ref<'overview' | 'matrix' | 'runs' | 'statistics'>('overview')
const id = computed(() => String(route.params.id))
const metrics: Array<{ key: MatrixMetricKey; label: string }> = [
  { key: 'success_rate', label: 'Success rate' }, { key: 'latency_p50_ms', label: 'Latency p50' },
  { key: 'latency_p95_ms', label: 'Latency p95' }, { key: 'infra_rate', label: 'Infra rate' },
  { key: 'pass_at_1', label: 'pass@1' }, { key: 'pass_at_3', label: 'pass@3' },
]

onMounted(async () => {
  await store.fetchExperiment(id.value)
  if (store.selected && !['completed', 'failed', 'cancelled'].includes(store.selected.status)) store.startPolling(id.value)
})
onBeforeUnmount(() => store.stopPolling())
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h2>{{ store.selected?.name ?? id }}</h2><p class="technical">{{ id }}</p></div>
      <div class="toolbar"><StatusBadge v-if="store.selected" :value="store.selected.status" /><StatusBadge v-if="store.durableStatus" :value="store.durableStatus.terminal ? 'DURABLE TERMINAL' : 'POLLING POSTGRES'" /></div>
    </div>
    <div v-if="store.loading" class="loading-state">Loading persisted Matrix evidence…</div>
    <div v-else-if="store.error" class="error-state">{{ store.error }}</div>
    <template v-else-if="store.selected">
      <div class="tabs" role="tablist">
        <button v-for="name in ['overview', 'matrix', 'runs', 'statistics'] as const" :key="name" class="tab-button" :class="{ active: tab === name }" @click="tab = name">{{ name.toUpperCase() }}</button>
      </div>
      <template v-if="tab === 'overview'">
        <div class="metric-grid">
          <div class="metric-card accent"><div class="label">Planned runs</div><div class="value">{{ store.selected.planned_run_count }}</div><div class="detail">{{ store.selected.repeat_count }} repeats</div></div>
          <div class="metric-card"><div class="label">Capability complete</div><div class="value">{{ store.selected.completed_capability_count }}</div></div>
          <div class="metric-card"><div class="label">Infra</div><div class="value">{{ store.selected.infra_count }}</div><div class="detail">Never hidden in success rate</div></div>
          <div class="metric-card"><div class="label">Dimensions</div><div class="value">{{ store.selected.task_count }} × {{ store.selected.cell_count }}</div><div class="detail">tasks × cells</div></div>
        </div>
        <div class="section-grid" style="margin-top: 16px">
          <div class="panel"><div class="panel-title"><h3>Experiment cells</h3></div><table class="data-table"><thead><tr><th>Cell</th><th>Lane</th><th>Model</th><th>Harness</th></tr></thead><tbody><tr v-for="cell in store.selected.cells" :key="cell.cell_id"><td class="technical">{{ cell.cell_id }}</td><td>{{ cell.lane }}</td><td>{{ cell.requested_model }}</td><td>{{ cell.harness }}@{{ cell.harness_version }}</td></tr></tbody></table></div>
          <div class="panel"><div class="panel-title"><h3>Evidence identity</h3></div><dl class="definition-list"><dt>Plan</dt><dd class="technical">{{ store.selected.plan_digest }}</dd><dt>Report</dt><dd class="technical">{{ store.selected.report_digest ?? 'NOT_REPORTED' }}</dd><dt>Tiers</dt><dd><StatusBadge v-for="tier in store.selected.evidence_tiers" :key="tier" :value="tier" style="margin-right: 4px" /></dd></dl></div>
        </div>
      </template>
      <div v-else-if="tab === 'matrix'" class="panel">
        <div class="panel-title"><h3>Matrix heatmap</h3><select v-model="store.selectedMetric" aria-label="Matrix metric"><option v-for="metric in metrics" :key="metric.key" :value="metric.key">{{ metric.label }}</option></select></div>
        <MatrixHeatmap v-if="store.matrix" :matrix="store.matrix" :metric="store.selectedMetric" />
        <div v-else class="empty-state">Matrix report is NOT_REPORTED.</div>
      </div>
      <div v-else-if="tab === 'runs'" class="panel">
        <div class="panel-title"><h3>Runs</h3><span class="muted">Persisted logical run IDs</span></div>
        <table class="data-table"><thead><tr><th>Run</th><th>Cell / Task</th><th>Lane</th><th>Status</th><th>Outcome</th></tr></thead><tbody><tr v-for="run in store.runs" :key="run.run_id"><td><RouterLink class="table-link technical" :to="`/runs/${run.run_id}`">{{ run.run_id.slice(0, 24) }}…</RouterLink></td><td>{{ run.cell_id }}<br/><span class="muted">{{ run.task_id }} r{{ run.repeat_index }}</span></td><td>{{ run.lane }}</td><td><StatusBadge :value="run.status" /></td><td><StatusBadge :value="run.normalized_outcome ?? 'NOT_REPORTED'" /></td></tr></tbody></table>
      </div>
      <div v-else class="panel"><div class="notice">Statistics are rendered from the immutable backend ExperimentReport. Regression comparison makes directional claims only and never causal attribution.</div><dl class="definition-list" style="margin-top: 14px"><dt>Comparability</dt><dd><span v-for="(count, status) in store.selected.comparability_summary" :key="status"><StatusBadge :value="String(status)" /> {{ count }} </span></dd><dt>Report digest</dt><dd class="technical">{{ store.selected.report_digest }}</dd></dl></div>
    </template>
  </section>
</template>
