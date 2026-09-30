<script setup lang="ts">
import PageState from '@/components/PageState.vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { workbenchApi } from '@/api/client'
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
const agentMessage = computed(() => trace.value?.events.find(event => event.type === 'AGENT_MESSAGE')?.summary ?? null)
const safeTrace = computed(() => trace.value && ({ ...trace.value, events: trace.value.events.map(event => event.type === 'REASONING_PRESENT' ? { ...event, summary: 'Private reasoning withheld.' } : event) }))
const claimConflict = computed(() => run.value?.verifier_passed === false && !!agentMessage.value && /success|pass|done|implement/i.test(agentMessage.value))
function downloadSafeEvidence() {
  if (!run.value) return
  const payload = { source: 'SameScale safe normalized API projection', run: run.value, trace: safeTrace.value }
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = `samescale-run-${run.value.run_id}.json`; anchor.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  try { [run.value, trace.value] = await Promise.all([workbenchApi.getRun(runId.value), workbenchApi.getTrace(runId.value)]) }
  catch { error.value = true } finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Run detail</h2><p class="technical">{{ runId }}</p></div><StatusBadge v-if="run" :value="run.status" /></div>
    <PageState v-if="loading" kind="loading">Loading persisted run evidence…</PageState>
    <PageState v-else-if="error || !run" kind="error" reload>Run evidence is unavailable or failed integrity checks.</PageState>
    <template v-else>
      <div class="notice">Source: {{ run.provenance ?? 'UNVERIFIED_SOURCE' }}. {{ run.provenance === 'FIXTURE_OFFLINE' ? 'Keyless Fake fixture; no real Provider/model execution.' : 'A persisted record alone does not authenticate a Provider response.' }}</div>
      <div class="panel"><div class="panel-title"><h3>What happened</h3><StatusBadge :value="run.verifier_passed === false ? 'VERIFIED_FAIL' : run.verifier_passed === true ? 'VERIFIED_PASS' : 'NOT_VERIFIED'" /></div>
        <dl class="definition-list"><dt>Agent action</dt><dd>{{ trace?.events.some(event => event.type === 'FILE_CHANGE') ? 'File-change event observed in trace' : 'No file-change event reported' }} · {{ trace?.events.filter(event => event.type === 'COMMAND_EXECUTION').length ?? 0 }} command events</dd><dt>Agent message</dt><dd>{{ agentMessage ?? 'No agent success claim reported' }}</dd><dt>Independent verifier</dt><dd>{{ run.verifier_passed === false ? 'FAIL' : run.verifier_passed === true ? 'PASS' : 'NOT_VERIFIED' }} · <EvidenceValue :evidence="run.verifier_score" /> · {{ run.summary ?? 'No verifier summary reported' }}</dd><dt>Most important evidence</dt><dd>{{ run.verifier_passed === false ? 'The independent verifier rejected the final workspace.' : run.summary ?? 'No outcome summary reported.' }}</dd></dl>
        <div v-if="claimConflict" class="diagnosis-warning"><strong>Agent claim ≠ verified result</strong><span>The Agent reported success, but the independent verifier failed. Treat the claim as a trace event, not a passed task.</span></div>
        <div class="toolbar"><RouterLink class="primary-button" :to="{ path: '/diagnosis', query: { experiment: run.experiment_id, candidate: route.query.candidate, run: run.run_id } }">Diagnose this experiment →</RouterLink><a class="secondary-button" href="#run-trace">Inspect trace and evidence ↓</a><RouterLink class="secondary-button" :to="{ path: `/experiments/${run.experiment_id}`, query: { tab: 'runs' } }">Back to runs</RouterLink></div>
      </div>
      <div class="section-grid">
        <div class="panel"><div class="panel-title"><h3>Identity and lifecycle</h3></div><dl class="definition-list"><dt>Experiment</dt><dd><RouterLink class="table-link technical" :to="`/experiments/${run.experiment_id}`">{{ run.experiment_id }}</RouterLink></dd><dt>Cell / task</dt><dd>{{ run.cell_id }} / {{ run.task_id }}@{{ run.task_version }}</dd><dt>Lane / repeat</dt><dd>{{ run.lane }} / {{ run.repeat_index }}</dd><dt>Attempt</dt><dd>{{ run.attempt }}</dd><dt>Outcome</dt><dd><StatusBadge :value="run.normalized_outcome ?? 'NOT_REPORTED'" /> <span class="technical muted">{{ run.source_outcome }}</span></dd><dt>Verifier</dt><dd>{{ run.verifier_passed === null ? 'NOT_REPORTED' : run.verifier_passed ? 'PASS' : 'FAIL' }} · <EvidenceValue :evidence="run.verifier_score" /></dd></dl></div>
        <div class="panel"><div class="panel-title"><h3>Execution facts</h3></div><dl class="definition-list"><dt>Requested model</dt><dd>{{ run.requested_model ?? 'NOT_REPORTED' }}</dd><dt>Observed model</dt><dd>{{ run.observed_model ?? 'NOT_REPORTED' }}</dd><dt>Provider route</dt><dd class="technical">{{ run.provider_route ?? 'NOT_REPORTED' }}</dd><dt>Harness</dt><dd>{{ run.harness }}@{{ run.harness_version }}</dd><dt>Trace coverage</dt><dd><StatusBadge :value="run.trace_coverage ?? 'NOT_REPORTED'" /></dd><dt>Comparability</dt><dd><StatusBadge :value="run.comparability ?? 'NOT_REPORTED'" /></dd><dt>Verified artifact</dt><dd class="technical">{{ run.artifact_name ?? 'NOT_REPORTED' }} / {{ run.evidence_digest ?? 'NOT_REPORTED' }}</dd></dl><button class="secondary-button" @click="downloadSafeEvidence">Download safe run evidence JSON</button><div v-if="run.experiment_id.startsWith('public-demo-')" class="toolbar"><a class="secondary-button" :href="`/api/workbench/runs/${run.run_id}/public-artifact`" target="_blank" rel="noopener">View verified verifier artifact</a><a class="secondary-button" :href="`/api/workbench/runs/${run.run_id}/public-artifact?download=true`">Download original verifier artifact</a></div><p class="muted">This download contains the API projection and normalized trace; private native transcript and original artifact paths stay server-side.</p></div>
      </div>
      <div class="panel"><div class="panel-title"><h3>Usage evidence</h3><span class="muted">Separate units; cost is not inferred.</span></div><div class="metric-grid"><div class="metric-card"><span>Latency (ms)</span><strong><EvidenceValue :evidence="run.duration_ms" /></strong></div><div class="metric-card"><span>Input tokens</span><strong><EvidenceValue :evidence="run.input_tokens" /></strong></div><div class="metric-card"><span>Output tokens</span><strong><EvidenceValue :evidence="run.output_tokens" /></strong></div><div class="metric-card"><span>Explicit cost</span><strong><EvidenceValue :evidence="run.explicit_cost" /></strong></div></div></div>
      <div id="run-trace" class="panel"><div class="panel-title"><h3>Safe normalized trace</h3><span class="muted">Native private transcript is withheld.</span></div><TraceTimeline v-if="trace" :trace="trace" /><PageState v-else kind="empty">TRACE = NOT_REPORTED</PageState></div>
      <details class="panel"><summary>Raw normalized API evidence</summary><pre class="technical raw-evidence">{{ JSON.stringify({ run, trace: safeTrace }, null, 2) }}</pre></details>
    </template>
  </section>
</template>
<style scoped>.raw-evidence { overflow: auto; max-height: 420px; white-space: pre-wrap; overflow-wrap: anywhere; }.metric-card span, .metric-card strong { display: block; }.metric-card strong { margin-top: 8px; font-size: 20px; }</style>
