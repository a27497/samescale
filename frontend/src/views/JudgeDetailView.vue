<script setup lang="ts">
import PageState from '@/components/PageState.vue'
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
    <div class="page-heading"><div><h2>Judge 校准详情</h2><p class="technical">{{ id }}</p></div><StatusBadge v-if="detail" :value="detail.real_judge_smoke" /></div>
    <PageState v-if="loading" kind="loading">正在读取 Judge 报告…</PageState>
    <PageState v-else-if="error || !detail" kind="error" reload>报告不存在、暂时无法读取或未通过摘要校验。请返回校准列表确认记录，检查服务后重试。</PageState>
    <template v-else>
      <div v-if="id.startsWith('phase-i-judge-keyless')" class="notice">离线 Fake Judge 样例，未发起真实 Judge 模型调用。</div>
      <div class="notice">校准结论只适用于 {{ detail.suite_id }}@{{ detail.suite_version }}，不代表 Judge 在所有任务上都可靠。</div>
      <div v-for="cell in detail.cells" :key="cell.judge_cell_id" class="panel">
        <div class="panel-title"><div><h3>{{ cell.judge_cell_id }}</h3><span class="muted">{{ cell.requested_judge_model }}</span></div><StatusBadge :value="cell.qualification" /></div>
        <div class="metric-grid">
          <div class="metric-card accent"><div class="label">标签准确率</div><div class="value"><EvidenceValue :evidence="cell.label_accuracy" /></div><div class="detail">覆盖率 <EvidenceValue :evidence="cell.coverage" /></div></div>
          <div class="metric-card"><div class="label">宏平均 F1</div><div class="value"><EvidenceValue :evidence="cell.macro_f1" /></div></div>
          <div class="metric-card"><div class="label">评分平均绝对误差</div><div class="value"><EvidenceValue :evidence="cell.score_mae" /></div><div class="detail">Spearman 相关系数 <EvidenceValue :evidence="cell.spearman_rho" /></div></div>
          <div class="metric-card"><div class="label">配对准确率</div><div class="value"><EvidenceValue :evidence="cell.pairwise_accuracy" /></div><div class="detail">位置一致性 <EvidenceValue :evidence="cell.position_consistency" /></div></div>
        </div>
        <dl class="definition-list" style="margin-top: 14px"><dt>校准范围</dt><dd>{{ cell.qualification_scope }}</dd><dt>冗长偏差</dt><dd><EvidenceValue :evidence="cell.verbosity_bias_rate" /></dd><dt>重复一致性</dt><dd><EvidenceValue :evidence="cell.repeat_consistency" /></dd><dt>服务商基础设施事件</dt><dd>{{ cell.provider_infra }}</dd><dt>L0 分歧 / 覆盖次数</dt><dd>{{ cell.l0_disagreements }} / {{ cell.l0_overrides }}</dd></dl>
      </div>
    </template>
  </section>
</template>
