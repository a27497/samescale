<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { analystApi } from '@/api/analyst'
import { useRoute } from 'vue-router'
import { copy as c } from '@/composables/visualLocale'
import { CircleCheck, Clock, Lock, ArrowRight, DocumentChecked, DataAnalysis, TrendCharts } from '@element-plus/icons-vue'
import { useAnalystAccess } from '@/composables/analystAccess'
import InvestigationReport from '@/components/InvestigationReport.vue'
import type { InvestigationExample } from '@/types/analyst'
const { access, loadAccess } = useAnalystAccess()
const route = useRoute()
function openRequestedExample() {
  if (route.query.example === 'offline' || route.query.example === 'historical') void open(route.query.example)
}
onMounted(() => { void loadAccess(); openRequestedExample() })
watch(() => route.query.example, openRequestedExample)
const example = ref<InvestigationExample | null>(null)
const busy = ref(false)
const error = ref('')
const result = ref<HTMLElement | null>(null)
const requestedKind = ref<'offline' | 'historical'>('offline')
let sequence = 0
onUnmounted(() => { sequence++ })
async function open(kind: 'offline' | 'historical') {
  const request = ++sequence
  requestedKind.value = kind
  busy.value = true; error.value = ''; example.value = null
  try { const response = kind === 'offline' ? await analystApi.offline() : await analystApi.historical(); if (request === sequence) example.value = response }
  catch { if (request === sequence) error.value = '案例加载失败。请确认工作区 API 可访问；历史证据缺失或摘要不匹配时不会显示替代结果。可以重试或选择其他入口。' }
  finally { if (request === sequence) busy.value = false }
  if (request === sequence && example.value) {
    await nextTick()
    result.value?.focus()
    result.value?.scrollIntoView?.({ block: 'start' })
  }
}
</script>

<template>
  <section class="analyst-home visual-home">
    <div class="home-hero"><span class="guide-badge">{{ c('从保存的证据开始', 'START WITH SAVED EVIDENCE') }}</span><h2>{{ c('从运行证据，看清 Agent 交付结果', 'Understand agent outcomes through evidence') }}</h2><p>{{ c('对照 Agent 的完成声明与独立验收记录，追踪失败线索，明确结论能够证明什么。', 'Compare agent claims with independent verification, investigate failure signals, and understand what the evidence supports.') }}</p>
      <div class="home-action-panel"><div><strong>{{ c('选择一个真实的调查入口', 'Choose an investigation entry point') }}</strong><small>{{ c('固定离线案例、冻结历史报告与已保存证据，各自保留来源。', 'Offline cases, frozen reports, and saved evidence retain their own provenance.') }}</small></div><button class="primary-button" :disabled="busy" @click="open('offline')">{{ c('体验离线调查', 'Try an offline investigation') }}</button></div><RouterLink class="home-secondary" to="/demo">{{ c('浏览公开证据', 'Explore the public demo') }} <ArrowRight class="ui-icon" /></RouterLink>
    </div>
    <div class="entry-cards">
      <article><div class="entry-top"><CircleCheck class="entry-icon" /><span class="status-pill neutral">FAKE · OFFLINE</span></div><h3>{{ c('固定离线调查', 'Offline investigation') }}</h3><p>{{ c('用固定合成案例体验调查流程和事实校验。不调用模型，也不保存为当前会话。', 'Explore the investigation flow with a fixed synthetic case. No model calls or saved session.') }}</p><button class="entry-link" :disabled="busy" @click="open('offline')"><span>{{ c('体验离线调查', 'Try offline investigation') }}</span><ArrowRight class="ui-icon" /></button></article>
      <article><div class="entry-top"><Clock class="entry-icon" /><span class="status-pill neutral">HISTORICAL REAL</span></div><h3>{{ c('历史真实调查', 'Historical real investigation') }}</h3><p>{{ c('阅读一份已冻结的真实模型调查报告。原会话不会在此恢复或继续执行。', 'Read a frozen report from a bounded real-model investigation. The original session is not resumed here.') }}</p><button class="entry-link" :disabled="busy" @click="open('historical')"><span>{{ c('阅读历史报告', 'Read historical report') }}</span><ArrowRight class="ui-icon" /></button></article>
      <article><div class="entry-top"><Lock class="entry-icon" /><span class="status-pill neutral">{{ access === 'public' ? 'READ_ONLY' : 'CURRENT SESSIONS' }}</span></div>
        <h3>{{ access === 'public' ? c('公开演示 · 只读', 'Public demo · Read-only') : c('已保存调查', 'Saved investigations') }}</h3>
        <template v-if="access === 'public'"><p>{{ c('沿一组已保存的离线样例查看运行、独立验收、失败诊断与候选对比。持久化会话仅限本地 / 私有工作区。', 'Follow a saved offline fixture through runs, verification, diagnosis, and comparison. Persistent sessions are limited to local / private workspaces.') }}</p><RouterLink class="entry-link" to="/demo"><span>{{ c('浏览公开证据', 'Explore public evidence') }}</span><ArrowRight class="ui-icon" /></RouterLink></template>
        <template v-else-if="access === 'private'"><p>{{ c('在私有工作区新建或恢复有界调查；Real 路径仍需配置、预算和明确确认。', 'Create or resume bounded investigations in a private workspace. Real runs still require configuration, budgets, and explicit confirmation.') }}</p><RouterLink class="entry-link" to="/analyst/sessions"><span>{{ c('进入调查工作区', 'Open investigation workspace') }}</span><ArrowRight class="ui-icon" /></RouterLink><RouterLink class="table-link" to="/analyst/sessions?backend=real">{{ c('进入 Real 调查', 'Open Real investigation') }}</RouterLink></template>
        <p v-else-if="access === 'loading'" role="status">{{ c('正在确认工作区权限…', 'Checking workspace access…') }}</p><template v-else><p role="alert">{{ c('暂时无法确认工作区权限。', 'Workspace access could not be confirmed.') }}</p><button class="secondary-button" @click="loadAccess">{{ c('重试权限检查', 'Retry access check') }}</button></template>
      </article>
    </div>
    <div class="home-reading panel"><h3>{{ c('让每个结论都有可检查的依据', 'Keep every conclusion inspectable') }}</h3><div class="reading-columns"><article><DocumentChecked class="ui-icon" /><strong>{{ c('先核对独立验收', 'Check independent verification') }}</strong><p>{{ c('Agent 自报和任务验收分开展示。', 'Agent claims and task verification stay separate.') }}</p></article><article><DataAnalysis class="ui-icon" /><strong>{{ c('沿证据追溯失败', 'Follow failure evidence') }}</strong><p>{{ c('分类帮助定位线索，事实与假设分开阅读。', 'Classification identifies leads; facts and hypotheses stay separate.') }}</p></article><article><TrendCharts class="ui-icon" /><strong>{{ c('先确认可比条件', 'Check comparison conditions') }}</strong><p>{{ c('缺失记录保持未知，不把描述性差异写成胜负。', 'Missing records stay unknown; descriptive differences do not establish a winner.') }}</p></article></div></div>
    <p v-if="busy" role="status" class="loading-state">{{ requestedKind === 'offline' ? c('正在运行固定离线案例…', 'Running the fixed offline case…') : c('正在核对冻结历史证据…', 'Checking frozen historical evidence…') }}</p>
    <div v-if="error" role="alert" class="error-state"><p>{{ c('案例暂不可用，请检查工作区服务或稍后重试。未生成替代报告。', 'This example is unavailable. Check the workspace service or retry later. No substitute report was generated.') }}</p><button class="secondary-button" @click="open(requestedKind)">{{ c('重试加载', 'Retry loading') }}</button></div>
    <article v-if="example" :key="example.kind" ref="result" tabindex="-1" class="example panel" :aria-label="c('调查案例', 'Investigation example')">
      <h2>{{ example.kind === 'offline_fake' ? c('离线案例调查报告', 'Offline investigation report') : c('历史真实调查报告', 'Historical real investigation report') }}</h2>
      <p class="original-label">{{ c('原始来源说明', 'Original provenance') }}</p><p class="provenance" role="status">{{ example.provenance }}</p>
      <p>{{ c('决策 / 上限', 'Decisions / limit') }}: {{ example.metadata.decisions }} / {{ example.metadata.decision_limit ?? 'NOT_REPORTED' }} · {{ c('工具 / 上限', 'Tools / limit') }}: {{ example.metadata.tools }} / {{ example.metadata.tool_limit ?? 'NOT_REPORTED' }}</p>
      <p v-if="example.kind === 'historical_real'">{{ example.metadata.limit_correction }} {{ example.metadata.trace_limit }}</p>
      <p v-else>Provider {{ c('请求', 'requests') }}: {{ example.metadata.provider_requests }} · {{ c('刷新后可重新运行固定案例。', 'Reload to run the fixed case again.') }}</p>
      <p v-if="example.kind === 'historical_real'" class="reading-guide">{{ c('阅读提示：当前证据不足以证明某个 Harness 在该任务上更强，也无法确立提高推理强度的因果收益。下方保留原始报告及其可定位引用。', 'The current evidence does not establish that one harness is stronger or that higher reasoning effort causes gains. The source report and its citations are preserved below.') }}</p>
      <InvestigationReport :report="example.report" :evidence="example.report.evidence_catalog"><template #next><p v-if="example.proposal">{{ c('历史待审阅方案', 'Historical proposal for review') }}: {{ example.proposal.objective }}</p><ul><li v-for="step in example.next_steps" :key="step">{{ step }}</li></ul><p>{{ c('此处只展示建议，不修改历史审批，不自动修复或执行实验。', 'These are suggestions for review. They do not change historical approvals or execute repairs or experiments.') }}</p></template></InvestigationReport>
      <details><summary>{{ c('来源、用量与调查过程', 'Provenance, usage and investigation process') }}</summary><pre>{{ JSON.stringify(example.metadata, null, 2) }}</pre></details>
    </article>
  </section>
</template>
