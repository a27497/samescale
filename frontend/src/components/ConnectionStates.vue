<script setup lang="ts">
import { computed } from 'vue'
import { t } from '@/composables/i18n'
import { registryReason } from '@/composables/registryPresentation'
import StatusBadge from './StatusBadge.vue'
import type { ProviderModelProfile, ProviderDefinition, HarnessDefinition, RegistrySettings, CapabilityAssessment } from '@/types/registry'
const props = defineProps<{
  profile?: ProviderModelProfile
  provider?: ProviderDefinition
  harness?: HarnessDefinition
  settings: RegistrySettings | null
  capability?: CapabilityAssessment
}>()
const credential = computed(() => props.settings?.credentials.find(item => item.credential_ref === props.profile?.credential_ref))
</script>
<template>
  <div class="connection-states">
    <section class="connection-state" data-state="credential"><h4>{{ t('凭据') }}</h4>
      <StatusBadge :value="credential?.status ?? 'NOT_REPORTED'" />
      <code v-if="profile">{{ profile.credential_ref }}</code><p>{{ t('仅检查引用是否有值。') }}</p>
    </section>
    <section class="connection-state" data-state="health"><h4>{{ t('连接健康') }}</h4>
      <div class="state-line"><span>{{ t('模型服务') }}</span><StatusBadge :value="provider?.health_status ?? 'UNKNOWN'" /></div>
      <div class="state-line"><span>{{ t('执行方式') }}</span><StatusBadge :value="harness?.runtime_health ?? 'UNKNOWN'" /></div>
      <p>{{ t('服务状态由操作者声明；本页不探测连接。') }}</p>
    </section>
    <section class="connection-state" data-state="compatibility"><h4>{{ t('组合兼容') }}</h4>
      <StatusBadge :value="capability?.status ?? 'NOT_VERIFIED'" />
      <ul v-if="capability?.reason_codes.length" class="state-reasons"><li v-for="code in capability.reason_codes" :key="code"><span>{{ t(registryReason(code)) }}</span><code>{{ code }}</code></li></ul>
      <p v-else>{{ t(capability ? '来自服务端兼容性注册表。' : '缺少此组合的兼容性结果。') }}</p>
    </section>
    <section class="connection-state" data-state="authorization"><h4>{{ t('执行授权') }}</h4>
      <span class="status-pill neutral" data-status="NO_EXECUTION_GRANT">{{ t('此页不授权执行') }}</span>
      <p>{{ t('查看配置、兼容性或保存计划都不会启动评测。') }}</p>
      <details v-if="provider || profile" class="resource-disclosure"><summary>{{ t('配置开关与调用策略') }}</summary>
        <div class="state-line" v-if="provider"><span>{{ t('服务配置') }}</span><StatusBadge :value="provider.enabled ? 'ENABLED' : 'DISABLED'" /></div>
        <div class="state-line" v-if="profile"><span>{{ t('模型配置') }}</span><StatusBadge :value="profile.enabled ? 'ENABLED' : 'DISABLED'" /></div>
        <p>{{ t(provider && profile ? (provider.automation_allowed && profile.automation_allowed ? '配置允许自动调用；实际执行仍需单独授权。' : '配置禁止自动调用。') : '调用策略未完整读取。') }}</p>
      </details>
    </section>
  </div>
</template>
<style scoped>
.connection-states { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }
.connection-state { min-width:0; padding:18px; border:1px solid var(--line); border-radius:10px; background:var(--panel); }
h4 { margin:0 0 12px; font:var(--type-control); font-weight:600; }
p, code, li { font:var(--type-caption); overflow-wrap:anywhere; }
p { color:var(--muted); margin:10px 0 0; }
code { display:block; margin-top:8px; color:var(--muted); }
.state-line { display:flex; justify-content:space-between; gap:10px; margin:8px 0; flex-wrap:wrap; font:var(--type-caption); }
.state-reasons { margin:12px 0 0; padding-left:16px; }.state-reasons li + li { margin-top:12px; }.state-reasons code { font-size:11px; }
@media(max-width:600px) { .connection-states { grid-template-columns:1fr; } }
</style>
