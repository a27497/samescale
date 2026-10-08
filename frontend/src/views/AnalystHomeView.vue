<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { analystApi } from '@/api/analyst'
import { useRoute } from 'vue-router'
import PublicAnalystNotice from '@/components/PublicAnalystNotice.vue'
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
async function open(kind: 'offline' | 'historical') {
  requestedKind.value = kind
  busy.value = true; error.value = ''; example.value = null
  try { example.value = kind === 'offline' ? await analystApi.offline() : await analystApi.historical() }
  catch { error.value = '案例加载失败。请确认工作区 API 可访问；历史证据缺失或摘要不匹配时不会显示替代结果。可以重试或选择其他入口。' }
  finally { busy.value = false }
  if (example.value) {
    await nextTick()
    result.value?.focus()
    result.value?.scrollIntoView?.({ block: 'start' })
  }
}
</script>

<template>
  <section class="analyst-home">
    <div class="workspace-hero investigation-hero">
      <div class="hero-copy">
        <span class="eyebrow">ANALYST / 工程问题调查</span>
        <h2>从工程问题，<br />到有依据的结论。</h2>
        <p>沿运行记录核对证据，区分事实与假设，<br class="desktop-copy-break" />把下一步整理成可审阅的调查报告。</p>
        <span class="hero-caption">先看案例，再进入你的调查工作区。</span>
      </div>
      <aside class="report-outline" aria-label="调查报告的阅读顺序">
        <span class="outline-label">你会得到什么</span>
        <ol><li><span>01</span><div><strong>有依据的结论</strong><small>事实附可定位的证据引用</small></div></li><li><span>02</span><div><strong>明确的证明边界</strong><small>限制与待验证假设分开展示</small></div></li><li><span>03</span><div><strong>可审阅的下一步</strong><small>方案审阅与执行授权保持独立</small></div></li></ol>
      </aside>
    </div>
    <div class="entry-heading"><div><h3>选择你的起点</h3><p>演示、历史记录与当前会话，各自保留来源和证明范围。</p></div><span class="technical">THREE ENTRY POINTS</span></div>
    <div class="entry-cards">
      <article class="primary-entry"><div class="entry-top"><span class="entry-number">01 / 推荐起点</span><span class="status-pill info">FAKE · OFFLINE</span></div><h3>先体验一次调查</h3>
        <p>去重任务为什么没有通过？用固定合成案例运行现有调查图和事实校验。无需 Provider Key、数据库或 Docker。</p>
        <p class="muted">固定脚本，不调用模型；结果不保存为数据库会话。</p>
        <button class="start-demo" :disabled="busy" @click="open('offline')">运行离线演示</button></article>
      <article><div class="entry-top"><span class="entry-number">02 / 历史记录</span><span class="status-pill neutral">HISTORICAL REAL</span></div><h3>阅读真实调查报告</h3>
        <p>回看 2026-09-09 的真实模型调查：为什么现有证据不足以证明某个 Harness 更强？</p>
        <p class="muted">读取冻结文件；不是当前会话，原数据库会话尚未恢复。</p>
        <button :disabled="busy" @click="open('historical')">查看历史真实记录</button></article>
      <article><div class="entry-top"><span class="entry-number">03 / 工作区</span><span class="status-pill neutral">{{ access === 'public' ? 'READ ONLY' : 'CURRENT SESSIONS' }}</span></div><h3>{{ access === 'public' ? '会话功能仅限私有工作区' : '继续调查已有证据' }}</h3>
        <PublicAnalystNotice v-if="access === 'public'" compact />
        <p v-else-if="access === 'loading'" role="status">正在确认工作区权限…</p>
        <p v-else-if="access === 'unavailable'" role="alert">暂时无法确认工作区权限。<button @click="loadAccess">重试权限检查</button></p>
        <template v-else>
        <p>选择当前数据库中的实验，新建或恢复有界调查，保存并审阅回归方案。</p>
        <p class="muted">Fake 可无密钥演练持久化；Real 需配置、预算与逐步确认，无静默回退。</p>
        <RouterLink to="/analyst/sessions?backend=real" class="entry-link">进入 Real 调查</RouterLink>
        <RouterLink to="/analyst/sessions" class="entry-link">Fake 与已保存会话</RouterLink></template></article>
    </div>
    <p v-if="busy" role="status" class="loading-state">{{ requestedKind === 'offline' ? '正在运行合成案例并校验事实…' : '正在核对冻结历史证据…' }}</p>
    <div v-if="error" role="alert" class="error-state"><p>{{ error }}</p><button @click="open(requestedKind)">重试加载</button></div>
    <article v-if="example" :key="example.kind" ref="result" tabindex="-1" class="example" aria-label="调查案例">
      <h2 class="result-heading">{{ example.kind === 'offline_fake' ? '离线案例调查报告' : '历史真实调查报告' }}</h2>
      <p class="provenance" role="status">{{ example.provenance }}</p>
      <p v-if="example.kind === 'historical_real'">历史实际用量：{{ example.metadata.decisions }}/{{ example.metadata.decision_limit }} 决策 · {{ example.metadata.tools }}/{{ example.metadata.tool_limit }} 工具。{{ example.metadata.limit_correction }} {{ example.metadata.trace_limit }}</p>
      <p v-else>本次合成演示：{{ example.metadata.decisions }} 决策 · {{ example.metadata.tools }} 工具 · Provider 请求 {{ example.metadata.provider_requests }}。刷新后可重新运行。</p>
      <p v-if="example.kind === 'historical_real'" class="reading-guide">阅读提示：当前证据不足以证明某个 Harness 在该任务上更强，也无法确立提高推理强度的因果收益。下方保留原始报告及其可定位引用。</p>
      <InvestigationReport :report="example.report" :evidence="example.report.evidence_catalog">
        <template #next><p v-if="example.proposal">历史待审阅方案：{{ example.proposal.objective }}</p>
          <ul><li v-for="step in example.next_steps" :key="step">{{ step }}</li></ul>
          <p>此处只展示建议，不修改历史审批，不自动修复或执行实验。</p></template>
      </InvestigationReport>
      <details><summary>来源、用量与调查过程</summary><pre>{{ JSON.stringify(example.metadata, null, 2) }}</pre></details>
    </article>
  </section>
</template>

<style scoped>
.analyst-home { font-size: 14px; line-height: 1.7; overflow-wrap: anywhere; }
.investigation-hero { background: var(--panel); }
.investigation-hero h2 { color: var(--ink); }
.hero-caption { display: block; margin-top: 24px; font-size: 13px; color: var(--accent); font-weight: 600; }
.report-outline { border-left: 1px solid var(--line); padding-left: 32px; }
.outline-label { color: var(--muted); font-size: 13px; }
.report-outline ol { display: grid; gap: 22px; padding: 0; margin: 20px 0 0; list-style: none; }
.report-outline li { display: flex; gap: 14px; align-items: baseline; }
.report-outline li > span { font: 600 12px/1.5 ui-monospace, monospace; color: var(--accent); }
.report-outline strong, .report-outline small { display: block; }
.report-outline strong { font-weight: 600; }
.report-outline small { margin-top: 3px; font-size: 13px; color: var(--muted); }
.entry-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 32px 0 18px; }
.entry-heading h3 { margin: 0; font-size: 18px; }
.entry-heading p { margin: 5px 0 0; color: var(--muted); font-size: 13px; }
.entry-heading > span { color: var(--muted); flex: none; }
.entry-cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.entry-cards article { display: flex; flex-direction: column; align-items: flex-start; min-width: 0; border: 1px solid var(--line); border-radius: 12px; padding: 24px; background: var(--panel); }
.entry-cards .primary-entry { border-color: #9bc8c2; background: #f1f9f7; }
.entry-top { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.entry-number { font-size: 12px; color: var(--muted); }
h3 { font-size: 19px; margin: 22px 0 0; letter-spacing: -.02em; }
.entry-cards p { margin: 12px 0; }
.entry-cards .muted { color: var(--muted); font-size: 13px; margin-bottom: 22px; }
.entry-cards article > button:first-of-type, .entry-cards article > a:first-of-type { margin-top: auto; }
button, .entry-link { display: inline-flex; align-items: center; justify-content: center; min-height: 44px; padding: 10px 16px; margin-top: 8px; color: var(--accent); border: 1px solid var(--line); background: var(--panel); border-radius: 7px; cursor: pointer; font: inherit; font-weight: 600; text-decoration: none; text-align: center; max-width: 100%; }
button:hover, .entry-link:hover { border-color: var(--accent); background: var(--accent-soft); }
button.start-demo { background: var(--accent); color: white; border-color: var(--accent); }
button.start-demo:hover { background: #0c635b; }
button:disabled { opacity: .55; cursor: wait; }
.example { margin-top: 28px; padding: 28px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); scroll-margin-top: 110px; }
.example:focus { outline: 2px solid var(--accent); outline-offset: 4px; }
.result-heading { font-size: 25px; margin: 0 0 16px; }
.provenance { font-weight: 600; padding: 14px 16px; border-left: 3px solid var(--accent); background: var(--accent-soft); border-radius: 0 6px 6px 0; }
pre { max-height: 380px; overflow: auto; white-space: pre-wrap; font-size: 12px; }
summary { cursor: pointer; padding-block: 12px; }
@media (max-width: 1120px) { .entry-cards { grid-template-columns: minmax(0, 1fr); } .entry-top { width: 100%; justify-content: space-between; } }
@media (max-width: 1000px) { .report-outline { border-left: 0; padding-left: 0; border-top: 1px solid var(--line); padding-top: 24px; } .report-outline ol { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; } }
@media (max-width: 600px) { .report-outline { display: none; } .entry-heading > span { display: none; } .entry-cards article { padding: 22px; } .entry-cards article > button, .entry-cards article > .entry-link { width: 100%; } .example { padding: 18px; } }
</style>
