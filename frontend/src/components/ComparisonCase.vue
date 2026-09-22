<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { t } from '@/composables/i18n'
import type { ComparisonExample, ComparisonSource } from '@/types/comparison'

const props = defineProps<{ example: ComparisonExample }>()
const root = ref<HTMLElement | null>(null)
const drawer = ref<HTMLDialogElement | null>(null)
const selected = ref<ComparisonSource | null>(null)
const sourceOrigin = ref<HTMLElement | null>(null)
const headingId = useId()
const paired = computed(() => props.example.comparison.descriptive_statistics.capability)
const checksPassed = computed(() => props.example.failure.verifier.checks.filter(check => check.passed).length)
const sections = ['结果', '比较条件', '具体失败', '限制与下一步']
const checkNames: Record<string, string> = {
  'first-records': '首次结果保存成功', 'identical-retry-idempotent': '相同重试不重复写入',
  'conflict-rejected': '冲突重试被拒绝', 'conflict-preserves-original': '冲突后保留原结果',
  'empty-key-rejected': '空操作键被拒绝',
}
const cellName = (index: number) => t(index === 0 ? '直接调用' : 'Codex · medium')
const percent = (numerator: number, denominator: number) => denominator > 0 ? `${(numerator / denominator * 100).toFixed(1)}%` : t('未知')
const seconds = (value: number | null) => value === null ? t('未采集') : `${(value / 1000).toFixed(2)} s`
const cost = (value: number | null) => value === null ? t('未知') : `$${value.toFixed(4)}`
function jump(index: number) {
  const section = root.value?.querySelector<HTMLElement>(`[data-case-section="${index}"]`)
  section?.focus({ preventScroll: true }); section?.scrollIntoView?.({ block: 'start' })
}
async function inspect(id: string, event: Event) {
  const value = props.example.sources.find(source => source.id === id)
  if (!value) return
  sourceOrigin.value = event.currentTarget as HTMLElement
  selected.value = value
  await nextTick()
  drawer.value?.showModal?.()
  if (!drawer.value?.open) drawer.value?.setAttribute('open', '')
  drawer.value?.querySelector<HTMLButtonElement>('button')?.focus()
}
function closeEvidence() {
  drawer.value?.close?.(); drawer.value?.removeAttribute('open')
  selected.value = null
  sourceOrigin.value?.focus({ preventScroll: true })
  sourceOrigin.value = null
}
watch(() => props.example, closeEvidence)
onBeforeUnmount(() => { drawer.value?.close?.() })
</script>

<template>
  <article ref="root" class="comparison-case">
    <header class="case-heading">
      <h2>{{ t('直接调用与 Codex：这组任务表现如何？') }}</h2>
      <p>{{ example.cells[0].requested_model }} · {{ example.cells[0].provider }} · {{ example.cells[0].reasoning_effort }}</p>
      <p>{{ example.task_count }} {{ t('个代码修复任务') }} · Python / Java / TypeScript · {{ t('每项') }} {{ example.repeat_count }} {{ t('次') }}</p>
      <p class="case-date">{{ t('数据截至') }} <time :datetime="example.recorded_at">{{ example.recorded_at.slice(0, 10) }}</time> · {{ t('历史结果，包含基础设施恢复') }}</p>
    </header>
    <nav class="case-nav" :aria-label="t('案例章节')"><button v-for="(section, index) in sections" :key="section" @click="jump(index)">{{ t(section) }}</button></nav>

    <section data-case-section="0" tabindex="-1">
      <h3>{{ t('这组任务中，直接调用通过更多') }}</h3>
      <p class="case-lead">{{ t('结果仅描述这次运行，不能据此判定 Codex 或模型本身更弱。') }}</p>
      <div class="result-grid">
        <article v-for="(cell, index) in example.cells" :key="cell.cell_id" class="result-card">
          <header><h4>{{ cellName(index) }}</h4><button class="source-link" :aria-label="`${t('核对结果证据')} · ${cellName(index)}`" @click="inspect(`result-${index}`, $event)">{{ t('证据') }} ↗</button></header>
          <div class="pass-count"><strong>{{ cell.passed }}<span> / {{ cell.denominator }}</span></strong><span>{{ t('通过 / 有效运行') }} · {{ percent(cell.passed, cell.denominator) }}</span></div>
          <div class="pass-track" aria-hidden="true"><span :style="{ width: cell.denominator ? `${cell.passed / cell.denominator * 100}%` : '0%' }" /></div>
          <div class="card-usage">
            <div><span>{{ t('首次耗时中位数') }}</span><strong>{{ seconds(cell.primary_latency_ms) }}</strong><small>{{ t('已采集') }} {{ cell.latency_observations }}/{{ cell.planned }}</small></div>
            <div><span>{{ t('历史成本估算') }}</span><strong>{{ cost(cell.estimated_cost_usd) }}</strong><small>{{ t('实际账单未知') }}</small></div>
          </div>
          <p class="run-accounting">{{ t('计划') }} {{ cell.planned }} · {{ t('基础设施未恢复') }} {{ cell.infra_missing }} · {{ t('已取消') }} {{ cell.cancelled }}</p>
          <details><summary>{{ t('运行明细与失败分类') }}</summary>
            <dl><dt>{{ t('首次通过 / 恢复后通过') }}</dt><dd>{{ cell.primary_passed }} / {{ cell.recovered_passes }}</dd><dt>{{ t('测试失败') }}</dt><dd>{{ cell.test_failures }}</dd><dt>{{ t('执行预算耗尽') }}</dt><dd>{{ cell.budget_failures }}</dd><dt>{{ t('输出格式错误') }}</dt><dd>{{ cell.output_failures }}</dd></dl>
          </details>
        </article>
      </div>
      <p class="case-note">{{ t('分母只包含已判定通过或失败的运行。基础设施失败与取消另计；预算耗尽按原规则判为失败。') }}</p>
      <div class="paired-result">
        <header><h4>{{ t('对齐任务与重复次数后') }}</h4><button class="source-link" @click="inspect('comparison', $event)">{{ t('核对配对证据') }} ↗</button></header>
        <p><strong>{{ paired.complete_pairs }} / {{ paired.total_possible_pairs }}</strong> {{ t('对有完整结果') }} · {{ example.comparison.discordance_summary.excluded_missing_pairs }} {{ t('对因基础设施失败或取消排除') }}</p>
        <dl class="pair-counts"><dt>{{ t('两侧都通过') }}</dt><dd>{{ paired.both_pass }}</dd><dt>{{ t('仅直接调用通过') }}</dt><dd>{{ paired.discordant_baseline_pass_variant_fail }}</dd><dt>{{ t('仅 Codex 通过') }}</dt><dd>{{ paired.discordant_baseline_fail_variant_pass }}</dd><dt>{{ t('两侧都未通过') }}</dt><dd>{{ paired.both_fail }}</dd></dl>
        <p class="case-note">{{ t('完整结果不等于严格可比。以上配对均为部分可比，不能作因果归因。') }}</p>
        <details><summary>{{ t('原统计口径') }}</summary><p>{{ t('Codex 减去直接调用，按任务等权的通过率差异：') }} {{ (paired.delta * 100).toFixed(2) }} {{ t('个百分点') }}。</p><p>{{ t('这与上方两侧各自的通过率、按配对逐行计算的差异使用不同口径。') }}</p></details>
      </div>
      <div class="responsive-table"><table class="cost-table"><caption>{{ t('耗时与成本') }}</caption><thead><tr><th scope="col">{{ t('指标') }}</th><th v-for="(_, index) in example.cells" :key="index" scope="col">{{ cellName(index) }}</th></tr></thead><tbody>
        <tr><th scope="row">{{ t('首次执行耗时中位数') }}</th><td v-for="(cell, index) in example.cells" :key="cell.cell_id">{{ seconds(cell.primary_latency_ms) }} <button class="source-link" :aria-label="`${t('核对耗时证据')} · ${cellName(index)}`" @click="inspect(`timing-${index}`, $event)">↗</button><small>{{ t('已采集') }} {{ cell.latency_observations }}/{{ cell.planned }}</small></td></tr>
        <tr><th scope="row">{{ t('整组成本估算 · USD') }}</th><td v-for="(cell, index) in example.cells" :key="cell.cell_id">{{ cost(cell.estimated_cost_usd) }} <button class="source-link" :aria-label="`${t('核对成本证据')} · ${cellName(index)}`" @click="inspect(`cost-${index}`, $event)">↗</button></td></tr>
        <tr><th scope="row">{{ t('实际账单') }}</th><td v-for="cell in example.cells" :key="cell.cell_id">{{ t('未知') }}</td></tr>
      </tbody></table></div>
      <p class="case-note">{{ t('耗时只统计首次执行，未采集不按零计算。成本为历史保守估算，含恢复和缺失用量预留，不是实际账单。') }}</p>
    </section>

    <section data-case-section="1" tabindex="-1">
      <h3>{{ t('比较条件') }}</h3>
      <dl class="conditions">
        <dt>{{ t('任务与重复') }}</dt><dd>{{ example.task_count }} × {{ example.repeat_count }} <button class="source-link" @click="inspect('scope', $event)">{{ t('任务范围') }} ↗</button></dd>
        <dt>{{ t('请求模型') }}</dt><dd>{{ example.cells[0].requested_model }} · {{ example.cells[0].provider }} · {{ example.cells[0].reasoning_effort }}</dd>
        <dt>{{ t('执行方式') }}</dt><dd>{{ t('直接生成补丁 / Codex 工具循环') }}</dd>
        <dt>{{ t('每次模型请求') }}</dt><dd>{{ example.output_tokens_per_request }} tokens · {{ example.request_timeout_seconds }} s</dd>
        <dt>{{ t('计划运行上限') }}</dt><dd>{{ example.plan_timeout_seconds }} s <button class="source-link" @click="inspect('budget', $event)">{{ t('预算范围') }} ↗</button></dd>
      </dl>
      <p class="case-note">{{ t('请求输出上限不代表整个 Codex 任务的总输出上限。运行时模型身份、服务配置和轨迹存在缺口，正式比较资格未通过。') }}</p>
      <div class="source-actions"><button v-for="(_, index) in example.cells" :key="index" class="source-link" @click="inspect(`config-${index}`, $event)">{{ cellName(index) }} · {{ t('冻结配置') }} ↗</button></div>
    </section>

    <section data-case-section="2" tabindex="-1">
      <header class="failure-heading"><div><span class="case-eyebrow">Python · {{ t('直接调用') }}</span><h3>{{ t('具体失败：空操作键被接受') }}</h3></div><button class="source-link" @click="inspect('failure', $event)">{{ t('核对失败证据') }} ↗</button></header>
      <p>{{ t('任务是修复重试账本：首次保存结果，相同重试不重复写入，冲突重试保留原结果并报错。') }} <button class="source-link" @click="inspect('instruction', $event)">{{ t('任务原文') }} ↗</button></p>
      <div class="failure-example">
        <div><span>{{ t('测试输入') }}</span><code>{{ example.failure.input_expression }}</code><button class="source-link" @click="inspect('probe', $event)">{{ t('测试调用') }} ↗</button></div>
        <div><span>{{ t('预期 · 冻结验证器') }}</span><strong>ValueError</strong></div>
        <div><span>{{ t('实际 · 冻结记录与源码') }}</span><strong>True</strong><p>{{ t('接受并保存了空键。') }}</p></div>
      </div>
      <p><strong>{{ checksPassed }} / {{ example.failure.verifier.checks.length }}</strong> {{ t('项检查通过，任务仍判为失败。') }}</p>
      <ul class="verifier-checks"><li v-for="check in example.failure.verifier.checks" :key="check.name"><span :class="{ failed: !check.passed }">{{ t(check.passed ? '通过' : '未通过') }}</span>{{ t(checkNames[check.name] ?? check.name) }}</li></ul>
      <p class="specification-note">{{ t('任务说明明确了非空键的行为，但没有明确要求拒绝空键；冻结验证器要求拒绝。这个规格限制与原始失败结果一并保留。') }}</p>
      <details><summary>{{ t('查看最终代码差异') }}</summary><pre v-for="diff in example.failure.source_diffs" :key="diff">{{ diff }}</pre></details>
      <details><summary>{{ t('运行身份与证据边界') }}</summary><dl class="conditions"><dt>{{ t('任务') }}</dt><dd>{{ example.failure.task_id }}@{{ example.failure.task_version }}</dd><dt>{{ t('运行') }}</dt><dd>{{ example.failure.run_id }}</dd><dt>{{ t('Agent 轨迹') }}</dt><dd>{{ t('未采集；不重建推理或操作过程。') }}</dd></dl><p>{{ t('失败记录已冻结核验；配对另一侧的文件完整性有限，不能据此还原两侧完整过程。') }}</p></details>
    </section>

    <section data-case-section="3" tabindex="-1">
      <h3>{{ t('能确认什么') }}</h3>
      <p>{{ t('已核对通过数量、缺失记录和空键测试失败。差异原因尚未确认，结果不构成模型能力排名。') }}</p>
      <h4>{{ t('下一步') }}</h4>
      <p>{{ t('先明确空键约定，再审阅对照测试方案。判断 Agent 运行时的影响，还需补齐身份与轨迹，并控制比较条件。') }}</p>
      <p class="case-note">{{ t('以上是待验证建议。本页只读历史记录，不运行模型或测试。') }}</p>
    </section>

    <dialog ref="drawer" class="case-evidence-dialog" :aria-labelledby="headingId" @cancel.prevent="closeEvidence" @keydown.esc.prevent="closeEvidence">
      <template v-if="selected"><header><h3 :id="headingId">{{ t('原始证据') }}</h3><button class="secondary-button" @click="closeEvidence">{{ t('关闭并返回引用') }}</button></header><p class="evidence-path">{{ selected.path }}{{ selected.pointer ? `#${selected.pointer}` : '' }}</p><code class="source-digest">{{ selected.sha256 }}</code><pre>{{ typeof selected.data === 'string' ? selected.data : JSON.stringify(selected.data, null, 2) }}</pre></template>
    </dialog>
  </article>
</template>

<style scoped>
.comparison-case { max-width: 920px; margin: 0 auto; overflow-wrap: anywhere; }
.case-heading { margin: 28px 0 24px; }.case-heading h2 { font: var(--type-title); margin: 0 0 12px; }.case-heading p { margin: 6px 0; color: var(--muted); }.case-date, .case-note, .case-eyebrow { font: var(--type-caption); color: var(--muted); }
.case-nav { display: flex; gap: 8px 24px; flex-wrap: wrap; border-bottom: 1px solid var(--line); padding-bottom: 12px; margin-bottom: 32px; }.case-nav button { border: 0; background: transparent; padding: 6px 0; color: var(--muted); cursor: pointer; font: var(--type-control); }
section { margin-top: 36px; scroll-margin-top: 84px; }section:focus { outline: 2px solid var(--accent); outline-offset: 8px; }h3 { font: var(--type-section); margin: 0 0 12px; }h4 { font: var(--type-control); font-weight: 600; margin: 0; }p { margin: 10px 0 16px; }.case-lead { color: var(--muted); }
.result-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }.result-card { border: 1px solid var(--line); background: white; border-radius: 12px; padding: 22px; }.result-card header, .paired-result header, .failure-heading, .case-evidence-dialog header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.pass-count { display: flex; flex-direction: column; gap: 4px; margin-top: 22px; }.pass-count strong { font: 500 32px/1.3 var(--font-ui); font-variant-numeric: tabular-nums; }.pass-count strong span { color: var(--muted); font-size: 22px; }.pass-count > span { color: var(--muted); font: var(--type-caption); }.pass-track { height: 5px; margin: 18px 0; background: #eceeef; border-radius: 8px; overflow: hidden; }.pass-track span { display: block; height: 100%; background: #667985; }
.card-usage { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }.card-usage span, .card-usage small { display: block; font: var(--type-caption); color: var(--muted); }.card-usage strong { display: block; margin: 5px 0; font: var(--type-control); font-weight: 500; }.run-accounting { color: var(--muted); font: var(--type-caption); margin: 18px 0 0; }
dl { display: grid; grid-template-columns: 1fr auto; gap: 8px 16px; margin: 16px 0; font: var(--type-caption); }dt { color: var(--muted); }dd { margin: 0; font-variant-numeric: tabular-nums; }summary { cursor: pointer; color: var(--muted); font: var(--type-control); }details { margin: 16px 0 0; }details p { color: var(--muted); }
.paired-result { padding: 22px 0; margin: 20px 0; border-block: 1px solid var(--line); }.pair-counts { grid-template-columns: 1fr auto 1fr auto; column-gap: 24px; }.source-link { display: inline; border: 0; background: transparent; color: var(--link); font: var(--type-caption); padding: 4px; cursor: pointer; text-underline-offset: 4px; }.source-link:hover { text-decoration: underline; }.source-actions { display: flex; gap: 20px; flex-wrap: wrap; }
.cost-table { width: 100%; border-collapse: collapse; text-align: left; font: var(--type-caption); }.cost-table caption { text-align: left; font: var(--type-section); margin-bottom: 14px; }.cost-table th, .cost-table td { border-bottom: 1px solid var(--line); padding: 12px 8px; font-weight: 400; }.cost-table th { color: var(--muted); }.cost-table small { display: block; color: var(--muted); }.conditions { grid-template-columns: minmax(100px, .5fr) 2fr; font: var(--type-control); }
.failure-example { display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 20px; background: white; border: 1px solid var(--line); border-radius: 10px; padding: 20px; margin: 20px 0; }.failure-example div { min-width: 0; }.failure-example span { display: block; color: var(--muted); font: var(--type-caption); margin-bottom: 12px; }.failure-example code { display: block; font: var(--type-code); }.failure-example strong { font: var(--type-control); font-weight: 600; }.failure-example p { font: var(--type-caption); margin-bottom: 0; }.verifier-checks { padding: 0; list-style: none; }.verifier-checks li { display: flex; align-items: baseline; gap: 16px; padding: 5px 0; }.verifier-checks span { color: #4b6d60; font: var(--type-caption); min-width: 44px; }.verifier-checks span.failed { color: var(--danger); }.specification-note { padding-left: 16px; border-left: 2px solid #bac0c5; color: var(--muted); }
pre { max-width: 100%; max-height: 450px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: var(--type-code); background: #f5f6f7; padding: 16px; border-radius: 6px; }.case-evidence-dialog { width: min(780px, calc(100vw - 32px)); max-height: calc(100dvh - 48px); overflow-y: auto; border: 1px solid var(--line); border-radius: 12px; padding: 24px; color: var(--ink); box-shadow: 0 16px 60px #10182026; }.case-evidence-dialog::backdrop { background: #18212e50; }.case-evidence-dialog h3 { margin: 0; }.evidence-path, .source-digest { overflow-wrap: anywhere; font: var(--type-code); }.source-digest { color: var(--muted); }.case-evidence-dialog pre { max-height: none; }
@media (max-width: 600px) { .result-grid { grid-template-columns: 1fr; }.result-card { padding: 20px; }.failure-example { grid-template-columns: 1fr; gap: 24px; }.pair-counts { grid-template-columns: 1fr auto; }.case-nav { gap: 6px 18px; }.case-heading h2 { font-size: 22px; }.case-evidence-dialog { padding: 16px; }.case-evidence-dialog header, .failure-heading { align-items: flex-start; flex-wrap: wrap; }.conditions { grid-template-columns: 100px 1fr; }.cost-table th, .cost-table td { padding-inline: 4px; } }
</style>
