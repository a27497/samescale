<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { workbenchApi } from '@/api/client'
import EvidenceValue from '@/components/EvidenceValue.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import type { JudgeCalibrationDetail } from '@/types/workbench'

const route = useRoute()
const detail = ref<JudgeCalibrationDetail | null>(null)
const loading = ref(true)
const error = ref(false)
const id = computed(() => String(route.params.calibrationId))
onMounted(async () => {
  try { detail.value = await workbenchApi.getCalibration(id.value) }
  catch { error.value = true } finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Judge calibration</h2><p class="technical">{{ id }}</p></div><StatusBadge v-if="detail" :value="detail.real_judge_smoke" /></div>
    <div v-if="loading" class="loading-state">Loading verified Judge report…</div>
    <div v-else-if="error || !detail" class="error-state">Judge report is unavailable or failed digest verification.</div>
    <template v-else>
      <div class="notice">QUALIFIED_FOR_SUITE applies only to {{ detail.suite_id }}@{{ detail.suite_version }}. It is not universal Judge reliability.</div>
      <div v-for="cell in detail.cells" :key="cell.judge_cell_id" class="panel">
        <div class="panel-title"><div><h3>{{ cell.judge_cell_id }}</h3><span class="muted">{{ cell.requested_judge_model }}</span></div><StatusBadge :value="cell.qualification" /></div>
        <div class="metric-grid">
          <div class="metric-card accent"><div class="label">Label accuracy</div><div class="value"><EvidenceValue :evidence="cell.label_accuracy" /></div><div class="detail">Coverage <EvidenceValue :evidence="cell.coverage" /></div></div>
          <div class="metric-card"><div class="label">Macro F1</div><div class="value"><EvidenceValue :evidence="cell.macro_f1" /></div></div>
          <div class="metric-card"><div class="label">Score MAE</div><div class="value"><EvidenceValue :evidence="cell.score_mae" /></div><div class="detail">Spearman <EvidenceValue :evidence="cell.spearman_rho" /></div></div>
          <div class="metric-card"><div class="label">Pairwise accuracy</div><div class="value"><EvidenceValue :evidence="cell.pairwise_accuracy" /></div><div class="detail">Position <EvidenceValue :evidence="cell.position_consistency" /></div></div>
        </div>
        <dl class="definition-list" style="margin-top: 14px"><dt>Qualification scope</dt><dd>{{ cell.qualification_scope }}</dd><dt>Verbosity bias</dt><dd><EvidenceValue :evidence="cell.verbosity_bias_rate" /></dd><dt>Repeat consistency</dt><dd><EvidenceValue :evidence="cell.repeat_consistency" /></dd><dt>Provider infra</dt><dd>{{ cell.provider_infra }}</dd><dt>L0 disagreements / overrides</dt><dd>{{ cell.l0_disagreements }} / {{ cell.l0_overrides }}</dd></dl>
      </div>
    </template>
  </section>
</template>
