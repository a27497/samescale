<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
import { copy as c } from '@/composables/visualLocale'
import type { AnalystSession } from '@/types/analyst'
const props = defineProps<{
  report: NonNullable<AnalystSession['report']>
  evidence: AnalystSession['evidence']
}>()
const reportId = useId()
const origin = ref<HTMLElement | null>(null)
const reportRoot = ref<HTMLElement | null>(null)
const sections = computed(() => [c('结论', 'Conclusion'), c('证据', 'Evidence'), c('限制与假设', 'Limits & hypotheses'), c('下一步', 'Next steps')])
function focusSection(index: number) {
  const target = reportRoot.value?.querySelector<HTMLElement>(`[data-report-section="${index}"]`)
  target?.focus()
  target?.scrollIntoView?.({ block: 'start' })
}
function returnToFact() {
  origin.value?.focus()
  origin.value?.scrollIntoView?.({ block: 'center' })
}
const catalogOpen = ref(false)
const selected = ref('')
const catalog = ref<HTMLElement | null>(null)
async function locate(id: string, event: Event) {
  origin.value = event.currentTarget as HTMLElement
  selected.value = id
  catalogOpen.value = true
  await nextTick()
  const target = catalog.value?.querySelector<HTMLElement>(`[data-evidence-index="${props.evidence.findIndex(entry => entry.ref.id === id)}"]`)
  target?.focus()
  target?.scrollIntoView?.({ block: 'center' })
}
watch(() => props.evidence, () => {
  selected.value = ''
  origin.value = null
  catalogOpen.value = false
})
</script>

<template>
  <section ref="reportRoot" class="investigation-report" :aria-label="c('调查结果', 'Investigation result')">
    <nav class="report-nav" :aria-label="c('报告章节', 'Report sections')">
      <button v-for="(label, index) in sections" :key="label" :aria-controls="`${reportId}-${index}`" @click="focusSection(index)">{{ index + 1 }} · {{ label }}</button>
    </nav>
    <div class="report-body">
    <h3 :id="`${reportId}-0`" data-report-section="0" tabindex="-1">{{ c('1 · 结论', '1 · Conclusion') }}</h3>
    <p class="conclusion">{{ report.summary }}</p>
    <h3 :id="`${reportId}-1`" data-report-section="1" tabindex="-1">{{ c('2 · 证据', '2 · Evidence') }}</h3>
    <p>{{ c('以下事实经过宿主校验。点击引用可查看具体工具数据与来源摘要；合成案例的校验仅针对合成输入。', 'The host validated these facts. Follow citations to inspect tool data and digest bindings. Synthetic-case validation applies only to synthetic inputs.') }}</p>
    <p v-if="!report.verified_facts.length">{{ c('尚无可验证事实；不要据此推断根因。', 'No verified facts are available; do not infer root cause.') }}</p>
    <article v-for="(fact, index) in report.verified_facts" :key="index" class="fact">
      <strong>{{ c('已验证事实 ', 'Verified fact ') }}{{ index + 1 }}</strong>
      <dl v-if="fact.assertions?.length" class="assertions">
        <template v-for="(assertion, n) in fact.assertions" :key="n">
          <dt>{{ assertion.tool }} · {{ assertion.field_path.join('.') }}</dt>
          <dd>{{ JSON.stringify(assertion.expected_value) }}</dd>
        </template>
      </dl>
      <p v-else>{{ fact.statement }}</p>
      <div v-for="id in fact.evidence_refs" :key="id">
        <button v-if="evidence.some(entry => entry.ref.id === id)" class="citation" @click="locate(id, $event)">{{ c('查看证据：', 'View evidence: ') }}{{ id }}</button>
        <span v-else>{{ c('来源不可用：', 'Source unavailable: ') }}{{ id }}</span>
      </div>
    </article>
    <details ref="catalog" :open="catalogOpen" class="catalog" @toggle="catalogOpen = ($event.target as HTMLDetailsElement).open">
      <summary>{{ c('证据目录（', 'Evidence catalog (') }}{{ evidence.length }}{{ c('）', ')') }}</summary>
      <article v-for="(entry, index) in evidence" :key="entry.ref.id" :data-evidence-index="index" tabindex="-1" :class="{ selected: selected === entry.ref.id }">
        <strong>{{ entry.ref.id }}</strong>
        <button v-if="selected === entry.ref.id && origin" class="return-citation" @click="returnToFact">{{ c('返回引用处', 'Return to citation') }}</button>
        <details :open="selected === entry.ref.id"><summary>{{ c('工具返回数据与摘要', 'Tool data & digests') }}</summary><pre>{{ JSON.stringify(entry.data_by_tool, null, 2) }}</pre>
          <p>{{ c('来源摘要：', 'Source digests: ') }}{{ entry.digest_bindings.join(', ') || c('未提供', 'Not reported') }}</p>
        </details>
      </article>
    </details>
    <h3 :id="`${reportId}-2`" data-report-section="2" tabindex="-1">{{ c('3 · 限制与待验证假设', '3 · Limits & hypotheses') }}</h3>
    <p v-if="!report.limitations.length">{{ c('报告未列出限制；这不代表根因已被证实。', 'The report lists no limitations; this does not establish root cause.') }}</p>
    <ul><li v-for="limit in report.limitations" :key="limit">{{ limit }}</li></ul>
    <article v-for="hypothesis in report.hypotheses" :key="hypothesis.statement" class="fact">
      <strong>{{ c('假设 · 未证实', 'Hypothesis · unverified') }}</strong><p>{{ hypothesis.statement }}</p>
      <p>{{ c('需要补充：', 'Additional evidence needed: ') }}{{ hypothesis.additional_evidence_needed }}</p>
      <div v-for="id in hypothesis.evidence_refs ?? []" :key="id">
        <button v-if="evidence.some(entry => entry.ref.id === id)" class="citation" @click="locate(id, $event)">{{ c('查看证据：', 'View evidence: ') }}{{ id }}</button>
        <span v-else>{{ c('来源不可用：', 'Source unavailable: ') }}{{ id }}</span>
      </div>
    </article>
    <h3 :id="`${reportId}-3`" data-report-section="3" tabindex="-1">{{ c('4 · 下一步', '4 · Next steps') }}</h3>
    <slot name="next"><p>{{ c('根据证据和限制准备回归方案，人工审阅后另行授权验证。保存或审批不执行实验。', 'Prepare a regression proposal from the evidence and limits. Validation requires separate authorization after review. Saving or approving does not execute an experiment.') }}</p></slot>
    </div>
  </section>
</template>

<style scoped>
.investigation-report { min-width: 0; overflow-wrap: anywhere; line-height: 1.65; display: grid; grid-template-columns: 145px minmax(0, 1fr); gap: 28px; align-items: start; margin-top: 24px; }
.report-body { min-width: 0; }
.report-nav { display: grid; gap: 8px; position: sticky; top: 110px; }
.report-nav button, .return-citation { cursor: pointer; color: var(--accent); background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 11px; text-align: left; font: inherit; }
.return-citation { display: block; margin: 8px 0; }
[data-report-section], .catalog article { scroll-margin-top: 110px; }
h3 { margin: 26px 0 12px; font-size: 18px; }
.conclusion { padding: 20px; background: var(--accent-soft); border-left: 3px solid var(--accent); }
.fact { border: 1px solid var(--line); padding: 16px; margin: 12px 0; border-radius: 6px; }
.citation { background: transparent; border: 0; color: var(--accent); text-decoration: underline; cursor: pointer; font: inherit; text-align: left; overflow-wrap: anywhere; max-width: 100%; padding: 6px 0; }
.assertions { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px 16px; font-size: 13px; }
dd { margin: 0; }
dt { color: var(--muted); }
.catalog { margin: 16px 0; padding: 12px; border: 1px solid var(--line); }
.catalog article { margin: 12px 0; padding: 12px; }
.selected { background: var(--accent-soft); }
pre { max-height: 380px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; }
summary { cursor: pointer; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
@media (max-width: 900px) { .investigation-report { grid-template-columns: minmax(0, 1fr); gap: 0; } .report-nav { position: static; display: flex; flex-wrap: wrap; } }
@media (max-width: 600px) { .assertions { grid-template-columns: minmax(0, 1fr); } }
</style>
