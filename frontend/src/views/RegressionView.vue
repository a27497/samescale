<script setup lang="ts">
import PageState from '@/components/PageState.vue'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { workbenchApi } from '@/api/client'
import EvidenceValue from '@/components/EvidenceValue.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ExperimentSummary, RegressionIntent, RegressionResponse } from '@/types/workbench'
import { experimentDisplayName } from '@/utils/evidenceCopy'

const route = useRoute()
const router = useRouter()
const baseline = ref('')
const candidate = ref('')
const intent = ref<RegressionIntent>('MODEL_COMPARISON')
const experiments = ref<ExperimentSummary[]>([])
const result = ref<RegressionResponse | null>(null)
const loading = ref(false)
const error = ref('')

async function compare(updateUrl = true) {
  loading.value = true; error.value = ''; result.value = null
  if (updateUrl && router) void router.push({ query: { baseline: baseline.value, candidate: candidate.value, intent: intent.value } })
  try { result.value = await workbenchApi.compare(baseline.value, candidate.value, intent.value) }
  catch { error.value = 'Persisted reports could not be compared. Check experiment IDs and evidence integrity.' }
  finally { loading.value = false }
}

onMounted(async () => {
  const queryBaseline = route?.query?.baseline
  const queryCandidate = route?.query?.candidate
  const queryIntent = route?.query?.intent
  if (typeof queryBaseline === 'string') baseline.value = queryBaseline
  if (typeof queryCandidate === 'string') candidate.value = queryCandidate
  if (typeof queryIntent === 'string' && [
    'MODEL_COMPARISON', 'HARNESS_UPLIFT', 'NATIVE_HARNESS_SYSTEM_COMPARISON', 'GENERAL',
  ].includes(queryIntent)) intent.value = queryIntent as RegressionIntent
  try { experiments.value = (await workbenchApi.listExperiments({ limit: 100 })).items }
  catch { /* Manual IDs remain available when the list cannot load. */ }
  if (baseline.value && candidate.value) await compare(false)
})
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Regression compare</h2><p>Directional, immutable evidence comparison. No subject rerun and no causal attribution.</p></div><div class="toolbar"><StatusBadge value="READ_ONLY" /><a v-if="typeof route?.query?.run === 'string'" class="secondary-button" :href="`/api/workbench/runs/${encodeURIComponent(route.query.run)}/public-artifact`" target="_blank" rel="noopener">View baseline verifier artifact →</a></div></div>
    <div class="panel"><div class="toolbar"><input v-model="baseline" list="regression-experiments" aria-label="Baseline experiment ID" placeholder="Baseline experiment ID" /><input v-model="candidate" list="regression-experiments" aria-label="Candidate experiment ID" placeholder="Candidate experiment ID" /><datalist id="regression-experiments"><option v-for="experiment in experiments" :key="experiment.experiment_id" :value="experiment.experiment_id">{{ experimentDisplayName(experiment.name, experiment.provenance) }}</option></datalist><select v-model="intent" aria-label="Comparison intent"><option value="MODEL_COMPARISON">Model comparison</option><option value="HARNESS_UPLIFT">Resource-normalized Harness uplift</option><option value="NATIVE_HARNESS_SYSTEM_COMPARISON">Native Harness system comparison</option><option value="GENERAL">General exploratory</option></select><button class="primary-button" :disabled="!baseline || !candidate || loading" @click="compare()">{{ loading ? 'Comparing…' : 'Compare reports' }}</button></div><PageState v-if="error" kind="error" style="margin-top: 14px">{{ error }}</PageState></div>
    <PageState v-if="!result && !loading && !error" kind="empty">Choose two completed experiments to compare verified, common task observations. No provider call is made.</PageState>
    <div v-if="result" class="panel">
      <div class="notice">{{ result.limitation }}</div>
      <div class="notice">Baseline: {{ result.baseline_provenance }} · Candidate: {{ result.candidate_provenance }}. FIXTURE_OFFLINE means a keyless Fake execution, not a model Provider run.</div>
      <div class="technical muted" style="margin-top: 12px">Declared intent: {{ result.intent }}</div>
      <div class="regression-cards"><article v-for="item in result.comparisons" :key="`${item.baseline_cell_id}:${item.candidate_cell_id}`" class="panel regression-card">
        <h3 class="technical">{{ item.baseline_cell_id }} → {{ item.candidate_cell_id }}</h3>
        <p><StatusBadge :value="item.comparability" /> <span class="technical muted">{{ item.reason_codes.join(', ') }}</span></p>
        <dl class="definition-list"><dt>Comparable paired observations</dt><dd>{{ item.eligible_paired_observations }} / {{ item.paired_observations }}</dd><dt>Common-task raw baseline / candidate</dt><dd><EvidenceValue :evidence="item.common_baseline_value" /> → <EvidenceValue :evidence="item.common_candidate_value" /></dd><dt>Comparable common-task baseline / candidate</dt><dd><EvidenceValue :evidence="item.baseline_value" /> → <EvidenceValue :evidence="item.candidate_value" /></dd><dt>Eligible direction</dt><dd>{{ item.direction === 'NOT_REPORTED' ? 'INSUFFICIENT_EVIDENCE' : item.direction }} · <EvidenceValue :evidence="item.delta" /></dd><dt>Overall raw baseline / candidate</dt><dd><EvidenceValue :evidence="item.overall_baseline_value" /> → <EvidenceValue :evidence="item.overall_candidate_value" /> (delta <EvidenceValue :evidence="item.overall_delta" />)</dd><dt>Infrastructure baseline / candidate</dt><dd>{{ item.baseline_infra_count }} / {{ item.candidate_infra_count }}</dd></dl>
        <p class="muted">Overall raw rates include each experiment's own task set and do not support the direction above.</p>
      </article></div>
      <dl class="definition-list" style="margin-top: 14px"><dt>Baseline report</dt><dd class="technical">{{ result.baseline_report_digest }}</dd><dt>Candidate report</dt><dd class="technical">{{ result.candidate_report_digest }}</dd><dt>Common tasks</dt><dd>{{ result.common_tasks.join(', ') || 'None' }}</dd></dl>
    </div>
  </section>
</template>
<style scoped>
.regression-cards { display: grid; gap: 14px; margin-top: 14px; min-width: 0; }
.regression-card { min-width: 0; overflow-wrap: anywhere; margin: 0; }
.regression-card .definition-list { min-width: 0; }
@media (min-width: 900px) { .regression-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
