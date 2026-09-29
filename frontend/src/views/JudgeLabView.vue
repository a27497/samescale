<script setup lang="ts">
import PageState from '@/components/PageState.vue'
import { onMounted, ref } from 'vue'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { JudgeCalibrationSummary } from '@/types/workbench'

const items = ref<JudgeCalibrationSummary[]>([])
const loading = ref(true)
const error = ref(false)
onMounted(async () => {
  try { items.value = (await workbenchApi.listCalibrations()).items }
  catch { error.value = true } finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>JudgeLab calibrations</h2><p>Suite-scoped qualification from persisted Phase H reports.</p></div><StatusBadge value="REAL_JUDGE_SMOKE=NOT_RUN" /></div>
    <div class="panel">
      <PageState v-if="loading" kind="loading">Loading persisted Judge reports…</PageState>
      <PageState v-else-if="error" kind="error" reload>Judge calibration evidence is unavailable.</PageState>
      <PageState v-else-if="!items.length" kind="empty">No Judge calibration is reported.</PageState>
      <div v-else class="responsive-table" role="region" aria-label="Judge calibrations" tabindex="0"><table class="data-table"><thead><tr><th>Calibration</th><th>Suite</th><th>Status</th><th>Report evidence</th><th>Cells</th><th>Qualification</th></tr></thead><tbody><tr v-for="item in items" :key="item.calibration_id"><td><RouterLink class="table-link technical" :to="`/judgelab/${item.calibration_id}`">{{ item.calibration_id }}</RouterLink><div class="technical muted">{{ item.plan_digest.slice(0, 20) }}…</div></td><td>{{ item.suite_id }}@{{ item.suite_version }}</td><td><StatusBadge :value="item.status" /></td><td><StatusBadge :value="item.report_evidence_status" /></td><td>{{ item.judge_cell_count }}</td><td><StatusBadge v-for="value in item.qualifications" :key="value" :value="value" style="margin-right: 4px" /></td></tr></tbody></table></div>
    </div>
  </section>
</template>
