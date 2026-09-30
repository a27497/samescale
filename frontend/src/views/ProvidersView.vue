<script setup lang="ts">
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
    <div class="page-heading"><div><h2>Provider Registry</h2><p>Safe route identity, credential presence and runtime state. Secret values and private URLs stay server side.</p></div></div>
    <PageState v-if="loading" kind="loading">Loading provider registry…</PageState>
    <PageState v-else-if="error" kind="error" reload>Provider registry is unavailable.</PageState>
    <PageState v-else-if="!items.length" kind="empty">No provider definitions are reported.</PageState>
    <div v-else class="registry-card-grid">
      <article v-for="item in items" :key="item.provider_id" class="panel registry-card">
        <div class="panel-title"><h3>{{ item.display_name }}</h3><StatusBadge :value="operationalState(item)" /></div>
        <dl class="definition-list">
          <dt>Provider ID</dt><dd class="technical">{{ item.provider_id }}</dd>
          <dt>Registration</dt><dd>{{ item.enabled ? 'Registered for planning' : 'Disabled' }}</dd>
          <dt>Credential</dt><dd>{{ settings?.credentials.find(value => value.credential_ref === item.credential_ref)?.status ?? 'UNKNOWN' }}</dd>
          <dt>Runtime health</dt><dd>{{ item.health_status }}</dd>
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
