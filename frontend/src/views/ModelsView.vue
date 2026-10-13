<script setup lang="ts">
import { statusLabel, metadataLabel } from '@/utils/statusLabels'
import PageState from '@/components/PageState.vue'
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
  Object.entries(model.reasoning_controls).filter(([, enabled]) => enabled).map(([name]) => metadataLabel(name))
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h2>模型注册表</h2><p>模型能力信息与各服务商的路由、实验配置身份分开展示。</p></div>
      <span class="status-pill neutral">只读</span>
    </div>
    <div class="registry-principle"><strong>身份规则</strong><span>模型定义描述能力；每个服务商配置保留独立实验身份，不能混用。</span></div>
    <PageState v-if="loading" kind="loading">正在读取模型注册表…</PageState>
    <PageState v-else-if="error" kind="error" reload>模型注册表暂时无法读取。请检查后端服务后重新加载。</PageState>
    <PageState v-else-if="!models.length" kind="empty">暂无模型定义。请在“连接与配置”中查看本地配置，或由操作员配置服务端注册表。</PageState>
    <div v-else class="registry-card-grid">
      <article v-for="model in models" :key="model.model_id" class="panel registry-card model-card">
        <div class="panel-title">
          <div><span class="panel-kicker">{{ model.model_family }}</span><h3>{{ model.display_name }}</h3></div>
          <StatusBadge :value="model.context_metadata_status" />
        </div>
        <div class="identity-block"><span>模型 ID</span><strong class="technical">{{ model.model_id }}</strong></div>
        <dl class="definition-list compact-definitions">
          <dt>能力</dt><dd><span v-for="capability in model.capabilities" :key="capability" class="metadata-chip">{{ metadataLabel(capability) }}</span><span v-if="!model.capabilities.length">{{ statusLabel('NONE_REPORTED') }}</span></dd>
          <dt>协议</dt><dd>{{ model.supported_protocols.map(metadataLabel).join('、') || statusLabel('NONE_REPORTED') }}</dd>
          <dt>上下文窗口</dt><dd>{{ model.context_window_tokens?.toLocaleString() ?? statusLabel('NOT_AVAILABLE') }} <span v-if="model.context_window_tokens" class="muted">tokens</span></dd>
          <dt>推理控制</dt><dd>{{ enabledControlNames(model).join('、') || statusLabel('NONE_REPORTED') }}</dd>
        </dl>

        <div v-if="!modelProfiles(model.model_id).length" class="notice"><span class="technical">{{ statusLabel('CONFIGURED_MODEL_ID_REQUIRED') }}；请在连接与配置中登记模型。</span></div>
        <details v-else class="profile-details">
          <summary>服务商配置 · {{ modelProfiles(model.model_id).length }} <small>路由与身份详情</small></summary>
          <div v-for="profile in modelProfiles(model.model_id)" :key="profile.profile_id" class="provider-profile">
            <div class="provider-profile-head"><strong class="technical">{{ profile.profile_id }}</strong><StatusBadge :value="profile.enabled ? 'REGISTERED FOR PLANNING' : 'DISABLED'" /></div>
            <dl class="mini-definition-list">
              <dt>服务商 / 协议</dt><dd>{{ profile.provider_id }} / {{ metadataLabel(profile.protocol) }}</dd>
              <dt>请求模型</dt><dd class="technical">{{ profile.requested_model }}</dd>
              <dt>路由身份</dt><dd class="technical">{{ profile.provider_route_identity }}</dd>
              <dt>实际模型依据</dt><dd>{{ statusLabel(profile.observed_model_capability) }}</dd>
              <dt>控制参数</dt><dd>推理强度：{{ metadataLabel(profile.reasoning_effort) }} · 最大输出：{{ profile.max_output_tokens }}</dd>
              <dt>配置摘要</dt><dd class="technical">{{ profile.profile_identity }}</dd>
            </dl>
          </div>
        </details>
      </article>
    </div>
  </section>
</template>
