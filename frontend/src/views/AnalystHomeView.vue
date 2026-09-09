<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { analystApi } from '@/api/analyst'
import InvestigationReport from '@/components/InvestigationReport.vue'
import type { InvestigationExample } from '@/types/analyst'
const example = ref<InvestigationExample | null>(null)
const busy = ref(false)
const error = ref('')
const result = ref<HTMLElement | null>(null)
const requestedKind = ref<'offline' | 'historical'>('offline')
async function open(kind: 'offline' | 'historical') {
  requestedKind.value = kind
  busy.value = true; error.value = ''; example.value = null
  try { example.value = kind === 'offline' ? await analystApi.offline() : await analystApi.historical() }
  catch { error.value = '案例加载失败。请确认本地 API 已启动；历史证据缺失或摘要不匹配时不会显示替代结果。可以重试或选择其他入口。' }
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
    <div class="investigation-hero">
      <span class="eyebrow">SAMESCALE / INVESTIGATE</span>
      <h2>从一次失败，<br />找到有证据的下一步。</h2>
      <p>查询运行记录，核对失败证据，区分事实与假设。<br />把工程问题变成一份可审阅的调查报告。</p>
      <ol class="journey" aria-label="调查路径"><li>提出问题</li><li>核对证据</li><li>审阅下一步</li></ol>
    </div>
    <div class="entry-cards">
      <article class="primary-entry"><span class="status-pill info">FAKE · OFFLINE</span><h3>从一个失败案例开始</h3>
        <p>去重任务为什么没有通过？用固定合成案例运行现有调查图和事实校验。无需 Provider Key、数据库或 Docker。</p>
        <p class="muted">固定脚本，不调用模型；结果不保存为数据库会话。</p>
        <button class="start-demo" :disabled="busy" @click="open('offline')">运行离线演示</button></article>
      <article><span class="status-pill neutral">HISTORICAL REAL · READ ONLY</span><h3>查看历史真实调查</h3>
        <p>回看 2026-09-09 的真实模型调查：为什么现有证据不足以证明某个 Harness 更强？</p>
        <p class="muted">读取冻结文件；不是当前会话，原数据库会话尚未恢复。</p>
        <button :disabled="busy" @click="open('historical')">查看历史真实记录</button></article>
      <article><span class="status-pill neutral">CURRENT SESSIONS</span><h3>调查已有工程证据</h3>
        <p>选择当前数据库中的实验，新建或恢复有界调查，保存并审阅回归方案。</p>
        <p class="muted">Fake 可无密钥演练持久化；Real 需配置、预算与逐步确认，无静默回退。</p>
        <RouterLink to="/analyst/sessions?backend=real" class="entry-link">进入 Real 调查</RouterLink>
        <RouterLink to="/analyst/sessions" class="entry-link">Fake 与已保存会话</RouterLink></article>
    </div>
    <p v-if="busy" role="status" class="loading-state">{{ requestedKind === 'offline' ? '正在运行合成案例并校验事实…' : '正在核对冻结历史证据…' }}</p>
    <div v-if="error" role="alert" class="error-state"><p>{{ error }}</p><button @click="open(requestedKind)">重试加载</button></div>
    <article v-if="example" :key="example.kind" ref="result" tabindex="-1" class="example" aria-label="调查案例">
      <h2 class="result-heading">{{ example.kind === 'offline_fake' ? '离线案例调查报告' : '历史真实调查报告' }}</h2>
      <p class="provenance" role="status">{{ example.provenance }}</p>
      <p v-if="example.kind === 'historical_real'">历史实际用量：{{ example.metadata.decisions }}/{{ example.metadata.decision_limit }} 决策 · {{ example.metadata.tools }}/{{ example.metadata.tool_limit }} 工具。{{ example.metadata.limit_correction }} {{ example.metadata.trace_limit }}</p>
      <p v-else>本次运行：{{ example.metadata.decisions }} 决策 · {{ example.metadata.tools }} 工具 · Provider 请求 {{ example.metadata.provider_requests }}。刷新后可重新运行。</p>
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
.analyst-home { font-size: 14px; line-height: 1.65; overflow-wrap: anywhere; }
h2 { max-width: 760px; font-size: clamp(23px, 3vw, 34px); line-height: 1.3; }
.investigation-hero { padding: 30px 0 24px; }
.investigation-hero h2 { font-size: clamp(30px, 3.5vw, 46px); letter-spacing: -.04em; margin: 18px 0; }
.investigation-hero p { color: var(--muted); font-size: 15px; }
.journey { display: flex; flex-wrap: wrap; gap: 12px 30px; padding: 0; list-style: none; counter-reset: journey; color: var(--accent); margin: 26px 0 0; }
.journey li { counter-increment: journey; }
.journey li::before { content: '0' counter(journey); margin-right: 8px; font: 12px ui-monospace, monospace; }
.primary-entry { border-top: 3px solid var(--accent) !important; }
button.start-demo { background: var(--accent); color: white; border-color: var(--accent); }
.entry-cards article > button:first-of-type, .entry-cards article > a:first-of-type { margin-top: auto; }
.result-heading { font-size: 24px; margin-top: 30px; }
.example { scroll-margin-top: 110px; }
.example:focus { outline: none; }
.entry-cards { display: grid; grid-template-columns: 1.15fr 1fr 1fr; gap: 18px; }
.entry-cards article { display: flex; flex-direction: column; align-items: flex-start; border: 1px solid var(--line); border-radius: 8px; padding: 22px; background: var(--panel); }
h3 { font-size: 18px; margin: 16px 0 0; }
.muted { color: var(--muted); font-size: 12px; }
button, .entry-link { padding: 11px 14px; margin-top: 10px; color: var(--accent); border: 1px solid var(--line); background: var(--panel); border-radius: 4px; cursor: pointer; font: inherit; }
button:disabled { opacity: .55; }
.example { margin-top: 28px; border-top: 1px solid var(--line); }
.provenance { font-weight: 600; padding: 16px; border: 1px solid var(--accent); }
pre { max-height: 380px; overflow: auto; white-space: pre-wrap; font-size: 12px; }
summary { cursor: pointer; }
@media (max-width: 1050px) { .entry-cards { grid-template-columns: 1fr; } }
</style>
