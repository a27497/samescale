<script setup lang="ts">
import { computed, inject, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { registryApi } from '@/api/client'
import { productModeKey } from '@/composables/productContext'
import { t } from '@/composables/i18n'
import { runtimeName, runtimeGroup, runtimeProfileGroups } from '@/composables/registryPresentation'
import ConnectionStates from '@/components/ConnectionStates.vue'
import LocalModelConfigurations from '@/components/LocalModelConfigurations.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ModelDefinition, ProviderModelProfile, ProviderDefinition, HarnessDefinition, CapabilityAssessment, RegistrySettings } from '@/types/registry'
const route = useRoute(); const router = useRouter()
const mode = inject(productModeKey, ref('unknown'))
const models = ref<ModelDefinition[]>([]); const profiles = ref<ProviderModelProfile[]>([])
const providers = ref<ProviderDefinition[]>([]); const harnesses = ref<HarnessDefinition[]>([])
const capabilities = ref<CapabilityAssessment[]>([]); const settings = ref<RegistrySettings | null>(null)
const loading = ref(true); const errors = ref<string[]>([])
const harnessProfiles = computed(() => harnesses.value.flatMap(h => h.profiles.map(p => ({ ...p, harness: h }))))
const profileId = computed(() => route.query.profile === undefined ? profiles.value[0]?.profile_id ?? '' : typeof route.query.profile === 'string' ? route.query.profile : '')
const harnessId = computed(() => route.query.harness === undefined ? harnessProfiles.value[0]?.profile_id ?? '' : typeof route.query.harness === 'string' ? route.query.harness : '')
const profile = computed(() => profiles.value.find(p => p.profile_id === profileId.value))
const harness = computed(() => harnessProfiles.value.find(p => p.profile_id === harnessId.value)?.harness)
const provider = computed(() => providers.value.find(p => p.provider_id === profile.value?.provider_id))
const model = computed(() => models.value.find(m => m.model_id === profile.value?.model_id))
const capability = computed(() => profile.value && harness.value ? capabilities.value.find(c => c.provider_profile_id === profileId.value && c.harness_profile_id === harnessId.value) : undefined)
function select(key: 'profile' | 'harness', event: Event) {
  void router.push({ query: { ...route.query, profile: profileId.value, harness: harnessId.value, [key]: (event.target as HTMLSelectElement).value } })
}
let generation = 0
async function load() {
  const current = ++generation
  loading.value = true; errors.value = []; profiles.value = []; models.value = []; providers.value = []; harnesses.value = []; capabilities.value = []; settings.value = null
  const results = await Promise.allSettled([registryApi.models(), registryApi.providers(), registryApi.harnesses(), registryApi.capabilities(), registryApi.settings()])
  if (current !== generation) return
  const [m,p,h,c,s] = results
  if (m.status === 'fulfilled') { models.value = m.value.models; profiles.value = m.value.provider_profiles } else errors.value.push('模型配置')
  if (p.status === 'fulfilled') providers.value = p.value.items; else errors.value.push('模型服务')
  if (h.status === 'fulfilled') harnesses.value = h.value.items; else errors.value.push('执行方式')
  if (c.status === 'fulfilled') capabilities.value = c.value.items; else errors.value.push('组合兼容')
  if (s.status === 'fulfilled') settings.value = s.value; else errors.value.push('凭据与默认值')
  loading.value = false
}
onMounted(load); onBeforeUnmount(() => generation++)
</script>
<template>
  <section class="connections-page">
    <div class="page-heading"><div><h2>{{ t('连接与配置') }}</h2><p>{{ t('选择模型配置和执行方式。') }}</p></div><span class="status-pill neutral">{{ t('内置目录只读') }}</span></div>
    <div class="connections-toolbar"><RouterLink class="table-link" to="/settings#appearance">{{ t('外观与阅读') }}</RouterLink><button class="secondary-button" :disabled="loading" @click="load">{{ t('重新读取配置') }}</button></div>
    <p v-if="loading" class="loading-state" role="status">{{ t('正在读取连接与配置…') }}</p>
    <template v-else>
      <div v-if="errors.length" class="error-state" role="alert">{{ t('以下信息读取失败，相关状态保留未知：') }}{{ errors.map(label => t(label)).join(' / ') }}</div>
      <div class="connection-selectors">
        <label>{{ t('模型服务配置') }}<select :value="profileId" :aria-label="t('模型服务配置')" @change="select('profile', $event)"><option v-if="!profile" :value="profileId" disabled>{{ t('配置未找到') }}</option><option v-for="p in profiles" :key="p.profile_id" :value="p.profile_id">{{ p.profile_id }}</option></select></label>
        <label>{{ t('执行方式') }}<select :value="harnessId" :aria-label="t('执行方式')" @change="select('harness', $event)"><option v-if="!harness" :value="harnessId" disabled>{{ t('配置未找到') }}</option><optgroup v-for="group in runtimeProfileGroups(harnesses)" :key="group.label" :label="t(group.label)"><option v-for="p in group.profiles" :key="p.profile_id" :value="p.profile_id">{{ p.profile_id }}</option></optgroup></select></label>
      </div>
      <p v-if="!profiles.length || !harnessProfiles.length" class="notice">{{ t('模型或运行配置缺失。') }}</p>
      <p v-else-if="!profile || !harness" class="notice" role="status">{{ t('链接中的配置已不存在，请重新选择。') }}</p>
      <nav class="connection-relations" :aria-label="t('当前配置关系')">
        <RouterLink v-if="profile" :to="{ path: '/models', query: { id: profile.model_id } }"><small>{{ t('模型') }}</small><strong>{{ model?.display_name ?? profile.model_id }}</strong><span>{{ profile.requested_model }}</span></RouterLink>
        <RouterLink v-if="profile" :to="{ path: '/providers', query: { id: profile.provider_id } }"><small>{{ t('模型服务') }}</small><strong>{{ provider?.display_name ?? profile.provider_id }}</strong><span>{{ profile.protocol }}</span></RouterLink>
        <RouterLink v-if="harness" :to="{ path: '/harnesses', query: { id: harness.harness_id } }"><small>{{ t(runtimeGroup(harness)) }}</small><strong>{{ runtimeName(harness) }}</strong><span>v{{ harness.version }}</span></RouterLink>
      </nav>
      <ConnectionStates :profile="profile" :provider="provider" :harness="harness" :settings="settings" :capability="capability" />
      <p class="connections-note">{{ t('模型配置关联服务与凭据；运行配置列出支持的模型配置。') }}</p>
      <div class="connections-links"><RouterLink to="/models">{{ t('全部模型') }}</RouterLink><RouterLink to="/providers">{{ t('全部模型服务') }}</RouterLink><RouterLink to="/harnesses">{{ t('全部运行配置') }}</RouterLink><RouterLink to="/capabilities">{{ t('全部兼容组合') }}</RouterLink><RouterLink v-if="mode === 'workspace'" to="/experiments/new">{{ t('创建评测计划') }}</RouterLink></div>
      <section id="runtime" class="settings-section" aria-labelledby="runtime-title"><div class="settings-section-heading"><h3 id="runtime-title">{{ t('运行默认值') }}</h3><span>{{ t('服务端只读') }}</span></div>
        <p v-if="!settings">{{ t('默认值与凭据状态未读取。') }}</p>
        <template v-else><dl class="definition-list settings-definitions">
          <dt>{{ t('默认模型配置') }}</dt><dd class="technical">{{ settings.defaults.default_provider_profile_id }}</dd>
          <dt>{{ t('评测模式') }}</dt><dd><StatusBadge :value="settings.defaults.default_evaluation_mode" /></dd>
          <dt>{{ t('调度种子') }}</dt><dd>{{ settings.defaults.default_schedule_seed }}</dd>
          <dt>{{ t('并行运行上限') }}</dt><dd>{{ settings.defaults.default_concurrency }}</dd>
          <dt>{{ t('费用预算') }}</dt><dd>{{ settings.defaults.default_cost_budget ?? t('未配置') }}</dd>
        </dl><details id="credentials" class="credential-details"><summary>{{ t('全部凭据引用') }} · {{ settings.credentials.length }}</summary><p v-if="!settings.credentials.length">{{ t('未声明凭据引用。') }}</p><div v-for="item in settings.credentials" :key="item.credential_ref" class="settings-row"><code class="technical">{{ item.credential_ref }}</code><StatusBadge :value="item.status" /></div></details></template>
        <p class="connections-note">{{ t(mode === 'workspace' ? '内置服务、凭据与运行默认值仍为只读。本地模型配置在下方管理。' : '当前网页不编辑 API Key 或服务端配置。') }}</p>
      </section>
    </template>
    <LocalModelConfigurations v-if="mode === 'workspace'" :profiles="profiles" :harnesses="harnesses" :providers="providers" @changed="load" />
  </section>
</template>
<style scoped>
.connections-page { max-width:1040px; margin:0 auto; }
.connections-toolbar, .connections-links { display:flex; flex-wrap:wrap; align-items:center; gap:18px; margin-bottom:24px; }.connections-toolbar button { margin-left:auto; }
.connection-selectors { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:20px; margin:24px 0; }
.connection-selectors label { display:grid; gap:8px; min-width:0; font:var(--type-control); }
select { width:100%; min-width:0; padding:10px; border:1px solid var(--line); border-radius:6px; background:var(--panel); color:var(--ink); font:var(--type-control); }
.connection-relations { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin-bottom:20px; }
.connection-relations a { display:grid; gap:6px; padding:16px; border:1px solid var(--line); border-radius:8px; text-decoration:none; color:var(--ink); min-width:0; overflow-wrap:anywhere; }
.connection-relations small, .connection-relations span, .connections-note { font:var(--type-caption); color:var(--muted); }.connections-note { margin:16px 0 24px; }
.connections-links a { font:var(--type-control); }.settings-section { margin-top:24px; }
@media(max-width:600px) { .connection-selectors { grid-template-columns:1fr; }.connection-relations { grid-template-columns:1fr; }.connections-toolbar { gap:12px; } }
</style>
