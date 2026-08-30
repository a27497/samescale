<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ModelDefinition, ProviderModelProfile } from '@/types/registry'

const models = ref<ModelDefinition[]>([])
const profiles = ref<ProviderModelProfile[]>([])
const loading = ref(true)
const error = ref(false)

onMounted(async () => {
  try {
    const data = await registryApi.models()
    models.value = data.models
    profiles.value = data.provider_profiles
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
})

const modelProfiles = (modelId: string) => profiles.value.filter((item) => item.model_id === modelId)
const enabledControlNames = (model: ModelDefinition) =>
  Object.entries(model.reasoning_controls).filter(([, enabled]) => enabled).map(([name]) => name)
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h2>Model Registry</h2><p>Canonical model metadata is separated from provider-specific routing and treatment identity.</p></div>
      <span class="status-pill neutral">READ ONLY</span>
    </div>
    <div class="registry-principle"><strong>Identity rule</strong><span>A model definition describes capability; each provider profile below remains a distinct experimental treatment.</span></div>
    <div v-if="loading" class="loading-state">Loading model registry…</div>
    <div v-else-if="error" class="error-state">Model registry is unavailable.</div>
    <div v-else-if="!models.length" class="empty-state">No configured model definitions are reported.</div>
    <div v-else class="registry-card-grid">
      <article v-for="model in models" :key="model.model_id" class="panel registry-card model-card">
        <div class="panel-title">
          <div><span class="panel-kicker">{{ model.model_family }}</span><h3>{{ model.display_name }}</h3></div>
          <StatusBadge :value="model.context_metadata_status" />
        </div>
        <div class="identity-block"><span>MODEL ID</span><strong class="technical">{{ model.model_id }}</strong></div>
        <dl class="definition-list compact-definitions">
          <dt>Capabilities</dt><dd><span v-for="capability in model.capabilities" :key="capability" class="metadata-chip">{{ capability }}</span><span v-if="!model.capabilities.length">NONE_REPORTED</span></dd>
          <dt>Protocols</dt><dd>{{ model.supported_protocols.join(', ') || 'NONE_REPORTED' }}</dd>
          <dt>Context window</dt><dd>{{ model.context_window_tokens?.toLocaleString() ?? 'NOT_AVAILABLE' }} <span v-if="model.context_window_tokens" class="muted">tokens</span></dd>
          <dt>Reasoning controls</dt><dd>{{ enabledControlNames(model).join(', ') || 'NONE_REPORTED' }}</dd>
        </dl>

        <div class="subsection-heading"><span>Provider profiles</span><b>{{ modelProfiles(model.model_id).length }}</b></div>
        <div v-if="!modelProfiles(model.model_id).length" class="notice"><span class="technical">CONFIGURED_MODEL_ID_REQUIRED</span></div>
        <div v-for="profile in modelProfiles(model.model_id)" :key="profile.profile_id" class="provider-profile">
          <div class="provider-profile-head"><strong class="technical">{{ profile.profile_id }}</strong><StatusBadge :value="profile.enabled ? 'ENABLED' : 'DISABLED'" /></div>
          <dl class="mini-definition-list">
            <dt>Provider / protocol</dt><dd>{{ profile.provider_id }} / {{ profile.protocol }}</dd>
            <dt>Requested model</dt><dd class="technical">{{ profile.requested_model }}</dd>
            <dt>Route identity</dt><dd class="technical">{{ profile.provider_route_identity }}</dd>
            <dt>Observed identity</dt><dd>{{ profile.observed_model_capability }}</dd>
            <dt>Controls</dt><dd>effort={{ profile.reasoning_effort ?? 'NOT_AVAILABLE' }} · max output={{ profile.max_output_tokens }}</dd>
            <dt>Profile digest</dt><dd class="technical">{{ profile.profile_identity }}</dd>
          </dl>
        </div>
      </article>
    </div>
  </section>
</template>
