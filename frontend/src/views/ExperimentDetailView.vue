<script setup lang="ts">
import { copy as c } from '@/composables/visualLocale'
import PageState from '@/components/PageState.vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import TechnicalDetails from '@/components/TechnicalDetails.vue'
import { configName, experimentName, runName, taskName, identityKey } from '@/utils/displayIdentity'
import { loadOutcomeCounts, unreportedCounts } from '@/utils/experimentResults'
import { evidenceLabel } from '@/utils/evidenceLabels'
import MatrixHeatmap from '@/components/MatrixHeatmap.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useExperimentStore } from '@/stores/experiments'
import type { MatrixMetricKey, ExperimentDetail } from '@/types/workbench'

const route = useRoute()
const router = useRouter()
const store = useExperimentStore()
const tabs = ['overview', 'matrix', 'runs', 'statistics'] as const
const tabLabels = computed(() => ({ overview: c('概览', 'Overview'), matrix: c('任务矩阵', 'Matrix'), runs: c('运行记录', 'Runs'), statistics: c('统计与限制', 'Statistics') }))
const tab = ref<typeof tabs[number]>(tabs.find(value => value === route.query.tab) ?? 'overview')
function selectTab(value: typeof tabs[number]) { tab.value = value; void router.push({ query: { ...route.query, tab: value } }) }
const runSearch = computed({ get: () => typeof route.query.search === 'string' ? route.query.search : '', set: value => { void router.replace({ query: { ...route.query, search: value || undefined } }) } })
const filteredRuns = computed(() => store.runs.filter(run => `${runName(run, store.runs.map(item => item.run_id))} ${run.run_id} ${run.task_id} ${run.cell_id}`.toLowerCase().includes(runSearch.value.toLowerCase())))
const id = computed(() => String(route.params.id))
const outcomes = ref(unreportedCounts())
const analysis = computed(() => store.modelComparison?.analysis ?? null)
const metrics = computed<Array<{ key: MatrixMetricKey; label: string }>>(() => [
  { key: 'success_rate', label: c('通过率', 'Success rate') }, { key: 'latency_p50_ms', label: c('耗时中位数', 'Latency p50') },
  { key: 'latency_p95_ms', label: c('耗时第 95 百分位', 'Latency p95') }, { key: 'infra_rate', label: c('基础设施失败率', 'Infra rate') },
  { key: 'pass_at_1', label: 'pass@1' }, { key: 'pass_at_3', label: 'pass@3' },
])

const rateText = (value: { status: string; value: number | null }) =>
  value.status === 'AVAILABLE' && value.value !== null
    ? `${(value.value * 100).toFixed(1)}%`
    : c('未报告', 'NOT_AVAILABLE')

const percentagePointText = (value: number | null) =>
  value === null ? c('未报告', 'NOT_AVAILABLE') : `${value.toFixed(1)} pp`

const identityText = (value: { status: string; counts: Record<string, number>; missing_slots: number }) => {
  const known = Object.entries(value.counts).map(([name, count]) => `${name.length > 32 ? `${c('身份', 'Identity')} · ${identityKey(name)}` : evidenceLabel(name)} (${count})`)
  if (value.missing_slots) known.push(`${c('未报告', 'NOT_AVAILABLE')} (${value.missing_slots})`)
  return known.length ? known.join(', ') : c('未报告', 'NOT_AVAILABLE')
}

async function loadExperiment() {
  const requested = id.value
  outcomes.value = unreportedCounts()
  store.stopPolling(); store.selected = null; store.durableStatus = null
  await store.fetchExperiment(requested)
  const selected = store.selected as ExperimentDetail | null
  if (id.value === requested && selected && !['completed', 'failed', 'cancelled'].includes(selected.status)) store.startPolling(requested)
}
watch(() => store.selected, async selected => {
  outcomes.value = unreportedCounts()
  if (!selected) return
  const counts = await loadOutcomeCounts(selected)
  if (store.selected === selected) outcomes.value = counts
})
onMounted(loadExperiment)
onBeforeUnmount(() => store.stopPolling())
watch(() => route.params.id, async value => { if (value) await loadExperiment() })
watch(() => route.query.tab, value => { tab.value = tabs.find(item => item === value) ?? 'overview' })
</script>

<template>
  <section class="experiments-page evidence-page">
    <div class="page-heading">
      <div><h2>{{ store.selected ? experimentName(store.selected) : c('实验详情', 'Experiment details') }}</h2></div>
      <div class="toolbar"><StatusBadge localized v-if="store.selected" :value="store.selected.status" context="experiment" /></div>
    </div>
    <PageState v-if="store.loading" kind="loading">{{ c('正在读取已保存实验证据…', 'Loading persisted Matrix evidence…') }}</PageState>
    <PageState v-else-if="store.error" kind="error" reload>{{ c('实验证据暂不可用或完整性校验未通过，未展示替代结果。', 'Experiment evidence is unavailable or failed integrity checks. No substitute results are shown.') }}<details><summary>{{ c('查看错误记录', 'View error record') }}</summary>{{ store.error }}</details></PageState>
    <template v-else-if="store.selected">
      <div class="experiment-context"><StatusBadge localized :value="store.selected.provenance ?? 'UNVERIFIED_SOURCE'" /> {{ store.selected.provenance === 'FIXTURE_OFFLINE' ? c('固定 Fake 样例，不代表真实 Provider 或模型执行。', 'Keyless Fake fixture evidence; no real Provider/model execution.') : c('保存记录本身不认证 Provider 来源。', 'Persisted evidence does not by itself authenticate a Provider response.') }}</div>
      <div class="tabs" role="tablist" :aria-label="c('实验证据章节', 'Experiment sections')">
        <button v-for="name in tabs" :key="name" class="tab-button" role="tab" :aria-selected="tab === name" :class="{ active: tab === name }" @click="selectTab(name)">{{ tabLabels[name] }}</button>
      </div>
      <template v-if="tab === 'overview'">
        <div class="metric-grid result-metrics">
          <div class="metric-card accent"><div class="label">{{ c('计划运行', 'Planned runs') }}</div><div class="value">{{ store.selected.planned_run_count }}</div><div class="detail">{{ store.selected.task_count }} {{ c('任务 ×', 'tasks ×') }} {{ store.selected.cell_count }} {{ c('配置；', 'configurations;') }} {{ store.selected.repeat_count }} {{ c('次重复', 'repeats') }}</div></div>
          <div class="metric-card"><div class="label">{{ c('已收集任务结果', 'Collected task results') }}</div><div class="value">{{ store.selected.completed_capability_count ?? c('未报告', 'Not reported') }}</div><div class="detail">{{ c('通过 + 未通过，不是通过数量', 'Passed + failed, not a pass count') }}</div></div>
          <div class="metric-card"><div class="label">{{ c('任务通过', 'Task passed') }}</div><div class="value">{{ outcomes.passed ?? c('未报告', 'Not reported') }}</div></div>
          <div class="metric-card"><div class="label">{{ c('任务未通过', 'Task failed') }}</div><div class="value">{{ outcomes.failed ?? c('未报告', 'Not reported') }}</div></div>
          <div class="metric-card"><div class="label">{{ c('基础设施失败', 'Infra') }}</div><div class="value">{{ store.selected.infra_count ?? c('未报告', 'Not reported') }}</div><div class="detail">{{ c('与任务结果分别计数', 'Never hidden in success rate') }}</div></div>
        </div>
        <div class="section-grid" style="margin-top: 16px">
          <div class="panel"><div class="panel-title"><h3>{{ c('实验配置（Cell）', 'Experiment cells') }}</h3></div><div class="responsive-table" role="region" :aria-label="c('实验证据表格', 'Experiment evidence')" tabindex="0"><table class="data-table"><thead><tr><th>{{ c('配置', 'Configuration') }}</th><th>{{ c('通道', 'Lane') }}</th><th>{{ c('请求模型', 'Model') }}</th><th>{{ c('Harness', 'Harness') }}</th></tr></thead><tbody><tr v-for="cell in store.selected.cells" :key="cell.cell_id"><td>{{ configName(cell.cell_id, store.selected.cells.map(item => item.cell_id)) }}<TechnicalDetails :fields="[{ label: 'Cell ID', value: cell.cell_id }, { label: c('请求模型', 'Requested model'), value: cell.requested_model }, { label: 'Harness', value: `${cell.harness}@${cell.harness_version}` }, { label: 'Provider route', value: cell.provider_route }]" /></td><td>{{ cell.lane }}</td><td>{{ cell.requested_model === 'fake-public-demo-model' ? c('离线演示模型', 'Offline demo model') : cell.requested_model.length > 32 ? c('见配置详情', 'See configuration details') : cell.requested_model }}</td><td>{{ cell.harness }}</td></tr></tbody></table></div></div>
          <div class="panel"><h3>{{ c('证据概况', 'Evidence overview') }}</h3><p>{{ c('保存的任务结果与配置；正式比较须先检查可比条件。', 'Saved task outcomes and configurations. Formal comparison requires eligible evidence.') }}</p><div class="toolbar"><StatusBadge localized v-for="tier in store.selected.evidence_tiers" :key="tier" :value="tier" /></div></div>
        </div>
      </template>
      <div v-else-if="tab === 'matrix'" class="panel">
        <div class="panel-title"><h3>{{ c('任务矩阵', 'Matrix heatmap') }}</h3><select v-model="store.selectedMetric" :aria-label="c('矩阵指标', 'Matrix metric')"><option v-for="metric in metrics" :key="metric.key" :value="metric.key">{{ metric.label }}</option></select></div>
        <MatrixHeatmap v-if="store.matrix" :matrix="store.matrix" :metric="store.selectedMetric" localized />
        <PageState v-else kind="empty">{{ c('尚未报告任务矩阵。', 'Matrix report is NOT_REPORTED.') }}</PageState>
      </div>
      <div v-else-if="tab === 'runs'" class="panel">
        <div class="panel-title"><h3>{{ c('运行记录', 'Runs') }}</h3><input v-model="runSearch" :aria-label="c('搜索运行', 'Search runs')" :placeholder="c('搜索任务、配置或原始 ID', 'Search task, configuration or original ID')" /></div>
        <p class="muted">{{ c('显示', 'Showing') }} {{ filteredRuns.length }} / {{ store.runs.length }} {{ c('条已加载运行', 'loaded runs') }}</p><PageState v-if="!filteredRuns.length" kind="empty">{{ c('没有匹配的已加载运行，试试任务名或原始 ID。', 'No loaded runs match. Try a task name or original ID.') }}</PageState><div v-else class="responsive-table" role="region" :aria-label="c('实验证据表格', 'Experiment evidence')" tabindex="0"><table class="data-table"><thead><tr><th>{{ c('运行', 'Run') }}</th><th>{{ c('配置', 'Configuration') }}</th><th>{{ c('通道', 'Lane') }}</th><th>{{ c('运行状态', 'Status') }}</th><th>{{ c('任务结果', 'Outcome') }}</th></tr></thead><tbody><tr v-for="run in filteredRuns" :key="run.run_id"><td><RouterLink class="table-link" :to="{ path: `/runs/${run.run_id}`, query: { candidate: route.query.candidate, from: route.fullPath } }">{{ runName(run, store.runs.map(item => item.run_id)) }}</RouterLink></td><td>{{ configName(run.cell_id, store.selected.cells.map(item => item.cell_id)) }}<br/><span class="muted">{{ c('版本', 'Version') }} {{ run.task_version }}</span><TechnicalDetails :fields="[{ label: 'Run ID', value: run.run_id }, { label: 'Cell ID', value: run.cell_id }, { label: c('任务 ID', 'Task ID'), value: run.task_id }, { label: 'repeat_index', value: run.repeat_index }, { label: 'attempt', value: run.attempt }]" /></td><td>{{ run.lane }}</td><td><StatusBadge localized :value="run.status" context="run" /></td><td><StatusBadge localized :value="run.normalized_outcome ?? 'NOT_REPORTED'" /></td></tr></tbody></table></div>
      </div>
      <template v-else>
        <div v-if="analysis" class="panel">
          <div class="notice">{{ c('通过率差异仅作描述。先核对可比性与缺失记录，再解读数值。', 'Pass-rate differences are descriptive. Check comparability and missingness first.') }}<details><summary>{{ c('后端原始解释范围', 'Original backend interpretation') }}</summary>{{ analysis.conclusion_semantics.permitted_interpretation }}</details></div>
          <div class="metric-grid" style="margin-top: 16px">
            <div class="metric-card accent"><div class="label">{{ c('计划观察', 'Planned slots') }}</div><div class="value">{{ analysis.overall.planned_slots }}</div></div>
            <div class="metric-card"><div class="label">{{ c('已收集观察', 'Acquired slots') }}</div><div class="value">{{ analysis.overall.acquired_slots }}</div><div class="detail">{{ c('未收集', 'Unacquired') }} {{ analysis.overall.unacquired_slots }}</div></div>
            <div class="metric-card"><div class="label">{{ c('能力结果分母', 'Capability denominator') }}</div><div class="value">{{ analysis.overall.capability_denominator }}</div></div>
            <div class="metric-card"><div class="label">{{ c('任务通过', 'PASS') }}</div><div class="value">{{ analysis.overall.passed }}</div></div>
            <div class="metric-card"><div class="label">{{ c('任务未通过', 'FAIL') }}</div><div class="value">{{ analysis.overall.failed }}</div></div>
            <div class="metric-card"><div class="label">{{ c('基础设施失败', 'INFRA') }}</div><div class="value">{{ analysis.overall.infra }}</div></div>
          </div>

          <div class="section-grid" style="margin-top: 16px">
            <div class="panel">
              <div class="panel-title"><h3>{{ c('配对能力结果', 'Matched capability pairs') }}</h3><StatusBadge localized :value="analysis.comparability.category" /></div>
              <dl class="definition-list">
                <dt>{{ c('已匹配 / 计划配对', 'Matched / planned') }}</dt><dd>{{ analysis.pairs.matched_capability_pairs }} / {{ analysis.pairs.planned_pairs }}</dd>
                <dt>{{ c('两侧均通过', 'Both pass') }}</dt><dd>{{ analysis.pairs.both_pass }}</dd>
                <dt>{{ c('仅 A 通过', 'Model A only') }}</dt><dd>{{ analysis.pairs.model_a_only_pass }}</dd>
                <dt>{{ c('仅 B 通过', 'Model B only') }}</dt><dd>{{ analysis.pairs.model_b_only_pass }}</dd>
                <dt>{{ c('两侧均未通过', 'Both fail') }}</dt><dd>{{ analysis.pairs.both_fail }}</dd>
                <dt>{{ c('基础设施失败 / 缺失', 'Infra / missing') }}</dt><dd>{{ analysis.pairs.infra_pairs }} / {{ analysis.pairs.missing_pairs }}</dd>
                <dt>{{ c('各模型能力通过率差（B − A）', 'Per-model capability rates (B − A)') }}</dt><dd>{{ percentagePointText(analysis.pass_rate_differences.per_model_capability_pass_rate_difference_pp) }}</dd>
                <dt>{{ c('配对能力通过率差（B − A）', 'Matched capability-pair rates (B − A)') }}</dt><dd>{{ percentagePointText(analysis.pass_rate_differences.matched_capability_pair_pass_rate_difference_pp) }}</dd>
              </dl>
            </div>
            <div class="panel">
              <div class="panel-title"><h3>{{ c('证据限制', 'Evidence limits') }}</h3></div>
              <dl class="definition-list">
                <dt>{{ c('可比性原因', 'Comparability reasons') }}</dt><dd class="technical">{{ Object.keys(analysis.comparability.reason_counts).map(reason => evidenceLabel(reason) === reason ? c('未分类约束', 'Unclassified constraint') : evidenceLabel(reason)).join('、') || c('未报告', 'Not reported') }}</dd>
                <dt>{{ c('控制条件变化', 'Control drift') }}</dt><dd><StatusBadge localized :value="analysis.control_drift.status" /> {{ analysis.control_drift.affected_pairs }} {{ c('对 /', 'pairs /') }} {{ analysis.control_drift.affected_runs }} {{ c('条运行', 'runs') }}</dd>
                <dt>{{ c('Trace 覆盖', 'Trace coverage') }}</dt><dd>{{ identityText(analysis.trace_coverage) }}</dd>
                <dt>{{ c('观察到的模型', 'Observed models') }}</dt><dd>{{ identityText(analysis.observed_models) }}</dd>
                <dt>{{ c('观察到的 Provider', 'Observed providers') }}</dt><dd>{{ identityText(analysis.observed_providers) }}</dd>
                <dt>{{ c('恢复记录', 'Recovery evidence') }}</dt><dd><StatusBadge localized :value="analysis.recovery_attempts.status" /> {{ c('首轮', 'primary') }}={{ analysis.recovery_attempts.explicitly_marked_primary_acquisitions }}, {{ c('恢复', 'recovery') }}={{ analysis.recovery_attempts.explicitly_marked_recovery_acquisitions }}, {{ c('未标记', 'unmarked') }}={{ analysis.recovery_attempts.unmarked_acquisitions }}</dd>
                <dt>{{ c('租约领取次数', 'Lease claims') }}</dt><dd>{{ analysis.recovery_attempts.lease_claim_attempts }} — {{ c('不作为恢复尝试次数', 'not interpreted as recovery attempts') }}</dd>
              </dl>
            </div>
          </div>

          <div class="panel" style="margin-top: 16px">
            <div class="panel-title"><h3>{{ c('各模型的结果、身份、用量与费用', 'Per-model outcomes, identity, usage, and cost') }}</h3></div>
            <div class="responsive-table" role="region" :aria-label="c('实验证据表格', 'Experiment evidence')" tabindex="0"><table class="data-table">
              <thead><tr><th>{{ c('请求模型', 'Model') }}</th><th>{{ c('通过 / 未通过 / 基础设施失败', 'PASS / FAIL / INFRA') }}</th><th>{{ c('通过率', 'Pass rate') }}</th><th>{{ c('观察身份', 'Observed identity') }}</th><th>{{ c('Trace 覆盖', 'Trace') }}</th><th>{{ c('已报告用量 / 费用', 'Known usage / cost') }}</th></tr></thead>
              <tbody>
                <tr v-for="model in analysis.models" :key="model.cell_id">
                  <td><strong>{{ model.model_label === 'MODEL_A' ? c('模型 A', 'Model A') : c('模型 B', 'Model B') }}</strong><TechnicalDetails :fields="[{ label: 'Cell ID', value: model.cell_id }, { label: c('请求模型', 'Requested model'), value: model.requested_model }]" /></td>
                  <td>{{ model.passed }} / {{ model.failed }} / {{ model.infra }}<br/><span class="muted">{{ c('分母', 'denominator') }} {{ model.capability_denominator }}, {{ c('未收集', 'unacquired') }} {{ model.unacquired_slots }}</span></td>
                  <td>{{ rateText(model.pass_rate) }}<br/><StatusBadge localized :value="model.evidence_tier" /></td>
                  <td>{{ identityText(model.observed_models) }}<br/><span class="muted">Provider: {{ identityText(model.observed_providers) }}</span></td>
                  <td>{{ identityText(model.trace_coverage) }}</td>
                  <td>{{ c('输入', 'Input') }} {{ model.usage_and_cost.input_tokens.known_total ?? c('未报告', 'NOT_AVAILABLE') }} / {{ c('输出', 'output') }} {{ model.usage_and_cost.output_tokens.known_total ?? c('未报告', 'NOT_AVAILABLE') }} tokens<br/><StatusBadge localized :value="model.usage_and_cost.explicit_cost.status" /> {{ c('费用', 'cost') }} {{ model.usage_and_cost.explicit_cost.total ?? c('未报告', 'NOT_AVAILABLE') }}</td>
                </tr>
              </tbody>
            </table></div>
          </div>

          <div class="section-grid" style="margin-top: 16px">
            <div class="panel">
              <div class="panel-title"><h3>{{ c('失败分类', 'Failure presentation') }}</h3></div>
              <div class="responsive-table" role="region" :aria-label="c('实验证据表格', 'Experiment evidence')" tabindex="0"><table class="data-table"><thead><tr><th>{{ c('类别', 'Category') }}</th><th>{{ c('观察数量', 'Slots') }}</th></tr></thead><tbody><tr v-for="(count, category) in analysis.overall.failure_categories" :key="category"><td><StatusBadge localized :value="String(category)" /></td><td>{{ count }}</td></tr></tbody></table></div>
            </div>
            <div class="panel">
              <div class="panel-title"><h3>{{ c('按语言 / 任务类型统计', 'Language / task-family breakdown') }}</h3></div>
              <div class="responsive-table" role="region" :aria-label="c('实验证据表格', 'Experiment evidence')" tabindex="0"><table class="data-table"><thead><tr><th>{{ c('维度', 'Dimension') }}</th><th>{{ c('值', 'Value') }}</th><th>{{ c('配对数量', 'Pairs') }}</th><th>{{ c('A / B 通过率', 'A / B pass rate') }}</th><th>{{ c('基础设施失败 / 缺失', 'Infra / missing') }}</th></tr></thead><tbody><tr v-for="row in analysis.breakdowns" :key="`${row.dimension}:${row.value}`"><td>{{ row.dimension === 'language' ? c('语言', 'Language') : c('任务类型', 'Task family') }}</td><td>{{ row.value }}</td><td>{{ row.matched_capability_pairs }} / {{ row.planned_pairs }}</td><td>{{ rateText(row.model_a_pass_rate) }} / {{ rateText(row.model_b_pass_rate) }}</td><td>{{ row.infra_pairs }} / {{ row.missing_pairs }}</td></tr></tbody></table></div>
            </div>
          </div>
          <details><summary>{{ c('恢复记录说明 · 原文', 'Recovery note · source') }}</summary><p>{{ analysis.recovery_attempts.note }}</p></details>
        </div>
        <div v-else class="panel"><div class="notice">{{ c('统计来自已保存的后端报告。对比需先满足可比条件，描述性方向不证明因果。', 'Statistics come from the saved backend report. Comparisons require eligible evidence; descriptive direction does not establish causality.') }}</div><dl class="definition-list" style="margin-top: 14px"><dt>{{ c('可比性', 'Comparability') }}</dt><dd><StatusBadge localized v-if="!Object.keys(store.selected.comparability_summary ?? {}).length" value="NOT_REPORTED" /><span v-for="(count, status) in store.selected.comparability_summary" :key="status"><StatusBadge localized :value="String(status)" /> {{ count }} </span></dd></dl></div>
      </template>
      <TechnicalDetails class="panel" :summary="c('实验身份与完整配置', 'Experiment identity & full configuration')" :fields="[{ label: 'Experiment ID', value: store.selected.experiment_id }, { label: c('原始名称', 'Original name'), value: store.selected.name }, { label: c('计划 SHA256', 'Plan SHA256'), value: store.selected.plan_digest }, { label: c('报告 SHA256', 'Report SHA256'), value: store.selected.report_digest }, { label: c('分析 SHA256', 'Analysis SHA256'), value: store.modelComparison?.analysis_digest }, { label: c('比较目的 / 模式', 'Intent / mode'), value: `${store.selected.comparison_intent} / ${store.selected.evaluation_mode}` }]" ><details><summary>{{ c('配置和统计原文', 'Source configuration & statistics') }}</summary><pre class="raw-evidence">{{ JSON.stringify({ experiment: store.selected, analysis: store.modelComparison }, null, 2) }}</pre></details></TechnicalDetails>
    </template>
  </section>
</template>
