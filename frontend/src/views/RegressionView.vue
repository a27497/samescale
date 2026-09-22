<script setup lang="ts">
import { t } from '@/composables/i18n'
import { ref, watch } from 'vue'

import { workbenchApi } from '@/api/client'
import EvidenceValue from '@/components/EvidenceValue.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import type { RegressionIntent, RegressionResponse } from '@/types/workbench'

const baseline = ref('')
const candidate = ref('')
const intent = ref<RegressionIntent>('MODEL_COMPARISON')
const result = ref<RegressionResponse | null>(null)
const loading = ref(false)
const error = ref('')

let generation = 0
watch([baseline, candidate, intent], () => { generation++; result.value = null; error.value = '' }, { flush: 'sync' })
async function compare() {
  if (loading.value || !baseline.value.trim() || !candidate.value.trim()) return
  const ownGeneration = generation
  loading.value = true; error.value = ''; result.value = null
  try { const value = await workbenchApi.compare(baseline.value.trim(), candidate.value.trim(), intent.value); if (ownGeneration === generation) result.value = value }
  catch { if (ownGeneration === generation) error.value = '无法对比报告，请核对实验 ID 与证据完整性。' }
  finally { loading.value = false }
}
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>{{ t('回归对比') }}</h2><p>{{ t('对比已保存报告的差异，不重跑实验，不把相关性解释为因果。') }}</p></div><StatusBadge value="READ_ONLY" /></div>
    <div class="panel"><div class="toolbar"><input v-model="baseline" :aria-label="t('基线实验 ID')" :placeholder="t('基线实验 ID')" /><input v-model="candidate" :aria-label="t('候选实验 ID')" :placeholder="t('候选实验 ID')" /><select v-model="intent" :aria-label="t('对比目的')"><option value="MODEL_COMPARISON">{{ t('比较模型') }}</option><option value="HARNESS_UPLIFT">{{ t('同预算：直接调用 vs Agent') }}</option><option value="NATIVE_HARNESS_SYSTEM_COMPARISON">{{ t('原生 Agent 系统比较') }}</option><option value="GENERAL">{{ t('一般探索') }}</option></select><button class="primary-button" :disabled="!baseline.trim() || !candidate.trim() || loading" @click="compare">{{ loading ? t('正在对比…') : t('对比报告') }}</button></div><div v-if="error" class="error-state" style="margin-top: 14px">{{ t(error) }}</div></div>
    <div v-if="result" class="panel">
      <div class="notice">{{ result.limitation }}</div>
      <div class="technical muted" style="margin-top: 12px">{{ t('声明的对比目的：') }} {{ result.intent }}</div>
      <table class="data-table" style="margin-top: 14px"><thead><tr><th>{{ t('单元映射') }}</th><th>{{ t('可比性') }}</th><th>{{ t('基线') }}</th><th>{{ t('候选') }}</th><th>{{ t('原始差值') }}</th><th>{{ t('原始方向') }}</th><th>{{ t('配对数') }}</th><th>{{ t('基础设施：基线 / 候选') }}</th></tr></thead><tbody><tr v-for="item in result.comparisons" :key="`${item.baseline_cell_id}:${item.candidate_cell_id}`"><td class="technical">{{ item.baseline_cell_id }} → {{ item.candidate_cell_id }}</td><td><StatusBadge :value="item.comparability" /><div class="technical muted">{{ item.reason_codes.join(', ') }}</div></td><td><EvidenceValue :evidence="item.baseline_value" /> <StatusBadge :value="item.baseline_tier" /></td><td><EvidenceValue :evidence="item.candidate_value" /> <StatusBadge :value="item.candidate_tier" /></td><td><EvidenceValue :evidence="item.delta" /></td><td><span class="technical" :class="{ muted: item.comparability === 'NOT_COMPARABLE' }">{{ item.direction }}</span></td><td>{{ item.paired_observations }}</td><td>{{ item.baseline_infra_count }} / {{ item.candidate_infra_count }}</td></tr></tbody></table>
      <dl class="definition-list" style="margin-top: 14px"><dt>{{ t('基线报告') }}</dt><dd class="technical">{{ result.baseline_report_digest }}</dd><dt>{{ t('候选报告') }}</dt><dd class="technical">{{ result.candidate_report_digest }}</dd><dt>{{ t('共同任务') }}</dt><dd>{{ result.common_tasks.join(', ') }}</dd></dl>
    </div>
  </section>
</template>
