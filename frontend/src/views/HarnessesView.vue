<script setup lang="ts">
import { t } from '@/composables/i18n'
import { runtimeName, runtimeGroup } from '@/composables/registryPresentation'
import { computed, onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import ResourceManager from '@/components/ResourceManager.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import type { HarnessDefinition } from '@/types/registry'

const items = ref<HarnessDefinition[]>([])
const loading = ref(true)
const error = ref(false)
async function load() {
  loading.value = true; error.value = false; items.value = []

  try { items.value = (await registryApi.harnesses()).items }
  catch { error.value = true }
  finally { loading.value = false }
}
onMounted(load)
const resources = computed(() => items.value.map(item => ({ id: item.harness_id, name: runtimeName(item), group: runtimeGroup(item), description: `v${item.version} · ${item.supported_protocols.join(', ')}` })))
</script>

<template>
  <section>
    <button v-if="error && !loading" class="secondary-button retry-button" @click="load">{{ t('重新加载') }}</button>
    <div v-if="loading" class="loading-state">{{ t('正在读取运行配置…') }}</div>
    <div v-else-if="error" class="error-state">{{ t('运行配置读取失败，请重试。') }}</div>
    <div v-else-if="!items.length" class="empty-state">{{ t('暂无运行配置。') }}</div>
    <ResourceManager v-else kind="harnesses" :items="resources" v-slot="{ selectedId }">
      <article v-for="item in items.filter(value => value.harness_id === selectedId)" :key="item.harness_id" class="panel registry-card harness-card">
        <div class="panel-title">
          <div><span class="panel-kicker">{{ t(runtimeGroup(item)) }} · {{ item.harness_id }}</span><h3>{{ runtimeName(item) }} <span class="muted">v{{ item.version }}</span></h3></div>
          <StatusBadge :value="item.runtime_health" />
        </div>
        <div class="harness-facts">
          <div><span>{{ t('轨迹覆盖') }}</span><StatusBadge :value="item.trace_coverage" /></div>
          <div><span>{{ t('网络') }}</span><strong>{{ item.network_capability }}</strong></div>
          <div><span>{{ t('观测模型') }}</span><strong>{{ item.observed_model_exposure }}</strong></div>
        </div>
        <details class="resource-disclosure"><summary>{{ t('运行环境与执行能力') }}</summary><dl class="definition-list compact-definitions">
          <dt>{{ t('镜像') }}</dt><dd class="technical">{{ item.image_reference }}</dd>
          <dt>{{ t('镜像摘要') }}</dt><dd class="technical">{{ item.image_digest ?? 'NOT_REPORTED' }}</dd>
          <dt>{{ t('运行时身份') }}</dt><dd class="technical">{{ item.cli_runtime_identity }}</dd>
          <dt>{{ t('执行器合同') }}</dt><dd class="technical">{{ item.runner_contract }}</dd>
          <dt>{{ t('协议') }}</dt><dd>{{ item.supported_protocols.join(', ') || 'NONE_REPORTED' }}</dd>
          <dt>{{ t('工具范围') }}</dt><dd><span v-for="tool in item.tool_surface" :key="tool" class="metadata-chip">{{ tool }}</span><span v-if="!item.tool_surface.length">NONE</span></dd>
          <dt>{{ t('执行能力') }}</dt><dd>{{ t('原生工具=') }}{{ item.native_tools }} · mcp={{ item.mcp_capability }} {{ t('· 工作区修改=') }}{{ item.workspace_mutation }}</dd>
        </dl></details>
        <div class="subsection-heading"><span>{{ t('运行配置与支持的模型服务') }}</span><b>{{ item.profiles.length }}</b></div>
        <div class="profile-stack">
          <div v-for="profile in item.profiles" :key="profile.profile_id" class="provider-profile">
            <div class="provider-profile-head"><strong class="technical">{{ profile.profile_id }}</strong><span class="muted">{{ t('推理强度=') }}{{ profile.reasoning_effort ?? 'NOT_AVAILABLE' }}</span></div>
            <RouterLink class="table-link" :to="{ path: '/connections', query: { harness: profile.profile_id } }">{{ t('查看连接与兼容性') }}</RouterLink>
            <details class="resource-disclosure"><summary>{{ t('支持的服务配置与摘要') }}</summary><div class="supported-models"><span>{{ t('支持的服务配置') }}</span><code v-for="supported in profile.supported_provider_profile_ids" :key="supported">{{ supported }}</code><em v-if="!profile.supported_provider_profile_ids.length">NONE_REPORTED</em></div>
            <small class="technical">{{ profile.harness_config_identity }}</small></details>
          </div>
        </div>
      </article>
    </ResourceManager>
  </section>
</template>
