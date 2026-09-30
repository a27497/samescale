<script setup lang="ts">
import PageState from '@/components/PageState.vue'
import { onMounted, ref } from 'vue'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { JudgeCalibrationSummary, JudgeCalibrationListResponse } from '@/types/workbench'

const registry = ref<JudgeCalibrationListResponse | null>(null)
const items = ref<JudgeCalibrationSummary[]>([])
const loading = ref(true)
const error = ref(false)
onMounted(async () => {
  try { registry.value = await workbenchApi.listCalibrations(); items.value = registry.value.items }
  catch { error.value = true } finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>JudgeLab calibrations</h2><p>Current JudgeLab registry — suite-scoped qualification from saved reports.</p></div><StatusBadge v-if="registry" :value="`REAL_JUDGE_SMOKE=${registry.real_judge_smoke}`" /></div>
    <div class="notice">The release snapshot and the current JudgeLab registry are different evidence scopes. <RouterLink class="table-link" to="/core-readiness">View frozen release snapshot →</RouterLink></div>
    <div class="notice">The phase-i-judge-keyless calibration is an offline fixture. A persisted report does not establish a real Judge model call.</div>
    <div class="panel">
      <PageState v-if="loading" kind="loading">Loading persisted Judge reports…</PageState>
      <PageState v-else-if="error" kind="error" reload>Judge calibration evidence is unavailable.</PageState>
      <PageState v-else-if="!items.length" kind="empty">No Judge calibration is reported.</PageState>
      <div v-else class="responsive-table" role="region" aria-label="Judge calibrations" tabindex="0"><table class="data-table"><thead><tr><th>Calibration</th><th>Suite</th><th>Status</th><th>Report evidence</th><th>Cells</th><th>Qualification</th></tr></thead><tbody><tr v-for="item in items" :key="item.calibration_id"><td><RouterLink class="table-link technical" :to="`/judgelab/${item.calibration_id}`">{{ item.calibration_id }}</RouterLink><div class="technical muted">{{ item.plan_digest.slice(0, 20) }}…</div></td><td>{{ item.suite_id }}@{{ item.suite_version }}</td><td><StatusBadge :value="item.status" /></td><td><StatusBadge :value="item.report_evidence_status" /></td><td>{{ item.judge_cell_count }}</td><td><StatusBadge v-for="value in item.qualifications" :key="value" :value="value" style="margin-right: 4px" /></td></tr></tbody></table></div>
    </div>
  </section>
</template>
