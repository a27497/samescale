<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, onMounted, ref, watch } from 'vue'

import { registryApi } from '@/api/client'
import { registryReason } from '@/composables/registryPresentation'
import StatusBadge from '@/components/StatusBadge.vue'
import type { CapabilityAssessment } from '@/types/registry'

const items = ref<CapabilityAssessment[]>([])
const filter = ref('ALL')
const search = ref('')
const loading = ref(true)
const error = ref(false)
const page = ref(1)
const pageSize = 10
const expanded = ref('')
const identity = (item: CapabilityAssessment) => `${item.provider_profile_id}:${item.harness_profile_id}`
const pages = computed(() => Math.max(1, Math.ceil(visible.value.length / pageSize)))
const paged = computed(() => visible.value.slice((page.value - 1) * pageSize, page.value * pageSize))
watch([filter, search], () => { page.value = 1; expanded.value = '' })
watch(page, () => { expanded.value = '' })
const visible = computed(() => {
  const query = search.value.trim().toLowerCase()
  return items.value.filter((item) => {
    const statusMatches = filter.value === 'ALL' || item.status === filter.value
    const identityMatches = !query || `${item.provider_profile_id} ${item.harness_profile_id} ${item.reason_codes.join(' ')}`.toLowerCase().includes(query)
    return statusMatches && identityMatches
  })
})
const statusCount = (status: string) => items.value.filter((item) => item.status === status).length
async function load() {
  loading.value = true; error.value = false; items.value = []; page.value = 1; expanded.value = ''

  try { items.value = (await registryApi.capabilities()).items }
  catch { error.value = true }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <section>
    <div class="page-heading capability-heading">
      <div><h2>{{ t('兼容性检查') }}</h2><p>{{ t('检查模型服务与执行方式是否兼容。') }}</p></div>
      <div class="toolbar">
        <input v-model="search" :aria-label="t('搜索兼容性')" :placeholder="t('搜索配置或限制原因')">
        <select v-model="filter" :aria-label="t('筛选兼容状态')"><option value="ALL">{{ t('全部') }}</option><option value="SUPPORTED">{{ t('支持') }}</option><option value="PARTIALLY_SUPPORTED">{{ t('部分支持') }}</option><option value="UNSUPPORTED">{{ t('不支持') }}</option></select>
      </div>
    </div>
    <button v-if="error && !loading" class="secondary-button retry-button" @click="load">{{ t('重新加载') }}</button>
    <div v-if="loading" class="loading-state">{{ t('正在读取兼容性结果…') }}</div>
    <div v-else-if="error" class="error-state">{{ t('暂时无法读取兼容性结果，请检查本地 API。') }}</div>
    <template v-else>
      <div class="compatibility-summary" :aria-label="t('兼容性概况')"><span>{{ t('全部组合') }} <b>{{ items.length }}</b></span><span>{{ t('支持') }} <b>{{ statusCount('SUPPORTED') }}</b></span><span>{{ t('部分支持') }} <b>{{ statusCount('PARTIALLY_SUPPORTED') }}</b></span><span>{{ t('不支持') }} <b>{{ statusCount('UNSUPPORTED') }}</b></span></div>
      <div class="panel">
        <div class="panel-title"><div><span class="panel-kicker">{{ t('兼容性矩阵') }}</span><h3>{{ visible.length }} {{ t('个配置组合') }}</h3></div><span class="status-pill neutral">{{ t('服务端判定') }}</span></div>
        <div v-if="!visible.length" class="empty-state">{{ t('没有符合当前筛选条件的组合。') }}</div>
        <div v-else class="compatibility-list">
          <article v-for="item in paged" :key="identity(item)" class="compatibility-item">
            <button class="compatibility-toggle" :aria-expanded="expanded === identity(item)" @click="expanded = expanded === identity(item) ? '' : identity(item)">
              <span class="compatibility-pair"><strong class="technical">{{ item.provider_profile_id }}</strong><span class="technical">{{ item.harness_profile_id }}</span></span>
              <StatusBadge :value="item.status" /><span class="compatibility-chevron" aria-hidden="true">{{ expanded === identity(item) ? '−' : '+' }}</span>
            </button>
            <div v-if="expanded === identity(item)" class="compatibility-details">
              <div><h4>{{ t('兼容性依据') }}</h4><RouterLink class="table-link" :to="{ path: '/connections', query: { profile: item.provider_profile_id, harness: item.harness_profile_id } }">{{ t('查看连接与兼容性') }}</RouterLink><dl class="definition-list"><dt>{{ t('协议') }}</dt><dd>{{ item.protocol_compatible ? 'COMPATIBLE' : 'INCOMPATIBLE' }}</dd><dt>{{ t('模型 / 服务') }}</dt><dd>{{ item.model_provider_compatible ? 'COMPATIBLE' : 'INCOMPATIBLE' }}</dd><dt>{{ t('推理控制') }}</dt><dd>{{ item.reasoning_control_supported ? 'SUPPORTED' : 'NOT_SUPPORTED' }}</dd><dt>{{ t('增益资格') }}</dt><dd>{{ item.harness_uplift_eligible ? '✓' : '—' }}</dd><dt>{{ t('评审资格') }}</dt><dd>{{ item.judge_eligible ? '✓' : '—' }}</dd></dl></div>
              <div><h4>{{ t('证据与执行') }}</h4><dl class="definition-list"><dt>{{ t('轨迹') }}</dt><dd>{{ item.trace_coverage }}</dd><dt>{{ t('观测模型') }}</dt><dd>{{ item.observed_model }}</dd><dt>{{ t('工具 / 工作区') }}</dt><dd>{{ item.native_tools ? 'NATIVE' : 'NONE' }} / {{ item.workspace_mutation ? 'MUTABLE' : 'READ_ONLY' }}</dd><dt>{{ t('网络') }}</dt><dd>{{ item.network_requirement }}</dd></dl></div>
              <div class="compatibility-reasons"><h4>{{ t('限制原因') }}</h4><div v-if="item.reason_codes.length" class="reason-stack"><div v-for="reason in item.reason_codes" :key="reason"><p>{{ t(registryReason(reason)) }}</p><code>{{ reason }}</code></div></div><p v-else class="muted">{{ t('未报告限制') }}</p></div>
            </div>
          </article>
        </div>
        <nav v-if="visible.length" class="pagination" :aria-label="t('兼容性分页')"><span>{{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, visible.length) }} / {{ visible.length }}</span><div><button class="secondary-button" :disabled="page === 1" @click="page--">{{ t('上一页') }}</button><span>{{ page }} / {{ pages }}</span><button class="secondary-button" :disabled="page === pages" @click="page++">{{ t('下一页') }}</button></div></nav>
      </div>
    </template>
  </section>
</template>
