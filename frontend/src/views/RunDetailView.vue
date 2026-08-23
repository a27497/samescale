<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { workbenchApi } from '@/api/client'
import EvidenceChart from '@/components/EvidenceChart.vue'
import EvidenceValue from '@/components/EvidenceValue.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import TraceTimeline from '@/components/TraceTimeline.vue'
import type { RunDetail, TraceResponse } from '@/types/workbench'

const route = useRoute()
const run = ref<RunDetail | null>(null)
const trace = ref<TraceResponse | null>(null)
const loading = ref(true)
const error = ref(false)
const runId = computed(() => String(route.params.runId))
const chartItems = computed(() => run.value ? [
  { label: 'Latency ms', evidence: run.value.duration_ms },
  { label: 'Input tokens', evidence: run.value.input_tokens },
  { label: 'Output tokens', evidence: run.value.output_tokens },
  { label: 'Explicit cost', evidence: run.value.explicit_cost },
] : [])

onMounted(async () => {
  try { [run.value, trace.value] = await Promise.all([workbenchApi.getRun(runId.value), workbenchApi.getTrace(runId.value)]) }
  catch { error.value = true } finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Run detail</h2><p class="technical">{{ runId }}</p></div><StatusBadge v-if="run" :value="run.status" /></div>
    <div v-if="loading" class="loading-state">Loading persisted run evidence…</div>
    <div v-else-if="error || !run" class="error-state">Run evidence is unavailable or failed integrity checks.</div>
    <template v-else>
      <div class="section-grid">
        <div class="panel"><div class="panel-title"><h3>Identity and lifecycle</h3></div><dl class="definition-list"><dt>Experiment</dt><dd><RouterLink class="table-link technical" :to="`/experiments/${run.experiment_id}`">{{ run.experiment_id }}</RouterLink></dd><dt>Cell / task</dt><dd>{{ run.cell_id }} / {{ run.task_id }}@{{ run.task_version }}</dd><dt>Lane / repeat</dt><dd>{{ run.lane }} / {{ run.repeat_index }}</dd><dt>Attempt</dt><dd>{{ run.attempt }}</dd><dt>Outcome</dt><dd><StatusBadge :value="run.normalized_outcome ?? 'NOT_REPORTED'" /> <span class="technical muted">{{ run.source_outcome }}</span></dd><dt>Verifier</dt><dd>{{ run.verifier_passed === null ? 'NOT_REPORTED' : run.verifier_passed ? 'PASS' : 'FAIL' }} · <EvidenceValue :evidence="run.verifier_score" /></dd></dl></div>
        <div class="panel"><div class="panel-title"><h3>Execution facts</h3></div><dl class="definition-list"><dt>Requested model</dt><dd>{{ run.requested_model ?? 'NOT_REPORTED' }}</dd><dt>Observed model</dt><dd>{{ run.observed_model ?? 'NOT_REPORTED' }}</dd><dt>Provider route</dt><dd class="technical">{{ run.provider_route ?? 'NOT_REPORTED' }}</dd><dt>Harness</dt><dd>{{ run.harness }}@{{ run.harness_version }}</dd><dt>Trace coverage</dt><dd><StatusBadge :value="run.trace_coverage ?? 'NOT_REPORTED'" /></dd><dt>Comparability</dt><dd><StatusBadge :value="run.comparability ?? 'NOT_REPORTED'" /></dd><dt>Artifact</dt><dd class="technical">{{ run.artifact_name }} / {{ run.evidence_digest }}</dd></dl></div>
      </div>
      <div class="panel"><div class="panel-title"><h3>Latency / token / cost evidence</h3><span class="muted">Cost is never inferred from model names.</span></div><EvidenceChart title="Run usage evidence" :items="chartItems" /></div>
      <div class="panel"><div class="panel-title"><h3>Safe Normalized Trace</h3><span class="muted">Native private transcript is never loaded.</span></div><TraceTimeline v-if="trace" :trace="trace" /><div v-else class="empty-state">TRACE = NOT_REPORTED</div></div>
    </template>
  </section>
</template>
