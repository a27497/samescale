<script setup lang="ts">
import PageState from '@/components/PageState.vue'
import { computed, onMounted, ref } from 'vue'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { CoreReadiness, ExperimentSummary } from '@/types/workbench'
import { experimentName } from '@/utils/displayIdentity'

const readiness = ref<CoreReadiness | null>(null)
const experiments = ref<ExperimentSummary[]>([])
const loading = ref(true)
const error = ref(false)
const listFailed = ref(false)
const readinessFailed = ref(false)

const activeExperiments = computed(() =>
  experiments.value.filter((item) => !['completed', 'failed', 'cancelled'].includes(item.status)).length,
)
const infrastructureEvents = computed(() =>
  experiments.value.reduce((total, item) => total + item.infra_count, 0),
)

onMounted(async () => {
  const [ready, list] = await Promise.allSettled([
    workbenchApi.readiness(),
    workbenchApi.listExperiments({ limit: 5 }),
  ])
  if (ready.status === 'fulfilled') readiness.value = ready.value
  if (list.status === 'fulfilled') experiments.value = list.value.items
  listFailed.value = list.status === 'rejected'
  readinessFailed.value = ready.status === 'rejected'
  error.value = ready.status === 'rejected' && list.status === 'rejected'
  loading.value = false
})
</script>

<template>
  <section>
    <div class="hero-panel">
      <div>
        <span class="eyebrow">证据工作台</span>
        <h2>从配置到运行，查看可复核的证据。</h2>
        <p>
          无需密钥即可规划实验，查看已保存运行证据；任务结果与基础设施恢复分开展示。
        </p>
        <div class="hero-actions">
          <RouterLink class="primary-button" to="/experiments/new">规划实验</RouterLink>
          <RouterLink class="secondary-button" to="/run-control">查看运行控制</RouterLink>
        </div>
      </div>
      <div class="hero-readiness">
        <span class="label">核心就绪度</span>
        <StatusBadge :value="readiness?.status ?? 'NOT_REPORTED'" />
        <strong>{{ readiness?.blockers.length ?? '—' }}</strong>
        <small>待解决项</small>
        <small v-if="readinessFailed">就绪检查暂时无法读取，请查看详情并检查服务。</small><RouterLink to="/core-readiness">查看证据 →</RouterLink>
      </div>
    </div>

    <PageState v-if="loading" kind="loading">正在读取已保存证据…</PageState>
    <PageState v-else-if="error" kind="error" reload>工作台证据暂时无法读取。请检查后端服务连接后重试。</PageState>
    <template v-else>
      <div class="metric-grid overview-metrics">
        <div class="metric-card accent">
          <div class="label">最近实验</div><div class="value">{{ listFailed ? '—' : experiments.length }}</div>
          <div class="detail">当前读取的有限列表</div>
        </div>
        <div class="metric-card">
          <div class="label">进行中</div><div class="value">{{ listFailed ? '—' : activeExperiments }}</div>
          <div class="detail">本页等待运行或正在运行的实验</div>
        </div>
        <div class="metric-card">
          <div class="label">基础设施事件</div><div class="value">{{ listFailed ? '—' : infrastructureEvents }}</div>
          <div class="detail">与任务结果分开展示</div>
        </div>
        <div class="metric-card">
          <div class="label">任务集</div><div class="value">{{ readiness?.task_corpus_size ?? '—' }}</div>
          <div class="detail">已登记并保存的任务身份</div>
        </div>
      </div>

      <div class="overview-layout">
        <div class="panel">
          <div class="panel-title">
            <div><span class="panel-kicker">最近活动</span><h3>实验记录</h3></div>
            <RouterLink class="table-link" to="/experiments">查看全部</RouterLink>
          </div>
          <PageState v-if="listFailed" kind="error" reload>实验列表暂时无法读取，不是空列表。请检查后端服务后重试；已有就绪检查仍保留。</PageState>
          <PageState v-else-if="!experiments.length" kind="empty">暂无已保存实验。可以先规划实验，或打开公开演示查看示例。</PageState>
          <div v-else class="responsive-table" role="region" aria-label="最近实验" tabindex="0">
            <table class="data-table">
              <thead><tr><th>实验</th><th>来源</th><th>状态</th><th>组合矩阵</th><th>任务结果 / 基础设施</th></tr></thead>
              <tbody>
                <tr v-for="item in experiments" :key="item.experiment_id">
                  <td><RouterLink class="table-link technical" :to="`/experiments/${item.experiment_id}`">{{ experimentName(item) }}</RouterLink></td>
                  <td><StatusBadge :value="item.provenance ?? 'UNVERIFIED_SOURCE'" /></td>
                  <td><StatusBadge :value="item.status" /></td>
                  <td>{{ item.task_count }} 项任务 × {{ item.cell_count }} 个组合</td>
                  <td>{{ item.completed_capability_count }} / {{ item.infra_count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <aside class="panel launchpad">
          <div class="panel-title"><div><span class="panel-kicker">常用入口</span><h3>工作台功能</h3></div></div>
          <RouterLink to="/models"><span class="launch-mark">01</span><span><strong>注册表</strong><small>模型、服务商、Harness 与兼容能力</small></span><b>→</b></RouterLink>
          <RouterLink to="/experiments/new"><span class="launch-mark">02</span><span><strong>实验规划</strong><small>服务端验证计划，不执行运行</small></span><b>→</b></RouterLink>
          <RouterLink to="/run-control"><span class="launch-mark">03</span><span><strong>运行控制</strong><small>运行状态与恢复边界</small></span><b>→</b></RouterLink>
          <RouterLink to="/diagnosis"><span class="launch-mark">04</span><span><strong>失败诊断</strong><small>检查独立验收与失败证据</small></span><b>→</b></RouterLink>
          <RouterLink to="/regression"><span class="launch-mark">05</span><span><strong>候选对比</strong><small>比较符合条件的共同任务</small></span><b>→</b></RouterLink>
        </aside>
      </div>
    </template>
  </section>
</template>
