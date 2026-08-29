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
const analysis = computed(() => store.modelComparison?.analysis ?? null)
const metrics: Array<{ key: MatrixMetricKey; label: string }> = [
  { key: 'success_rate', label: 'Success rate' }, { key: 'latency_p50_ms', label: 'Latency p50' },
  { key: 'latency_p95_ms', label: 'Latency p95' }, { key: 'infra_rate', label: 'Infra rate' },
  { key: 'pass_at_1', label: 'pass@1' }, { key: 'pass_at_3', label: 'pass@3' },
]

const rateText = (value: { status: string; value: number | null }) =>
  value.status === 'AVAILABLE' && value.value !== null
    ? `${(value.value * 100).toFixed(1)}%`
    : 'NOT_AVAILABLE'

const identityText = (value: { status: string; counts: Record<string, number>; missing_slots: number }) => {
  const known = Object.entries(value.counts).map(([name, count]) => `${name} (${count})`)
  if (value.missing_slots) known.push(`NOT_AVAILABLE (${value.missing_slots})`)
  return known.length ? known.join(', ') : 'NOT_AVAILABLE'
}

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
          <div class="panel"><div class="panel-title"><h3>Evidence identity</h3></div><dl class="definition-list"><dt>Plan</dt><dd class="technical">{{ store.selected.plan_digest }}</dd><dt>Report</dt><dd class="technical">{{ store.selected.report_digest ?? 'NOT_REPORTED' }}</dd><dt>Intent / mode</dt><dd>{{ store.selected.comparison_intent }} / {{ store.selected.evaluation_mode }}</dd><dt>Tiers</dt><dd><StatusBadge v-for="tier in store.selected.evidence_tiers" :key="tier" :value="tier" style="margin-right: 4px" /></dd></dl></div>
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
      <template v-else>
        <div v-if="analysis" class="panel">
          <div class="notice">{{ analysis.conclusion_semantics.permitted_interpretation }} Raw differences are descriptive and remain subordinate to comparability and missingness.</div>
          <div class="metric-grid" style="margin-top: 16px">
            <div class="metric-card accent"><div class="label">Planned slots</div><div class="value">{{ analysis.overall.planned_slots }}</div></div>
            <div class="metric-card"><div class="label">Acquired slots</div><div class="value">{{ analysis.overall.acquired_slots }}</div><div class="detail">Unacquired {{ analysis.overall.unacquired_slots }}</div></div>
            <div class="metric-card"><div class="label">Capability denominator</div><div class="value">{{ analysis.overall.capability_denominator }}</div></div>
            <div class="metric-card"><div class="label">PASS</div><div class="value">{{ analysis.overall.passed }}</div></div>
            <div class="metric-card"><div class="label">FAIL</div><div class="value">{{ analysis.overall.failed }}</div></div>
            <div class="metric-card"><div class="label">INFRA</div><div class="value">{{ analysis.overall.infra }}</div></div>
          </div>

          <div class="section-grid" style="margin-top: 16px">
            <div class="panel">
              <div class="panel-title"><h3>Matched capability pairs</h3><StatusBadge :value="analysis.comparability.category" /></div>
              <dl class="definition-list">
                <dt>Matched / planned</dt><dd>{{ analysis.pairs.matched_capability_pairs }} / {{ analysis.pairs.planned_pairs }}</dd>
                <dt>Both pass</dt><dd>{{ analysis.pairs.both_pass }}</dd>
                <dt>Model A only</dt><dd>{{ analysis.pairs.model_a_only_pass }}</dd>
                <dt>Model B only</dt><dd>{{ analysis.pairs.model_b_only_pass }}</dd>
                <dt>Both fail</dt><dd>{{ analysis.pairs.both_fail }}</dd>
                <dt>Infra / missing</dt><dd>{{ analysis.pairs.infra_pairs }} / {{ analysis.pairs.missing_pairs }}</dd>
                <dt>Raw B − A</dt><dd>{{ analysis.pairs.raw_percentage_point_difference === null ? 'NOT_AVAILABLE' : `${analysis.pairs.raw_percentage_point_difference.toFixed(1)} pp` }}</dd>
              </dl>
            </div>
            <div class="panel">
              <div class="panel-title"><h3>Evidence limits</h3></div>
              <dl class="definition-list">
                <dt>Comparability reasons</dt><dd class="technical">{{ Object.keys(analysis.comparability.reason_counts).join(', ') || 'NONE_REPORTED' }}</dd>
                <dt>Control drift</dt><dd><StatusBadge :value="analysis.control_drift.status" /> {{ analysis.control_drift.affected_pairs }} pairs / {{ analysis.control_drift.affected_runs }} runs</dd>
                <dt>Trace coverage</dt><dd>{{ identityText(analysis.trace_coverage) }}</dd>
                <dt>Observed models</dt><dd>{{ identityText(analysis.observed_models) }}</dd>
                <dt>Observed providers</dt><dd>{{ identityText(analysis.observed_providers) }}</dd>
                <dt>Recovery evidence</dt><dd><StatusBadge :value="analysis.recovery_attempts.status" /> primary={{ analysis.recovery_attempts.explicitly_marked_primary_acquisitions }}, recovery={{ analysis.recovery_attempts.explicitly_marked_recovery_acquisitions }}, unmarked={{ analysis.recovery_attempts.unmarked_acquisitions }}</dd>
                <dt>Lease claims</dt><dd>{{ analysis.recovery_attempts.lease_claim_attempts }} — not interpreted as recovery attempts</dd>
              </dl>
            </div>
          </div>

          <div class="panel" style="margin-top: 16px">
            <div class="panel-title"><h3>Per-model outcomes, identity, usage, and cost</h3></div>
            <table class="data-table">
              <thead><tr><th>Model</th><th>PASS / FAIL / INFRA</th><th>Pass rate</th><th>Observed identity</th><th>Trace</th><th>Known usage / cost</th></tr></thead>
              <tbody>
                <tr v-for="model in analysis.models" :key="model.cell_id">
                  <td><strong>{{ model.model_label }}</strong> · {{ model.requested_model }}<br/><span class="muted technical">{{ model.cell_id }}</span></td>
                  <td>{{ model.passed }} / {{ model.failed }} / {{ model.infra }}<br/><span class="muted">denominator {{ model.capability_denominator }}, unacquired {{ model.unacquired_slots }}</span></td>
                  <td>{{ rateText(model.pass_rate) }}<br/><StatusBadge :value="model.evidence_tier" /></td>
                  <td>{{ identityText(model.observed_models) }}<br/><span class="muted">Provider: {{ identityText(model.observed_providers) }}</span></td>
                  <td>{{ identityText(model.trace_coverage) }}</td>
                  <td>Input {{ model.usage_and_cost.input_tokens.known_total ?? 'NOT_AVAILABLE' }} / output {{ model.usage_and_cost.output_tokens.known_total ?? 'NOT_AVAILABLE' }} tokens<br/><StatusBadge :value="model.usage_and_cost.explicit_cost.status" /> cost {{ model.usage_and_cost.explicit_cost.total ?? 'NOT_AVAILABLE' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="section-grid" style="margin-top: 16px">
            <div class="panel">
              <div class="panel-title"><h3>Failure presentation</h3></div>
              <table class="data-table"><thead><tr><th>Category</th><th>Slots</th></tr></thead><tbody><tr v-for="(count, category) in analysis.overall.failure_categories" :key="category"><td><StatusBadge :value="String(category)" /></td><td>{{ count }}</td></tr></tbody></table>
            </div>
            <div class="panel">
              <div class="panel-title"><h3>Language / task-family breakdown</h3></div>
              <table class="data-table"><thead><tr><th>Dimension</th><th>Value</th><th>Pairs</th><th>A / B pass rate</th><th>Infra / missing</th></tr></thead><tbody><tr v-for="row in analysis.breakdowns" :key="`${row.dimension}:${row.value}`"><td>{{ row.dimension }}</td><td>{{ row.value }}</td><td>{{ row.matched_capability_pairs }} / {{ row.planned_pairs }}</td><td>{{ rateText(row.model_a_pass_rate) }} / {{ rateText(row.model_b_pass_rate) }}</td><td>{{ row.infra_pairs }} / {{ row.missing_pairs }}</td></tr></tbody></table>
            </div>
          </div>
          <dl class="definition-list" style="margin-top: 16px"><dt>Analysis digest</dt><dd class="technical">{{ store.modelComparison?.analysis_digest }}</dd><dt>Recovery distinction</dt><dd>{{ analysis.recovery_attempts.note }}</dd></dl>
        </div>
        <div v-else class="panel"><div class="notice">Statistics are rendered from the immutable backend ExperimentReport. Regression comparison makes directional claims only and never causal attribution.</div><dl class="definition-list" style="margin-top: 14px"><dt>Comparability</dt><dd><span v-for="(count, status) in store.selected.comparability_summary" :key="status"><StatusBadge :value="String(status)" /> {{ count }} </span></dd><dt>Report digest</dt><dd class="technical">{{ store.selected.report_digest }}</dd></dl></div>
      </template>
    </template>
  </section>
</template>
