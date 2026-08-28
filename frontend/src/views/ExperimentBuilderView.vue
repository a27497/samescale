<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { registryApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type {
  ComparisonType,
  EvaluationMode,
  ExperimentBuilderRequest,
  ExperimentPreflight,
  ExperimentSnapshot,
  HarnessDefinition,
  MethodologyRegistryItem,
  ProviderModelProfile,
  TaskRegistryItem,
} from '@/types/registry'

const methodology = ref<MethodologyRegistryItem | null>(null)
const profiles = ref<ProviderModelProfile[]>([])
const harnesses = ref<HarnessDefinition[]>([])
const tasks = ref<TaskRegistryItem[]>([])
const selectedTasks = ref<string[]>([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const preflight = ref<ExperimentPreflight | null>(null)
const snapshot = ref<ExperimentSnapshot | null>(null)
const form = reactive({ name: 'Cost-aware evaluation', mode: 'QUICK' as EvaluationMode, comparison: 'HARNESS_UPLIFT' as ComparisonType, scheduleSeed: 20260828, concurrency: 1, wallTime: 90, outputTokens: 2000, leftProfile: 'gpt56-relay-gpt56-responses', leftHarness: 'direct-gpt56-relay-gpt56-responses', rightProfile: 'gpt56-relay-gpt56-responses', rightHarness: 'codex-gpt56-medium' })
const repeatCount = computed(() => methodology.value?.repeat_counts[form.mode] ?? 1)
const harnessProfiles = computed(() => harnesses.value.flatMap((item) => item.profiles))

onMounted(async () => {
  try {
    const [modelData, harnessData, taskData, methodologyData, settingData] = await Promise.all([registryApi.models(), registryApi.harnesses(), registryApi.tasks(), registryApi.methodologies(), registryApi.settings()])
    profiles.value = modelData.provider_profiles
    harnesses.value = harnessData.items
    tasks.value = taskData.items
    methodology.value = methodologyData.items[0] ?? null
    form.mode = settingData.defaults.default_evaluation_mode
    form.scheduleSeed = settingData.defaults.default_schedule_seed
    form.concurrency = settingData.defaults.default_concurrency
    selectedTasks.value = taskData.items.slice(0, 1).map((item) => item.task_id)
  } catch { error.value = 'Registry Builder contracts are unavailable.' } finally { loading.value = false }
})

function request(): ExperimentBuilderRequest {
  if (!methodology.value) throw new Error('Active methodology is unavailable')
  return {
    name: form.name, methodology_id: methodology.value.methodology_id, methodology_digest: methodology.value.methodology_digest, evaluation_mode: form.mode, comparison_type: form.comparison, task_ids: selectedTasks.value,
    cells: [
      { cell_id: 'left', provider_model_profile_id: form.leftProfile, harness_profile_id: form.leftHarness },
      { cell_id: 'right', provider_model_profile_id: form.rightProfile, harness_profile_id: form.rightHarness },
    ],
    budget: {
      max_wall_time: { status: 'ENFORCED', value: form.wallTime, unit: 'seconds' }, max_output_tokens: { status: 'ENFORCED', value: form.outputTokens, unit: 'tokens' },
      max_model_turns: { status: 'NOT_AVAILABLE', value: null, unit: 'turns' }, max_tool_calls: { status: 'NOT_AVAILABLE', value: null, unit: 'calls' }, max_provider_requests: { status: 'NOT_AVAILABLE', value: null, unit: 'requests' }, max_cost: { status: 'NOT_AVAILABLE', value: null, unit: 'USD' },
    },
    schedule_seed: form.scheduleSeed, max_parallel_runs: form.concurrency, billing_modes: {},
  }
}

async function runPreflight() { error.value = ''; snapshot.value = null; busy.value = true; try { preflight.value = await registryApi.preflight(request()) } catch { error.value = 'Preflight request failed.' } finally { busy.value = false } }
async function freezeSnapshot() { error.value = ''; busy.value = true; try { snapshot.value = await registryApi.snapshot(request()) } catch { error.value = 'Immutable snapshot could not be frozen.' } finally { busy.value = false } }
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Experiment Builder Lite</h2><p>Methodology v2 authoritative planning only — no provider call and no run creation.</p></div><StatusBadge :value="preflight?.status ?? 'NOT_REPORTED'" /></div>
    <div v-if="loading" class="loading-state">Loading Registry contracts…</div>
    <div v-else class="builder-layout">
      <div class="panel builder-form">
        <div v-if="error" class="error-state">{{ error }}</div>
        <div class="form-grid">
          <label>Experiment name<input v-model="form.name" aria-label="Experiment name"></label>
          <label>Evaluation mode<select v-model="form.mode" aria-label="Evaluation mode"><option value="QUICK">QUICK</option><option value="INFORMAL">INFORMAL</option><option value="FORMAL_EXHAUSTIVE">FORMAL_EXHAUSTIVE</option></select></label>
          <label>Repeat policy<input :value="`n=${repeatCount} (backend fixed)`" aria-label="Repeat policy" disabled></label>
          <label>Comparison type<select v-model="form.comparison" aria-label="Comparison type"><option value="END_TO_END_SYSTEM_COMPARISON">END_TO_END_SYSTEM_COMPARISON</option><option value="MODEL_COMPARISON">MODEL_COMPARISON</option><option value="HARNESS_UPLIFT">HARNESS_UPLIFT</option><option value="CONTROLLED_ABLATION">CONTROLLED_ABLATION</option></select></label>
          <label>Schedule seed<input v-model.number="form.scheduleSeed" type="number" aria-label="Schedule seed"></label>
          <label>Max parallel runs<input v-model.number="form.concurrency" type="number" min="1" max="64" aria-label="Max parallel runs"></label>
          <label>Max wall time / slot<input v-model.number="form.wallTime" type="number" min="1" aria-label="Max wall time"></label>
          <label>Max output tokens<input v-model.number="form.outputTokens" type="number" min="1" aria-label="Max output tokens"></label>
        </div>
        <div class="builder-section"><h3>Cells</h3><div class="cell-grid"><div><strong>Left treatment</strong><label>Provider model profile<select v-model="form.leftProfile" aria-label="Left provider profile"><option v-for="item in profiles" :key="item.profile_id" :value="item.profile_id">{{ item.profile_id }}</option></select></label><label>Harness profile<select v-model="form.leftHarness" aria-label="Left Harness profile"><option v-for="item in harnessProfiles" :key="item.profile_id" :value="item.profile_id">{{ item.profile_id }}</option></select></label></div><div><strong>Right treatment</strong><label>Provider model profile<select v-model="form.rightProfile" aria-label="Right provider profile"><option v-for="item in profiles" :key="item.profile_id" :value="item.profile_id">{{ item.profile_id }}</option></select></label><label>Harness profile<select v-model="form.rightHarness" aria-label="Right Harness profile"><option v-for="item in harnessProfiles" :key="item.profile_id" :value="item.profile_id">{{ item.profile_id }}</option></select></label></div></div></div>
        <div class="builder-section"><h3>Tier-A tasks</h3><div class="task-picker"><label v-for="task in tasks" :key="task.task_id"><input v-model="selectedTasks" type="checkbox" :value="task.task_id">{{ task.task_id }}</label></div></div>
        <div class="toolbar"><button class="primary-button" :disabled="busy || !selectedTasks.length" @click="runPreflight">Run keyless preflight</button><button class="secondary-button" :disabled="busy || !preflight" @click="freezeSnapshot">Freeze immutable snapshot</button></div>
      </div>
      <aside class="panel preview-panel">
        <div class="panel-title"><h3>Planning preview</h3><span class="status-pill neutral">NO EXECUTION</span></div>
        <div v-if="!preflight" class="empty-state">Run preflight to preview backend-authoritative scheduling.</div>
        <template v-else><dl class="definition-list"><dt>Status</dt><dd><StatusBadge :value="preflight.status" /></dd><dt>Logical slots</dt><dd>{{ preflight.estimated_logical_slots }}</dd><dt>Mode / n</dt><dd>{{ preflight.evaluation_mode }} / {{ preflight.repeat_count }}</dd><dt>Max wall bound</dt><dd>{{ preflight.estimated_maximum_wall_time_seconds ?? 'NOT_AVAILABLE' }} seconds</dd><dt>Cost estimate</dt><dd>{{ preflight.cost_estimate.status }}</dd><dt>Plan digest</dt><dd class="technical">{{ preflight.candidate_plan_digest }}</dd></dl><div class="check-list"><div v-for="check in preflight.checks" :key="`${check.key}:${check.reason_code}`" class="check-row"><StatusBadge :value="check.status" /><div><strong class="technical">{{ check.reason_code }}</strong><small>{{ check.detail }}</small></div></div></div><div v-for="block in preflight.schedule_preview.slice(0, 3)" :key="block.block_identity" class="schedule-block"><strong>{{ block.task_id }} / repeat={{ block.repeat_index }}</strong><span class="technical">{{ block.cell_execution_order.join(' → ') }}</span></div></template>
        <div v-if="snapshot" class="snapshot-confirmation"><strong>Immutable snapshot frozen</strong><span class="technical">{{ snapshot.snapshot_id }}</span><span class="technical">{{ snapshot.snapshot_digest }}</span></div>
      </aside>
    </div>
  </section>
</template>
