<script setup lang="ts">
import PageState from '@/components/PageState.vue'
import { onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ProviderDefinition } from '@/types/registry'

const items = ref<ProviderDefinition[]>([])
const loading = ref(true)
const error = ref(false)

onMounted(async () => {
  try { items.value = (await registryApi.providers()).items } catch { error.value = true } finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Provider Registry</h2><p>安全路由身份、凭证引用与运营状态；不返回密钥或私有 URL。</p></div></div>
    <PageState v-if="loading" kind="loading">Loading provider registry…</PageState>
    <PageState v-else-if="error" kind="error" reload>Provider registry is unavailable.</PageState>
    <PageState v-else-if="!items.length" kind="empty">No provider definitions are reported.</PageState>
    <div v-else class="registry-card-grid">
      <article v-for="item in items" :key="item.provider_id" class="panel registry-card">
        <div class="panel-title"><h3>{{ item.display_name }}</h3><StatusBadge :value="item.health_status" /></div>
        <dl class="definition-list">
          <dt>Provider ID</dt><dd class="technical">{{ item.provider_id }}</dd>
          <dt>Region</dt><dd>{{ item.region }}</dd>
          <dt>Endpoint class</dt><dd>{{ item.endpoint_class }}</dd>
          <dt>Protocols</dt><dd>{{ item.protocols.join(', ') }}</dd>
          <dt>Billing</dt><dd>{{ item.billing_mode }}</dd>
          <dt>Credential ref</dt><dd class="technical">{{ item.credential_ref }}</dd>
          <dt>Runtime ref</dt><dd class="technical">{{ item.base_url_reference ?? 'PUBLIC_REGISTERED_ROUTE' }}</dd>
          <dt>Automation</dt><dd>{{ item.automation_allowed ? 'ALLOWED' : 'BLOCKED' }}</dd>
        </dl>
        <div v-if="item.configuration_reason_codes.length" class="notice technical">{{ item.configuration_reason_codes.join(' · ') }}</div>
      </article>
    </div>
  </section>
</template>
