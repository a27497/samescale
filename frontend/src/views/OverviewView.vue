<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, onMounted, ref } from 'vue'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { CoreReadiness, ExperimentSummary } from '@/types/workbench'

const readiness = ref<CoreReadiness | null>(null)
const experiments = ref<ExperimentSummary[]>([])
const loading = ref(true)
const error = ref(false)
const listUnavailable = ref(false)
const readinessUnavailable = ref(false)

const activeExperiments = computed(() =>
  experiments.value.filter((item) => !['completed', 'failed', 'cancelled'].includes(item.status)).length,
)
const infrastructureEvents = computed(() =>
  experiments.value.reduce((total, item) => total + item.infra_count, 0),
)

async function load() {
  loading.value = true; error.value = false; readiness.value = null; experiments.value = []
  const [ready, list] = await Promise.allSettled([
    workbenchApi.readiness(),
    workbenchApi.listExperiments({ limit: 5 }),
  ])
  readinessUnavailable.value = ready.status === 'rejected'
  listUnavailable.value = list.status === 'rejected'
  if (ready.status === 'fulfilled') readiness.value = ready.value
  if (list.status === 'fulfilled') experiments.value = list.value.items
  error.value = ready.status === 'rejected' && list.status === 'rejected'
  loading.value = false
}
onMounted(load)
</script>

<template>
  <section>
    <div class="hero-panel">
      <div>
        <span class="eyebrow">{{ t('评测工作区') }}</span>
        <h2>{{ t('规划实验，核对运行证据') }}</h2>
        <p>
          {{ t('选择模型与执行方式，规划实验并查看结果。') }}
        </p>
        <div class="hero-actions">
          <RouterLink class="primary-button" to="/experiments/new">{{ t('创建评测计划') }}</RouterLink>
          <RouterLink class="secondary-button" to="/run-control">{{ t('查看运行记录') }}</RouterLink>
        </div>
      </div>
      <div class="hero-readiness">
        <span class="label">{{ t('就绪状态') }}</span>
        <StatusBadge :value="readiness?.status ?? 'NOT_REPORTED'" />
        <strong>{{ readiness?.blockers.length ?? '—' }}</strong>
        <small>{{ t('个阻断项') }}</small>
        <RouterLink to="/core-readiness">{{ t('查看检查结果 →') }}</RouterLink>
      </div>
    </div>

    <button v-if="!loading && (error || listUnavailable || readinessUnavailable)" class="secondary-button retry-button" @click="load">{{ t('重新加载') }}</button>
    <div v-if="loading" class="loading-state">{{ t('正在读取已保存证据…') }}</div>
    <div v-else-if="error" class="error-state">{{ t('暂时无法读取评测数据，请确认完整服务已启动。') }}</div>
    <template v-else>
      <p v-if="listUnavailable || readinessUnavailable" role="status" class="notice">{{ listUnavailable ? t('实验列表暂不可用；下方不将缺失数据记为零。') : t('就绪检查暂不可用；已加载的实验证据仍可查看。') }}</p>
      <div class="metric-grid overview-metrics">
        <div class="metric-card accent">
          <div class="label">{{ t('近期实验') }}</div><div class="value">{{ listUnavailable ? '—' : experiments.length }}</div>
          <div class="detail">{{ t('当前返回的最近一页') }}</div>
        </div>
        <div class="metric-card">
          <div class="label">{{ t('进行中') }}</div><div class="value">{{ listUnavailable ? '—' : activeExperiments }}</div>
          <div class="detail">{{ t('本页排队或运行中的实验') }}</div>
        </div>
        <div class="metric-card">
          <div class="label">{{ t('基础设施事件') }}</div><div class="value">{{ listUnavailable ? '—' : infrastructureEvents }}</div>
          <div class="detail">{{ t('与能力结果分别统计') }}</div>
        </div>
        <div class="metric-card">
          <div class="label">{{ t('任务集') }}</div><div class="value">{{ readiness?.task_corpus_size ?? '—' }}</div>
          <div class="detail">{{ t('以已保存记录为准') }}</div>
        </div>
      </div>

      <div class="overview-layout">
        <div class="panel">
          <div class="panel-title">
            <div><span class="panel-kicker">{{ t('最近记录') }}</span><h3>{{ t('实验证据') }}</h3></div>
            <RouterLink class="table-link" to="/experiments">{{ t('查看全部') }}</RouterLink>
          </div>
          <div v-if="listUnavailable" class="empty-state">{{ t('实验列表读取失败。') }}</div>
          <div v-else-if="!experiments.length" class="empty-state">{{ t('尚无已保存实验。') }}</div>
          <div v-else class="responsive-table">
            <table class="data-table">
              <thead><tr><th>{{ t('实验') }}</th><th>{{ t('状态') }}</th><th>{{ t('矩阵') }}</th><th>{{ t('能力完成 / 基础设施') }}</th></tr></thead>
              <tbody>
                <tr v-for="item in experiments" :key="item.experiment_id">
                  <td><RouterLink class="table-link technical" :to="`/experiments/${item.experiment_id}`">{{ item.experiment_id }}</RouterLink><br><span class="muted">{{ item.name }}</span></td>
                  <td><StatusBadge :value="item.status" /></td>
                  <td>{{ item.task_count }} {{ t('个任务 ×') }} {{ item.cell_count }} {{ t('个单元') }}</td>
                  <td>{{ item.completed_capability_count }} / {{ item.infra_count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <aside class="panel launchpad">
          <div class="panel-title"><div><span class="panel-kicker">{{ t('工具入口') }}</span><h3>{{ t('常用工具') }}</h3></div></div>
          <RouterLink to="/models"><span class="launch-mark">01</span><span><strong>{{ t('资源配置') }}</strong><small>{{ t('模型、服务、运行配置与兼容性') }}</small></span><b>→</b></RouterLink>
          <RouterLink to="/experiments/new"><span class="launch-mark">02</span><span><strong>{{ t('实验规划') }}</strong><small>{{ t('服务端预检，不执行实验') }}</small></span><b>→</b></RouterLink>
          <RouterLink to="/run-control"><span class="launch-mark">03</span><span><strong>{{ t('运行记录') }}</strong><small>{{ t('运行状态与恢复边界') }}</small></span><b>→</b></RouterLink>
          <RouterLink to="/diagnosis"><span class="launch-mark">04</span><span><strong>{{ t('失败诊断') }}</strong><small>{{ t('失败聚类与证据定位') }}</small></span><b>→</b></RouterLink>
        </aside>
      </div>
    </template>
  </section>
</template>
