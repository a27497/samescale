<script setup lang="ts">
import PageState from '@/components/PageState.vue'
import { onMounted, ref } from 'vue'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { CoreReadiness } from '@/types/workbench'

const readiness = ref<CoreReadiness | null>(null)
const loading = ref(true)
const error = ref(false)
onMounted(async () => {
  try { readiness.value = await workbenchApi.readiness() }
  catch { error.value = true } finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Core release-candidate readiness</h2><p>Evidence-driven checklist only. This page never creates a tag.</p></div><StatusBadge :value="readiness?.status ?? 'NOT_REPORTED'" /></div>
    <PageState v-if="loading" kind="loading">Evaluating structured evidence…</PageState>
    <PageState v-else-if="error || !readiness" kind="error" reload>Readiness evidence is unavailable.</PageState>
    <template v-else>
      <div class="notice">Core remains NOT_READY while any structured requirement is blocked, NOT_REPORTED, or NOT_VERIFIED.</div>
      <div class="panel"><p class="notice">READY entries below cite a saved source. Frozen evidence / not part of current experiment registry. Snapshot numbers may differ from today's QA fixtures. Generated time is shown only when recorded by the source.</p><div class="readiness-cards"><article v-for="check in readiness.checks" :key="check.key" class="panel"><h3>{{ check.label }} <StatusBadge :value="check.status" /></h3><p>{{ check.evidence }}</p><details v-if="check.status === 'READY'"><summary>Evidence provenance</summary><dl class="definition-list"><dt>Evidence/report ID</dt><dd>{{ check.source_id ?? 'NOT_REPORTED' }}</dd><dt>Snapshot/version</dt><dd>{{ check.snapshot ?? 'NOT_REPORTED' }}</dd><dt>Generated time</dt><dd>{{ check.generated_at ?? 'NOT_REPORTED' }}</dd><dt>Repository artifact / digest</dt><dd class="technical">{{ check.artifact_reference ?? 'NOT_REPORTED' }}</dd></dl><RouterLink v-if="check.source_route" class="table-link" :to="check.source_route">Open saved report →</RouterLink><p v-else class="muted">Frozen evidence / not part of current experiment registry. Open the cited repository artifact to inspect the frozen snapshot.</p></details></article></div></div>
      <div class="panel"><div class="panel-title"><h3>Blocking keys</h3><span>{{ readiness.blockers.length }}</span></div><div class="toolbar"><StatusBadge v-for="blocker in readiness.blockers" :key="blocker" :value="blocker" /></div></div>
    </template>
  </section>
</template>
