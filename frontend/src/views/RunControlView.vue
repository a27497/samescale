<script setup lang="ts">
import { statusLabel } from '@/utils/statusLabels'
import PageState from '@/components/PageState.vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import { experimentOption, runName, taskName } from '@/utils/displayIdentity'
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
  if (classification === 'INFRASTRUCTURE') return '恢复待审查'
  if (classification === 'CAPABILITY_TERMINAL') return '已结束'
  return '查看状态'
}

async function loadSelected(syncRoute = true) {
  if (!selectedExperimentId.value) {
    status.value = null
    runs.value = []
    return
  }
  refreshing.value = true
  error.value = ''
  try {
    const [statusResponse, runResponse] = await Promise.all([
      workbenchApi.getStatus(selectedExperimentId.value),
      workbenchApi.getRuns(selectedExperimentId.value, { limit: 100 }),
    ])
    status.value = statusResponse
    runs.value = runResponse.items
    if (syncRoute && route.query.experiment !== selectedExperimentId.value) {
      await router.replace({ query: { ...route.query, experiment: selectedExperimentId.value } })
    }
  } catch {
    error.value = '运行状态暂时无法读取。请检查服务或记录完整性后重试。'
  } finally {
    refreshing.value = false
  }
}

onMounted(async () => {
  try {
    const response = await workbenchApi.listExperiments({ limit: 100 })
    experiments.value = response.items
    const requested = typeof route.query.experiment === 'string' ? route.query.experiment : ''
    selectedExperimentId.value = requested || response.items[0]?.experiment_id || ''
    await loadSelected(Boolean(selectedExperimentId.value))
  } catch {
    error.value = '实验运行记录暂时无法读取。请检查服务连接后重试。'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <h2>运行控制</h2>
        <p>查看已保存的运行状态与恢复边界。任务结果保留原样，不自动重试。</p>
      </div>
      <StatusBadge :value="status?.terminal ? 'DURABLE TERMINAL' : status?.status ?? 'NOT_REPORTED'" />
    </div>

    <div class="control-banner">
      <span class="control-banner-mark">↻</span>
      <div><strong>已保存的运行状态</strong><p>打开或刷新只读取后端已保存状态，不发起模型服务请求。</p></div>
      <span class="status-pill neutral">不自动重试</span>
    </div>

    <PageState v-if="loading" kind="loading">正在读取实验运行状态…</PageState>
    <template v-else>
      <div class="run-control-toolbar panel">
        <label>
          <span>实验</span>
          <select v-model="selectedExperimentId" aria-label="选择运行控制实验" @change="loadSelected()">
            <option v-if="!experiments.length" value="">暂无实验</option>
            <option v-else-if="selectedExperimentId && !selectedIsListed" :value="selectedExperimentId">{{ selectedExperimentId }} · 直接打开的记录</option>
            <option v-for="item in experiments" :key="item.experiment_id" :value="item.experiment_id">
              {{ experimentOption(item, experiments) }} · {{ statusLabel(item.provenance ?? 'UNVERIFIED_SOURCE') }}
            </option>
          </select>
        </label>
        <button class="secondary-button" :disabled="refreshing || !selectedExperimentId" @click="loadSelected(false)">
          {{ refreshing ? '正在刷新…' : '刷新已保存状态' }}
        </button>
        <RouterLink v-if="selectedExperimentId" class="table-link" :to="`/experiments/${selectedExperimentId}`">查看实验详情 →</RouterLink>
      </div>

      <PageState v-if="error" kind="error">{{ error }}</PageState>
      <template v-else-if="selectedExperimentId">
        <div class="notice">服务商已登记不代表可以执行。请在“设置”和“服务商注册表”中检查凭据、运行环境及预检；离线示例的来源在下方单独标注。</div>
        <div class="metric-grid">
          <div class="metric-card accent"><div class="label">运行状态</div><div class="value compact-value"><StatusBadge :value="status?.status ?? 'NOT_REPORTED'" context="experiment" /></div><div class="detail">{{ status?.terminal ? '已保存终态' : '状态仍可能变化' }}</div></div>
          <div class="metric-card"><div class="label">已记录运行</div><div class="value">{{ runs.length }}</div><div class="detail">当前读取前 100 条运行</div></div>
          <div class="metric-card"><div class="label">任务结果已确定</div><div class="value">{{ capabilityCount }}</div><div class="detail">不能通过重试替换任务结果</div></div>
          <div class="metric-card"><div class="label">基础设施</div><div class="value">{{ infrastructureCount }}</div><div class="detail">需按范围审查恢复条件</div></div>
        </div>

        <div class="recovery-policy-grid">
          <article class="policy-card terminal-policy">
            <span class="policy-icon">✓</span>
            <div><span class="panel-kicker">任务结果</span><h3>保留原始验收结果</h3><p>验收失败与任务失败都是证据。不能为提高分数而重跑或替换服务商、模型、路由与 Harness。</p></div>
          </article>
          <article class="policy-card recovery-policy">
            <span class="policy-icon">↻</span>
            <div><span class="panel-kicker">恢复审查</span><h3>按运行单元审查基础设施恢复</h3><p>恢复必须保留冻结的评测方法与配置身份，并采用操作员批准的执行路径。此页面只读取记录。</p></div>
          </article>
        </div>

        <div class="panel">
          <div class="panel-title run-list-heading">
            <div><span class="panel-kicker">已记录运行</span><h3>运行状态列表</h3></div>
            <div class="segmented-control" aria-label="筛选运行类别">
              <button v-for="value in ['ALL', 'CAPABILITY_TERMINAL', 'INFRASTRUCTURE', 'LIFECYCLE'] as const" :key="value" :class="{ active: filter === value }" @click="filter = value">{{ statusLabel(value) }}</button>
            </div>
          </div>
          <PageState v-if="!visibleRuns.length" kind="empty">此类别暂无运行。可以切换“全部”查看其他记录。</PageState>
          <div v-else class="responsive-table" role="region" aria-label="运行状态" tabindex="0">
            <table class="data-table run-control-table">
              <thead><tr><th>运行身份</th><th>运行单元</th><th>来源</th><th>状态 / 结果</th><th>操作边界</th><th>证据</th></tr></thead>
              <tbody>
                <tr v-for="run in visibleRuns" :key="run.run_id">
                  <td><strong class="technical">{{ runName(run, runs.map(item => item.run_id)) }}</strong><div class="muted">尝试 {{ run.attempt }}</div></td>
                  <td>{{ run.cell_id }} · {{ taskName(run.task_id) }}<div class="technical muted">第 {{ run.repeat_index + 1 }} 次 · 通道 {{ run.lane }}</div></td>
                  <td><StatusBadge :value="run.provenance ?? 'UNVERIFIED_SOURCE'" /></td>
                  <td><StatusBadge :value="run.status" /> <StatusBadge :value="run.normalized_outcome ?? 'NOT_REPORTED'" /></td>
                  <td><span class="status-pill" :class="outcomeClass(run) === 'INFRASTRUCTURE' ? 'warn' : 'neutral'">{{ controlLabel(run) }}</span><div class="boundary-note">{{ outcomeClass(run) === 'INFRASTRUCTURE' ? '保留原配置，审查恢复条件。' : outcomeClass(run) === 'CAPABILITY_TERMINAL' ? '保留已记录结果，不重试替换。' : '查看后端已保存状态。' }}</div></td>
                  <td><RouterLink class="table-link" :to="`/runs/${run.run_id}`">诊断与事件记录 →</RouterLink></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
      <PageState v-else kind="empty">暂无可查看的实验。请先打开“实验与运行”，或进入公开演示查看示例。</PageState>
    </template>
  </section>
</template>
