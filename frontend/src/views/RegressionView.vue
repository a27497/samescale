<script setup lang="ts">
import { ref } from 'vue'

import { workbenchApi } from '@/api/client'
import EvidenceValue from '@/components/EvidenceValue.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import type { RegressionIntent, RegressionResponse } from '@/types/workbench'

const baseline = ref('')
const candidate = ref('')
const intent = ref<RegressionIntent>('MODEL_COMPARISON')
const result = ref<RegressionResponse | null>(null)
const loading = ref(false)
const error = ref('')

async function compare() {
  loading.value = true; error.value = ''; result.value = null
  try { result.value = await workbenchApi.compare(baseline.value, candidate.value, intent.value) }
  catch { error.value = 'Persisted reports could not be compared. Check experiment IDs and evidence integrity.' }
  finally { loading.value = false }
}
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Regression compare</h2><p>Directional, immutable evidence comparison. No subject rerun and no causal attribution.</p></div><StatusBadge value="READ_ONLY" /></div>
    <div class="panel"><div class="toolbar"><input v-model="baseline" aria-label="Baseline experiment ID" placeholder="Baseline experiment ID" /><input v-model="candidate" aria-label="Candidate experiment ID" placeholder="Candidate experiment ID" /><select v-model="intent" aria-label="Comparison intent"><option value="MODEL_COMPARISON">Model comparison</option><option value="HARNESS_UPLIFT">Resource-normalized Harness uplift</option><option value="NATIVE_HARNESS_SYSTEM_COMPARISON">Native Harness system comparison</option><option value="GENERAL">General exploratory</option></select><button class="primary-button" :disabled="!baseline || !candidate || loading" @click="compare">{{ loading ? 'Comparing…' : 'Compare reports' }}</button></div><div v-if="error" class="error-state" style="margin-top: 14px">{{ error }}</div></div>
    <div v-if="result" class="panel">
      <div class="notice">{{ result.limitation }}</div>
      <div class="technical muted" style="margin-top: 12px">Declared intent: {{ result.intent }}</div>
      <table class="data-table" style="margin-top: 14px"><thead><tr><th>Cell mapping</th><th>Comparability eligibility</th><th>Baseline</th><th>Candidate</th><th>Raw delta</th><th>Raw direction</th><th>Pairs</th><th>Infra B/C</th></tr></thead><tbody><tr v-for="item in result.comparisons" :key="`${item.baseline_cell_id}:${item.candidate_cell_id}`"><td class="technical">{{ item.baseline_cell_id }} → {{ item.candidate_cell_id }}</td><td><StatusBadge :value="item.comparability" /><div class="technical muted">{{ item.reason_codes.join(', ') }}</div></td><td><EvidenceValue :evidence="item.baseline_value" /> <StatusBadge :value="item.baseline_tier" /></td><td><EvidenceValue :evidence="item.candidate_value" /> <StatusBadge :value="item.candidate_tier" /></td><td><EvidenceValue :evidence="item.delta" /></td><td><span class="technical" :class="{ muted: item.comparability === 'NOT_COMPARABLE' }">{{ item.direction }}</span></td><td>{{ item.paired_observations }}</td><td>{{ item.baseline_infra_count }} / {{ item.candidate_infra_count }}</td></tr></tbody></table>
      <dl class="definition-list" style="margin-top: 14px"><dt>Baseline report</dt><dd class="technical">{{ result.baseline_report_digest }}</dd><dt>Candidate report</dt><dd class="technical">{{ result.candidate_report_digest }}</dd><dt>Common tasks</dt><dd>{{ result.common_tasks.join(', ') }}</dd></dl>
    </div>
  </section>
</template>
