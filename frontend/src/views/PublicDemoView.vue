<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { workbenchApi } from '@/api/client'
import PageState from '@/components/PageState.vue'
import type { PublicDemo } from '@/types/workbench'

const demo = ref<PublicDemo | null>(null)
const loading = ref(true)
const error = ref('')
onMounted(async () => {
  try {
    const result = await workbenchApi.getPublicDemo()
    if (!result.public_demo_ready) error.value = 'Public demo validation did not pass. Evidence is unavailable.'
    else demo.value = result
  }
  catch (failure) {
    const code = (failure as { response?: { data?: { error?: { code?: string } } } })?.response?.data?.error?.code
    error.value = code === 'DEMO_NOT_CONFIGURED' ? 'No public demo is configured for this workspace.' : 'Evidence integrity failed. This demo is unavailable; no substitute evidence was used.'
  } finally { loading.value = false }
})
</script>
<template>
  <section>
    <div class="page-heading"><div><h2>Did the Agent actually finish?</h2><p>Follow an Agent success claim through independent verification, failure diagnosis, and a candidate comparison.</p></div></div>
    <PageState v-if="loading" kind="loading">Verifying public demo evidence…</PageState>
    <PageState v-else-if="error" kind="error" reload>{{ error }} <RouterLink to="/analyst">Open offline investigation examples</RouterLink></PageState>
    <template v-else-if="demo">
      <div class="notice"><strong>Offline fixture demonstration</strong><p>{{ demo.limitation }}</p><span class="technical">{{ demo.demo_id }} · {{ demo.generated_at }}</span></div>
      <div class="panel"><div class="panel-title"><h3>Follow the evidence</h3></div><div class="toolbar">
        <RouterLink class="primary-button" :to="{ path: `/experiments/${demo.baseline_id}`, query: { tab: 'runs', candidate: demo.candidate_id } }">1. Open baseline experiment →</RouterLink>
        <RouterLink class="secondary-button" :to="{ path: `/runs/${demo.failed_run_id}`, query: { candidate: demo.candidate_id } }">2. Agent claim vs failed verifier →</RouterLink>
        <RouterLink class="secondary-button" :to="{ path: '/diagnosis', query: { experiment: demo.baseline_id, candidate: demo.candidate_id, run: demo.failed_run_id } }">3. Diagnose the failure →</RouterLink>
        <RouterLink class="secondary-button" :to="{ path: '/regression', query: { baseline: demo.baseline_id, candidate: demo.candidate_id, run: demo.failed_run_id } }">4. Compare candidate →</RouterLink>
        <a class="secondary-button" :href="`/api/workbench/runs/${demo.failed_run_id}/public-artifact`" target="_blank" rel="noopener">5. View verified artifact →</a>
      </div><p class="muted">Browsing uses saved evidence and does not require credentials. Configuration and execution are disabled on this public instance.</p></div>
      <div class="panel"><h3>Evidence identity</h3><dl class="definition-list"><dt>Source</dt><dd>{{ demo.provenance }}</dd><dt>Generated</dt><dd>{{ demo.generated_at }}</dd><dt>Runs / files</dt><dd>{{ demo.run_count }} / {{ demo.artifact_file_count }}</dd><dt>Manifest</dt><dd class="technical">{{ demo.manifest_digest }}</dd></dl></div>
      <details v-if="demo.historical_integrity_failures.length" class="panel"><summary>Historical QA evidence — artifact integrity failed</summary><p>The original QA records and digests remain preserved. Their artifacts were not recovered; this demonstration uses new evidence identities.</p><ul><li v-for="id in demo.historical_integrity_failures" :key="id"><RouterLink :to="`/experiments/${id}`">{{ id }}</RouterLink></li></ul></details>
    </template>
  </section>
</template>
