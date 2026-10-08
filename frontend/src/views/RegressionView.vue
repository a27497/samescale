<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { workbenchApi } from '@/api/client'
import EvidenceValue from '@/components/EvidenceValue.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import PageState from '@/components/PageState.vue'
import { copy as c } from '@/composables/visualLocale'
import { eligibleDirection } from '@/utils/visualEvidence'
import type { ExperimentSummary, RegressionIntent, RegressionResponse } from '@/types/workbench'
const route = useRoute()
const router = useRouter()
const baseline = ref('')
const candidate = ref('')
const intent = ref<RegressionIntent>('MODEL_COMPARISON')
const experiments = ref<ExperimentSummary[]>([])
const result = ref<RegressionResponse | null>(null)
const loading = ref(false)
const error = ref(false)
const listError = ref(false)
let sequence = 0
onUnmounted(() => { sequence++ })
const intents = computed(() => ({ MODEL_COMPARISON: c('模型对比', 'Model comparison'), HARNESS_UPLIFT: c('Harness 差异探索', 'Harness uplift investigation'), NATIVE_HARNESS_SYSTEM_COMPARISON: c('原生 Harness 系统对比', 'Native harness-system comparison'), GENERAL: c('探索性对比', 'Exploratory comparison') }))
function clearResult() { sequence++; result.value = null; error.value = false; loading.value = false }
watch([baseline, candidate, intent], clearResult)
async function compare(updateUrl = true) {
  if (!baseline.value || !candidate.value || loading.value) return
  const request = ++sequence
  loading.value = true; error.value = false; result.value = null
  if (updateUrl && router) void router.push({ query: { ...route?.query, baseline: baseline.value, candidate: candidate.value, intent: intent.value } })
  try { const response = await workbenchApi.compare(baseline.value, candidate.value, intent.value); if (request === sequence) result.value = response }
  catch { if (request === sequence) error.value = true }
  finally { if (request === sequence) loading.value = false }
}
function readQuery() {
  const q = route?.query
  baseline.value = typeof q?.baseline === 'string' ? q.baseline : ''
  candidate.value = typeof q?.candidate === 'string' ? q.candidate : ''
  if (typeof q?.intent === 'string' && q.intent in intents.value) intent.value = q.intent as RegressionIntent
}
watch(() => route?.fullPath, async () => {
  const q = route?.query
  if (q?.baseline === baseline.value && q?.candidate === candidate.value && (!q?.intent || q.intent === intent.value)) return
  readQuery(); await Promise.resolve(); if (baseline.value && candidate.value) void compare(false)
})
onMounted(async () => {
  readQuery()
  try { experiments.value = (await workbenchApi.listExperiments({ limit: 100 })).items }
  catch { listError.value = true }
  if (baseline.value && candidate.value) await compare(false)
})
</script>
<template>
  <section class="evidence-page regression-page"><div class="page-heading"><div><h2>{{ c('候选对比', 'Regression comparison') }}</h2><p>{{ c('先确认可比条件，再阅读已保存报告中的差异。不会重新运行 Agent。', 'Check comparability before interpreting saved report differences. No agent is rerun.') }}</p></div><StatusBadge value="READ_ONLY" localized /></div>
    <div class="comparison-inputs"><label class="panel"><span class="evidence-label">{{ c('基线实验', 'Baseline experiment') }}</span><input v-model="baseline" list="regression-experiments" :aria-label="c('基线实验 ID', 'Baseline experiment ID')" data-test="baseline" :placeholder="c('输入或选择实验 ID', 'Enter or select an experiment ID')" /><small>{{ experiments.find(item => item.experiment_id === baseline)?.name ?? c('已有实验的保存身份', 'Saved identity of an existing experiment') }}</small></label><label class="panel"><span class="evidence-label">{{ c('候选实验', 'Candidate experiment') }}</span><input v-model="candidate" list="regression-experiments" :aria-label="c('候选实验 ID', 'Candidate experiment ID')" data-test="candidate" :placeholder="c('输入或选择实验 ID', 'Enter or select an experiment ID')" /><small>{{ experiments.find(item => item.experiment_id === candidate)?.name ?? c('已有实验的保存身份', 'Saved identity of an existing experiment') }}</small></label><datalist id="regression-experiments"><option v-for="experiment in experiments" :key="experiment.experiment_id" :value="experiment.experiment_id">{{ experiment.name }}</option></datalist></div>
    <div class="comparison-toolbar toolbar"><label>{{ c('比较目的', 'Comparison intent') }}<select v-model="intent" :aria-label="c('比较目的', 'Comparison intent')" data-test="intent"><option v-for="(label, key) in intents" :key="key" :value="key">{{ label }}</option></select></label><button class="primary-button" :disabled="!baseline || !candidate || loading" @click="compare()">{{ loading ? c('正在对比…', 'Comparing…') : c('对比保存的报告', 'Compare saved reports') }}</button><RouterLink v-if="typeof route?.query?.run === 'string'" class="secondary-button" :to="{ path: `/runs/${route.query.run}`, query: { candidate } }">{{ c('查看基线运行', 'View baseline run') }}</RouterLink></div><p v-if="listError" class="muted">{{ c('实验列表暂不可用；仍可通过已有 ID 对比。', 'The experiment list is unavailable; existing IDs can still be compared.') }}</p>
    <PageState v-if="loading" kind="loading">{{ c('正在核对保存报告与可比条件…', 'Checking saved reports and comparison conditions…') }}</PageState><PageState v-else-if="error" kind="error">{{ c('暂时无法比较这些报告。请检查实验身份及证据完整性。', 'These reports could not be compared. Check experiment identities and evidence integrity.') }}<button class="secondary-button" @click="compare(false)">{{ c('重试', 'Retry') }}</button></PageState><PageState v-else-if="!result" kind="empty">{{ c('请选择两个已有的实验以比较保存的报告。', 'Select two existing experiments to compare their saved reports.') }}</PageState>
    <template v-if="result"><article v-for="(item, index) in result.comparisons" :key="`${item.baseline_cell_id}:${item.candidate_cell_id}`" class="regression-comparison"><section class="panel comparability-panel"><div class="panel-title"><div><span class="evidence-label">{{ c('可比性与证据限制', 'Comparability & evidence limits') }} · {{ index + 1 }}</span><h3>{{ item.comparability === 'COMPARABLE' ? c('满足已报告的可比条件；方向仅作描述。', 'Reported comparability conditions are met; direction is descriptive only.') : item.comparability === 'PARTIALLY_COMPARABLE' ? c('仅部分观察可比，不能据此判断整体改进或回归。', 'Only some observations are comparable; no overall improvement or regression can be concluded.') : c('当前证据不满足可比条件，暂不判断改进或回归。', 'Current evidence is not comparable. No improvement or regression is concluded.') }}</h3></div><StatusBadge :value="item.comparability" localized /></div><div class="comparability-count"><span>{{ c('可比配对 / 已配对观察', 'Eligible pairs / paired observations') }}</span><strong>{{ item.eligible_paired_observations }} / {{ item.paired_observations }}</strong><span class="technical">{{ item.baseline_cell_id }} / {{ item.candidate_cell_id }}</span></div><div class="reason-grid"><article v-for="reason in item.reason_codes" :key="reason"><span class="evidence-label">{{ c('不满足条件的原因', 'Comparability constraint') }}</span><strong class="technical">{{ reason }}</strong></article></div></section>
        <section class="panel metric-comparison"><div class="panel-header"><h3>{{ c('描述性指标对照', 'Descriptive metric comparison') }}</h3><span class="status-pill neutral">DESCRIPTIVE_DIFF</span></div><div class="responsive-table"><table class="data-table"><thead><tr><th>{{ c('维度 / 指标', 'Dimension / metric') }}</th><th>{{ c('基线', 'Baseline') }}</th><th>{{ c('候选', 'Candidate') }}</th><th>{{ c('解释范围', 'Interpretation') }}</th></tr></thead><tbody>
          <tr><td>{{ c('证据来源', 'Evidence provenance') }}</td><td><StatusBadge :value="result.baseline_provenance" localized /></td><td><StatusBadge :value="result.candidate_provenance" localized /></td><td>{{ c('固定 Fake 与真实调用保持区分', 'Fake fixtures remain distinct from real calls') }}</td></tr>
          <tr><td>{{ c('共同任务原始通过率', 'Raw rate on common tasks') }}</td><td><EvidenceValue :evidence="item.common_baseline_value" localized /></td><td><EvidenceValue :evidence="item.common_candidate_value" localized /></td><td>{{ c('共同任务中的原始描述值', 'Raw descriptive values on common tasks') }}</td></tr>
          <tr><td>{{ c('可比配对通过率', 'Comparable-pair rate') }}</td><td><EvidenceValue :evidence="item.baseline_value" localized /></td><td><EvidenceValue :evidence="item.candidate_value" localized /></td><td>{{ c('只使用满足可比条件的观察', 'Only eligible comparable observations') }}</td></tr>
          <tr><td>{{ c('全量原始通过率', 'Overall raw baseline / candidate') }}</td><td><EvidenceValue :evidence="item.overall_baseline_value" localized /></td><td><EvidenceValue :evidence="item.overall_candidate_value" localized /></td><td>{{ c('两份报告各自任务集，不能代替配对方向', 'Each report has its own task set; this does not establish paired direction') }}</td></tr>
          <tr><td>{{ c('证据层级', 'Evidence tier') }}</td><td>{{ item.baseline_tier }}</td><td>{{ item.candidate_tier }}</td><td>{{ c('保留后端原始层级', 'Backend evidence tiers preserved') }}</td></tr>
          <tr><td>{{ c('基础设施失败数量', 'Infrastructure failure count') }}</td><td>{{ item.baseline_infra_count }}</td><td>{{ item.candidate_infra_count }}</td><td>{{ c('与能力结果分开计数', 'Counted separately from capability outcomes') }}</td></tr>
        </tbody></table></div><div class="direction-row"><span>{{ c('配对描述性方向', 'Paired descriptive direction') }}</span><StatusBadge :value="eligibleDirection(item)" localized /><EvidenceValue v-if="eligibleDirection(item) !== 'NOT_REPORTED'" :evidence="item.delta" localized /><span v-else class="technical">INSUFFICIENT_EVIDENCE</span></div><details><summary>{{ c('原始方向与差值记录', 'Original direction and delta records') }}</summary><pre class="raw-evidence">{{ JSON.stringify({ comparability: item.comparability, direction: item.direction, delta: item.delta, overall_delta: item.overall_delta }, null, 2) }}</pre></details></section>
      </article><PageState v-if="!result.comparisons.length" kind="empty">{{ c('报告未包含可比较的 Cell 配对。', 'The reports contain no cell pairs to compare.') }}</PageState>
      <section class="panel"><div class="panel-header"><h3>{{ c('证据限制与报告身份', 'Evidence limits & report identities') }}</h3></div><p class="boundary-note">{{ c('数值变化是描述性观察，不证明因果、模型排名或统计显著性。', 'Numerical differences are descriptive; they do not prove causality, model rankings, or statistical significance.') }}</p><p class="original-label">{{ c('原始比较限制', 'Original comparison limitation') }}</p><p>{{ result.limitation }}</p><dl class="definition-list"><dt>{{ c('声明的比较目的', 'Declared intent') }}</dt><dd>{{ result.intent }}</dd><dt>{{ c('基线报告摘要', 'Baseline report digest') }}</dt><dd class="technical">{{ result.baseline_report_digest }}</dd><dt>{{ c('候选报告摘要', 'Candidate report digest') }}</dt><dd class="technical">{{ result.candidate_report_digest }}</dd><dt>{{ c('共同任务', 'Common tasks') }}</dt><dd>{{ result.common_tasks.join(', ') || 'NOT_REPORTED' }}</dd></dl><div class="toolbar"><RouterLink class="secondary-button" :to="{ path: '/diagnosis', query: { experiment: result.baseline_experiment_id, candidate: result.candidate_experiment_id, run: route?.query?.run } }">{{ c('查看基线失败诊断', 'Inspect baseline diagnosis') }}</RouterLink><RouterLink class="secondary-button" :to="{ path: '/diagnosis', query: { experiment: result.candidate_experiment_id } }">{{ c('查看候选失败诊断', 'Inspect candidate diagnosis') }}</RouterLink></div></section>
    </template>
  </section>
</template>
