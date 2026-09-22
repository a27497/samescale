<script setup lang="ts">
import { computed, inject, onMounted, ref } from 'vue'
import { registryApi } from '@/api/client'
import { t } from '@/composables/i18n'
import { productModeKey } from '@/composables/productContext'
import type { TaskRegistryItem } from '@/types/registry'

const mode = inject(productModeKey, ref('unknown'))
const tasks = ref<TaskRegistryItem[]>([])
const loading = ref(true)
const error = ref(false)
const search = ref('')
const filteredTasks = computed(() => tasks.value.filter(task =>
  `${task.task_id} ${task.task_version} ${task.tier}`.toLowerCase().includes(search.value.trim().toLowerCase())))
async function load() {
  loading.value = true; error.value = false; tasks.value = []
  try { tasks.value = (await registryApi.tasks()).items }
  catch { error.value = true }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h2>{{ t('任务集') }}</h2><p>{{ t('查看任务范围，再选择模型与执行方式。') }}</p></div>
      <RouterLink v-if="mode === 'workspace'" class="primary-button" to="/experiments/new">{{ t('创建评测计划') }}</RouterLink>
    </div>
    <p class="notice">{{ t('这里展示服务端注册的任务，供评测规划使用。小型契约任务的结果不能代表通用工程能力；注册任务不等于已经完成评测。') }}</p>
    <p v-if="loading" class="loading-state" role="status">{{ t('正在读取任务集…') }}</p>
    <div v-else-if="error" class="error-state" role="alert">
      <p>{{ t('无法读取任务集，请检查服务后重试。') }}</p><button class="secondary-button" @click="load">{{ t('重新加载') }}</button>
    </div>
    <p v-else-if="!tasks.length" class="empty-state">{{ t('当前没有已注册任务。') }}</p>
    <template v-else>
      <div class="toolbar task-search"><label for="task-search">{{ t('查找任务') }}</label><input id="task-search" v-model="search" type="search" :placeholder="t('按任务标识、版本或类别筛选')" /></div>
      <p class="muted" role="status">{{ t('匹配任务数：') }}{{ filteredTasks.length }} / {{ tasks.length }}</p>
      <p v-if="!filteredTasks.length" class="empty-state">{{ t('没有匹配的任务。请调整筛选条件。') }}</p>
      <article v-for="task in filteredTasks" :key="task.task_id" class="panel task-card">
        <div class="panel-title"><h3 class="technical">{{ task.task_id }}</h3><span class="metadata-chip">{{ t('版本') }} {{ task.task_version }}</span></div>
        <p>{{ task.tier === 'TIER_A_MICRO_CONTRACT' ? t('小型契约任务：验证明确输入与输出要求。') : task.tier }}</p>
        <details><summary>{{ t('任务身份与来源') }}</summary><dl class="definition-list">
          <dt>{{ t('任务类别') }}</dt><dd class="technical">{{ task.tier }}</dd>
          <dt>{{ t('任务摘要') }}</dt><dd class="technical">{{ task.task_digest }}</dd>
          <dt>{{ t('任务包') }}</dt><dd class="technical">{{ task.package_path }}</dd>
        </dl></details>
      </article>
    </template>
  </section>
</template>

<style scoped>
.task-search { flex-wrap: wrap; margin-top: 24px; }
.task-search input { min-width: 0; flex: 1; }
.task-card p { color: var(--muted); }
.task-card summary { cursor: pointer; color: var(--link); }
.task-card details { margin-top: 12px; }
.task-card .definition-list { margin-bottom: 0; }
</style>
