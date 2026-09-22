<script setup lang="ts">
import { t } from '@/composables/i18n'
import { onMounted, ref } from 'vue'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { JudgeCalibrationSummary } from '@/types/workbench'

const items = ref<JudgeCalibrationSummary[]>([])
const loading = ref(true)
const error = ref(false)
async function load() {
  loading.value = true; error.value = false

  try { items.value = (await workbenchApi.listCalibrations()).items }
  catch { error.value = true } finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>{{ t('评审校准') }}</h2><p>{{ t('查看已有校准报告，资格结论仅适用于对应测试套件。') }}</p></div></div>
    <p>{{ t('当前工作区校准记录：仅反映本数据库中的记录，不代表冻结历史 Judge 冒烟状态。') }}</p>
    <RouterLink class="table-link" to="/core-readiness">{{ t('查看冻结历史 Judge 证据') }}</RouterLink>
    <div class="panel">
      <button v-if="error && !loading" class="secondary-button retry-button" @click="load">{{ t('重新加载') }}</button>
    <div v-if="loading" class="loading-state">{{ t('正在读取评审报告…') }}</div>
      <div v-else-if="error" class="error-state">{{ t('暂时无法读取评审校准证据。') }}</div>
      <div v-else-if="!items.length" class="empty-state">{{ t('尚无评审校准记录。') }}</div>
      <table v-else class="data-table"><thead><tr><th>{{ t('校准记录') }}</th><th>{{ t('测试套件') }}</th><th>{{ t('状态') }}</th><th>{{ t('报告证据') }}</th><th>{{ t('实验单元') }}</th><th>{{ t('资格状态') }}</th></tr></thead><tbody><tr v-for="item in items" :key="item.calibration_id"><td><RouterLink class="table-link technical" :to="`/judgelab/${item.calibration_id}`">{{ item.calibration_id }}</RouterLink><div class="technical muted">{{ item.plan_digest.slice(0, 20) }}…</div></td><td>{{ item.suite_id }}@{{ item.suite_version }}</td><td><StatusBadge :value="item.status" /></td><td><StatusBadge :value="item.report_evidence_status" /></td><td>{{ item.judge_cell_count }}</td><td><StatusBadge v-for="value in item.qualifications" :key="value" :value="value" style="margin-right: 4px" /></td></tr></tbody></table>
    </div>
  </section>
</template>
