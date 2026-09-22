<script setup lang="ts">
import { inject, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { t } from '@/composables/i18n'
import { preferences } from '@/composables/preferences'
import { productModeKey } from '@/composables/productContext'
import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import BrandMark from '@/components/BrandMark.vue'
import type { ExperimentSummary } from '@/types/workbench'

const router = useRouter()
const productMode = inject(productModeKey, ref('unknown'))
const comparison = ref(window.history.state?.evaluationComparison === 'HARNESS_UPLIFT' ? 'HARNESS_UPLIFT' : 'MODEL_COMPARISON')
const recent = ref<ExperimentSummary[]>([])
const error = ref(false)
const loading = ref(false)
let generation = 0
onBeforeUnmount(() => { generation++ })
async function loadRecent() {
  const current = ++generation
  recent.value = []; error.value = false; loading.value = false
  if (productMode.value !== 'workspace') return
  loading.value = true
  try {
    const result = await workbenchApi.listExperiments({ limit: 3 })
    if (current === generation) recent.value = result.items.slice(0, 3)
  } catch { if (current === generation) error.value = true }
  finally { if (current === generation) loading.value = false }
}
watch(productMode, loadRecent, { immediate: true })
function next() {
  if (productMode.value !== 'workspace') return
  window.history.replaceState({ ...window.history.state, evaluationComparison: comparison.value }, '')
  void router.push({ path: '/experiments/new', query: { comparison: comparison.value } })
}
function dateLabel(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString(preferences.language, { month: 'short', day: 'numeric' })
}
</script>

<template>
  <section class="evaluation-home">
    <BrandMark class="home-brand-mark" />
    <h1>{{ t(productMode === 'workspace' ? '规划一次评测' : productMode === 'demo' ? '查看评测案例' : '首页') }}</h1>
    <form v-if="productMode === 'workspace'" class="evaluation-choice" @submit.prevent="next">
      <fieldset>
        <legend class="sr-only">{{ t('比较对象') }}</legend>
        <label :class="{ selected: comparison === 'MODEL_COMPARISON' }"><input v-model="comparison" type="radio" name="comparison" value="MODEL_COMPARISON">{{ t('比较模型') }}</label>
        <label :class="{ selected: comparison === 'HARNESS_UPLIFT' }"><input v-model="comparison" type="radio" name="comparison" value="HARNESS_UPLIFT">{{ t('直接调用 vs Agent') }}</label>
      </fieldset>
      <button type="submit" class="primary-button evaluation-start">{{ t('创建计划') }}<span aria-hidden="true">→</span></button>
    </form>
    <RouterLink v-if="productMode === 'demo'" class="primary-button home-comparison-link" to="/examples?example=comparison">{{ t('查看比较案例') }}<span aria-hidden="true">→</span></RouterLink>
    <RouterLink class="home-example-link" to="/examples">{{ t(productMode === 'demo' ? '其他示例' : '查看示例') }}<span aria-hidden="true">↗</span></RouterLink>
    <section v-if="recent.length" class="recent-records" :aria-label="t('最近记录')">
      <header><h2>{{ t('最近记录') }}</h2><RouterLink to="/experiments">{{ t('全部记录') }}</RouterLink></header>
      <ul><li v-for="item in recent" :key="item.experiment_id">
        <RouterLink :to="`/experiments/${encodeURIComponent(item.experiment_id)}`" :title="item.name">{{ item.name }}</RouterLink>
        <StatusBadge :value="item.status" />
        <time :datetime="item.created_at" :title="item.created_at">{{ dateLabel(item.created_at) }}</time>
      </li></ul>
    </section>
    <p v-else-if="error" role="alert" class="recent-error">{{ t('最近记录加载失败。') }} <button @click="loadRecent">{{ t('重试') }}</button></p>
    <span v-else-if="loading" role="status" class="sr-only">{{ t('正在读取最近记录…') }}</span>
  </section>
</template>

<style scoped>
.evaluation-home { width: 100%; max-width: 640px; margin: 0 auto; padding-top: clamp(40px, 21vh, 240px); padding-bottom: 40px; }
.home-brand-mark { width: 64px; height: 64px; margin: 0 auto 24px; }
h1 { font: 500 30px/1.4 var(--font-ui); text-align: center; margin: 0 0 32px; }
.evaluation-choice { display: flex; align-items: center; gap: 20px; padding: 14px; border: 1px solid var(--line); border-radius: 16px; box-shadow: 0 3px 12px #10182005; }
fieldset { display: flex; flex: 1; gap: 4px; border: 0; margin: 0; padding: 0; min-width: 0; }
label { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px 14px; border-radius: 9px; cursor: pointer; color: var(--muted); }
label.selected { background: var(--hover); color: var(--ink); }
input { margin: 0; accent-color: var(--ink); }
.evaluation-start { gap: 18px; min-height: 44px; flex-shrink: 0; border-radius: 9px; }
.home-comparison-link { display: flex; align-items: center; justify-content: center; gap: 18px; width: fit-content; max-width: 100%; min-height: 44px; margin: 0 auto; padding: 12px 20px; border-radius: 9px; text-decoration: none; }
.home-example-link { display: flex; align-items: center; gap: 6px; width: fit-content; margin: 20px auto 0; color: var(--muted); text-decoration: none; font: var(--type-caption); padding: 8px; }
a:hover { text-decoration: underline; text-underline-offset: 4px; }
.recent-records { margin-top: 56px; }
.recent-records header { display: flex; align-items: center; justify-content: space-between; color: var(--muted); font: var(--type-caption); }
h2 { margin: 0; font: inherit; }header a { text-decoration: none; }
ul { list-style: none; margin: 12px 0 0; padding: 0; }
li { display: flex; gap: 16px; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--line); }
li > a { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-decoration: none; }
time { font: var(--type-caption); color: var(--muted); white-space: nowrap; }
.recent-error { margin-top: 40px; color: var(--muted); font: var(--type-caption); text-align: center; }.recent-error button { border: 0; background: transparent; color: var(--link); cursor: pointer; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
@media (max-width: 600px) { .evaluation-home { padding-top: 9vh; }.home-brand-mark { width: 56px; height: 56px; margin-bottom: 20px; }h1 { font-size: 26px; }.evaluation-choice { flex-direction: column; align-items: stretch; gap: 12px; }fieldset { justify-content: center; }label { flex: 1; padding: 12px 6px; }.recent-records { margin-top: 36px; }li { gap: 8px; } }
</style>
