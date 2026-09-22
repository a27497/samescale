<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { workbenchApi } from '@/api/client'
import EvidenceChart from '@/components/EvidenceChart.vue'
import EvidenceValue from '@/components/EvidenceValue.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import TraceTimeline from '@/components/TraceTimeline.vue'
import type { RunDetail, TraceResponse } from '@/types/workbench'

const route = useRoute()
const run = ref<RunDetail | null>(null)
const trace = ref<TraceResponse | null>(null)
const loading = ref(true)
const error = ref(false)
const runId = computed(() => String(route.params.runId))
const chartItems = computed(() => run.value ? [
  { label: '耗时（毫秒）', evidence: run.value.duration_ms },
  { label: '输入 Token', evidence: run.value.input_tokens },
  { label: '输出 Token', evidence: run.value.output_tokens },
  { label: '已报告费用', evidence: run.value.explicit_cost },
] : [])

async function load() {
  loading.value = true; error.value = false

  try { [run.value, trace.value] = await Promise.all([workbenchApi.getRun(runId.value), workbenchApi.getTrace(runId.value)]) }
  catch { error.value = true } finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <section>
    <RouterLink class="back-link" :to="run ? { path: `/experiments/${run.experiment_id}`, query: { tab: 'runs' } } : '/run-control'">{{ run ? t('返回所属实验的运行记录') : t('返回运行记录') }}</RouterLink>
    <div class="page-heading"><div><h2>{{ t('运行详情') }}</h2><p class="technical">{{ runId }}</p></div><StatusBadge v-if="run" :value="run.status" /></div>
    <button v-if="error && !loading" class="secondary-button retry-button" @click="load">{{ t('重新加载') }}</button>
    <div v-if="loading" class="loading-state">{{ t('正在读取运行证据…') }}</div>
    <div v-else-if="error || !run" class="error-state">{{ t('运行证据不可用或未通过完整性校验。') }}</div>
    <template v-else>
      <div class="section-grid">
        <div class="panel"><div class="panel-title"><h3>{{ t('身份与运行状态') }}</h3></div><dl class="definition-list"><dt>{{ t('实验') }}</dt><dd><RouterLink class="table-link technical" :to="`/experiments/${run.experiment_id}`">{{ run.experiment_id }}</RouterLink></dd><dt>{{ t('单元 / 任务') }}</dt><dd>{{ run.cell_id }} / {{ run.task_id }}@{{ run.task_version }}</dd><dt>{{ t('分组 / 重复序号') }}</dt><dd>{{ run.lane }} / {{ run.repeat_index }}</dd><dt>{{ t('尝试序号') }}</dt><dd>{{ run.attempt }}</dd><dt>{{ t('结果') }}</dt><dd><StatusBadge :value="run.normalized_outcome ?? 'NOT_REPORTED'" /> <span class="technical muted">{{ run.source_outcome }}</span></dd><dt>{{ t('校验器') }}</dt><dd>{{ run.verifier_passed === null ? 'NOT_REPORTED' : run.verifier_passed ? 'PASS' : 'FAIL' }} · <EvidenceValue :evidence="run.verifier_score" /></dd></dl></div>
        <div class="panel"><div class="panel-title"><h3>{{ t('执行信息') }}</h3></div><dl class="definition-list"><dt>{{ t('请求模型') }}</dt><dd>{{ run.requested_model ?? 'NOT_REPORTED' }}</dd><dt>{{ t('观测模型') }}</dt><dd>{{ run.observed_model ?? 'NOT_REPORTED' }}</dd><dt>{{ t('服务路由') }}</dt><dd class="technical">{{ run.provider_route ?? 'NOT_REPORTED' }}</dd><dt>{{ t('执行方式') }}</dt><dd>{{ run.harness }}@{{ run.harness_version }}</dd><dt>{{ t('轨迹覆盖') }}</dt><dd><StatusBadge :value="run.trace_coverage ?? 'NOT_REPORTED'" /></dd><dt>{{ t('可比性') }}</dt><dd><StatusBadge :value="run.comparability ?? 'NOT_REPORTED'" /></dd><dt>{{ t('产物') }}</dt><dd class="technical">{{ run.artifact_name }} / {{ run.evidence_digest }}</dd></dl></div>
      </div>
      <div class="panel"><div class="panel-title"><h3>{{ t('耗时、Token 与费用证据') }}</h3><span class="muted">{{ t('不根据模型名称推测费用。') }}</span></div><EvidenceChart :title="t('运行用量证据')" :items="chartItems" /></div>
      <div class="panel"><div class="panel-title"><h3>{{ t('标准化轨迹') }}</h3><span class="muted">{{ t('不加载原生私有对话记录。') }}</span></div><TraceTimeline v-if="trace" :trace="trace" /><div v-else class="empty-state">{{ t('轨迹尚未报告') }}</div></div>
    </template>
  </section>
</template>
