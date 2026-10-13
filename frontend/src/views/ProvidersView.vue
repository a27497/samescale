<script setup lang="ts">
import { statusLabel, metadataLabel } from '@/utils/statusLabels'
import PageState from '@/components/PageState.vue'
import { onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ProviderDefinition, RegistrySettings } from '@/types/registry'

const items = ref<ProviderDefinition[]>([])
const settings = ref<RegistrySettings | null>(null)
const loading = ref(true)
const error = ref(false)

function operationalState(item: ProviderDefinition): string {
  if (!item.enabled || !item.automation_allowed || item.health_status === 'UNAVAILABLE' || item.health_status === 'QUOTA_EXHAUSTED') return 'UNAVAILABLE / ERROR'
  const credential = settings.value?.credentials.find(value => value.credential_ref === item.credential_ref)
  if (!credential) return 'CREDENTIAL STATUS UNKNOWN'
  if (credential.status !== 'SET') return 'CREDENTIAL MISSING'
  if (item.health_status === 'UNKNOWN') return 'RUNTIME UNVERIFIED'
  return item.health_status === 'AVAILABLE' ? 'READY TO EXECUTE (preflight still required)' : 'RUNTIME UNVERIFIED'
}
onMounted(async () => {
  try {
    const [providers, safeSettings] = await Promise.all([registryApi.providers(), registryApi.settings()])
    items.value = providers.items; settings.value = safeSettings
  } catch { error.value = true } finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>服务商注册表</h2><p>查看路由身份、凭据配置与运行环境状态。密钥与私有地址只保存在服务端。</p></div></div>
    <PageState v-if="loading" kind="loading">正在读取服务商注册表…</PageState>
    <PageState v-else-if="error" kind="error" reload>服务商注册表暂时无法读取。请检查后端服务后重新加载。</PageState>
    <PageState v-else-if="!items.length" kind="empty">暂无服务商定义。请在“连接与配置”中查看本地连接，或由操作员配置服务端注册表。</PageState>
    <div v-else class="registry-card-grid">
      <article v-for="item in items" :key="item.provider_id" class="panel registry-card">
        <div class="panel-title"><h3>{{ item.display_name }}</h3><StatusBadge :value="operationalState(item)" /></div>
        <dl class="definition-list">
          <dt>服务商 ID</dt><dd class="technical">{{ item.provider_id }}</dd>
          <dt>登记状态</dt><dd>{{ item.enabled ? '已登记 · 可规划' : '已停用' }}</dd>
          <dt>凭据</dt><dd><StatusBadge :value="settings?.credentials.find(value => value.credential_ref === item.credential_ref)?.status ?? 'UNKNOWN'" /></dd>
          <dt>运行环境状态</dt><dd><StatusBadge :value="item.health_status" context="provider" /></dd>
          <dt>区域</dt><dd>{{ metadataLabel(item.region) }}</dd>
          <dt>服务地址类型</dt><dd><StatusBadge :value="item.endpoint_class" /></dd>
          <dt>协议</dt><dd>{{ item.protocols.map(metadataLabel).join('、') }}</dd>
          <dt>计费方式</dt><dd><StatusBadge :value="item.billing_mode" /></dd>
          <dt>凭据引用</dt><dd class="technical">{{ item.credential_ref }}</dd>
          <dt>服务地址引用</dt><dd class="technical">{{ item.base_url_reference ?? statusLabel('PUBLIC_REGISTERED_ROUTE') }}</dd>
          <dt>自动执行</dt><dd><StatusBadge :value="item.automation_allowed ? 'ALLOWED' : 'BLOCKED'" /></dd>
        </dl>
        <div v-if="item.configuration_reason_codes.length" class="notice"><p v-for="reason in item.configuration_reason_codes" :key="reason" :title="reason">{{ statusLabel(reason) }}。请由操作员检查服务端配置。</p><RouterLink class="table-link" to="/connections">查看连接与配置 →</RouterLink></div>
      </article>
    </div>
  </section>
</template>
