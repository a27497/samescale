<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import type { AnalystSession } from '@/types/analyst'
const props = defineProps<{
  report: NonNullable<AnalystSession['report']>
  evidence: AnalystSession['evidence']
}>()
const reportId = useId()
const origin = ref<HTMLElement | null>(null)
const reportRoot = ref<HTMLElement | null>(null)
const sections = ['结论', '证据', '限制与假设', '下一步']
function focusSection(index: number) {
  activeSection.value = index
  const target = reportRoot.value?.querySelector<HTMLElement>(`[data-report-section="${index}"]`)
  target?.focus()
  target?.scrollIntoView?.({ block: 'start' })
}
const catalogOpen = ref(false)
const selected = ref('')
const catalog = ref<HTMLDialogElement | null>(null)
const selectedEntry = computed(() => props.evidence.find(entry => entry.ref.id === selected.value))
const activeSection = ref(0)
const selectedTool = ref('')
const toolEntries = computed(() => Object.entries(selectedEntry.value?.data_by_tool ?? {}))
const visibleTools = computed(() => toolEntries.value.filter(([tool]) => tool === selectedTool.value))
watch(selectedEntry, () => { selectedTool.value = toolEntries.value[0]?.[0] ?? '' }, { flush: 'sync' })
let narrowScreen: MediaQueryList | undefined
function showDrawer() {
  if (!catalog.value || catalog.value.open) return
  if (narrowScreen?.matches) catalog.value.showModal?.()
  else catalog.value.show?.()
  if (!catalog.value.open) catalog.value.setAttribute('open', '')
}
function resizeDrawer() {
  if (!catalogOpen.value) return
  catalog.value?.close?.()
  showDrawer()
  catalog.value?.querySelector<HTMLElement>('[data-evidence-index]')?.focus({ preventScroll: true })
}
function escapeDrawer(event: KeyboardEvent) {
  if (event.key === 'Escape' && catalogOpen.value) { event.preventDefault(); returnToFact() }
}
onMounted(() => {
  narrowScreen = window.matchMedia?.('(max-width: 1100px)')
  narrowScreen?.addEventListener('change', resizeDrawer)
  document.addEventListener('keydown', escapeDrawer)
})
onBeforeUnmount(() => {
  narrowScreen?.removeEventListener('change', resizeDrawer)
  document.removeEventListener('keydown', escapeDrawer)
})
function returnToFact() {
  catalog.value?.close?.()
  catalogOpen.value = false
  origin.value?.focus({ preventScroll: true })
}
async function locate(id: string, event: Event, tool?: string) {
  origin.value = event.currentTarget as HTMLElement
  selected.value = id
  if (tool && selectedEntry.value?.data_by_tool[tool] !== undefined) selectedTool.value = tool
  activeSection.value = 1
  catalogOpen.value = true
  await nextTick()
  showDrawer()
  catalog.value?.querySelector<HTMLElement>('[data-evidence-index]')?.focus({ preventScroll: true })
}
watch(() => props.evidence, () => {
  catalog.value?.close?.()
  selected.value = ''
  origin.value = null
  catalogOpen.value = false
})
</script>

<template>
  <section ref="reportRoot" class="investigation-report" :aria-label="t('调查结果')">
    <nav class="report-nav" :aria-label="t('报告章节')">
      <button v-for="(label, index) in sections" :key="label" :class="{ active: activeSection === index }" :aria-controls="`${reportId}-${index}`" @click="focusSection(index)">{{ index + 1 }} · {{ t(label) }}</button>
    </nav>
    <div class="report-body">
    <h3 :id="`${reportId}-0`" data-report-section="0" tabindex="-1">{{ t('1 · 结论') }}</h3>
    <p class="conclusion">{{ report.summary }}</p>
    <h3 :id="`${reportId}-1`" data-report-section="1" tabindex="-1">{{ t('2 · 证据') }}</h3>
    <p>{{ t('以下事实经过宿主校验。点击引用可查看具体工具数据与来源摘要；合成案例的校验仅针对合成输入。') }}</p>
    <p v-if="!report.verified_facts.length">{{ t('尚无可验证事实；不要据此推断根因。') }}</p>
    <article v-for="(fact, index) in report.verified_facts" :key="index" class="fact">
      <strong>{{ t('已验证事实') }} {{ index + 1 }}</strong>
      <dl v-if="fact.assertions?.length" class="assertions">
        <template v-for="(assertion, n) in fact.assertions" :key="n">
          <dt>{{ assertion.tool }} · {{ assertion.field_path.join('.') }}</dt>
          <dd>{{ JSON.stringify(assertion.expected_value) }}</dd>
        </template>
      </dl>
      <p v-else>{{ fact.statement }}</p>
      <div v-for="id in fact.evidence_refs" :key="id">
        <button v-if="evidence.some(entry => entry.ref.id === id)" class="citation" @click="locate(id, $event, fact.assertions?.[0]?.tool)">{{ t('查看证据：') }}{{ id }}</button>
        <span v-else>{{ t('来源不可用：') }}{{ id }}</span>
      </div>
    </article>
    <button v-if="evidence.length" class="catalog-toggle" @click="locate(evidence[0]!.ref.id, $event)">{{ t('打开证据目录') }} <span>{{ evidence.length }} {{ t('个来源') }}</span></button>
    <dialog ref="catalog" class="evidence-drawer" :aria-label="t('证据检查器')" @cancel.prevent="returnToFact" @keydown.esc.prevent="returnToFact">
      <header class="drawer-header"><div><span class="eyebrow">{{ t('来源与工具数据') }}</span><h2>{{ t('证据检查器') }}</h2></div><button class="drawer-close" :aria-label="t('关闭证据')" @click="returnToFact">{{ t('关闭') }} <kbd>Esc</kbd></button></header>
      <div class="drawer-content">
        <label class="source-picker">{{ t('证据来源') }}<select v-model="selected" :aria-label="t('证据来源')"><option v-for="entry in evidence" :key="entry.ref.id" :value="entry.ref.id">{{ entry.ref.id }}</option></select></label>
        <article v-if="selectedEntry" :key="selectedEntry.ref.id" :data-evidence-index="evidence.indexOf(selectedEntry)" tabindex="-1" class="selected">
          <span class="eyebrow">{{ t('来源引用') }}</span><strong class="source-id">{{ selectedEntry.ref.id }}</strong>
          <p class="source-note">{{ t('工具返回的原始数据。证据范围与报告一致；来源摘要用于核对绑定。') }}</p>
          <div class="tool-tabs" role="group" :aria-label="t('选择证据工具')"><button v-for="[tool] in toolEntries" :key="tool" :aria-pressed="selectedTool === tool" @click="selectedTool = tool">{{ tool }}</button></div>
          <div v-for="[tool, data] in visibleTools" :key="tool" class="tool-evidence">
            <div class="tool-heading"><strong>{{ tool }}</strong><span>{{ t('工具结果') }}</span></div>
            <dl v-if="data && typeof data === 'object' && !Array.isArray(data)" class="evidence-fields">
              <template v-for="(value, field) in data" :key="field"><dt>{{ field }}</dt><dd><code>{{ JSON.stringify(value) }}</code></dd></template>
            </dl>
            <pre v-else>{{ JSON.stringify(data, null, 2) }}</pre>
          </div>
          <details class="raw-evidence"><summary>{{ t('工具返回数据与摘要') }}</summary><pre>{{ JSON.stringify(selectedEntry.data_by_tool, null, 2) }}</pre><p>{{ t('来源摘要：') }}{{ selectedEntry.digest_bindings.join(', ') || t('未提供') }}</p></details>
          <div class="digest-block"><span class="eyebrow">{{ t('摘要绑定') }}</span><code v-for="digest in selectedEntry.digest_bindings" :key="digest">{{ digest }}</code><span v-if="!selectedEntry.digest_bindings.length">{{ t('未提供') }}</span></div>
          <button v-if="catalogOpen && origin" class="return-citation" @click="returnToFact">{{ t('返回引用处') }}</button>
        </article>
      </div>
    </dialog>
    <h3 :id="`${reportId}-2`" data-report-section="2" tabindex="-1">{{ t('3 · 限制与待验证假设') }}</h3>
    <p v-if="!report.limitations.length">{{ t('报告未列出限制；这不代表根因已被证实。') }}</p>
    <ul><li v-for="limit in report.limitations" :key="limit">{{ limit }}</li></ul>
    <article v-for="hypothesis in report.hypotheses" :key="hypothesis.statement" class="fact">
      <strong>{{ t('假设 · 未证实') }}</strong><p>{{ hypothesis.statement }}</p>
      <p>{{ t('需要补充：') }}{{ hypothesis.additional_evidence_needed }}</p>
      <div v-for="id in hypothesis.evidence_refs ?? []" :key="id">
        <button v-if="evidence.some(entry => entry.ref.id === id)" class="citation" @click="locate(id, $event)">{{ t('查看证据：') }}{{ id }}</button>
        <span v-else>{{ t('来源不可用：') }}{{ id }}</span>
      </div>
    </article>
    <h3 :id="`${reportId}-3`" data-report-section="3" tabindex="-1">{{ t('4 · 下一步') }}</h3>
    <slot name="next"><p>{{ t('根据证据和限制准备回归方案，人工审阅后另行授权验证。保存或审批不执行实验。') }}</p></slot>
    </div>
  </section>
</template>

<style scoped>
.investigation-report { min-width: 0; overflow-wrap: anywhere; font: var(--type-body); margin-top: 24px; }
.report-body { min-width: 0; }
.report-nav { position: sticky; top: 64px; z-index: 10; background: #faf9f7; display: flex; flex-wrap: wrap; gap: 22px; border-bottom: 1px solid var(--line); margin-bottom: 20px; }
.report-nav button { cursor: pointer; color: var(--muted); background: transparent; border: 0; border-bottom: 2px solid transparent; padding: 10px 0; font: inherit; font-size: 13px; }
.report-nav button.active { color: var(--ink); border-bottom-color: #636e7d; }
[data-report-section] { scroll-margin-top: 112px; }
h3 { margin: 32px 0 12px; font: var(--type-section); }
h3:first-child { margin-top: 0; }
.conclusion { font: var(--type-body); padding: 0 0 20px; margin-bottom: 20px; border-bottom: 1px solid var(--line); max-width: 850px; }
.report-body > p:not(.conclusion) { color: var(--muted); font-size: 13px; }
.fact { border: 1px solid var(--line); padding: 18px 20px; margin: 14px 0; border-radius: 7px; background: #fff; }
.fact > strong { display: block; font: var(--type-control); font-weight: 500; color: #586677; }
.citation { display: inline-block; background: #f0f2f4; border: 1px solid #e2e6e9; border-radius: 5px; color: var(--accent); cursor: pointer; font: var(--type-code); text-align: left; overflow-wrap: anywhere; max-width: 100%; padding: 6px 9px; margin-top: 8px; }
.citation:hover { background: #e6ebf0; border-color: #b6c1cd; }
.assertions { display: grid; grid-template-columns: minmax(0, .8fr) minmax(0, 1.2fr); column-gap: 20px; font: var(--type-code); margin: 12px 0; }
dd { margin: 0; }
.assertions dt, .assertions dd { padding: 9px 0; border-bottom: 1px solid #f0f0ef; }
dt { color: var(--muted); }
.catalog-toggle { width: 100%; display: flex; justify-content: space-between; border: 0; border-block: 1px solid var(--line); background: transparent; padding: 14px 0; margin-top: 20px; color: var(--accent); font: inherit; cursor: pointer; }
.catalog-toggle span { color: var(--muted); font-size: 13px; }
.evidence-drawer { position: fixed; inset: 64px 0 0 auto; width: min(460px, 100vw); max-width: 100vw; height: calc(100dvh - 64px); max-height: none; margin: 0; border: 0; border-left: 1px solid #cfd4d9; padding: 0; background: rgb(239 242 244 / 92%); backdrop-filter: blur(24px); box-shadow: -12px 0 38px rgb(45 55 65 / 5%); color: var(--ink); z-index: 24; overflow: hidden; }
.evidence-drawer[open] { display: flex; flex-direction: column; }
.evidence-drawer::backdrop { background: rgb(42 46 52 / 22%); }
.drawer-header { display: flex; flex: none; justify-content: space-between; align-items: center; padding: 20px 22px; border-bottom: 1px solid #d5dadd; }
.drawer-header h2 { margin: 6px 0 0; font: var(--type-section); }
.drawer-header h2 span { color: var(--muted); font-size: 13px; font-weight: 400; margin-left: 6px; }
.drawer-close, .return-citation { border: 1px solid #cfd5dc; border-radius: 5px; padding: 7px 10px; background: transparent; color: #4c5968; font: inherit; font-size: 13px; cursor: pointer; }
kbd { margin-left: 5px; color: var(--muted); font-size: 12px; }
.drawer-content { overflow: auto; padding: 22px; flex: 1; }
.source-picker { display: grid; gap: 8px; color: var(--muted); font-size: 13px; margin-bottom: 20px; }
.source-picker select { width: 100%; min-width: 0; border: 1px solid #d1d7dc; background: #f9fafb; border-radius: 5px; padding: 9px 8px; font: var(--type-code); color: #46566a; }
.source-id { display: block; font: var(--type-code); margin-top: 10px; }
.source-note { font-size: 13px; line-height: 1.8; color: var(--muted); margin-bottom: 22px; }
.tool-tabs { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 14px; }
.tool-tabs button { border: 1px solid #d5dce2; border-radius: 5px; background: transparent; color: #697583; padding: 7px 8px; font: var(--type-code); cursor: pointer; }
.tool-tabs button[aria-pressed="true"] { background: #e0e6ec; color: #3e5065; border-color: #c5cfd9; }
.tool-evidence { background: #fafbfc; border: 1px solid #dce1e5; border-radius: 6px; margin: 12px 0; overflow: hidden; }
.tool-heading { display: flex; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid #e1e5e9; font: var(--type-code); }
.tool-heading strong { font-weight: 500; }.tool-heading span { color: var(--muted); font-family: inherit; }
.evidence-fields { margin: 0; padding: 4px 12px 12px; font-size: 13px; }
.evidence-fields dt { margin-top: 10px; }.evidence-fields dd { margin-top: 4px; color: #3e4d5f; }
.raw-evidence { border-block: 1px solid #d9dfe4; padding: 12px 0; margin-top: 22px; font-size: 13px; }
.digest-block { display: grid; gap: 10px; padding: 20px 0; }.digest-block code { font: 400 12px/20px var(--font-code); color: #78818c; }
pre { max-height: 380px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: var(--type-code); }
summary { cursor: pointer; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.selected:focus { outline: none; }
@media (max-width: 860px) { .evidence-drawer { inset: 0 0 0 auto; height: 100dvh; width: min(480px, 100vw); } }
@media (max-width: 600px) { .assertions { grid-template-columns: minmax(0, 1fr); }.assertions dt { border-bottom: 0; padding-bottom: 0; }.assertions dd { padding-top: 3px; } .report-nav { gap: 16px; }.report-nav button { font-size: 13px; }.fact { padding: 16px; } }
</style>
<style>
@media (min-width: 1101px) { body:has(.evidence-drawer[open]) .page-container { width: calc(100% - 460px); margin-right: 460px; padding-inline: 28px; } }
</style>
