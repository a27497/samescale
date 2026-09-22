<script setup lang="ts">
import { t } from '@/composables/i18n'
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
async function load() {
  loading.value = true; error.value = false

  try { detail.value = await workbenchApi.getCalibration(id.value) }
  catch { error.value = true } finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>{{ t('校准详情') }}</h2><p class="technical">{{ id }}</p></div><StatusBadge v-if="detail" :value="detail.real_judge_smoke" /></div>
    <button v-if="error && !loading" class="secondary-button retry-button" @click="load">{{ t('重新加载') }}</button>
    <div v-if="loading" class="loading-state">{{ t('正在读取已校验的评审报告…') }}</div>
    <div v-else-if="error || !detail" class="error-state">{{ t('评审报告不可用或未通过摘要校验。') }}</div>
    <template v-else>
      <div class="notice">{{ t('资格合格仅适用于') }} {{ detail.suite_id }}@{{ detail.suite_version }}{{ t('，不代表评审模型在所有场景可靠。') }}</div>
      <div v-for="cell in detail.cells" :key="cell.judge_cell_id" class="panel">
        <div class="panel-title"><div><h3>{{ cell.judge_cell_id }}</h3><span class="muted">{{ cell.requested_judge_model }}</span></div><StatusBadge :value="cell.qualification" /></div>
        <div class="metric-grid">
          <div class="metric-card accent"><div class="label">{{ t('标签准确率') }}</div><div class="value"><EvidenceValue :evidence="cell.label_accuracy" /></div><div class="detail">{{ t('覆盖率') }} <EvidenceValue :evidence="cell.coverage" /></div></div>
          <div class="metric-card"><div class="label">{{ t('宏平均 F1') }}</div><div class="value"><EvidenceValue :evidence="cell.macro_f1" /></div></div>
          <div class="metric-card"><div class="label">{{ t('评分平均绝对误差') }}</div><div class="value"><EvidenceValue :evidence="cell.score_mae" /></div><div class="detail">Spearman <EvidenceValue :evidence="cell.spearman_rho" /></div></div>
          <div class="metric-card"><div class="label">{{ t('成对准确率') }}</div><div class="value"><EvidenceValue :evidence="cell.pairwise_accuracy" /></div><div class="detail">{{ t('位置一致性') }} <EvidenceValue :evidence="cell.position_consistency" /></div></div>
        </div>
        <dl class="definition-list" style="margin-top: 14px"><dt>{{ t('资格适用范围') }}</dt><dd>{{ cell.qualification_scope }}</dd><dt>{{ t('冗长度偏差') }}</dt><dd><EvidenceValue :evidence="cell.verbosity_bias_rate" /></dd><dt>{{ t('重复一致性') }}</dt><dd><EvidenceValue :evidence="cell.repeat_consistency" /></dd><dt>{{ t('服务基础设施') }}</dt><dd>{{ cell.provider_infra }}</dd><dt>{{ t('L0 分歧 / 覆盖') }}</dt><dd>{{ cell.l0_disagreements }} / {{ cell.l0_overrides }}</dd></dl>
      </div>
    </template>
  </section>
</template>
