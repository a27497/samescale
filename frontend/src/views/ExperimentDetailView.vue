<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import MatrixHeatmap from '@/components/MatrixHeatmap.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useExperimentStore } from '@/stores/experiments'
import type { MatrixMetricKey } from '@/types/workbench'

const route = useRoute()
const store = useExperimentStore()
const router = useRouter()
type EvidenceTab = 'overview' | 'matrix' | 'runs' | 'statistics'
const tab = computed<EvidenceTab>({
  get: () => ['overview', 'matrix', 'runs', 'statistics'].includes(String(route.query.tab)) ? route.query.tab as EvidenceTab : 'overview',
  set: value => { void router.replace({ query: { ...route.query, tab: value } }) },
})
const id = computed(() => String(route.params.id))
const analysis = computed(() => store.modelComparison?.analysis ?? null)
const metrics: Array<{ key: MatrixMetricKey; label: string }> = [
  { key: 'success_rate', label: '成功率' }, { key: 'latency_p50_ms', label: '耗时 p50' },
  { key: 'latency_p95_ms', label: '耗时 p95' }, { key: 'infra_rate', label: '基础设施失败率' },
  { key: 'pass_at_1', label: 'pass@1' }, { key: 'pass_at_3', label: 'pass@3' },
]

const rateText = (value: { status: string; value: number | null }) =>
  value.status === 'AVAILABLE' && value.value !== null
    ? `${(value.value * 100).toFixed(1)}%`
    : 'NOT_AVAILABLE'

const percentagePointText = (value: number | null) =>
  value === null ? 'NOT_AVAILABLE' : `${value.toFixed(1)} pp`

const identityText = (value: { status: string; counts: Record<string, number>; missing_slots: number }) => {
  const known = Object.entries(value.counts).map(([name, count]) => `${name} (${count})`)
  if (value.missing_slots) known.push(`NOT_AVAILABLE (${value.missing_slots})`)
  return known.length ? known.join(', ') : 'NOT_AVAILABLE'
}

async function load() {
  store.stopPolling()
  const generation = store.pollingGeneration
  const loaded = await store.fetchExperiment(id.value, generation)
  if (loaded && generation === store.pollingGeneration && store.selected && !['completed', 'failed', 'cancelled'].includes(store.selected.status)) store.startPolling(id.value)
}
onMounted(load)
onBeforeUnmount(() => store.stopPolling())
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h2>{{ store.selected?.name ?? id }}</h2><p class="technical">{{ id }}</p></div>
      <div class="toolbar"><StatusBadge v-if="store.selected" :value="store.selected.status" /><StatusBadge v-if="store.durableStatus" :value="store.durableStatus.terminal ? 'DURABLE TERMINAL' : 'POLLING POSTGRES'" /></div>
    </div>
    <button v-if="store.error && !store.loading" class="secondary-button retry-button" @click="load">{{ t('重新加载') }}</button>
    <div v-if="store.loading" class="loading-state">{{ t('正在读取矩阵证据…') }}</div>
    <div v-else-if="store.error" class="error-state">{{ store.error }}</div>
    <template v-else-if="store.selected">
      <div class="tabs" :aria-label="t('实验证据视图')">
        <button v-for="name in ['overview', 'matrix', 'runs', 'statistics'] as const" :key="name" class="tab-button" :class="{ active: tab === name }" :aria-pressed="tab === name" @click="tab = name">{{ { overview: t('概览'), matrix: t('矩阵'), runs: t('运行记录'), statistics: t('统计') }[name] }}</button>
      </div>
      <template v-if="tab === 'overview'">
        <div class="metric-grid">
          <div class="metric-card accent"><div class="label">{{ t('计划运行数') }}</div><div class="value">{{ store.selected.planned_run_count }}</div><div class="detail">{{ store.selected.repeat_count }} {{ t('次重复') }}</div></div>
          <div class="metric-card"><div class="label">{{ t('能力结果完成数') }}</div><div class="value">{{ store.selected.completed_capability_count }}</div></div>
          <div class="metric-card"><div class="label">{{ t('基础设施') }}</div><div class="value">{{ store.selected.infra_count }}</div><div class="detail">{{ t('单独列出，不计入能力通过率') }}</div></div>
          <div class="metric-card"><div class="label">{{ t('维度') }}</div><div class="value">{{ store.selected.task_count }} × {{ store.selected.cell_count }}</div><div class="detail">{{ t('任务 × 单元') }}</div></div>
        </div>
        <div class="section-grid" style="margin-top: 16px">
          <div class="panel"><div class="panel-title"><h3>{{ t('实验单元') }}</h3></div><table class="data-table"><thead><tr><th>{{ t('单元') }}</th><th>{{ t('运行分组') }}</th><th>{{ t('模型') }}</th><th>{{ t('执行方式') }}</th></tr></thead><tbody><tr v-for="cell in store.selected.cells" :key="cell.cell_id"><td class="technical">{{ cell.cell_id }}</td><td>{{ cell.lane }}</td><td>{{ cell.requested_model }}</td><td>{{ cell.harness }}@{{ cell.harness_version }}</td></tr></tbody></table></div>
          <div class="panel"><div class="panel-title"><h3>{{ t('证据身份') }}</h3></div><dl class="definition-list"><dt>{{ t('计划') }}</dt><dd class="technical">{{ store.selected.plan_digest }}</dd><dt>{{ t('报告') }}</dt><dd class="technical">{{ store.selected.report_digest ?? 'NOT_REPORTED' }}</dd><dt>{{ t('对比目的 / 模式') }}</dt><dd>{{ store.selected.comparison_intent }} / {{ store.selected.evaluation_mode }}</dd><dt>{{ t('证据等级') }}</dt><dd><StatusBadge v-for="tier in store.selected.evidence_tiers" :key="tier" :value="tier" style="margin-right: 4px" /></dd></dl></div>
        </div>
      </template>
      <div v-else-if="tab === 'matrix'" class="panel">
        <div class="panel-title"><h3>{{ t('矩阵热图') }}</h3><select v-model="store.selectedMetric" :aria-label="t('矩阵指标')"><option v-for="metric in metrics" :key="metric.key" :value="metric.key">{{ t(metric.label) }}</option></select></div>
        <MatrixHeatmap v-if="store.matrix" :matrix="store.matrix" :metric="store.selectedMetric" />
        <div v-else class="empty-state">{{ t('尚无矩阵报告。') }}</div>
      </div>
      <div v-else-if="tab === 'runs'" class="panel">
        <div class="panel-title"><h3>{{ t('运行记录') }}</h3><span class="muted">{{ t('已保存的逻辑运行标识') }}</span></div>
        <table class="data-table"><thead><tr><th>{{ t('运行') }}</th><th>{{ t('单元 / 任务') }}</th><th>{{ t('运行分组') }}</th><th>{{ t('状态') }}</th><th>{{ t('结果') }}</th></tr></thead><tbody><tr v-for="run in store.runs" :key="run.run_id"><td><RouterLink class="table-link technical" :to="`/runs/${run.run_id}`">{{ run.run_id.slice(0, 24) }}…</RouterLink></td><td>{{ run.cell_id }}<br/><span class="muted">{{ run.task_id }} r{{ run.repeat_index }}</span></td><td>{{ run.lane }}</td><td><StatusBadge :value="run.status" /></td><td><StatusBadge :value="run.normalized_outcome ?? 'NOT_REPORTED'" /></td></tr></tbody></table>
      </div>
      <template v-else>
        <div v-if="analysis" class="panel">
          <div class="notice">{{ analysis.conclusion_semantics.permitted_interpretation }} {{ t('通过率差异仅为描述，仍需考虑可比性与缺失数据。') }}</div>
          <div class="metric-grid" style="margin-top: 16px">
            <div class="metric-card accent"><div class="label">{{ t('计划槽位') }}</div><div class="value">{{ analysis.overall.planned_slots }}</div></div>
            <div class="metric-card"><div class="label">{{ t('已采集槽位') }}</div><div class="value">{{ analysis.overall.acquired_slots }}</div><div class="detail">{{ t('未采集') }} {{ analysis.overall.unacquired_slots }}</div></div>
            <div class="metric-card"><div class="label">{{ t('能力分母') }}</div><div class="value">{{ analysis.overall.capability_denominator }}</div></div>
            <div class="metric-card"><div class="label">{{ t('通过') }}</div><div class="value">{{ analysis.overall.passed }}</div></div>
            <div class="metric-card"><div class="label">{{ t('失败') }}</div><div class="value">{{ analysis.overall.failed }}</div></div>
            <div class="metric-card"><div class="label">{{ t('基础设施') }}</div><div class="value">{{ analysis.overall.infra }}</div></div>
          </div>

          <div class="section-grid" style="margin-top: 16px">
            <div class="panel">
              <div class="panel-title"><h3>{{ t('配对能力结果') }}</h3><StatusBadge :value="analysis.comparability.category" /></div>
              <dl class="definition-list">
                <dt>{{ t('已配对 / 计划') }}</dt><dd>{{ analysis.pairs.matched_capability_pairs }} / {{ analysis.pairs.planned_pairs }}</dd>
                <dt>{{ t('两者均通过') }}</dt><dd>{{ analysis.pairs.both_pass }}</dd>
                <dt>{{ t('仅模型 A 通过') }}</dt><dd>{{ analysis.pairs.model_a_only_pass }}</dd>
                <dt>{{ t('仅模型 B 通过') }}</dt><dd>{{ analysis.pairs.model_b_only_pass }}</dd>
                <dt>{{ t('两者均失败') }}</dt><dd>{{ analysis.pairs.both_fail }}</dd>
                <dt>{{ t('基础设施 / 缺失') }}</dt><dd>{{ analysis.pairs.infra_pairs }} / {{ analysis.pairs.missing_pairs }}</dd>
                <dt>{{ t('各模型能力通过率差（B − A）') }}</dt><dd>{{ percentagePointText(analysis.pass_rate_differences.per_model_capability_pass_rate_difference_pp) }}</dd>
                <dt>{{ t('配对能力通过率差（B − A）') }}</dt><dd>{{ percentagePointText(analysis.pass_rate_differences.matched_capability_pair_pass_rate_difference_pp) }}</dd>
              </dl>
            </div>
            <div class="panel">
              <div class="panel-title"><h3>{{ t('证据限制') }}</h3></div>
              <dl class="definition-list">
                <dt>{{ t('可比性原因') }}</dt><dd class="technical">{{ Object.keys(analysis.comparability.reason_counts).join(', ') || 'NONE_REPORTED' }}</dd>
                <dt>{{ t('控制条件漂移') }}</dt><dd><StatusBadge :value="analysis.control_drift.status" /> {{ analysis.control_drift.affected_pairs }} {{ t('对 /') }} {{ analysis.control_drift.affected_runs }} {{ t('次运行') }}</dd>
                <dt>{{ t('轨迹覆盖') }}</dt><dd>{{ identityText(analysis.trace_coverage) }}</dd>
                <dt>{{ t('观测模型') }}</dt><dd>{{ identityText(analysis.observed_models) }}</dd>
                <dt>{{ t('观测服务') }}</dt><dd>{{ identityText(analysis.observed_providers) }}</dd>
                <dt>{{ t('恢复证据') }}</dt><dd><StatusBadge :value="analysis.recovery_attempts.status" /> {{ t('初始采集=') }}{{ analysis.recovery_attempts.explicitly_marked_primary_acquisitions }}{{ t(', 恢复=') }}{{ analysis.recovery_attempts.explicitly_marked_recovery_acquisitions }}{{ t(', 未标记=') }}{{ analysis.recovery_attempts.unmarked_acquisitions }}</dd>
                <dt>{{ t('租约领取') }}</dt><dd>{{ analysis.recovery_attempts.lease_claim_attempts }} {{ t('— 不解释为恢复尝试') }}</dd>
              </dl>
            </div>
          </div>

          <div class="panel" style="margin-top: 16px">
            <div class="panel-title"><h3>{{ t('各模型结果、身份、用量与费用') }}</h3></div>
            <table class="data-table">
              <thead><tr><th>{{ t('模型') }}</th><th>{{ t('通过 / 失败 / 基础设施') }}</th><th>{{ t('通过率') }}</th><th>{{ t('观测身份') }}</th><th>{{ t('轨迹') }}</th><th>{{ t('已知用量 / 费用') }}</th></tr></thead>
              <tbody>
                <tr v-for="model in analysis.models" :key="model.cell_id">
                  <td><strong>{{ model.model_label }}</strong> · {{ model.requested_model }}<br/><span class="muted technical">{{ model.cell_id }}</span></td>
                  <td>{{ model.passed }} / {{ model.failed }} / {{ model.infra }}<br/><span class="muted">{{ t('分母') }} {{ model.capability_denominator }}{{ t('，未采集') }} {{ model.unacquired_slots }}</span></td>
                  <td>{{ rateText(model.pass_rate) }}<br/><StatusBadge :value="model.evidence_tier" /></td>
                  <td>{{ identityText(model.observed_models) }}<br/><span class="muted">{{ t('服务：') }}{{ identityText(model.observed_providers) }}</span></td>
                  <td>{{ identityText(model.trace_coverage) }}</td>
                  <td>{{ t('输入') }} {{ model.usage_and_cost.input_tokens.known_total ?? 'NOT_AVAILABLE' }} {{ t('/ 输出') }} {{ model.usage_and_cost.output_tokens.known_total ?? 'NOT_AVAILABLE' }} tokens<br/><StatusBadge :value="model.usage_and_cost.explicit_cost.status" /> {{ t('费用') }} {{ model.usage_and_cost.explicit_cost.total ?? 'NOT_AVAILABLE' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="section-grid" style="margin-top: 16px">
            <div class="panel">
              <div class="panel-title"><h3>{{ t('失败表现') }}</h3></div>
              <table class="data-table"><thead><tr><th>{{ t('类别') }}</th><th>{{ t('槽位') }}</th></tr></thead><tbody><tr v-for="(count, category) in analysis.overall.failure_categories" :key="category"><td><StatusBadge :value="String(category)" /></td><td>{{ count }}</td></tr></tbody></table>
            </div>
            <div class="panel">
              <div class="panel-title"><h3>{{ t('按语言与任务类别细分') }}</h3></div>
              <table class="data-table"><thead><tr><th>{{ t('维度') }}</th><th>{{ t('数值') }}</th><th>{{ t('配对数') }}</th><th>{{ t('A / B 通过率') }}</th><th>{{ t('基础设施 / 缺失') }}</th></tr></thead><tbody><tr v-for="row in analysis.breakdowns" :key="`${row.dimension}:${row.value}`"><td>{{ row.dimension }}</td><td>{{ row.value }}</td><td>{{ row.matched_capability_pairs }} / {{ row.planned_pairs }}</td><td>{{ rateText(row.model_a_pass_rate) }} / {{ rateText(row.model_b_pass_rate) }}</td><td>{{ row.infra_pairs }} / {{ row.missing_pairs }}</td></tr></tbody></table>
            </div>
          </div>
          <dl class="definition-list" style="margin-top: 16px"><dt>{{ t('分析摘要') }}</dt><dd class="technical">{{ store.modelComparison?.analysis_digest }}</dd><dt>{{ t('恢复边界') }}</dt><dd>{{ analysis.recovery_attempts.note }}</dd></dl>
        </div>
        <div v-else class="panel"><div class="notice">{{ t('统计来自已保存的不可变实验报告。回归对比只描述差异方向，不作因果归因。') }}</div><dl class="definition-list" style="margin-top: 14px"><dt>{{ t('可比性') }}</dt><dd><span v-for="(count, status) in store.selected.comparability_summary" :key="status"><StatusBadge :value="String(status)" /> {{ count }} </span></dd><dt>{{ t('报告摘要') }}</dt><dd class="technical">{{ store.selected.report_digest }}</dd></dl></div>
      </template>
    </template>
  </section>
</template>
