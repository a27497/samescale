<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import type { ModelDefinition, ProviderModelProfile } from '@/types/registry'

const models = ref<ModelDefinition[]>([])
const profiles = ref<ProviderModelProfile[]>([])
const loading = ref(true)
const error = ref(false)

onMounted(async () => {
  try { const data = await registryApi.models(); models.value = data.models; profiles.value = data.provider_profiles } catch { error.value = true } finally { loading.value = false }
})

const modelProfiles = (modelId: string) => profiles.value.filter((item) => item.model_id === modelId)
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Model Registry</h2><p>Model 与 Provider 分离；同名模型的不同 Provider Profile 是不同实验处理。</p></div></div>
    <div v-if="loading" class="loading-state">Loading model registry…</div>
    <div v-else-if="error" class="error-state">Model registry is unavailable.</div>
    <div v-else class="panel">
      <table class="data-table"><thead><tr><th>Model</th><th>Capabilities</th><th>Provider profiles</th></tr></thead>
        <tbody><tr v-for="model in models" :key="model.model_id">
          <td><strong>{{ model.display_name }}</strong><br><span class="technical muted">{{ model.model_id }} · {{ model.model_family }}</span></td>
          <td>{{ model.capabilities.join(', ') }}<br><span class="muted">context={{ model.context_metadata_status }}</span></td>
          <td><div v-for="profile in modelProfiles(model.model_id)" :key="profile.profile_id" class="profile-line"><span class="technical">{{ profile.profile_id }}</span><span>{{ profile.provider_id }} / {{ profile.protocol }}</span><small class="technical">{{ profile.profile_identity }}</small></div><span v-if="!modelProfiles(model.model_id).length" class="status-pill warn">CONFIGURED_MODEL_ID_REQUIRED</span></td>
        </tr></tbody>
      </table>
    </div>
  </section>
</template>
