<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

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
const form = reactive({ name: 'Cost-aware evaluation', mode: 'QUICK' as EvaluationMode, comparison: 'HARNESS_UPLIFT' as ComparisonType, scheduleSeed: 20260828, concurrency: 1, wallTime: 90, outputTokens: 2000, leftProfile: '', leftHarness: '', rightProfile: '', rightHarness: '' })
const repeatCount = computed(() => methodology.value?.repeat_counts[form.mode] ?? 'UNKNOWN')
const harnessProfiles = computed(() => harnesses.value.flatMap((item) => item.profiles))
const profileFor = (id: string) => profiles.value.find(p => p.profile_id === id)
const harnessProfileFor = (id: string) => harnessProfiles.value.find(p => p.profile_id === id)
const harnessFor = (id: string) => harnesses.value.find(h => h.profiles.some(p => p.profile_id === id))
const cells = computed(() => [
  { id: 'left', profile: form.leftProfile, harness: form.leftHarness },
  { id: 'right', profile: form.rightProfile, harness: form.rightHarness },
])
const includesDirect = computed(() => cells.value.some(c => harnessFor(c.harness)?.harness_id === 'direct-model'))
// Registry wire contract omits purpose when its value is SUBJECT, including local profiles.
const isSubject = (p: ProviderModelProfile) => p.purpose === undefined || p.purpose === 'SUBJECT'
const compatible = (profile: string, harness: string) => {
  const p = profileFor(profile); const h = harnessProfileFor(harness)
  return p?.enabled === true && isSubject(p) && h !== undefined && h.enabled !== false
    && h.supported_provider_profile_ids.includes(profile)
}
const formValid = computed(() => !loading.value && Boolean(methodology.value?.active && form.name.trim()
  && form.name.length <= 200 && selectedTasks.value.length && selectedTasks.value.length <= 18)
  && selectedTasks.value.every(id => tasks.value.some(t => t.task_id === id))
  && cells.value.every(c => compatible(c.profile, c.harness))
  && Number.isInteger(form.concurrency) && form.concurrency >= 1 && form.concurrency <= 64
  && Number.isInteger(form.scheduleSeed) && Number.isInteger(form.wallTime) && form.wallTime > 0
  && Number.isInteger(form.outputTokens) && form.outputTokens > 0
  && cells.value.every(c => profileFor(c.profile)?.max_output_tokens_limit == null
    || form.outputTokens <= profileFor(c.profile)!.max_output_tokens_limit!))
let generation = 0
let loadGeneration = 0
let alive = true
watch([form, selectedTasks], () => { generation++; preflight.value = null; snapshot.value = null }, { deep: true, flush: 'sync' })
async function load() {
  const current = ++loadGeneration; generation++
  loading.value = true; error.value = ''; preflight.value = null; snapshot.value = null
  profiles.value = []; harnesses.value = []; methodology.value = null; tasks.value = []
  try {
    const [modelData, harnessData, taskData, methodologyData, settingData] = await Promise.all([registryApi.models(), registryApi.harnesses(), registryApi.tasks(), registryApi.methodologies(), registryApi.settings()])
    if (!alive || current !== loadGeneration) return
    profiles.value = modelData.provider_profiles.filter(isSubject)
    harnesses.value = harnessData.items
    tasks.value = taskData.items
    methodology.value = methodologyData.items.find(item => item.active) ?? null
    form.mode = settingData.defaults.default_evaluation_mode
    form.scheduleSeed = settingData.defaults.default_schedule_seed
    form.concurrency = settingData.defaults.default_concurrency
    // Model, Harness and task choices are explicit. Never substitute another identity on reload.
  } catch { if (alive && current === loadGeneration) error.value = 'Registry Builder contracts are unavailable.' }
  finally { if (alive && current === loadGeneration) loading.value = false }
}
onMounted(load)
onBeforeUnmount(() => { alive = false; generation++; loadGeneration++ })

function request(): ExperimentBuilderRequest {
  if (!methodology.value) throw new Error('Active methodology is unavailable')
  return {
    name: form.name, methodology_id: methodology.value.methodology_id, methodology_digest: methodology.value.methodology_digest, evaluation_mode: form.mode, comparison_type: form.comparison, task_ids: [...selectedTasks.value],
    cells: [
      { cell_id: 'left', provider_model_profile_id: form.leftProfile, harness_profile_id: form.leftHarness },
      { cell_id: 'right', provider_model_profile_id: form.rightProfile, harness_profile_id: form.rightHarness },
    ],
    budget: {
      max_wall_time: { status: 'ENFORCED', value: form.wallTime, unit: 'seconds', scopes: ['PER_LOGICAL_RUN'] }, max_output_tokens: { status: 'ENFORCED', value: form.outputTokens, unit: 'tokens', scopes: includesDirect.value ? ['PER_PROVIDER_REQUEST', 'PER_LOGICAL_RUN'] : ['PER_PROVIDER_REQUEST'] },
      max_model_turns: includesDirect.value ? { status: 'ENFORCED', value: 1, unit: 'turns', scopes: ['PER_LOGICAL_RUN'] } : { status: 'NOT_AVAILABLE', value: null, unit: 'turns', scopes: ['NOT_AVAILABLE'] }, max_tool_calls: includesDirect.value ? { status: 'ENFORCED', value: 0, unit: 'calls', scopes: ['PER_LOGICAL_RUN'] } : { status: 'NOT_AVAILABLE', value: null, unit: 'calls', scopes: ['NOT_AVAILABLE'] }, max_provider_requests: includesDirect.value ? { status: 'ENFORCED', value: 1, unit: 'requests', scopes: ['PER_LOGICAL_RUN'] } : { status: 'NOT_AVAILABLE', value: null, unit: 'requests', scopes: ['NOT_AVAILABLE'] }, max_cost: { status: 'NOT_AVAILABLE', value: null, unit: 'USD', scopes: ['NOT_AVAILABLE'] },
    },
    schedule_seed: form.scheduleSeed, max_parallel_runs: form.concurrency, billing_modes: {},
  }
}

async function runPreflight() {
  if (busy.value || !formValid.value) return
  const current = generation
  error.value = ''; preflight.value = null; snapshot.value = null; busy.value = true
  try { const result = await registryApi.preflight(request()); if (alive && current === generation) preflight.value = result }
  catch { if (alive && current === generation) error.value = 'Preflight request failed.' }
  finally { if (alive) busy.value = false }
}
async function freezeSnapshot() {
  if (busy.value || !formValid.value || !preflight.value || preflight.value.status === 'BLOCKED') return
  const current = generation
  error.value = ''; snapshot.value = null; busy.value = true
  try { const result = await registryApi.snapshot(request()); if (alive && current === generation) snapshot.value = result }
  catch { if (alive && current === generation) { preflight.value = null; error.value = 'Immutable snapshot could not be frozen. Reload configuration and run preflight again.' } }
  finally { if (alive) busy.value = false }
}
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Experiment Builder Lite</h2><p>Methodology v2 authoritative planning only — no provider call and no run creation.</p></div><StatusBadge :value="preflight?.status ?? 'NOT_REPORTED'" /></div>
    <button class="secondary-button" :disabled="loading || busy" @click="load">Reload planning configuration</button>
    <div v-if="loading" class="loading-state">Loading Registry contracts…</div>
    <div v-else class="builder-layout">
      <div class="panel builder-form">
        <div v-if="error" class="error-state">{{ error }}</div>
        <div class="form-grid">
          <label>Experiment name<input v-model="form.name" aria-label="Experiment name" maxlength="200"></label>
          <label>Evaluation mode<select v-model="form.mode" aria-label="Evaluation mode"><option value="QUICK">QUICK</option><option value="INFORMAL">INFORMAL</option><option value="FORMAL_EXHAUSTIVE">FORMAL_EXHAUSTIVE</option></select></label>
          <label>Repeat policy<input :value="`n=${repeatCount} (backend fixed)`" aria-label="Repeat policy" disabled></label>
          <label>Comparison type<select v-model="form.comparison" aria-label="Comparison type"><option value="END_TO_END_SYSTEM_COMPARISON">END_TO_END_SYSTEM_COMPARISON</option><option value="MODEL_COMPARISON">MODEL_COMPARISON</option><option value="HARNESS_UPLIFT">HARNESS_UPLIFT</option><option value="CONTROLLED_ABLATION">CONTROLLED_ABLATION</option></select></label>
          <label>Schedule seed<input v-model.number="form.scheduleSeed" type="number" aria-label="Schedule seed"></label>
          <label>Max parallel runs<input v-model.number="form.concurrency" type="number" min="1" max="64" aria-label="Max parallel runs"></label>
          <label>Max wall time / slot<input v-model.number="form.wallTime" type="number" min="1" aria-label="Max wall time"></label>
          <label>Max output tokens<input v-model.number="form.outputTokens" type="number" min="1" aria-label="Max output tokens"></label>
        </div>
        <div class="builder-section"><h3>Cells — explicit SUBJECT selections</h3><div class="cell-grid">
          <div v-for="side in (['left', 'right'] as const)" :key="side" :data-cell="side">
            <strong>{{ side === 'left' ? 'Left' : 'Right' }} treatment</strong>
            <label>Provider model profile<select v-model="form[`${side}Profile`]" :aria-label="`${side === 'left' ? 'Left' : 'Right'} provider profile`">
              <option disabled value="">Unconfigured — select a SUBJECT model</option>
              <option v-if="form[`${side}Profile`] && !profileFor(form[`${side}Profile`])" :value="form[`${side}Profile`]" disabled>Unavailable: {{ form[`${side}Profile`] }}</option>
              <option v-for="item in profiles" :key="item.profile_id" :value="item.profile_id" :disabled="!item.enabled">{{ item.profile_id }}{{ !item.enabled ? ' (unavailable)' : '' }}</option>
            </select></label>
            <label>Harness profile<select v-model="form[`${side}Harness`]" :aria-label="`${side === 'left' ? 'Left' : 'Right'} Harness profile`">
              <option disabled value="">Unconfigured — select a Harness version</option>
              <option v-if="form[`${side}Harness`] && !harnessProfileFor(form[`${side}Harness`])" :value="form[`${side}Harness`]" disabled>Unavailable: {{ form[`${side}Harness`] }}</option>
              <option v-for="item in harnessProfiles" :key="item.profile_id" :value="item.profile_id" :disabled="!compatible(form[`${side}Profile`], item.profile_id)">{{ item.profile_id }} · {{ harnessFor(item.profile_id)?.version ?? 'UNKNOWN' }}</option>
            </select></label>
            <dl class="definition-list selection-details">
              <dt>Role</dt><dd>{{ profileFor(form[`${side}Profile`]) ? 'SUBJECT' : 'UNKNOWN' }}</dd>
              <dt>Model profile / revision</dt><dd>{{ profileFor(form[`${side}Profile`])?.profile_id ?? 'UNKNOWN / unconfigured' }}</dd>
              <dt>Profile identity</dt><dd>{{ profileFor(form[`${side}Profile`])?.profile_identity ?? 'UNKNOWN' }}</dd>
              <dt>Requested model / provider</dt><dd>{{ profileFor(form[`${side}Profile`])?.requested_model ?? 'UNKNOWN' }} / {{ profileFor(form[`${side}Profile`])?.provider_id ?? 'UNKNOWN' }}</dd>
              <dt>Harness profile / runtime version</dt><dd>{{ harnessProfileFor(form[`${side}Harness`])?.profile_id ?? 'UNKNOWN / unconfigured' }} / {{ harnessFor(form[`${side}Harness`])?.version ?? 'UNKNOWN' }}</dd>
              <dt>Harness configuration identity</dt><dd>{{ harnessProfileFor(form[`${side}Harness`])?.harness_config_identity ?? 'UNKNOWN' }}</dd>
              <dt>Effective reasoning effort</dt><dd>{{ (harnessFor(form[`${side}Harness`])?.harness_id === 'direct-model' ? profileFor(form[`${side}Profile`])?.reasoning_effort : harnessProfileFor(form[`${side}Harness`])?.reasoning_effort ?? profileFor(form[`${side}Profile`])?.reasoning_effort) ?? 'NOT_AVAILABLE' }}</dd>
              <dt>Configured output ceiling</dt><dd>{{ profileFor(form[`${side}Profile`])?.max_output_tokens_limit ?? 'NOT_CONFIGURED' }}</dd>
              <dt>Request timeout / seconds</dt><dd>{{ profileFor(form[`${side}Profile`])?.request_timeout_seconds ?? 'UNKNOWN' }}</dd>
              <dt>Runtime health</dt><dd>{{ harnessFor(form[`${side}Harness`])?.runtime_health ?? 'UNKNOWN' }}</dd>
            </dl>
            <p v-if="!compatible(form[`${side}Profile`], form[`${side}Harness`])" role="status">Select an available SUBJECT model and its compatible Harness revision. Unknown or stale selections are not substituted.</p>
          </div>
        </div></div>
        <p v-if="cells.some(c => profileFor(c.profile)?.max_output_tokens_limit != null && form.outputTokens > profileFor(c.profile)!.max_output_tokens_limit!)" role="alert">Output budget exceeds a selected model configuration limit. Change the budget or explicitly select another configuration.</p>
        <p v-if="includesDirect" class="notice">Direct contract: 1 provider request, 1 model turn, 0 tool calls per logical run. Output tokens are bounded per request and per run. The backend validates this shared planning budget for both cells.</p>
        <p v-else class="notice">Model turns, tool calls and provider request bounds: NOT_AVAILABLE. Output tokens are bounded per provider request only.</p>
        <p>Cost bound: NOT_AVAILABLE. Configuration and planning do not verify credentials, connection health or execution readiness.</p>
        <div class="builder-section"><h3>Tier-A tasks</h3><div class="task-picker"><label v-for="task in tasks" :key="task.task_id"><input v-model="selectedTasks" type="checkbox" :value="task.task_id">{{ task.task_id }}</label></div></div>
        <div class="toolbar"><button class="primary-button" :disabled="busy || !formValid" @click="runPreflight">Run keyless preflight</button><button class="secondary-button" :disabled="busy || !formValid || !preflight || preflight.status === 'BLOCKED'" @click="freezeSnapshot">Freeze immutable snapshot</button></div>
      </div>
      <aside class="panel preview-panel">
        <div class="panel-title"><h3>Planning preview</h3><span class="status-pill neutral">NO EXECUTION</span></div>
        <div v-if="!preflight" class="empty-state">Run preflight to preview backend-authoritative scheduling.</div>
        <template v-else><dl class="definition-list"><dt>Status</dt><dd><StatusBadge :value="preflight.status" /></dd><dt>Logical slots</dt><dd>{{ preflight.estimated_logical_slots }}</dd><dt>Mode / n</dt><dd>{{ preflight.evaluation_mode }} / {{ preflight.repeat_count }}</dd><dt>Max wall bound</dt><dd>{{ preflight.estimated_maximum_wall_time_seconds ?? 'NOT_AVAILABLE' }} seconds</dd><dt>Cost estimate</dt><dd>{{ preflight.cost_estimate.status }}</dd><dt>Plan digest</dt><dd class="technical">{{ preflight.candidate_plan_digest }}</dd></dl><div class="check-list"><div v-for="check in preflight.checks" :key="`${check.key}:${check.reason_code}`" class="check-row"><StatusBadge :value="check.status" /><div><strong class="technical">{{ check.reason_code }}</strong><small>{{ check.detail }}</small></div></div></div><div v-for="block in preflight.schedule_preview.slice(0, 3)" :key="block.block_identity" class="schedule-block"><strong>{{ block.task_id }} / repeat={{ block.repeat_index }}</strong><span class="technical">{{ block.cell_execution_order.join(' → ') }}</span></div></template>
        <div v-if="snapshot" class="snapshot-confirmation"><strong>Immutable snapshot frozen</strong><span class="technical">{{ snapshot.snapshot_id }}</span><span class="technical">{{ snapshot.snapshot_digest }}</span>
          <div v-for="selection in snapshot.provider_selections" :key="selection.cell_id" class="frozen-selection" :data-frozen-cell="selection.cell_id">
            <strong>{{ selection.cell_id }} · persisted selection</strong>
            <div>{{ selection.provider_profile_id }} / {{ selection.harness_profile_id }}</div>
            <div>{{ selection.provider_profile_identity }}</div>
            <div>Effective runtime: {{ selection.effective_runtime_profile_identity ?? 'NOT_AVAILABLE' }}</div>
            <div>Resource envelope: {{ selection.resource_envelope_identity ?? 'NOT_AVAILABLE' }}</div>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
/* Keep exact configuration identities readable inside the existing planning layout. */
.selection-details dd, .preview-panel { overflow-wrap: anywhere; }
.check-row > div { min-width: 0; }
</style>
