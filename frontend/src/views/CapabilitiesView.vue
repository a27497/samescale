<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { CapabilityAssessment } from '@/types/registry'

const items = ref<CapabilityAssessment[]>([])
const filter = ref('ALL')
const search = ref('')
const loading = ref(true)
const error = ref(false)
const visible = computed(() => {
  const query = search.value.trim().toLowerCase()
  return items.value.filter((item) => {
    const statusMatches = filter.value === 'ALL' || item.status === filter.value
    const identityMatches = !query || `${item.provider_profile_id} ${item.harness_profile_id} ${item.reason_codes.join(' ')}`.toLowerCase().includes(query)
    return statusMatches && identityMatches
  })
})
const statusCount = (status: string) => items.value.filter((item) => item.status === status).length
onMounted(async () => {
  try { items.value = (await registryApi.capabilities()).items }
  catch { error.value = true }
  finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading capability-heading">
      <div><h2>Capability Registry</h2><p>Fail-closed ProviderModelProfile × Harness compatibility facts and explicit limitations.</p></div>
      <div class="toolbar">
        <input v-model="search" aria-label="Search capabilities" placeholder="Search treatment or reason">
        <select v-model="filter" aria-label="Capability status filter"><option>ALL</option><option>SUPPORTED</option><option>PARTIALLY_SUPPORTED</option><option>UNSUPPORTED</option></select>
      </div>
    </div>
    <div v-if="loading" class="loading-state">Deriving capabilities…</div>
    <div v-else-if="error" class="error-state">Capability registry is unavailable.</div>
    <template v-else>
      <div class="metric-grid capability-metrics">
        <button :class="['metric-card', { accent: filter === 'ALL' }]" @click="filter = 'ALL'"><span class="label">All assessments</span><strong class="value">{{ items.length }}</strong></button>
        <button :class="['metric-card', { accent: filter === 'SUPPORTED' }]" @click="filter = 'SUPPORTED'"><span class="label">Supported</span><strong class="value">{{ statusCount('SUPPORTED') }}</strong></button>
        <button :class="['metric-card', { accent: filter === 'PARTIALLY_SUPPORTED' }]" @click="filter = 'PARTIALLY_SUPPORTED'"><span class="label">Partial</span><strong class="value">{{ statusCount('PARTIALLY_SUPPORTED') }}</strong></button>
        <button :class="['metric-card', { accent: filter === 'UNSUPPORTED' }]" @click="filter = 'UNSUPPORTED'"><span class="label">Unsupported</span><strong class="value">{{ statusCount('UNSUPPORTED') }}</strong></button>
      </div>
      <div class="panel">
        <div class="panel-title"><div><span class="panel-kicker">COMPATIBILITY MATRIX</span><h3>{{ visible.length }} treatment pair{{ visible.length === 1 ? '' : 's' }}</h3></div><span class="status-pill neutral">BACKEND DERIVED</span></div>
        <div v-if="!visible.length" class="empty-state">No capability assessment matches the current filters.</div>
        <div v-else class="responsive-table">
          <table class="data-table capability-table">
            <thead><tr><th>Treatment identity</th><th>Status</th><th>Protocol & model</th><th>Evidence & execution</th><th>Limitations</th></tr></thead>
            <tbody>
              <tr v-for="item in visible" :key="`${item.provider_profile_id}:${item.harness_profile_id}`">
                <td><span class="muted">Provider model</span><strong class="technical">{{ item.provider_profile_id }}</strong><span class="muted">Harness</span><strong class="technical">{{ item.harness_profile_id }}</strong></td>
                <td><StatusBadge :value="item.status" /><div class="eligibility-list"><span>uplift {{ item.harness_uplift_eligible ? '✓' : '—' }}</span><span>judge {{ item.judge_eligible ? '✓' : '—' }}</span></div></td>
                <td><dl class="inline-facts"><dt>Protocol</dt><dd>{{ item.protocol_compatible ? 'COMPATIBLE' : 'INCOMPATIBLE' }}</dd><dt>Model / provider</dt><dd>{{ item.model_provider_compatible ? 'COMPATIBLE' : 'INCOMPATIBLE' }}</dd><dt>Reasoning control</dt><dd>{{ item.reasoning_control_supported ? 'SUPPORTED' : 'NOT_SUPPORTED' }}</dd></dl></td>
                <td><dl class="inline-facts"><dt>Trace</dt><dd>{{ item.trace_coverage }}</dd><dt>Observed model</dt><dd>{{ item.observed_model }}</dd><dt>Tools / workspace</dt><dd>{{ item.native_tools ? 'NATIVE' : 'NONE' }} / {{ item.workspace_mutation ? 'MUTABLE' : 'READ_ONLY' }}</dd><dt>Network</dt><dd>{{ item.network_requirement }}</dd></dl></td>
                <td><div v-if="item.reason_codes.length" class="reason-stack"><code v-for="reason in item.reason_codes" :key="reason">{{ reason }}</code></div><span v-else class="muted">No limitations reported</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </section>
</template>
