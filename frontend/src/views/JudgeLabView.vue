<script setup lang="ts">
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
      <div v-if="loading" class="loading-state">Loading persisted Judge reports…</div>
      <div v-else-if="error" class="error-state">Judge calibration evidence is unavailable.</div>
      <div v-else-if="!items.length" class="empty-state">No Judge calibration is reported.</div>
      <table v-else class="data-table"><thead><tr><th>Calibration</th><th>Suite</th><th>Status</th><th>Report evidence</th><th>Cells</th><th>Qualification</th></tr></thead><tbody><tr v-for="item in items" :key="item.calibration_id"><td><RouterLink class="table-link technical" :to="`/judgelab/${item.calibration_id}`">{{ item.calibration_id }}</RouterLink><div class="technical muted">{{ item.plan_digest.slice(0, 20) }}…</div></td><td>{{ item.suite_id }}@{{ item.suite_version }}</td><td><StatusBadge :value="item.status" /></td><td><StatusBadge :value="item.report_evidence_status" /></td><td>{{ item.judge_cell_count }}</td><td><StatusBadge v-for="value in item.qualifications" :key="value" :value="value" style="margin-right: 4px" /></td></tr></tbody></table>
    </div>
  </section>
</template>
