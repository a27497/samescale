<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { CoreReadiness, ExperimentSummary } from '@/types/workbench'

const readiness = ref<CoreReadiness | null>(null)
const experiments = ref<ExperimentSummary[]>([])
const loading = ref(true)
const error = ref(false)

const activeExperiments = computed(() =>
  experiments.value.filter((item) => !['completed', 'failed', 'cancelled'].includes(item.status)).length,
)
const infrastructureEvents = computed(() =>
  experiments.value.reduce((total, item) => total + item.infra_count, 0),
)

onMounted(async () => {
  const [ready, list] = await Promise.allSettled([
    workbenchApi.readiness(),
    workbenchApi.listExperiments({ limit: 5 }),
  ])
  if (ready.status === 'fulfilled') readiness.value = ready.value
  if (list.status === 'fulfilled') experiments.value = list.value.items
  error.value = ready.status === 'rejected' && list.status === 'rejected'
  loading.value = false
})
</script>

<template>
  <section>
    <div class="hero-panel">
      <div>
        <span class="eyebrow">EVIDENCE OPERATIONS</span>
        <h2>Controlled evaluation, from registry to trace.</h2>
        <p>
          Plan keylessly, inspect authoritative run state, and keep capability outcomes separate
          from infrastructure recovery.
        </p>
        <div class="hero-actions">
          <RouterLink class="primary-button" to="/experiments/new">Plan an experiment</RouterLink>
          <RouterLink class="secondary-button" to="/run-control">Open Run Control</RouterLink>
        </div>
      </div>
      <div class="hero-readiness">
        <span class="label">Core readiness</span>
        <StatusBadge :value="readiness?.status ?? 'NOT_REPORTED'" />
        <strong>{{ readiness?.blockers.length ?? '—' }}</strong>
        <small>structured blocker{{ readiness?.blockers.length === 1 ? '' : 's' }}</small>
        <RouterLink to="/core-readiness">Inspect evidence →</RouterLink>
      </div>
    </div>

    <div v-if="loading" class="loading-state">Loading persisted evidence…</div>
    <div v-else-if="error" class="error-state">Workbench API evidence is unavailable.</div>
    <template v-else>
      <div class="metric-grid overview-metrics">
        <div class="metric-card accent">
          <div class="label">Recent experiments</div><div class="value">{{ experiments.length }}</div>
          <div class="detail">Latest bounded API page</div>
        </div>
        <div class="metric-card">
          <div class="label">Active</div><div class="value">{{ activeExperiments }}</div>
          <div class="detail">Queued or running in this page</div>
        </div>
        <div class="metric-card">
          <div class="label">Infrastructure events</div><div class="value">{{ infrastructureEvents }}</div>
          <div class="detail">Visible separately from capability</div>
        </div>
        <div class="metric-card">
          <div class="label">Task corpus</div><div class="value">{{ readiness?.task_corpus_size ?? '—' }}</div>
          <div class="detail">Persisted structured identities</div>
        </div>
      </div>

      <div class="overview-layout">
        <div class="panel">
          <div class="panel-title">
            <div><span class="panel-kicker">RECENT ACTIVITY</span><h3>Experiment evidence</h3></div>
            <RouterLink class="table-link" to="/experiments">View all</RouterLink>
          </div>
          <div v-if="!experiments.length" class="empty-state">No persisted experiments.</div>
          <div v-else class="responsive-table">
            <table class="data-table">
              <thead><tr><th>Experiment</th><th>Status</th><th>Matrix</th><th>Capability / Infra</th></tr></thead>
              <tbody>
                <tr v-for="item in experiments" :key="item.experiment_id">
                  <td><RouterLink class="table-link technical" :to="`/experiments/${item.experiment_id}`">{{ item.experiment_id }}</RouterLink><br><span class="muted">{{ item.name }}</span></td>
                  <td><StatusBadge :value="item.status" /></td>
                  <td>{{ item.task_count }} tasks × {{ item.cell_count }} cells</td>
                  <td>{{ item.completed_capability_count }} / {{ item.infra_count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <aside class="panel launchpad">
          <div class="panel-title"><div><span class="panel-kicker">LAUNCHPAD</span><h3>Product surfaces</h3></div></div>
          <RouterLink to="/models"><span class="launch-mark">01</span><span><strong>Registry</strong><small>Models, providers, harnesses, compatibility</small></span><b>→</b></RouterLink>
          <RouterLink to="/experiments/new"><span class="launch-mark">02</span><span><strong>Experiment Builder</strong><small>Backend-validated planning, no execution</small></span><b>→</b></RouterLink>
          <RouterLink to="/run-control"><span class="launch-mark">03</span><span><strong>Run Control</strong><small>Lifecycle and recovery boundaries</small></span><b>→</b></RouterLink>
          <RouterLink to="/regression"><span class="launch-mark">04</span><span><strong>Diagnosis</strong><small>Regression and comparative evidence</small></span><b>→</b></RouterLink>
        </aside>
      </div>
    </template>
  </section>
</template>
