<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { workbenchApi } from '@/api/client'
import { statusLabel } from '@/composables/labels'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ExperimentStatus, ExperimentSummary, RunSummary } from '@/types/workbench'

type OutcomeClass = 'CAPABILITY_TERMINAL' | 'INFRASTRUCTURE' | 'LIFECYCLE'

const route = useRoute()
const router = useRouter()
const experiments = ref<ExperimentSummary[]>([])
const selectedExperimentId = ref('')
const status = ref<ExperimentStatus | null>(null)
const runs = ref<RunSummary[]>([])
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const filter = ref<'ALL' | OutcomeClass>('ALL')

function outcomeClass(run: RunSummary): OutcomeClass {
  const outcome = (run.normalized_outcome ?? '').toLowerCase()
  if (outcome === 'infra_failure') return 'INFRASTRUCTURE'
  if (outcome === 'capability_pass' || outcome === 'capability_fail') return 'CAPABILITY_TERMINAL'
  return 'LIFECYCLE'
}

const visibleRuns = computed(() =>
  runs.value.filter((run) => filter.value === 'ALL' || outcomeClass(run) === filter.value),
)
const infrastructureCount = computed(() =>
  runs.value.filter((run) => outcomeClass(run) === 'INFRASTRUCTURE').length,
)
const capabilityCount = computed(() =>
  runs.value.filter((run) => outcomeClass(run) === 'CAPABILITY_TERMINAL').length,
)
const selectedIsListed = computed(() =>
  experiments.value.some((item) => item.experiment_id === selectedExperimentId.value),
)

function controlLabel(run: RunSummary) {
  const classification = outcomeClass(run)
  if (classification === 'INFRASTRUCTURE') return '待审阅恢复'
  if (classification === 'CAPABILITY_TERMINAL') return '终态'
  return '查看状态'
}

let generation = 0
onBeforeUnmount(() => { generation++ })
async function loadSelected(syncRoute = true) {
  const ownGeneration = ++generation
  const requestedId = selectedExperimentId.value
  status.value = null; runs.value = []
  if (!selectedExperimentId.value) {
    refreshing.value = false
    status.value = null
    runs.value = []
    return
  }
  refreshing.value = true
  error.value = ''
  try {
    const [statusResponse, runResponse] = await Promise.all([
      workbenchApi.getStatus(requestedId),
      workbenchApi.getRuns(requestedId, { limit: 100 }),
    ])
    if (ownGeneration !== generation) return
    status.value = statusResponse
    runs.value = runResponse.items
    if (syncRoute && route.query.experiment !== selectedExperimentId.value) {
      await router.replace({ query: { ...route.query, experiment: selectedExperimentId.value } })
    }
  } catch {
    if (ownGeneration !== generation) return
    error.value = '无法读取运行状态，请检查服务后刷新。'
  } finally {
    if (ownGeneration === generation) refreshing.value = false
  }
}

async function load() {
  loading.value = true; error.value = ''
  try {
    const response = await workbenchApi.listExperiments({ limit: 100 })
    experiments.value = response.items
    const requested = typeof route.query.experiment === 'string' ? route.query.experiment : ''
    selectedExperimentId.value = requested || response.items[0]?.experiment_id || ''
    await loadSelected(Boolean(selectedExperimentId.value))
  } catch {
    error.value = '无法读取实验列表，请确认本地数据库与 API 已启动。'
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(() => route.query.experiment, value => {
  if (typeof value === 'string' && value !== selectedExperimentId.value) { selectedExperimentId.value = value; void loadSelected(false) }
})
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <h2>{{ t('运行记录') }}</h2>
        <p>{{ t('查看已保存的运行状态与恢复边界。能力结果不在此重试。') }}</p>
      </div>
      <StatusBadge :value="status?.terminal ? 'DURABLE TERMINAL' : status?.status ?? 'NOT_REPORTED'" />
    </div>

    <div class="control-banner">
      <span class="control-banner-mark">RC</span>
      <div><strong>{{ t('以已保存状态为准') }}</strong><p>{{ t('打开或刷新只读取运行记录，不触发模型请求。') }}</p></div>
      <span class="status-pill neutral">{{ t('只读查看') }}</span>
    </div>

    <div v-if="loading" class="loading-state">{{ t('正在读取运行状态…') }}</div>
    <template v-else>
      <div class="run-control-toolbar panel">
        <label>
          <span>{{ t('实验') }}</span>
          <select v-model="selectedExperimentId" :aria-label="t('选择运行记录所属实验')" @change="loadSelected()">
            <option v-if="!experiments.length" value="">{{ t('尚无实验') }}</option>
            <option v-else-if="selectedExperimentId && !selectedIsListed" :value="selectedExperimentId">{{ selectedExperimentId }} {{ t('· 直接访问') }}</option>
            <option v-for="item in experiments" :key="item.experiment_id" :value="item.experiment_id">
              {{ item.name }} · {{ item.experiment_id }}
            </option>
          </select>
        </label>
        <button class="secondary-button" :disabled="refreshing || !selectedExperimentId" @click="loadSelected(false)">
          {{ refreshing ? t('正在刷新…') : t('刷新运行状态') }}
        </button>
        <RouterLink v-if="selectedExperimentId" class="table-link" :to="`/experiments/${selectedExperimentId}`">{{ t('查看实验证据 →') }}</RouterLink>
      </div>

      <div v-if="error" role="alert" class="error-state"><p>{{ t(error) }}</p><button class="secondary-button" :disabled="refreshing" @click="load">{{ t('重新加载实验与记录') }}</button></div>
      <template v-else-if="selectedExperimentId">
        <div class="metric-grid">
          <div class="metric-card accent"><div class="label">{{ t('运行状态') }}</div><div class="value compact-value">{{ statusLabel(status?.status ?? 'NOT_REPORTED') }}</div><div class="detail">{{ status?.terminal ? t('已保存的终态') : t('状态仍可能变化') }}</div></div>
          <div class="metric-card"><div class="label">{{ t('已记录运行') }}</div><div class="value">{{ runs.length }}</div><div class="detail">{{ t('最多显示前 100 条逻辑运行') }}</div></div>
          <div class="metric-card"><div class="label">{{ t('能力结果已完成') }}</div><div class="value">{{ capabilityCount }}</div><div class="detail">{{ t('不重试以改写能力结果') }}</div></div>
          <div class="metric-card"><div class="label">{{ t('基础设施') }}</div><div class="value">{{ infrastructureCount }}</div><div class="detail">{{ t('需要按范围审阅恢复方案') }}</div></div>
        </div>

        <div class="recovery-policy-grid">
          <article class="policy-card terminal-policy">
            <span class="policy-icon">✓</span>
            <div><span class="panel-kicker">{{ t('结果边界') }}</span><h3>{{ t('保留原始能力结果') }}</h3><p>{{ t('保留原始判定。重跑或更换模型、服务、路由、运行配置，都不能改写原成绩。') }}</p></div>
          </article>
          <article class="policy-card recovery-policy">
            <span class="policy-icon">↻</span>
            <div><span class="panel-kicker">{{ t('恢复边界') }}</span><h3>{{ t('按运行槽位审阅基础设施恢复') }}</h3><p>{{ t('恢复需保留冻结的方法与实验条件，并使用已授权的执行路径。') }}</p></div>
          </article>
        </div>

        <div class="panel">
          <div class="panel-title run-list-heading">
            <div><span class="panel-kicker">{{ t('逻辑运行') }}</span><h3>{{ t('运行清单') }}</h3></div>
            <div class="segmented-control" :aria-label="t('筛选运行类别')">
              <button v-for="value in ['ALL', 'CAPABILITY_TERMINAL', 'INFRASTRUCTURE', 'LIFECYCLE'] as const" :key="value" :class="{ active: filter === value }" :aria-pressed="filter === value" @click="filter = value">{{ { ALL: t('全部'), CAPABILITY_TERMINAL: t('能力结果'), INFRASTRUCTURE: t('基础设施'), LIFECYCLE: t('运行状态') }[value] }}</button>
            </div>
          </div>
          <div v-if="!visibleRuns.length" class="empty-state">{{ t('该类别下暂无运行记录。') }}</div>
          <div v-else class="responsive-table">
            <table class="data-table run-control-table">
              <thead><tr><th>{{ t('运行标识') }}</th><th>{{ t('运行槽位') }}</th><th>{{ t('状态 / 结果') }}</th><th>{{ t('操作边界') }}</th><th>{{ t('证据') }}</th></tr></thead>
              <tbody>
                <tr v-for="run in visibleRuns" :key="run.run_id">
                  <td><strong class="technical">{{ run.run_id }}</strong><div class="muted">{{ t('尝试') }} {{ run.attempt }}</div></td>
                  <td>{{ run.cell_id }} · {{ run.task_id }}<div class="technical muted">{{ t('重复=') }}{{ run.repeat_index }} {{ t('· 分组=') }}{{ run.lane }}</div></td>
                  <td><StatusBadge :value="run.status" /> <StatusBadge :value="run.normalized_outcome ?? 'NOT_REPORTED'" /></td>
                  <td><span class="status-pill" :class="outcomeClass(run) === 'INFRASTRUCTURE' ? 'warn' : 'neutral'">{{ t(controlLabel(run)) }}</span><div class="boundary-note">{{ outcomeClass(run) === 'INFRASTRUCTURE' ? t('保留原实验条件，审阅具体恢复方案。') : outcomeClass(run) === 'CAPABILITY_TERMINAL' ? t('结果已记录，不通过重试改写能力证据。') : t('查看服务端运行状态。') }}</div></td>
                  <td><RouterLink class="table-link" :to="`/runs/${run.run_id}`">{{ t('查看证据与轨迹 →') }}</RouterLink></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
      <div v-else class="empty-state">{{ t('尚无可查看运行记录的实验。') }}</div>
    </template>
  </section>
</template>
