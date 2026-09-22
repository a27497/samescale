<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, inject, ref, watch } from 'vue'
import { routerKey } from 'vue-router'
const props = defineProps<{ kind: 'models' | 'harnesses' | 'providers'; items: { id: string; name: string; description: string; group?: string }[] }>()
const router = inject(routerKey, null)
const search = ref('')
const localId = ref('')
const visible = computed(() => props.items.filter(item => `${item.name} ${item.id} ${item.description}`.toLowerCase().includes(search.value.trim().toLowerCase())))
const groups = computed(() => [...new Set(props.items.map(item => item.group ?? ''))].map(label => ({
  label, items: visible.value.filter(item => (item.group ?? '') === label),
})).filter(group => group.items.length))
const selectedId = computed(() => {
  const id = router ? router.currentRoute.value.query.id : localId.value
  if (id) return visible.value.some(item => item.id === id) ? String(id) : ''
  return visible.value[0]?.id ?? ''
})
function select(id: string) {
  localId.value = id
  if (router) void router.push({ query: { ...router.currentRoute.value.query, id } })
}
watch(() => props.kind, () => { search.value = ''; localId.value = '' })
</script>
<template>
  <section class="resource-manager">
    <div class="page-heading"><div><h2>{{ t(kind === 'models' ? '模型配置' : kind === 'providers' ? '模型服务' : '编程 Agent 运行时') }}</h2><p><RouterLink to="/connections">{{ t('连接总览') }}</RouterLink></p></div><span class="status-pill neutral">{{ t('只读') }}</span></div>
    <details v-if="kind === 'harnesses'" class="resource-disclosure"><summary>{{ t('术语') }}</summary><p>{{ t('Agent 运行时（Harness）') }}：{{ t('负责模型调用、工具执行和任务循环。') }} {{ t('直接调用作为比较基线单列。') }}</p></details>
    <div class="resource-workspace">
      <aside class="resource-browser" :aria-label="t('资源列表')">
        <input v-model="search" type="search" :aria-label="t('搜索资源')" :placeholder="t('搜索名称或配置 ID')" />
        <div class="resource-count">{{ visible.length }} / {{ items.length }}</div>
        <div class="resource-list"><section v-for="group in groups" :key="group.label" :data-resource-group="group.label"><h3 v-if="group.label" class="resource-group-label">{{ t(group.label) }}</h3><button v-for="item in group.items" :key="item.id" :aria-pressed="selectedId === item.id" @click="select(item.id)"><strong>{{ item.name }}</strong><small>{{ item.description }}</small><code>{{ item.id }}</code></button></section></div>
        <p v-if="!visible.length" class="empty-state">{{ t('没有符合条件的资源。') }}</p>
      </aside>
      <div class="resource-detail" aria-live="polite"><slot v-if="selectedId" :selected-id="selectedId" /><p v-else class="empty-state">{{ t('未找到所选资源，请在列表中重新选择。') }}</p></div>
    </div>
  </section>
</template>
<style scoped>
.resource-group-label { margin: 18px 0 8px; color: var(--muted); font: var(--type-caption); }
.resource-list section { display: grid; gap: 8px; min-width: 0; }
</style>
