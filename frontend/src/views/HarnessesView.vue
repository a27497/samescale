<script setup lang="ts">
import { statusLabel, metadataLabel } from '@/utils/statusLabels'
import TechnicalDetails from '@/components/TechnicalDetails.vue'
import { harnessDisplayName } from '@/utils/displayIdentity'
import PageState from '@/components/PageState.vue'
import { onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { HarnessDefinition } from '@/types/registry'

const items = ref<HarnessDefinition[]>([])
const loading = ref(true)
const error = ref(false)
onMounted(async () => {
  try { items.value = (await registryApi.harnesses()).items }
  catch { error.value = true }
  finally { loading.value = false }
})
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h2>Harness 注册表</h2><p>查看固定的运行环境、镜像、配置、工具、网络与证据覆盖信息。</p></div>
      <span class="status-pill neutral">只读</span>
    </div>
    <PageState v-if="loading" kind="loading">正在读取 Harness 注册表…</PageState>
    <PageState v-else-if="error" kind="error" reload>Harness 注册表暂时无法读取。请检查后端服务后重新加载。</PageState>
    <PageState v-else-if="!items.length" kind="empty">暂无 Harness 定义。请由操作员检查服务端注册表或本地 Harness 配置。</PageState>
    <div v-else class="registry-card-grid">
      <article v-for="item in items" :key="item.harness_id" class="panel registry-card harness-card">
        <div class="panel-title">
          <div><span class="panel-kicker">执行方式</span><h3 :title="item.display_name">{{ harnessDisplayName(item) }} <span class="muted">v{{ item.version }}</span></h3></div>
          <StatusBadge :value="item.runtime_health" />
        </div>
        <div class="harness-facts">
          <div><span>事件记录</span><StatusBadge :value="item.trace_coverage" /></div>
          <div><span>网络访问</span><strong>{{ statusLabel(item.network_capability) }}</strong></div>
          <div><span>实际模型依据</span><strong>{{ statusLabel(item.observed_model_exposure) }}</strong></div>
        </div>
        <dl class="definition-list compact-definitions">
          <dt>镜像</dt><dd class="technical">{{ item.image_reference }}</dd>
          <dt>镜像摘要</dt><dd class="technical">{{ item.image_digest ?? statusLabel('NOT_REPORTED') }}</dd>
          <dt>执行器契约</dt><dd class="technical">{{ item.runner_contract }}</dd>
          <dt>协议</dt><dd>{{ item.supported_protocols.map(metadataLabel).join('、') || statusLabel('NONE_REPORTED') }}</dd>
          <dt>工具能力</dt><dd><span v-for="tool in item.tool_surface" :key="tool" class="metadata-chip">{{ metadataLabel(tool) }}</span><span v-if="!item.tool_surface.length">{{ statusLabel('NONE') }}</span></dd>
          <dt>执行能力</dt><dd>原生工具：{{ item.native_tools ? '支持' : '不支持' }} · MCP：{{ item.mcp_capability ? '支持' : '不支持' }} · 工作区修改：{{ item.workspace_mutation ? '允许' : '只读' }}</dd>
        </dl>
        <TechnicalDetails summary="原始名称与运行环境身份" :fields="[
          { label: '原始名称', value: item.display_name }, { label: 'Harness ID', value: item.harness_id },
          { label: '版本', value: item.version }, { label: '运行环境身份', value: item.cli_runtime_identity },
        ]" />
        <details class="profile-details">
          <summary>配置与支持的模型组合 · {{ item.profiles.length }} <small>支持列表</small></summary>
          <div class="profile-stack">
            <div v-for="profile in item.profiles" :key="profile.profile_id" class="provider-profile">
              <div class="provider-profile-head"><strong class="technical">{{ profile.profile_id }}</strong><span class="muted">推理强度：{{ metadataLabel(profile.reasoning_effort) }}</span></div>
              <div class="supported-models"><span>支持的配置</span><code v-for="supported in profile.supported_provider_profile_ids" :key="supported">{{ supported }}</code><em v-if="!profile.supported_provider_profile_ids.length">{{ statusLabel('NONE_REPORTED') }}</em></div>
              <small class="technical">{{ profile.harness_config_identity }}</small>
            </div>
          </div>
        </details>
      </article>
    </div>
  </section>
</template>
