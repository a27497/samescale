<script setup lang="ts">
import { onMounted } from 'vue'

import StatusBadge from '@/components/StatusBadge.vue'
import { useExperimentStore } from '@/stores/experiments'

const store = useExperimentStore()
onMounted(() => void store.fetchList())
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h2>Experiments</h2><p>Browse durable Phase G experiment plans and outcomes.</p></div>
      <div class="toolbar">
        <RouterLink class="primary-button" to="/experiments/new">New keyless plan</RouterLink>
        <input v-model="store.search" aria-label="Search experiments" placeholder="Search id or name" @keyup.enter="store.fetchList" />
        <select v-model="store.statusFilter" aria-label="Filter by status" @change="store.fetchList">
          <option value="">All statuses</option><option value="queued">queued</option><option value="running">running</option><option value="completed">completed</option>
        </select>
        <button class="primary-button" @click="store.fetchList">Refresh</button>
      </div>
    </div>
    <div class="panel">
      <div v-if="store.loading" class="loading-state">Loading persisted experiments…</div>
      <div v-else-if="store.error" class="error-state">{{ store.error }}</div>
      <div v-else-if="!store.items.length" class="empty-state">No experiments match the current filters.</div>
      <table v-else class="data-table">
        <thead><tr><th>Experiment</th><th>Status</th><th>Plan</th><th>Dimensions</th><th>Runs</th><th>Infra</th></tr></thead>
        <tbody>
          <tr v-for="item in store.items" :key="item.experiment_id">
            <td><RouterLink class="table-link" :to="`/experiments/${item.experiment_id}`">{{ item.name }}</RouterLink><div class="technical muted">{{ item.experiment_id }}</div></td>
            <td><StatusBadge :value="item.status" /></td>
            <td class="technical">{{ item.plan_digest.slice(0, 19) }}…</td>
            <td>{{ item.task_count }} × {{ item.cell_count }}</td>
            <td>{{ item.completed_capability_count }} / {{ item.planned_run_count }}</td>
            <td>{{ item.infra_count }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
