<script setup lang="ts">
import { nextTick, ref } from 'vue'
import type { AnalystSession } from '@/types/analyst'
const props = defineProps<{
  report: NonNullable<AnalystSession['report']>
  evidence: AnalystSession['evidence']
}>()
const catalogOpen = ref(false)
const selected = ref('')
const catalog = ref<HTMLElement | null>(null)
async function locate(id: string) {
  selected.value = id
  catalogOpen.value = true
  await nextTick()
  const target = catalog.value?.querySelector<HTMLElement>(`[data-evidence-index="${props.evidence.findIndex(entry => entry.ref.id === id)}"]`)
  target?.focus()
  target?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
}
</script>

<template>
  <section class="investigation-report" aria-label="调查结果">
    <h3>1 · 结论</h3>
    <p class="conclusion">{{ report.summary }}</p>
    <h3>2 · 证据</h3>
    <p>以下事实经过宿主校验。点击引用可查看具体工具数据与来源摘要；合成案例的校验仅针对合成输入。</p>
    <p v-if="!report.verified_facts.length">尚无可验证事实；不要据此推断根因。</p>
    <article v-for="(fact, index) in report.verified_facts" :key="index" class="fact">
      <strong>已验证事实 {{ index + 1 }}</strong>
      <dl v-if="fact.assertions?.length" class="assertions">
        <template v-for="(assertion, n) in fact.assertions" :key="n">
          <dt>{{ assertion.tool }} · {{ assertion.field_path.join('.') }}</dt>
          <dd>{{ JSON.stringify(assertion.expected_value) }}</dd>
        </template>
      </dl>
      <p v-else>{{ fact.statement }}</p>
      <div v-for="id in fact.evidence_refs" :key="id">
        <button v-if="evidence.some(entry => entry.ref.id === id)" class="citation" @click="locate(id)">查看证据：{{ id }}</button>
        <span v-else>来源不可用：{{ id }}</span>
      </div>
    </article>
    <details ref="catalog" :open="catalogOpen" class="catalog" @toggle="catalogOpen = ($event.target as HTMLDetailsElement).open">
      <summary>证据目录（{{ evidence.length }}）</summary>
      <article v-for="(entry, index) in evidence" :key="entry.ref.id" :data-evidence-index="index" tabindex="-1" :class="{ selected: selected === entry.ref.id }">
        <strong>{{ entry.ref.id }}</strong>
        <details :open="selected === entry.ref.id"><summary>工具返回数据与摘要</summary><pre>{{ JSON.stringify(entry.data_by_tool, null, 2) }}</pre>
          <p>来源摘要：{{ entry.digest_bindings.join(', ') || '未提供' }}</p>
        </details>
      </article>
    </details>
    <h3>3 · 限制与待验证假设</h3>
    <ul><li v-for="limit in report.limitations" :key="limit">{{ limit }}</li></ul>
    <article v-for="hypothesis in report.hypotheses" :key="hypothesis.statement" class="fact">
      <strong>假设 · 未证实</strong><p>{{ hypothesis.statement }}</p>
      <p>需要补充：{{ hypothesis.additional_evidence_needed }}</p>
      <button v-for="id in (hypothesis.evidence_refs ?? []).filter(id => evidence.some(entry => entry.ref.id === id))" :key="id" class="citation" @click="locate(id)">查看证据：{{ id }}</button>
    </article>
    <h3>4 · 下一步</h3>
    <slot name="next"><p>根据证据和限制准备回归方案，人工审阅后另行授权验证。保存或审批不执行实验。</p></slot>
  </section>
</template>

<style scoped>
.investigation-report { min-width: 0; overflow-wrap: anywhere; line-height: 1.65; }
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
@media (max-width: 600px) { .assertions { grid-template-columns: minmax(0, 1fr); } }
</style>
