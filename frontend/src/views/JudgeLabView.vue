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
    <div class="page-heading"><div><h2>JudgeLab 校准</h2><p>查看当前保存的 Judge 校准报告。校准结论只适用于对应任务套件。</p></div><span v-if="registry">真实 Judge 烟测 <StatusBadge :value="registry.real_judge_smoke" /></span></div>
    <div class="notice">冻结发布快照与当前 JudgeLab 注册表属于不同证据范围。 <RouterLink class="table-link" to="/core-readiness">查看冻结发布快照 →</RouterLink></div>
    <div class="notice">离线校准样例不代表真实 Judge 模型调用；保存报告也不等于执行过模型。</div>
    <div class="panel">
      <PageState v-if="loading" kind="loading">正在读取已保存 Judge 报告…</PageState>
      <PageState v-else-if="error" kind="error" reload>Judge 校准证据暂时无法读取。请检查后端服务或报告完整性后重试。</PageState>
      <PageState v-else-if="!items.length" kind="empty">当前工作区暂无 Judge 校准报告。可先查看冻结发布快照；新增真实校准需由操作员单独授权。</PageState>
      <div v-else class="responsive-table" role="region" aria-label="Judge 校准列表" tabindex="0"><table class="data-table"><thead><tr><th>校准记录</th><th>任务套件</th><th>状态</th><th>报告证据</th><th>配置数</th><th>校准结论</th></tr></thead><tbody><tr v-for="item in items" :key="item.calibration_id"><td><RouterLink class="table-link technical" :to="`/judgelab/${item.calibration_id}`">{{ item.calibration_id }}</RouterLink><div class="technical muted">{{ item.plan_digest.slice(0, 20) }}…</div></td><td>{{ item.suite_id }}@{{ item.suite_version }}</td><td><StatusBadge :value="item.status" /></td><td><StatusBadge :value="item.report_evidence_status" /></td><td>{{ item.judge_cell_count }}</td><td><StatusBadge v-for="value in item.qualifications" :key="value" :value="value" style="margin-right: 4px" /></td></tr></tbody></table></div>
    </div>
  </section>
</template>
