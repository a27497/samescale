<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { registryApi } from '@/api/client'
import { t } from '@/composables/i18n'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ExperimentSnapshot, ExperimentSnapshotSummary } from '@/types/registry'

const route = useRoute()
const items = ref<ExperimentSnapshotSummary[]>([])
const total = ref(0)
const offset = ref(0)
const limit = ref(25)
const loading = ref(false)
const error = ref(false)
const selected = ref<ExperimentSnapshot | null>(null)
const reading = ref(false)
const detailError = ref(false)
let listGeneration = 0
let detailGeneration = 0
async function load(page = offset.value) {
  const generation = ++listGeneration
  loading.value = true; error.value = false; items.value = []; total.value = 0
  try {
    const result = await registryApi.snapshots(page)
    if (generation !== listGeneration) return
    items.value = result.items; total.value = result.total; offset.value = result.offset; limit.value = result.limit
  } catch { if (generation === listGeneration) error.value = true }
  finally { if (generation === listGeneration) loading.value = false }
}
async function read() {
  const generation = ++detailGeneration
  selected.value = null; detailError.value = false; reading.value = false
  const id = route?.query.snapshot
  if (typeof id !== 'string' || !id) return
  reading.value = true
  try {
    const result = await registryApi.getSnapshot(id)
    if (generation !== detailGeneration) return
    if (result.snapshot_id !== id) throw new Error('Snapshot identity mismatch')
    selected.value = result
  } catch { if (generation === detailGeneration) detailError.value = true }
  finally { if (generation === detailGeneration) reading.value = false }
}
onMounted(() => void load())
watch(() => route?.query.snapshot, read, { immediate: true })
onBeforeUnmount(() => { listGeneration++; detailGeneration++ })
</script>

<template>
  <section id="saved-plans" class="panel saved-plans" :aria-label="t('已保存计划')">
    <div class="panel-title"><h3>{{ t('已保存计划') }}</h3><button class="secondary-button" :disabled="loading" @click="load()">{{ t('重新读取计划') }}</button></div>
    <p>{{ t('不可变规划快照，与已执行实验分开保存。打开或刷新不会执行评测，也不会重新预检。') }}</p>
    <p v-if="loading" role="status">{{ t('正在读取已保存计划…') }}</p>
    <p v-else-if="error" role="alert">{{ t('无法读取已保存计划，请重试。') }}</p>
    <p v-else-if="!items.length">{{ t('尚无已保存计划。') }}</p>
    <ul v-else class="plan-list">
      <li v-for="item in items" :key="item.snapshot_id">
        <RouterLink class="table-link" :to="{ path: '/experiments', query: { snapshot: item.snapshot_id }, hash: '#saved-plans' }">{{ item.name }}</RouterLink>
        <code>{{ item.snapshot_id }}</code><span>{{ t('保存时间') }} · {{ item.created_at }}</span>
      </li>
    </ul>
    <div v-if="!loading && !error && total > limit" class="toolbar">
      <button class="secondary-button" :disabled="offset === 0" @click="load(Math.max(0, offset - limit))">{{ t('上一页计划') }}</button>
      <span>{{ offset + 1 }}–{{ offset + items.length }} / {{ total }}</span>
      <button class="secondary-button" :disabled="offset + items.length >= total" @click="load(offset + limit)">{{ t('下一页计划') }}</button>
    </div>
    <div v-if="route?.query.snapshot" class="saved-plan-detail">
      <RouterLink class="table-link" to="/experiments#saved-plans">{{ t('关闭计划详情') }}</RouterLink>
      <p v-if="reading" role="status">{{ t('正在读取计划…') }}</p>
      <template v-else-if="detailError"><p role="alert">{{ t('无法读取或校验此计划。请核对链接或重试。') }}</p><button class="secondary-button" @click="read">{{ t('重新读取此计划') }}</button></template>
      <article v-else-if="selected" :aria-label="t('完整计划（只读）')">
        <h4>{{ selected.plan.name }}</h4>
        <code>{{ selected.snapshot_id }}</code><code>{{ selected.snapshot_digest }}</code>
        <p>{{ t('保存时的预检状态；不是当前连接健康或执行授权。') }}</p>
        <StatusBadge :value="selected.preflight.status" />
        <p>{{ selected.plan.evaluation_mode }} · {{ selected.comparison_type }}</p>
        <details><summary>{{ t('完整计划（只读）') }}</summary><pre>{{ JSON.stringify(selected, null, 2) }}</pre></details>
      </article>
    </div>
  </section>
</template>

<style scoped>
.saved-plans { margin-top:24px; scroll-margin-top:80px; overflow-wrap:anywhere; }
.plan-list { list-style:none; padding:0; }.plan-list li { padding:12px 0; border-bottom:1px solid var(--line); }
.saved-plans code, .plan-list span { display:block; color:var(--muted); font-size:12px; }
.saved-plan-detail { margin-top:20px; border-top:1px solid var(--line); padding-top:16px; }
.saved-plans pre { white-space:pre-wrap; overflow-wrap:anywhere; font-size:12px; }
</style>
