<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { CapabilityAssessment } from '@/types/registry'

const items = ref<CapabilityAssessment[]>([])
const filter = ref('ALL')
const loading = ref(true)
const error = ref(false)
const visible = computed(() => items.value.filter((item) => filter.value === 'ALL' || item.status === filter.value))
onMounted(async () => { try { items.value = (await registryApi.capabilities()).items } catch { error.value = true } finally { loading.value = false } })
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Capability Registry</h2><p>Fail-closed ProviderModelProfile × Harness compatibility facts.</p></div><select v-model="filter" aria-label="Capability status filter"><option>ALL</option><option>SUPPORTED</option><option>PARTIALLY_SUPPORTED</option><option>UNSUPPORTED</option></select></div>
    <div v-if="loading" class="loading-state">Deriving capabilities…</div><div v-else-if="error" class="error-state">Capability registry is unavailable.</div>
    <div v-else class="panel"><table class="data-table"><thead><tr><th>Provider model profile</th><th>Harness profile</th><th>Status</th><th>Evidence surface</th><th>Reasons</th></tr></thead><tbody><tr v-for="item in visible" :key="`${item.provider_profile_id}:${item.harness_profile_id}`"><td class="technical">{{ item.provider_profile_id }}</td><td class="technical">{{ item.harness_profile_id }}</td><td><StatusBadge :value="item.status" /></td><td>{{ item.trace_coverage }} · observed={{ item.observed_model }}<br>tools={{ item.native_tools ? 'native' : 'none' }} · workspace={{ item.workspace_mutation }}</td><td class="technical muted">{{ item.reason_codes.join(', ') || 'NONE' }}</td></tr></tbody></table></div>
  </section>
</template>
