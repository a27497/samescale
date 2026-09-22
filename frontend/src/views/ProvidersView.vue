<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import ResourceManager from '@/components/ResourceManager.vue'
import { registryReason } from '@/composables/registryPresentation'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ProviderDefinition } from '@/types/registry'

const items = ref<ProviderDefinition[]>([])
const loading = ref(true)
const error = ref(false)

async function load() {
  loading.value = true; error.value = false; items.value = []

  try { items.value = (await registryApi.providers()).items } catch { error.value = true } finally { loading.value = false }
}
onMounted(load)
const resources = computed(() => items.value.map(item => ({ id: item.provider_id, name: item.display_name, description: item.protocols.join(', ') })))
</script>

<template>
  <section>
    <button v-if="error && !loading" class="secondary-button retry-button" @click="load">{{ t('重新加载') }}</button>
    <div v-if="loading" class="loading-state">{{ t('正在读取模型服务…') }}</div>
    <div v-else-if="error" class="error-state">{{ t('暂时无法读取模型服务，请检查本地 API。') }}</div>
    <div v-else-if="!items.length" class="empty-state">{{ t('尚无已注册模型服务。') }}</div>
    <ResourceManager v-else kind="providers" :items="resources" v-slot="{ selectedId }">
      <article v-for="item in items.filter(value => value.provider_id === selectedId)" :key="item.provider_id" class="panel registry-card">
        <div class="panel-title"><h3>{{ item.display_name }}</h3><StatusBadge :value="item.health_status" /></div>
        <dl class="definition-list">
          <dt>{{ t('服务标识') }}</dt><dd class="technical">{{ item.provider_id }}</dd>
          <dt>{{ t('区域') }}</dt><dd>{{ item.region }}</dd>
          <dt>{{ t('端点类型') }}</dt><dd>{{ item.endpoint_class }}</dd>
          <dt>{{ t('协议') }}</dt><dd>{{ item.protocols.join(', ') }}</dd>
          <dt>{{ t('计费方式') }}</dt><dd>{{ item.billing_mode }}</dd>
          <dt>{{ t('凭据引用') }}</dt><dd class="technical">{{ item.credential_ref }}</dd>
          <dt>{{ t('运行地址引用') }}</dt><dd class="technical">{{ item.base_url_reference ?? 'PUBLIC_REGISTERED_ROUTE' }}</dd>
          <dt>{{ t('服务配置') }}</dt><dd><StatusBadge :value="item.enabled ? 'ENABLED' : 'DISABLED'" /></dd>
          <dt>{{ t('调用策略') }}</dt><dd>{{ t(item.automation_allowed ? '配置允许自动调用；实际执行仍需单独授权。' : '配置禁止自动调用。') }}</dd>
        </dl>
        <p class="notice">{{ t('服务状态由操作者声明；本页不探测连接。') }}</p>
        <div v-for="code in item.configuration_reason_codes" :key="code" class="notice">{{ t(registryReason(code)) }} <code class="technical">{{ code }}</code></div>
      </article>
    </ResourceManager>
  </section>
</template>
