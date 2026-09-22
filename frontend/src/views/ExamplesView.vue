<script setup lang="ts">
import { t } from '@/composables/i18n'
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { analystApi } from '@/api/analyst'
import ComparisonCase from '@/components/ComparisonCase.vue'
import type { ComparisonExample } from '@/types/comparison'
import InvestigationReport from '@/components/InvestigationReport.vue'
import type { InvestigationExample } from '@/types/analyst'
const router = useRouter()
const route = useRoute()
const comparison = ref<ComparisonExample | null>(null)
type ExampleKind = 'comparison' | 'offline' | 'historical'
const example = ref<InvestigationExample | null>(null)
const busy = ref(false)
const error = ref('')
const result = ref<HTMLElement | null>(null)
const requestedKind = ref<ExampleKind>('offline')
let generation = 0
onBeforeUnmount(() => { generation++ })
async function open(kind: ExampleKind) {
  if (route.query.example !== kind) await router.push({ path: '/examples', query: { example: kind } })
  else await loadExample(kind)
}
async function loadExample(kind: ExampleKind) {
  const ownGeneration = ++generation
  requestedKind.value = kind
  busy.value = true; error.value = ''; example.value = null; comparison.value = null
  try {
    const value = kind === 'comparison' ? await analystApi.comparison() : kind === 'offline' ? await analystApi.offline() : await analystApi.historical()
    if (generation !== ownGeneration) return
    if (value.kind === 'historical_comparison') comparison.value = value
    else example.value = value
  }
  catch { if (generation !== ownGeneration) return; error.value = '示例加载失败，请重试。' }
  finally { if (generation === ownGeneration) busy.value = false }
  if (generation === ownGeneration && (example.value || comparison.value)) {
    await nextTick()
    result.value?.focus()
    result.value?.scrollIntoView?.({ block: 'start' })
  }
}
async function returnHome() {
  const comparisonReturn = route.query.example === 'comparison'
  await router.push('/analyst')
  await nextTick()
  document.querySelector<HTMLElement>(comparisonReturn ? '.home-comparison-link, .home-example-link' : '.home-example-link')?.focus()
}
watch(() => route.query.example, kind => {
  if (kind === 'comparison' || kind === 'offline' || kind === 'historical') void loadExample(kind)
  else { generation++; example.value = null; comparison.value = null; busy.value = false; error.value = '' }
}, { immediate: true })
</script>

<template>
  <section class="analyst-home">
    <div class="sample-toolbar">
      <div class="sample-switches">
        <button :class="{ active: !!comparison }" :disabled="busy" @click="open('comparison')">{{ t('比较案例') }}</button>
        <button :class="{ active: !!example && requestedKind === 'offline' }" :disabled="busy" @click="open('offline')">{{ t('运行离线演示') }}</button>
        <button :class="{ active: !!example && requestedKind === 'historical' }" :disabled="busy" @click="open('historical')">{{ t('查看历史真实记录') }}</button>
      </div>
    </div>
    <div v-if="!example && !comparison && !busy && !error" class="example-intro">
      <span class="status-pill neutral">{{ t('历史评测') }}</span>
      <h2>{{ t('直接调用与 Codex') }}</h2>
      <p>GPT-5.6 · {{ t('中转路由') }} · medium</p>
      <button class="primary-button" @click="open('comparison')">{{ t('查看比较案例') }} →</button>
      <p class="example-note">{{ t('离线演示与历史调查报告可从上方打开。') }}</p>
    </div>
    <div v-if="comparison" ref="result" tabindex="-1" class="comparison-result" :aria-label="t('比较案例')">
      <div class="result-label"><span class="status-pill neutral">{{ t('历史评测 · 只读') }}</span><button @click="returnHome">{{ t('返回首页') }}</button></div>
      <ComparisonCase :example="comparison" />
    </div>
    <p v-if="busy" role="status" class="loading-state">{{ requestedKind === 'offline' ? t('正在运行合成案例并校验事实…') : t('正在核对历史证据…') }}</p>
    <div v-if="error" role="alert" class="error-state"><p>{{ t(error) }}</p><button @click="open(requestedKind)">{{ t('重试加载') }}</button></div>
    <article v-if="example" :key="example.kind" ref="result" tabindex="-1" class="example" :aria-label="t('调查案例')">
      <div class="result-label"><span class="status-pill neutral">{{ example.kind === 'offline_fake' ? t('Sample · 合成案例') : t('历史真实记录 · 只读') }}</span><button @click="returnHome">{{ t('返回首页') }}</button></div>
      <h2 class="result-heading">{{ example.kind === 'offline_fake' ? t('离线案例调查报告') : t('历史真实调查报告') }}</h2>
      <p class="provenance" role="status">{{ example.provenance }}</p>
      <p v-if="example.kind === 'historical_real'">{{ t('历史实际用量：') }}{{ example.metadata.decisions }}/{{ example.metadata.decision_limit }} {{ t('决策 ·') }} {{ example.metadata.tools }}/{{ example.metadata.tool_limit }} {{ t('工具。') }}{{ example.metadata.limit_correction }} {{ example.metadata.trace_limit }}</p>
      <p v-else class="run-metadata">{{ t('本次运行：') }}{{ example.metadata.decisions }} {{ t('决策 ·') }} {{ example.metadata.tools }} {{ t('工具 · Provider 请求') }} {{ example.metadata.provider_requests }}{{ t('。刷新此案例地址会重新加载案例。') }}</p>
      <p v-if="example.kind === 'historical_real'" class="reading-guide">{{ t('当前证据无法判断哪个 Agent 运行时更强，也无法确认提高推理强度带来的收益。下方为原始报告与引用。') }}</p>
      <InvestigationReport :report="example.report" :evidence="example.report.evidence_catalog">
        <template #next><p v-if="example.proposal">{{ t('历史待审阅方案：') }}{{ example.proposal.objective }}</p>
          <ul><li v-for="step in example.next_steps" :key="step">{{ step }}</li></ul>
          <p>{{ t('此处只展示建议，不修改历史审批，不自动修复或执行实验。') }}</p></template>
      </InvestigationReport>
      <details class="example-metadata"><summary>{{ t('来源、用量与调查过程') }}</summary><pre>{{ JSON.stringify(example.metadata, null, 2) }}</pre></details>
    </article>
  </section>
</template>

<style scoped>
.analyst-home { overflow-wrap: anywhere; }
.sample-toolbar, .sample-switches, .result-label { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.sample-toolbar { padding-bottom: 20px; border-bottom: 1px solid var(--line); }
button { border: 1px solid var(--line); border-radius: 6px; background: transparent; color: var(--ink); min-height: 38px; padding: 8px 14px; cursor: pointer; font: var(--type-control); }
button:hover, button.active { background: var(--hover); }
button:disabled { opacity: .5; cursor: default; }
.example-intro { margin: 48px auto; max-width: 640px; }.example-intro .primary-button { background: var(--button-bg); color: white; }.example-note { font: var(--type-caption); margin-top: 24px; }.comparison-result { padding-top: 24px; scroll-margin-top: 84px; }.comparison-result:focus { outline: none; }.example-intro p { color: var(--muted); }
h2 { font: var(--type-title); }
.example { scroll-margin-top: 90px; padding-top: 28px; }.example:focus { outline: none; }
.result-label { justify-content: space-between; }.result-label button { border: 0; color: var(--muted); }
.result-heading { margin: 16px 0 12px; }.provenance, .run-metadata { color: var(--muted); font: var(--type-caption); }
.reading-guide { border-left: 2px solid #aab3bd; padding-left: 14px; }
.example-metadata { border-top: 1px solid var(--line); margin-top: 28px; padding-top: 18px; color: var(--muted); font: var(--type-caption); }
pre { max-height: 380px; overflow: auto; white-space: pre-wrap; font: var(--type-code); }summary { cursor: pointer; }
</style>
