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
      <div><h2>设置</h2><p>查看实验默认参数和环境配置是否存在；页面不读取密钥值。</p></div>
      <span class="status-pill neutral">服务端管理</span>
    </div>
    <div class="settings-security-banner"><span class="security-mark">•••</span><div><strong>仅展示配置状态</strong><p>请在服务端配置凭据。网页只展示引用名和是否已配置，密钥值不会传到浏览器。</p></div></div>
    <PageState v-if="loading" kind="loading">正在读取设置…</PageState>
    <PageState v-else-if="error" kind="error" reload>设置暂时无法读取。请检查后端服务后重新加载。</PageState>
    <template v-else-if="settings">
      <div class="section-grid settings-grid">
        <div class="panel">
          <div class="panel-title"><div><span class="panel-kicker">实验规划</span><h3>实验默认参数</h3></div><span class="status-pill neutral">非敏感参数</span></div>
          <dl class="definition-list settings-definitions">
            <dt>服务商配置</dt><dd class="technical">{{ settings.defaults.default_provider_profile_id }}</dd>
            <dt>评测模式</dt><dd><StatusBadge :value="settings.defaults.default_evaluation_mode" /></dd>
            <dt>调度随机种子</dt><dd>{{ settings.defaults.default_schedule_seed }}</dd>
            <dt>并发数</dt><dd>{{ settings.defaults.default_concurrency }}</dd>
            <dt>费用预算</dt><dd>{{ settings.defaults.default_cost_budget ?? '未设置' }}</dd>
          </dl>
          <div class="notice">这些参数用于服务端预检；重复次数与验证规则仍由服务端评测方法决定。</div>
        </div>
        <div class="panel">
          <div class="panel-title"><div><span class="panel-kicker">环境配置</span><h3>凭据配置状态</h3></div><span>{{ configuredCredentials }} / {{ settings.credentials.length }} 已配置</span></div>
          <PageState v-if="!settings.credentials.length" kind="empty">暂无凭据引用。请由操作员在服务端登记所需环境变量。</PageState>
          <div v-for="item in settings.credentials" :key="item.credential_ref" class="credential-row"><span><strong class="technical">{{ item.credential_ref }}</strong><small>不展示密钥值</small></span><StatusBadge :value="item.status" /></div>
          <div class="secret-editing-state"><span>网页密钥编辑</span><strong>{{ settings.secret_editing_supported ? '支持' : '请在服务端配置' }}</strong></div>
        </div>
      </div>
      <div class="panel provider-settings-panel">
        <div class="panel-title"><div><span class="panel-kicker">服务商</span><h3>规划登记状态</h3></div><RouterLink class="table-link" to="/providers">查看运行环境状态 →</RouterLink></div>
        <div class="notice">已登记或启用表示可以规划；执行还需要配置凭据、可用的运行环境和通过预检。</div>
        <div class="provider-toggle-grid">
          <div v-for="(enabled, provider) in settings.provider_enabled" :key="provider" class="provider-toggle-row"><span class="technical">{{ provider }}</span><StatusBadge :value="enabled ? 'REGISTERED FOR PLANNING' : 'DISABLED'" /></div>
        </div>
      </div>
    </template>
  </section>
</template>
