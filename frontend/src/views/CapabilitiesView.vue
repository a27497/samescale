<script setup lang="ts">
import { statusLabel, metadataLabel } from '@/utils/statusLabels'
import PageState from '@/components/PageState.vue'
import { computed, onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { CapabilityAssessment } from '@/types/registry'

const items = ref<CapabilityAssessment[]>([])
const filter = ref('ALL')
const search = ref('')
const loading = ref(true)
const error = ref(false)
const visible = computed(() => {
  const query = search.value.trim().toLowerCase()
  return items.value.filter((item) => {
    const statusMatches = filter.value === 'ALL' || item.status === filter.value
    const identityMatches = !query || `${item.provider_profile_id} ${item.harness_profile_id} ${item.reason_codes.join(' ')} ${item.reason_codes.map(value => statusLabel(value)).join(' ')}`.toLowerCase().includes(query)
    return statusMatches && identityMatches
  })
})
const statusCount = (status: string) => items.value.filter((item) => item.status === status).length
onMounted(async () => {
  try { items.value = (await registryApi.capabilities()).items }
  catch { error.value = true }
  finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading capability-heading">
      <div><h2>兼容能力</h2><p>查看模型服务配置与 Harness 的兼容性和限制。未知条件不能视为支持。</p></div>
      <div class="toolbar">
        <input v-model="search" aria-label="搜索兼容能力" placeholder="搜索配置或限制原因">
        <select v-model="filter" aria-label="筛选兼容状态"><option v-for="value in ['ALL', 'SUPPORTED', 'PARTIALLY_SUPPORTED', 'UNSUPPORTED']" :key="value" :value="value">{{ statusLabel(value) }}</option></select>
      </div>
    </div>
    <PageState v-if="loading" kind="loading">正在读取兼容能力…</PageState>
    <PageState v-else-if="error" kind="error" reload>兼容能力暂时无法读取。请检查服务端注册表后重试。</PageState>
    <template v-else>
      <div class="metric-grid capability-metrics">
        <button :class="['metric-card', { accent: filter === 'ALL' }]" @click="filter = 'ALL'"><span class="label">全部组合</span><strong class="value">{{ items.length }}</strong></button>
        <button :class="['metric-card', { accent: filter === 'SUPPORTED' }]" @click="filter = 'SUPPORTED'"><span class="label">支持</span><strong class="value">{{ statusCount('SUPPORTED') }}</strong></button>
        <button :class="['metric-card', { accent: filter === 'PARTIALLY_SUPPORTED' }]" @click="filter = 'PARTIALLY_SUPPORTED'"><span class="label">部分支持</span><strong class="value">{{ statusCount('PARTIALLY_SUPPORTED') }}</strong></button>
        <button :class="['metric-card', { accent: filter === 'UNSUPPORTED' }]" @click="filter = 'UNSUPPORTED'"><span class="label">不支持</span><strong class="value">{{ statusCount('UNSUPPORTED') }}</strong></button>
      </div>
      <div class="panel">
        <div class="panel-title"><div><span class="panel-kicker">兼容矩阵</span><h3>{{ visible.length }} 个配置组合</h3></div><span class="status-pill neutral">服务端判定</span></div>
        <p v-if="visible.length" class="table-scroll-hint">可搜索或筛选结果；表格内上下、左右滚动查看完整字段。</p>
        <PageState v-if="!visible.length" kind="empty">没有符合筛选条件的组合。请清除筛选；若仍为空，请先配置模型与 Harness。</PageState>
        <div v-else class="responsive-table capability-results" role="region" aria-label="兼容能力评估" tabindex="0">
          <table class="data-table capability-table">
            <thead><tr><th>配置身份</th><th>状态</th><th>协议与模型</th><th>证据与执行能力</th><th>限制原因</th></tr></thead>
            <tbody>
              <tr v-for="item in visible" :key="`${item.provider_profile_id}:${item.harness_profile_id}`">
                <td><span class="muted">服务商模型</span><strong class="technical">{{ item.provider_profile_id }}</strong><span class="muted">Harness</span><strong class="technical">{{ item.harness_profile_id }}</strong></td>
                <td><StatusBadge :value="item.status" /><div class="eligibility-list"><span>Harness 增益 {{ item.harness_uplift_eligible ? '✓' : '—' }}</span><span>Judge 校准 {{ item.judge_eligible ? '✓' : '—' }}</span></div></td>
                <td><dl class="inline-facts"><dt>协议</dt><dd><StatusBadge :value="item.protocol_compatible ? 'COMPATIBLE' : 'INCOMPATIBLE'" /></dd><dt>模型 / 服务商</dt><dd><StatusBadge :value="item.model_provider_compatible ? 'COMPATIBLE' : 'INCOMPATIBLE'" /></dd><dt>推理控制</dt><dd><StatusBadge :value="item.reasoning_control_supported ? 'SUPPORTED' : 'NOT_SUPPORTED'" /></dd></dl></td>
                <td><dl class="inline-facts"><dt>Trace</dt><dd><StatusBadge :value="item.trace_coverage" /></dd><dt>实际模型依据</dt><dd><StatusBadge :value="item.observed_model" /></dd><dt>工具 / 工作区</dt><dd>{{ item.native_tools ? '原生工具' : '无原生工具' }} / {{ item.workspace_mutation ? '允许修改' : '只读' }}</dd><dt>网络访问</dt><dd><StatusBadge :value="item.network_requirement" /></dd></dl></td>
                <td><div v-if="item.reason_codes.length" class="reason-stack"><span v-for="reason in item.reason_codes" :key="reason" :title="reason">{{ statusLabel(reason) }}</span></div><span v-else class="muted">未报告限制</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </section>
</template>
