<script setup lang="ts">
import { copy as c } from '@/composables/visualLocale'
import PageState from '@/components/PageState.vue'
import { onMounted, ref } from 'vue'

import { analystApi } from '@/api/analyst'
import TechnicalDetails from '@/components/TechnicalDetails.vue'
import { experimentOption } from '@/utils/displayIdentity'
import StatusBadge from '@/components/StatusBadge.vue'
import { useExperimentStore } from '@/stores/experiments'

const store = useExperimentStore()
const publicReadOnly = ref<boolean | null>(null)
onMounted(() => {
  void store.fetchList()
  void analystApi.capabilities().then(value => { publicReadOnly.value = value.public_demo_read_only }).catch(() => { publicReadOnly.value = null })
})
</script>

<template>
  <section class="experiments-page experiment-list evidence-page">
    <div class="page-heading">
      <div><h2>{{ c('实验与运行', 'Experiments') }}</h2><p>{{ c('浏览已保存实验与任务结果，来源和运行状态分别标注。', 'Browse saved experiment plans and verified outcomes. Fixture runs are labeled separately from Provider execution records.') }}</p></div>
      <div class="toolbar">
        <RouterLink v-if="publicReadOnly === false" class="secondary-button" to="/experiments/new">{{ c('新建离线计划', 'New keyless plan') }}</RouterLink>
        <input v-model="store.search" :aria-label="c('搜索实验', 'Search experiments')" :placeholder="c('搜索 ID 或名称', 'Search id or name')" @keyup.enter="store.fetchList" />
        <select v-model="store.statusFilter" :aria-label="c('按运行状态筛选', 'Filter by status')" @change="store.fetchList">
          <option value="">{{ c('全部状态', 'All statuses') }}</option><option value="queued">{{ c('等待运行', 'queued') }}</option><option value="running">{{ c('运行中', 'running') }}</option><option value="completed">{{ c('已结束', 'completed') }}</option>
        </select>
        <button class="primary-button" @click="store.fetchList">{{ c('查询', 'Refresh') }}</button>
      </div>
    </div>
    <p class="boundary-note">{{ c('已收集任务结果为通过与未通过之和；基础设施失败另计，不代表任务通过。', 'Collected task results are passes plus failures; infrastructure failures are counted separately.') }}</p>
    <div class="panel">
      <PageState v-if="store.loading" kind="loading">{{ c('正在读取已保存实验…', 'Loading persisted experiments…') }}</PageState>
      <PageState v-else-if="store.error" kind="error">{{ c('实验证据暂不可用，请稍后重试。', 'Experiment evidence is unavailable. Retry later.') }}<button class="secondary-button" @click="store.fetchList">{{ c('重试', 'Retry') }}</button></PageState>
      <PageState v-else-if="!store.items.length" kind="empty">{{ c('没有符合当前筛选条件的实验。', 'No experiments match the current filters.') }}</PageState>
      <div v-else class="responsive-table" role="region" :aria-label="c('实验列表', 'Experiments')" tabindex="0"><table class="data-table">
        <thead><tr><th>{{ c('实验', 'Experiment') }}</th><th>{{ c('来源', 'Source') }}</th><th>{{ c('运行状态', 'Status') }}</th><th>{{ c('任务 × 配置', 'Dimensions') }}</th><th>{{ c('已收集任务结果 / 计划', 'Collected task results / planned') }}</th><th>{{ c('通过', 'Passed') }}</th><th>{{ c('未通过', 'Failed') }}</th><th>{{ c('基础设施失败', 'Infrastructure failures') }}</th></tr></thead>
        <tbody>
          <tr v-for="item in store.items" :key="item.experiment_id">
            <td><RouterLink class="table-link" :to="`/experiments/${item.experiment_id}`">{{ experimentOption(item, store.items) }}</RouterLink><TechnicalDetails :fields="[{ label: 'Experiment ID', value: item.experiment_id }, { label: c('原始名称', 'Original name'), value: item.name }, { label: c('实验运行状态', 'Experiment lifecycle'), value: item.status }, { label: c('来源', 'Provenance'), value: item.provenance }, { label: 'SHA256', value: item.plan_digest }, { label: c('生成时间', 'Created at'), value: item.created_at }]" /><strong v-if="item.integrity_status === 'INTEGRITY_FAILED'" class="error-message">{{ c('历史证据完整性校验失败', 'Historical evidence — artifact integrity failed') }}</strong></td>
            <td><StatusBadge :value="item.provenance ?? 'UNVERIFIED_SOURCE'" localized /></td>
            <td><StatusBadge :value="item.status" context="experiment" localized /></td>

            <td>{{ item.task_count }} × {{ item.cell_count }}</td>
            <td>{{ item.completed_capability_count ?? c('未报告', 'Not reported') }} / {{ item.planned_run_count ?? c('未报告', 'Not reported') }}</td>
            <td>{{ store.outcomeCounts[item.experiment_id]?.passed ?? c('未报告', 'Not reported') }}</td><td>{{ store.outcomeCounts[item.experiment_id]?.failed ?? c('未报告', 'Not reported') }}</td><td>{{ item.infra_count ?? c('未报告', 'Not reported') }}</td>
          </tr>
        </tbody>
      </table></div>
      <div v-if="!store.loading && !store.error && store.items.length" class="list-pagination"><span>{{ c('已显示', 'Showing') }} {{ store.items.length }} / {{ store.total }}</span><button v-if="store.items.length < store.total" class="secondary-button" :disabled="store.moreLoading" @click="store.loadMore">{{ store.moreLoading ? c('读取中…', 'Loading…') : c('加载更多实验', 'Load more experiments') }}</button></div>
    </div>
  </section>
</template>
