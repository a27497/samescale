<script setup lang="ts">
import { ref } from 'vue'
import { analystApi } from '@/api/analyst'
import InvestigationReport from '@/components/InvestigationReport.vue'
import type { InvestigationExample } from '@/types/analyst'
const example = ref<InvestigationExample | null>(null)
const busy = ref(false)
const error = ref('')
async function open(kind: 'offline' | 'historical') {
  busy.value = true; error.value = ''; example.value = null
  try { example.value = kind === 'offline' ? await analystApi.offline() : await analystApi.historical() }
  catch { error.value = '案例加载失败。请确认本地 API 已启动；历史证据缺失或摘要不匹配时不会显示替代结果。可以重试或选择其他入口。' }
  finally { busy.value = false }
}
</script>

<template>
  <section class="analyst-home">
    <div class="page-heading"><div><span class="eyebrow">ENGINEERING INVESTIGATION AGENT</span><h2>工程任务失败了，证据告诉我们什么？</h2>
      <p>Analyst 查询运行记录、检查失败证据，区分事实与假设，再给出可审阅的回归建议。</p></div></div>
    <p class="journey">提出问题 → 只读工具调查 → 验证引用 → 结论与限制 → 审阅下一步</p>
    <div class="entry-cards">
      <article><span class="status-pill info">FAKE · OFFLINE</span><h3>先体验一次调查</h3>
        <p>去重任务为什么没有通过？用固定合成案例运行现有调查图和事实校验。无需 Provider Key、数据库或 Docker。</p>
        <p class="muted">固定脚本，不调用模型；结果不保存为数据库会话。</p>
        <button :disabled="busy" @click="open('offline')">运行离线演示</button></article>
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
    <p v-if="busy" role="status">正在读取证据并准备调查结果…</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <article v-if="example" :key="example.kind" class="example" aria-label="调查案例">
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
.journey { color: var(--accent); margin: 20px 0; }
.entry-cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.entry-cards article { display: flex; flex-direction: column; align-items: flex-start; border: 1px solid var(--line); border-radius: 8px; padding: 22px; background: var(--panel); }
h3 { font-size: 18px; margin: 16px 0 0; }
.muted { color: var(--muted); font-size: 12px; }
button, .entry-link { padding: 9px 12px; margin-top: 10px; color: var(--accent); border: 1px solid var(--line); background: var(--panel); border-radius: 4px; cursor: pointer; font: inherit; }
button:disabled { opacity: .55; }
.example { margin-top: 28px; border-top: 1px solid var(--line); }
.provenance { font-weight: 600; padding: 16px; border: 1px solid var(--accent); }
pre { max-height: 380px; overflow: auto; white-space: pre-wrap; font-size: 12px; }
summary { cursor: pointer; }
@media (max-width: 1050px) { .entry-cards { grid-template-columns: 1fr; } }
</style>
