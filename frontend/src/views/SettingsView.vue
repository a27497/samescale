<script setup lang="ts">
import PageState from '@/components/PageState.vue'
import { computed, onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { RegistrySettings } from '@/types/registry'

const settings = ref<RegistrySettings | null>(null)
const loading = ref(true)
const error = ref(false)
const configuredCredentials = computed(() => settings.value?.credentials.filter((item) => item.status === 'SET').length ?? 0)
onMounted(async () => {
  try { settings.value = await registryApi.settings() }
  catch { error.value = true }
  finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h2>Settings</h2><p>Non-secret product defaults and presence-only environment references.</p></div>
      <span class="status-pill neutral">SERVER MANAGED</span>
    </div>
    <div class="settings-security-banner"><span class="security-mark">•••</span><div><strong>Secret-safe by construction</strong><p>Secret editing is intentionally unavailable. Credential values are never returned or persisted in browser state; only reference names and SET / MISSING presence are shown.</p></div></div>
    <PageState v-if="loading" kind="loading">Loading safe settings…</PageState>
    <PageState v-else-if="error" kind="error" reload>Settings are unavailable.</PageState>
    <template v-else-if="settings">
      <div class="section-grid settings-grid">
        <div class="panel">
          <div class="panel-title"><div><span class="panel-kicker">PLANNING</span><h3>Experiment defaults</h3></div><span class="status-pill neutral">NON-SECRET</span></div>
          <dl class="definition-list settings-definitions">
            <dt>Provider profile</dt><dd class="technical">{{ settings.defaults.default_provider_profile_id }}</dd>
            <dt>Evaluation mode</dt><dd><StatusBadge :value="settings.defaults.default_evaluation_mode" /></dd>
            <dt>Schedule seed</dt><dd>{{ settings.defaults.default_schedule_seed }}</dd>
            <dt>Concurrency</dt><dd>{{ settings.defaults.default_concurrency }}</dd>
            <dt>Cost budget</dt><dd>{{ settings.defaults.default_cost_budget ?? 'NOT_AVAILABLE' }}</dd>
          </dl>
          <div class="notice">These values seed backend preflight requests. Methodology-owned repeat counts and validation remain backend-authoritative.</div>
        </div>
        <div class="panel">
          <div class="panel-title"><div><span class="panel-kicker">ENVIRONMENT</span><h3>Credential presence</h3></div><span>{{ configuredCredentials }} / {{ settings.credentials.length }} set</span></div>
          <PageState v-if="!settings.credentials.length" kind="empty">No credential references are declared.</PageState>
          <div v-for="item in settings.credentials" :key="item.credential_ref" class="credential-row"><span><strong class="technical">{{ item.credential_ref }}</strong><small>Value withheld</small></span><StatusBadge :value="item.status" /></div>
          <div class="secret-editing-state"><span>Browser secret editing</span><strong>{{ settings.secret_editing_supported ? 'SUPPORTED' : 'INTENTIONALLY UNAVAILABLE' }}</strong></div>
        </div>
      </div>
      <div class="panel provider-settings-panel">
        <div class="panel-title"><div><span class="panel-kicker">PROVIDERS</span><h3>Planning registration</h3></div><RouterLink class="table-link" to="/providers">Inspect operational state →</RouterLink></div>
        <div class="notice">Registered or enabled means selectable for planning. Execution also requires a present credential, a healthy runtime, and successful preflight.</div>
        <div class="provider-toggle-grid">
          <div v-for="(enabled, provider) in settings.provider_enabled" :key="provider" class="provider-toggle-row"><span class="technical">{{ provider }}</span><StatusBadge :value="enabled ? 'REGISTERED FOR PLANNING' : 'DISABLED'" /></div>
        </div>
      </div>
    </template>
  </section>
</template>
