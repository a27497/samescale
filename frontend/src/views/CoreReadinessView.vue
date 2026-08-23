<script setup lang="ts">
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
    <div v-if="loading" class="loading-state">Evaluating structured evidence…</div>
    <div v-else-if="error || !readiness" class="error-state">Readiness evidence is unavailable.</div>
    <template v-else>
      <div class="notice">Core remains NOT_READY while any structured requirement is blocked, NOT_REPORTED, or NOT_VERIFIED.</div>
      <div class="panel"><table class="data-table"><thead><tr><th>Requirement</th><th>Status</th><th>Structured evidence</th></tr></thead><tbody><tr v-for="check in readiness.checks" :key="check.key"><td><strong>{{ check.label }}</strong><div class="technical muted">{{ check.key }}</div></td><td><StatusBadge :value="check.status" /></td><td>{{ check.evidence }}</td></tr></tbody></table></div>
      <div class="panel"><div class="panel-title"><h3>Blocking keys</h3><span>{{ readiness.blockers.length }}</span></div><div class="toolbar"><StatusBadge v-for="blocker in readiness.blockers" :key="blocker" :value="blocker" /></div></div>
    </template>
  </section>
</template>
