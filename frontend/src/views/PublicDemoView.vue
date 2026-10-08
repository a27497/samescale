<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { workbenchApi } from '@/api/client'
import PageState from '@/components/PageState.vue'
import type { PublicDemo } from '@/types/workbench'

const demo = ref<PublicDemo | null>(null)
const loading = ref(true)
const error = ref('')
onMounted(async () => {
  try {
    const result = await workbenchApi.getPublicDemo()
    if (!result.public_demo_ready) error.value = '公开演示未通过完整性校验，当前证据不可用。'
    else demo.value = result
  }
  catch (failure) {
    const code = (failure as { response?: { data?: { error?: { code?: string } } } })?.response?.data?.error?.code
    error.value = code === 'DEMO_NOT_CONFIGURED' ? '此工作区尚未配置公开演示。' : '证据完整性校验失败，演示暂不可用。未使用替代证据。'
  } finally { loading.value = false }
})
</script>
<template>
  <section class="public-demo">
    <div class="workspace-hero demo-hero">
      <div class="hero-copy"><span class="eyebrow">PUBLIC DEMO / 只读证据导览</span><h2>Agent 说完成了，<br />验收结果怎么说？</h2><p>从一条完成声明出发，查看独立验收、失败诊断与候选对比。<br class="desktop-copy-break" />沿保存的证据，理解 SameScale 的工作方式。</p></div>
      <aside class="demo-scope" aria-label="演示范围"><template v-if="demo"><span class="status-pill neutral">{{ demo.provenance }}</span><strong>保存证据，不是实时执行</strong><p>固定 Fake 样例 · 无需模型密钥<br />不启动 Agent 或真实模型调用</p><small>不用于模型排名或因果结论</small></template><template v-else><span class="status-pill neutral">只读证据导览</span><strong>核对证据后再展示</strong><p>只有完整性检查通过，才展示保存的记录与阅读入口。</p><small>证据不可用时，不生成替代结果</small></template></aside>
    </div>
    <PageState v-if="loading" kind="loading">正在核对公开演示的证据完整性…</PageState>
    <PageState v-else-if="error" kind="error" reload>{{ error }} <RouterLink to="/analyst">查看离线调查案例</RouterLink></PageState>
    <template v-else-if="demo">
      <div class="demo-content">
        <div class="demo-journey"><div class="journey-heading"><span class="eyebrow">FOLLOW THE EVIDENCE</span><h3>沿这条路径阅读</h3><p>先看发生了什么，再看结论能证明什么。</p></div>
          <ol class="evidence-steps" aria-label="公开演示证据路径">
            <li><RouterLink class="demo-step primary-button" :to="{ path: `/experiments/${demo.baseline_id}`, query: { tab: 'runs', candidate: demo.candidate_id } }"><span class="step-number">01</span><span class="step-copy"><strong>查看基线实验</strong><span>从任务、配置与保存的运行结果开始。</span><small>Experiment / Runs</small></span><span class="step-action" aria-hidden="true">开始阅读 →</span></RouterLink></li>
            <li><RouterLink class="demo-step" :to="{ path: `/runs/${demo.failed_run_id}`, query: { candidate: demo.candidate_id } }"><span class="step-number">02</span><span class="step-copy"><strong>对照声明与独立验收</strong><span>Agent 自报完成，不等于任务契约通过。</span><small>Trace / Episode / Verifier</small></span><span class="step-action" aria-hidden="true">→</span></RouterLink></li>
            <li><RouterLink class="demo-step" :to="{ path: '/diagnosis', query: { experiment: demo.baseline_id, candidate: demo.candidate_id, run: demo.failed_run_id } }"><span class="step-number">03</span><span class="step-copy"><strong>追溯失败证据</strong><span>查看可观察的失败，保留根因归属的限制。</span><small>Diagnosis</small></span><span class="step-action" aria-hidden="true">→</span></RouterLink></li>
            <li><RouterLink class="demo-step" :to="{ path: '/regression', query: { baseline: demo.baseline_id, candidate: demo.candidate_id, run: demo.failed_run_id } }"><span class="step-number">04</span><span class="step-copy"><strong>阅读候选对比</strong><span>先检查可比性，再理解描述性的差异。</span><small>Regression / Comparability</small></span><span class="step-action" aria-hidden="true">→</span></RouterLink></li>
            <li><a class="demo-step" :href="`/api/workbench/runs/${demo.failed_run_id}/public-artifact`" target="_blank" rel="noopener"><span class="step-number">05</span><span class="step-copy"><strong>查看验收产物</strong><span>打开经过摘要校验、允许公开的 fixture 产物。</span><small>Verifier artifact · 新标签页</small></span><span class="step-action" aria-hidden="true">↗</span></a></li>
          </ol>
        </div>
        <aside class="demo-identity" aria-label="演示证据来源"><h3>这组证据来自哪里？</h3><p class="identity-description">完整性检查绑定保存的文件与身份，不代表来源真实性认证。</p><dl><dt>来源类型</dt><dd><span class="status-pill neutral">{{ demo.provenance }}</span></dd><dt>保存的运行 / 文件</dt><dd class="identity-count">{{ demo.run_count }} <small>runs</small> / {{ demo.artifact_file_count }} <small>files</small></dd><dt>生成时间</dt><dd class="technical"><time :datetime="demo.generated_at">{{ demo.generated_at }}</time></dd><dt>Demo 身份</dt><dd class="technical">{{ demo.demo_id }}</dd><dt>Manifest 摘要</dt><dd class="technical">{{ demo.manifest_digest }}</dd></dl><details class="source-limitation"><summary>查看原始来源限制</summary><p lang="en">{{ demo.limitation }}</p></details><p class="read-only-note">本公开实例只读浏览：配置修改与执行已禁用，无需账号或 Provider 凭据。</p></aside>
      </div>
      <details v-if="demo.historical_integrity_failures.length" class="historical-unavailable"><summary>历史 QA 证据不可用 <span>完整性失败 · 保留原记录</span></summary><p>原 QA 记录及摘要仍保留，原产物未恢复。本演示使用独立的新证据身份，不替换历史失败结果。</p><ul><li v-for="id in demo.historical_integrity_failures" :key="id"><RouterLink :to="`/experiments/${id}`">{{ id }}</RouterLink></li></ul></details>
    </template>
  </section>
</template>

<style scoped>
.public-demo { overflow-wrap: anywhere; }
.demo-hero { background: #163b3a; border-color: #163b3a; color: #fff; margin-bottom: 28px; }
.demo-hero .eyebrow { color: #96d0c5; }
.demo-hero .hero-copy p { color: #d0dfdc; }
.demo-scope { border-left: 1px solid #47716b; padding-left: 30px; }
.demo-scope > strong { display: block; margin-top: 18px; font-size: 18px; }
.demo-scope p { color: #d0dfdc; font-size: 14px; line-height: 1.8; margin: 12px 0; }
.demo-scope > small { color: #b9ceca; font-size: 13px; }
.demo-scope .status-pill { background: #264e49; color: #c4e3d9; border-color: #5a8177; }
.demo-content { display: grid; grid-template-columns: minmax(0, 1fr) 300px; align-items: start; gap: 24px; }
.journey-heading { margin-bottom: 20px; }
.journey-heading h3 { margin: 8px 0; font-size: 22px; letter-spacing: -.02em; }
.journey-heading p { color: var(--muted); font-size: 14px; margin: 0; }
.evidence-steps { display: grid; gap: 12px; padding: 0; margin: 0; list-style: none; }
.demo-step { display: flex; align-items: center; gap: 20px; min-height: 112px; padding: 22px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); color: var(--ink); text-decoration: none; text-align: left; font-weight: 400; }
.demo-step:hover { border-color: var(--accent); box-shadow: 0 2px 8px rgb(18 124 115 / 8%); }
.demo-step.primary-button { background: #edf7f4; border-color: #99bfb5; }
.step-number { font: 600 19px/1 ui-monospace, monospace; color: var(--accent); flex: none; }
.step-copy { min-width: 0; flex: 1; }
.step-copy > * { display: block; }
.step-copy strong { font-size: 17px; font-weight: 650; }
.step-copy > span { color: var(--muted); font-size: 14px; margin: 5px 0; }
.step-copy small { font: 12px/1.5 ui-monospace, monospace; color: var(--muted); }
.step-action { flex: none; font-size: 13px; font-weight: 600; color: var(--accent); }
.demo-identity { padding: 24px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); }
.demo-identity h3 { margin: 0 0 10px; font-size: 17px; }
.identity-description { color: var(--muted); font-size: 13px; line-height: 1.7; margin: 0 0 20px; }
.demo-identity dl { margin: 0; }
.demo-identity dt { color: var(--muted); font-size: 12px; margin-top: 18px; }
.demo-identity dd { margin: 7px 0 0; font-size: 13px; }
.demo-identity .identity-count { font: 600 22px/1.5 ui-monospace, monospace; color: var(--ink); }
.identity-count small { color: var(--muted); font-size: 12px; font-weight: 400; }
.source-limitation { border-top: 1px solid var(--line); margin-top: 22px; padding-top: 14px; font-size: 13px; }
.source-limitation summary { color: var(--accent); cursor: pointer; min-height: 44px; padding-block: 10px; }
.source-limitation p { line-height: 1.7; color: var(--muted); }
.read-only-note { font-size: 13px; line-height: 1.7; color: var(--muted); border-radius: 7px; background: #f4f7f6; padding: 13px; margin: 18px 0 0; }
.historical-unavailable { margin-top: 24px; padding: 18px 22px; border: 1px solid var(--line); border-radius: 10px; color: var(--muted); font-size: 13px; background: #fafbfc; }
.historical-unavailable summary { cursor: pointer; color: var(--ink); min-height: 44px; padding-block: 10px; }
.historical-unavailable summary span { margin-left: 8px; font-size: 12px; color: var(--muted); }
.historical-unavailable p { line-height: 1.7; }
.historical-unavailable a { color: var(--accent); }
@media (max-width: 1120px) { .demo-content { grid-template-columns: minmax(0, 1fr); } .demo-identity { margin-top: 4px; } }
@media (max-width: 1000px) { .demo-scope { padding: 20px 0 0; border-left: 0; border-top: 1px solid #47716b; } .demo-scope > strong { display: inline; margin: 0 0 0 12px; font-size: 16px; } }
@media (max-width: 600px) { .demo-step { gap: 14px; padding: 18px; } .step-copy strong { font-size: 16px; } .step-number { font-size: 16px; align-self: flex-start; margin-top: 4px; } .step-action { display: none; } .demo-scope > strong { display: block; margin: 12px 0 0; } .demo-identity { padding: 22px; } .historical-unavailable summary span { display: block; margin: 6px 0 0; } }
</style>
