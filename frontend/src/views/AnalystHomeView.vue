<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { analystApi } from '@/api/analyst'
import { useRoute, useRouter } from 'vue-router'
import { copy as c } from '@/composables/visualLocale'
import { CircleCheck, Clock, Lock, ArrowRight } from '@element-plus/icons-vue'
import { useAnalystAccess } from '@/composables/analystAccess'
import TechnicalDetails from '@/components/TechnicalDetails.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import InvestigationReport from '@/components/InvestigationReport.vue'
import type { InvestigationExample } from '@/types/analyst'
const { access, loadAccess } = useAnalystAccess()
const route = useRoute()
const router = useRouter()
function openRequestedExample() {
  if (route.query.example === 'offline' || route.query.example === 'historical') void open(route.query.example, false)
}
onMounted(() => { void loadAccess(); openRequestedExample() })
watch(() => route.query.example, value => { if ((value === 'offline' && example.value?.kind === 'offline_fake') || (value === 'historical' && example.value?.kind === 'historical_real')) return; openRequestedExample() })
const example = ref<InvestigationExample | null>(null)
const busy = ref(false)
const error = ref('')
const result = ref<HTMLElement | null>(null)
const requestedKind = ref<'offline' | 'historical'>('offline')
let sequence = 0
onUnmounted(() => { sequence++ })
async function open(kind: 'offline' | 'historical', focus = true) {
  const request = ++sequence
  requestedKind.value = kind
  busy.value = true; error.value = ''; example.value = null
  try { const response = kind === 'offline' ? await analystApi.offline() : await analystApi.historical(); if (request === sequence) example.value = response }
  catch { if (request === sequence) error.value = '案例加载失败。请确认工作区 API 可访问；历史证据缺失或摘要不匹配时不会显示替代结果。可以重试或选择其他入口。' }
  finally { if (request === sequence) busy.value = false }
  if (request === sequence && example.value && focus) {
    if (route.query.example !== kind) await router.replace({ query: { ...route.query, example: kind } })
    await nextTick()
    result.value?.focus()
    result.value?.scrollIntoView?.({ block: 'start' })
  }
}
</script>

<template>
  <section class="analyst-home visual-home">
    <div class="home-hero"><span class="guide-badge">{{ c('从保存的证据开始', 'START WITH SAVED EVIDENCE') }}</span><h2>{{ c('从运行证据，看清 Agent 交付结果', 'Understand agent outcomes through evidence') }}</h2><p>{{ c('对照 Agent 的完成声明与独立验收记录，追踪失败线索，明确结论能够证明什么。', 'Compare agent claims with independent verification, investigate failure signals, and understand what the evidence supports.') }}</p>
      </div>
    <div class="entry-cards">
      <article><div class="entry-top"><CircleCheck class="entry-icon" /><StatusBadge value="FIXTURE_OFFLINE" localized /></div><h3>{{ c('固定离线调查', 'Offline investigation') }}</h3><p>{{ c('用固定合成案例体验调查流程和事实校验。不调用模型，也不保存为当前会话。', 'Explore the investigation flow with a fixed synthetic case. No model calls or saved session.') }}</p><button class="primary-button entry-link" :disabled="busy" @click="open('offline')"><span>{{ c('体验离线调查', 'Try offline investigation') }}</span><ArrowRight class="ui-icon" /></button></article>
      <article><div class="entry-top"><Clock class="entry-icon" /><StatusBadge value="HISTORICAL_REAL" localized /></div><h3>{{ c('历史真实调查', 'Historical real investigation') }}</h3><p>{{ c('阅读一份已冻结的真实模型调查报告。原会话不会在此恢复或继续执行。', 'Read a frozen report from a bounded real-model investigation. The original session is not resumed here.') }}</p><button class="entry-link" :disabled="busy" @click="open('historical')"><span>{{ c('阅读历史报告', 'Read historical report') }}</span><ArrowRight class="ui-icon" /></button></article>
      <article><div class="entry-top"><Lock class="entry-icon" /><StatusBadge :value="access === 'public' ? 'READ_ONLY' : 'CURRENT_SESSIONS'" localized /></div>
        <h3>{{ access === 'public' ? c('公开演示 · 只读', 'Public demo · Read-only') : c('已保存调查', 'Saved investigations') }}</h3>
        <template v-if="access === 'public'"><p>{{ c('沿一组已保存的离线样例查看运行、独立验收、失败诊断与候选对比。持久化会话仅限本地 / 私有工作区。', 'Follow a saved offline fixture through runs, verification, diagnosis, and comparison. Persistent sessions are limited to local / private workspaces.') }}</p><RouterLink class="entry-link" to="/demo"><span>{{ c('浏览公开证据', 'Explore public evidence') }}</span><ArrowRight class="ui-icon" /></RouterLink></template>
        <template v-else-if="access === 'private'"><p>{{ c('在私有工作区新建或恢复有界调查；Real 路径仍需配置、预算和明确确认。', 'Create or resume bounded investigations in a private workspace. Real runs still require configuration, budgets, and explicit confirmation.') }}</p><RouterLink class="entry-link" to="/analyst/sessions"><span>{{ c('进入调查工作区', 'Open investigation workspace') }}</span><ArrowRight class="ui-icon" /></RouterLink><RouterLink class="table-link" to="/analyst/sessions?backend=real">{{ c('进入 Real 调查', 'Open Real investigation') }}</RouterLink></template>
        <p v-else-if="access === 'loading'" role="status">{{ c('正在确认工作区权限…', 'Checking workspace access…') }}</p><template v-else><p role="alert">{{ c('暂时无法确认工作区权限。', 'Workspace access could not be confirmed.') }}</p><button class="secondary-button" @click="loadAccess">{{ c('重试权限检查', 'Retry access check') }}</button></template>
      </article>
    </div>
    <p v-if="busy" role="status" class="loading-state">{{ requestedKind === 'offline' ? c('正在运行固定离线案例…', 'Running the fixed offline case…') : c('正在核对冻结历史证据…', 'Checking frozen historical evidence…') }}</p>
    <div v-if="error" role="alert" class="error-state"><p>{{ c('案例暂不可用，请检查工作区服务或稍后重试。未生成替代报告。', 'This example is unavailable. Check the workspace service or retry later. No substitute report was generated.') }}</p><button class="secondary-button" @click="open(requestedKind)">{{ c('重试加载', 'Retry loading') }}</button></div>
    <article v-if="example" :key="example.kind" ref="result" tabindex="-1" class="example panel" :aria-label="c('调查案例', 'Investigation example')">
      <h2>{{ example.kind === 'offline_fake' ? c('离线案例调查报告', 'Offline investigation report') : c('历史真实调查报告', 'Historical real investigation report') }}</h2>
      <div class="report-context"><StatusBadge :value="example.kind === 'historical_real' ? 'HISTORICAL_REAL' : 'FIXTURE_OFFLINE'" localized /><span>{{ example.kind === 'historical_real' ? c('已冻结报告 · 不恢复原会话', 'Frozen report · original session is not resumed') : c('固定合成输入 · 不调用模型', 'Fixed synthetic inputs · no model calls') }}</span></div>
      <InvestigationReport :report="example.report" :evidence="example.report.evidence_catalog" :source-kind="example.kind"><template #next><p v-if="example.proposal">{{ c('历史待审阅方案', 'Historical proposal for review') }}: {{ example.proposal.objective }}</p><ul><li v-for="step in example.next_steps" :key="step">{{ step }}</li></ul><p>{{ c('此处只展示建议，不修改历史审批，不自动修复或执行实验。', 'These are suggestions for review. They do not change historical approvals or execute repairs or experiments.') }}</p></template></InvestigationReport>
      <TechnicalDetails :summary="c('来源、用量与调查过程', 'Provenance, usage and investigation process')" :fields="[{ label: c('原始来源说明', 'Original provenance'), value: example.provenance }]" ><pre class="raw-evidence">{{ JSON.stringify(example.metadata, null, 2) }}</pre></TechnicalDetails>
    </article>
  </section>
</template>
