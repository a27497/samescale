<script setup lang="ts">
import PageState from '@/components/PageState.vue'
import { onMounted } from 'vue'

import StatusBadge from '@/components/StatusBadge.vue'
import { useExperimentStore } from '@/stores/experiments'
import { experimentDisplayName } from '@/utils/evidenceCopy'

const store = useExperimentStore()
onMounted(() => void store.fetchList())
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h2>Experiments</h2><p>Browse saved experiment plans and verified outcomes. Fixture runs are labeled separately from Provider execution records.</p></div>
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
      <PageState v-if="store.loading" kind="loading">Loading persisted experiments…</PageState>
      <PageState v-else-if="store.error" kind="error">{{ store.error }}</PageState>
      <PageState v-else-if="!store.items.length" kind="empty">No experiments match the current filters.</PageState>
      <div v-else class="responsive-table" role="region" aria-label="Experiments" tabindex="0"><table class="data-table">
        <thead><tr><th>Experiment</th><th>Source</th><th>Status</th><th>Plan</th><th>Dimensions</th><th>Runs</th><th>Infra</th></tr></thead>
        <tbody>
          <tr v-for="item in store.items" :key="item.experiment_id">
            <td><RouterLink class="table-link" :to="`/experiments/${item.experiment_id}`">{{ experimentDisplayName(item.name, item.provenance) }}</RouterLink><div class="technical muted">{{ item.experiment_id }}</div><strong v-if="item.integrity_status === 'INTEGRITY_FAILED'" class="error-message">Historical evidence — artifact integrity failed</strong></td>
            <td><StatusBadge :value="item.provenance ?? 'UNVERIFIED_SOURCE'" /></td>
            <td><StatusBadge :value="item.status" /></td>
            <td class="technical">{{ item.plan_digest.slice(0, 19) }}…</td>
            <td>{{ item.task_count }} × {{ item.cell_count }}</td>
            <td>{{ item.completed_capability_count }} / {{ item.planned_run_count }}</td>
            <td>{{ item.infra_count }}</td>
          </tr>
        </tbody>
      </table></div>
    </div>
  </section>
</template>
