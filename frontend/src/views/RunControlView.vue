<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ExperimentStatus, ExperimentSummary, RunSummary } from '@/types/workbench'

type OutcomeClass = 'CAPABILITY_TERMINAL' | 'INFRASTRUCTURE' | 'LIFECYCLE'

const route = useRoute()
const router = useRouter()
const experiments = ref<ExperimentSummary[]>([])
const selectedExperimentId = ref('')
const status = ref<ExperimentStatus | null>(null)
const runs = ref<RunSummary[]>([])
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const filter = ref<'ALL' | OutcomeClass>('ALL')

function outcomeClass(run: RunSummary): OutcomeClass {
  const outcome = (run.normalized_outcome ?? '').toLowerCase()
  if (outcome === 'infra_failure') return 'INFRASTRUCTURE'
  if (outcome === 'capability_pass' || outcome === 'capability_fail') return 'CAPABILITY_TERMINAL'
  return 'LIFECYCLE'
}

const visibleRuns = computed(() =>
  runs.value.filter((run) => filter.value === 'ALL' || outcomeClass(run) === filter.value),
)
const infrastructureCount = computed(() =>
  runs.value.filter((run) => outcomeClass(run) === 'INFRASTRUCTURE').length,
)
const capabilityCount = computed(() =>
  runs.value.filter((run) => outcomeClass(run) === 'CAPABILITY_TERMINAL').length,
)
const selectedIsListed = computed(() =>
  experiments.value.some((item) => item.experiment_id === selectedExperimentId.value),
)

function controlLabel(run: RunSummary) {
  const classification = outcomeClass(run)
  if (classification === 'INFRASTRUCTURE') return 'RECOVERY REVIEW'
  if (classification === 'CAPABILITY_TERMINAL') return 'TERMINAL'
  return 'OBSERVE'
}

async function loadSelected(syncRoute = true) {
  if (!selectedExperimentId.value) {
    status.value = null
    runs.value = []
    return
  }
  refreshing.value = true
  error.value = ''
  try {
    const [statusResponse, runResponse] = await Promise.all([
      workbenchApi.getStatus(selectedExperimentId.value),
      workbenchApi.getRuns(selectedExperimentId.value, { limit: 100 }),
    ])
    status.value = statusResponse
    runs.value = runResponse.items
    if (syncRoute && route.query.experiment !== selectedExperimentId.value) {
      await router.replace({ query: { ...route.query, experiment: selectedExperimentId.value } })
    }
  } catch {
    error.value = 'Authoritative run state could not be loaded.'
  } finally {
    refreshing.value = false
  }
}

onMounted(async () => {
  try {
    const response = await workbenchApi.listExperiments({ limit: 100 })
    experiments.value = response.items
    const requested = typeof route.query.experiment === 'string' ? route.query.experiment : ''
    selectedExperimentId.value = requested || response.items[0]?.experiment_id || ''
    await loadSelected(Boolean(selectedExperimentId.value))
  } catch {
    error.value = 'Experiment lifecycle evidence is unavailable.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <h2>Run Control</h2>
        <p>Observe durable lifecycle state and apply explicit recovery boundaries. This surface never retries a capability result.</p>
      </div>
      <StatusBadge :value="status?.terminal ? 'DURABLE TERMINAL' : status?.status ?? 'NOT_REPORTED'" />
    </div>

    <div class="control-banner">
      <span class="control-banner-mark">RC</span>
      <div><strong>Authoritative lifecycle only</strong><p>Refresh reads persisted backend state. No provider request is triggered by opening or refreshing this page.</p></div>
      <span class="status-pill neutral">NO RETRY-ALL</span>
    </div>

    <div v-if="loading" class="loading-state">Loading experiment lifecycle state…</div>
    <template v-else>
      <div class="run-control-toolbar panel">
        <label>
          <span>Experiment</span>
          <select v-model="selectedExperimentId" aria-label="Run Control experiment" @change="loadSelected()">
            <option v-if="!experiments.length" value="">No experiments reported</option>
            <option v-else-if="selectedExperimentId && !selectedIsListed" :value="selectedExperimentId">{{ selectedExperimentId }} · direct link</option>
            <option v-for="item in experiments" :key="item.experiment_id" :value="item.experiment_id">
              {{ item.name }} · {{ item.experiment_id }}
            </option>
          </select>
        </label>
        <button class="secondary-button" :disabled="refreshing || !selectedExperimentId" @click="loadSelected(false)">
          {{ refreshing ? 'Refreshing…' : 'Refresh authoritative state' }}
        </button>
        <RouterLink v-if="selectedExperimentId" class="table-link" :to="`/experiments/${selectedExperimentId}`">Open experiment evidence →</RouterLink>
      </div>

      <div v-if="error" class="error-state">{{ error }}</div>
      <template v-else-if="selectedExperimentId">
        <div class="metric-grid">
          <div class="metric-card accent"><div class="label">Lifecycle</div><div class="value compact-value">{{ status?.status ?? 'NOT_REPORTED' }}</div><div class="detail">{{ status?.terminal ? 'Durable terminal state' : 'May still change' }}</div></div>
          <div class="metric-card"><div class="label">Reported runs</div><div class="value">{{ runs.length }}</div><div class="detail">First 100 persisted logical runs</div></div>
          <div class="metric-card"><div class="label">Capability terminal</div><div class="value">{{ capabilityCount }}</div><div class="detail">Never eligible for semantic retry</div></div>
          <div class="metric-card"><div class="label">Infrastructure</div><div class="value">{{ infrastructureCount }}</div><div class="detail">Requires scoped recovery review</div></div>
        </div>

        <div class="recovery-policy-grid">
          <article class="policy-card terminal-policy">
            <span class="policy-icon">✓</span>
            <div><span class="panel-kicker">TERMINAL OUTCOME</span><h3>Capability results stay final</h3><p>A verifier or capability failure is evidence. Do not rerun it to improve a score or replace its provider, model, route, or harness.</p></div>
          </article>
          <article class="policy-card recovery-policy">
            <span class="policy-icon">↻</span>
            <div><span class="panel-kicker">EXPLICIT RECOVERY</span><h3>Infrastructure is reviewed by slot</h3><p>Recovery must preserve the frozen methodology and treatment identity. It needs an operator-approved acquisition path; this keyless shell does not invent one.</p></div>
          </article>
        </div>

        <div class="panel">
          <div class="panel-title run-list-heading">
            <div><span class="panel-kicker">LOGICAL RUNS</span><h3>Lifecycle inventory</h3></div>
            <div class="segmented-control" aria-label="Run classification filter">
              <button v-for="value in ['ALL', 'CAPABILITY_TERMINAL', 'INFRASTRUCTURE', 'LIFECYCLE'] as const" :key="value" :class="{ active: filter === value }" @click="filter = value">{{ value.replace('_TERMINAL', '') }}</button>
            </div>
          </div>
          <div v-if="!visibleRuns.length" class="empty-state">No runs match this lifecycle class.</div>
          <div v-else class="responsive-table">
            <table class="data-table run-control-table">
              <thead><tr><th>Run identity</th><th>Slot</th><th>Status / outcome</th><th>Control boundary</th><th>Evidence</th></tr></thead>
              <tbody>
                <tr v-for="run in visibleRuns" :key="run.run_id">
                  <td><strong class="technical">{{ run.run_id }}</strong><div class="muted">attempt {{ run.attempt }}</div></td>
                  <td>{{ run.cell_id }} · {{ run.task_id }}<div class="technical muted">repeat={{ run.repeat_index }} · lane={{ run.lane }}</div></td>
                  <td><StatusBadge :value="run.status" /> <StatusBadge :value="run.normalized_outcome ?? 'NOT_REPORTED'" /></td>
                  <td><span class="status-pill" :class="outcomeClass(run) === 'INFRASTRUCTURE' ? 'warn' : 'neutral'">{{ controlLabel(run) }}</span><div class="boundary-note">{{ outcomeClass(run) === 'INFRASTRUCTURE' ? 'Preserve exact treatment; review explicit recovery.' : outcomeClass(run) === 'CAPABILITY_TERMINAL' ? 'Recorded evidence; no semantic retry.' : 'Observe backend lifecycle state.' }}</div></td>
                  <td><RouterLink class="table-link" :to="`/runs/${run.run_id}`">Diagnosis & trace →</RouterLink></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
      <div v-else class="empty-state">No persisted experiment is available for run control.</div>
    </template>
  </section>
</template>
