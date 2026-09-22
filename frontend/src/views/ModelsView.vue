<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import ResourceManager from '@/components/ResourceManager.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ModelDefinition, ProviderModelProfile } from '@/types/registry'

const models = ref<ModelDefinition[]>([])
const profiles = ref<ProviderModelProfile[]>([])
const loading = ref(true)
const error = ref(false)

async function load() {
  loading.value = true; error.value = false; models.value = []; profiles.value = []

  try {
    const data = await registryApi.models()
    models.value = data.models
    profiles.value = data.provider_profiles
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}
onMounted(load)

const modelProfiles = (modelId: string) => profiles.value.filter((item) => item.model_id === modelId)
const enabledControlNames = (model: ModelDefinition) =>
  Object.entries(model.reasoning_controls).filter(([, enabled]) => enabled).map(([name]) => name)
const resources = computed(() => models.value.map(item => ({ id: item.model_id, name: item.display_name, description: item.model_family })))
</script>

<template>
  <section>
    <button v-if="error && !loading" class="secondary-button retry-button" @click="load">{{ t('重新加载') }}</button>
    <div v-if="loading" class="loading-state">{{ t('正在读取模型配置…') }}</div>
    <div v-else-if="error" class="error-state">{{ t('暂时无法读取模型配置，请检查本地 API。') }}</div>
    <div v-else-if="!models.length" class="empty-state">{{ t('尚无已配置模型。') }}</div>
    <ResourceManager v-else kind="models" :items="resources" v-slot="{ selectedId }">
      <article v-for="model in models.filter(item => item.model_id === selectedId)" :key="model.model_id" class="panel registry-card model-card">
        <div class="panel-title">
          <div><span class="panel-kicker">{{ model.model_family }}</span><h3>{{ model.display_name }}</h3></div>
          <StatusBadge :value="model.context_metadata_status" />
        </div>
        <div class="identity-block"><span>{{ t('模型标识') }}</span><strong class="technical">{{ model.model_id }}</strong></div>
        <dl class="definition-list compact-definitions">
          <dt>{{ t('模型能力') }}</dt><dd><span v-for="capability in model.capabilities" :key="capability" class="metadata-chip">{{ capability }}</span><span v-if="!model.capabilities.length">NONE_REPORTED</span></dd>
          <dt>{{ t('协议') }}</dt><dd>{{ model.supported_protocols.join(', ') || 'NONE_REPORTED' }}</dd>
          <dt>{{ t('上下文窗口') }}</dt><dd>{{ model.context_window_tokens?.toLocaleString() ?? 'NOT_AVAILABLE' }} <span v-if="model.context_window_tokens" class="muted">tokens</span></dd>
          <dt>{{ t('推理控制') }}</dt><dd>{{ enabledControlNames(model).join(', ') || 'NONE_REPORTED' }}</dd>
        </dl>

        <div class="subsection-heading"><span>{{ t('服务配置') }}</span><b>{{ modelProfiles(model.model_id).length }}</b></div>
        <div v-if="!modelProfiles(model.model_id).length" class="notice"><span class="technical">CONFIGURED_MODEL_ID_REQUIRED</span></div>
        <div v-for="profile in modelProfiles(model.model_id)" :key="profile.profile_id" class="provider-profile">
          <div class="provider-profile-head"><strong class="technical">{{ profile.profile_id }}</strong><StatusBadge :value="profile.enabled ? 'ENABLED' : 'DISABLED'" /></div>
          <RouterLink class="table-link" :to="{ path: '/connections', query: { profile: profile.profile_id } }">{{ t('查看连接与兼容性') }}</RouterLink>
          <details class="resource-disclosure"><summary>{{ t('路由、控制参数与配置摘要') }}</summary><dl class="mini-definition-list">
            <dt>{{ t('服务 / 协议') }}</dt><dd>{{ profile.provider_id }} / {{ profile.protocol }}</dd>
            <dt>{{ t('请求模型') }}</dt><dd class="technical">{{ profile.requested_model }}</dd>
            <dt>{{ t('路由身份') }}</dt><dd class="technical">{{ profile.provider_route_identity }}</dd>
            <dt>{{ t('观测身份') }}</dt><dd>{{ profile.observed_model_capability }}</dd>
            <dt>{{ t('控制参数') }}</dt><dd>{{ t('推理强度=') }}{{ profile.reasoning_effort ?? 'NOT_AVAILABLE' }} {{ t('· 最大输出=') }}{{ profile.max_output_tokens }}</dd>
            <dt>{{ t('配置摘要') }}</dt><dd class="technical">{{ profile.profile_identity }}</dd>
          </dl></details>
        </div>
      </article>
    </ResourceManager>
  </section>
</template>
