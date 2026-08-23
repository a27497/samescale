<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { CoreReadiness, ExperimentSummary } from '@/types/workbench'

const readiness = ref<CoreReadiness | null>(null)
const experiments = ref<ExperimentSummary[]>([])
const loading = ref(true)
const error = ref(false)

onMounted(async () => {
  try {
    const [ready, list] = await Promise.all([workbenchApi.readiness(), workbenchApi.listExperiments({ limit: 5 })])
    readiness.value = ready
    experiments.value = list.items
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <h2>Evidence overview</h2>
        <p>Persisted Matrix, run, comparability, and Judge calibration evidence.</p>
      </div>
      <StatusBadge :value="readiness?.status ?? 'NOT_REPORTED'" />
    </div>
    <div v-if="loading" class="loading-state">Loading persisted evidence…</div>
    <div v-else-if="error" class="error-state">Workbench API evidence is unavailable.</div>
    <template v-else>
      <div class="metric-grid">
        <div class="metric-card accent">
          <div class="label">Experiments</div><div class="value">{{ experiments.length }}</div>
          <div class="detail">Latest bounded API page</div>
        </div>
        <div class="metric-card">
          <div class="label">Task corpus</div><div class="value">{{ readiness?.task_corpus_size ?? 0 }}</div>
          <div class="detail">Structured persisted identities</div>
        </div>
        <div class="metric-card">
          <div class="label">Readiness blockers</div><div class="value">{{ readiness?.blockers.length ?? 0 }}</div>
          <div class="detail">Unverified evidence stays blocking</div>
        </div>
        <div class="metric-card">
          <div class="label">Operator mode</div><div class="value" style="font-size: 16px">READ_ONLY</div>
          <div class="detail">No provider execution routes</div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-title"><h3>Recent experiments</h3><RouterLink class="table-link" to="/experiments">View all</RouterLink></div>
        <div v-if="!experiments.length" class="empty-state">No persisted experiments.</div>
        <table v-else class="data-table">
          <thead><tr><th>Experiment</th><th>Status</th><th>Matrix</th><th>Capability / Infra</th></tr></thead>
          <tbody>
            <tr v-for="item in experiments" :key="item.experiment_id">
              <td><RouterLink class="table-link technical" :to="`/experiments/${item.experiment_id}`">{{ item.experiment_id }}</RouterLink><br/><span class="muted">{{ item.name }}</span></td>
              <td><StatusBadge :value="item.status" /></td>
              <td>{{ item.task_count }} tasks × {{ item.cell_count }} cells</td>
              <td>{{ item.completed_capability_count }} / {{ item.infra_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>
