<script setup lang="ts">
import { t } from '@/composables/i18n'
import { onMounted, onBeforeUnmount } from 'vue'

import SavedPlans from '@/components/SavedPlans.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useExperimentStore } from '@/stores/experiments'

const store = useExperimentStore()
onMounted(() => void store.fetchList())
onBeforeUnmount(() => { store.listGeneration++; store.loading = false })
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h2>{{ t('实验记录') }}</h2><p>{{ t('查看实验运行状态与结果；未执行的计划在下方单独列出。') }}</p></div>
      <div class="toolbar">
        <RouterLink class="primary-button" to="/experiments/new">{{ t('创建评测计划') }}</RouterLink>
        <input v-model="store.search" :aria-label="t('搜索实验')" :placeholder="t('搜索实验名称或 ID')" @keyup.enter="store.fetchList" />
        <select v-model="store.statusFilter" :aria-label="t('筛选实验状态')" @change="store.fetchList">
          <option value="">{{ t('全部状态') }}</option><option value="queued">{{ t('排队中') }}</option><option value="running">{{ t('运行中') }}</option><option value="completed">{{ t('已完成') }}</option><option value="failed">{{ t('失败') }}</option><option value="cancelled">{{ t('已取消') }}</option>
        </select>
        <button class="primary-button" @click="store.fetchList">{{ t('刷新') }}</button>
      </div>
    </div>
    <div class="panel">
      <div v-if="store.loading" class="loading-state">{{ t('正在读取实验列表…') }}</div>
      <div v-else-if="store.error" class="error-state">{{ store.error }}</div>
      <div v-else-if="!store.items.length" class="empty-state">{{ t('没有符合当前筛选条件的实验。') }}</div>
      <table v-else class="data-table">
        <thead><tr><th>{{ t('实验') }}</th><th>{{ t('状态') }}</th><th>{{ t('计划') }}</th><th>{{ t('维度') }}</th><th>{{ t('运行记录') }}</th><th>{{ t('基础设施') }}</th></tr></thead>
        <tbody>
          <tr v-for="item in store.items" :key="item.experiment_id">
            <td><RouterLink class="table-link" :to="`/experiments/${item.experiment_id}`">{{ item.name }}</RouterLink><div class="technical muted">{{ item.experiment_id }}</div></td>
            <td><StatusBadge :value="item.status" /></td>
            <td class="technical">{{ item.plan_digest.slice(0, 19) }}…</td>
            <td>{{ item.task_count }} × {{ item.cell_count }}</td>
            <td>{{ item.completed_capability_count }} / {{ item.planned_run_count }}</td>
            <td>{{ item.infra_count }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <SavedPlans />
  </section>
</template>
