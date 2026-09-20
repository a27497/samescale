<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { registryApi } from '@/api/client'
import { t } from '@/composables/i18n'
import LocalModelConfigurations from '@/components/LocalModelConfigurations.vue'
import type { ProviderModelProfile, ProviderDefinition, HarnessDefinition } from '@/types/registry'

const profiles = ref<ProviderModelProfile[]>([])
const providers = ref<ProviderDefinition[]>([]); const harnesses = ref<HarnessDefinition[]>([])
const loading = ref(true); const errors = ref<string[]>([])
let generation = 0
async function load() {
  const current = ++generation
  loading.value = true; errors.value = []; profiles.value = []; providers.value = []; harnesses.value = []
  const [m,p,h] = await Promise.allSettled([registryApi.models(), registryApi.providers(), registryApi.harnesses()])
  if (current !== generation) return
  if (m.status === 'fulfilled') profiles.value = m.value.provider_profiles; else errors.value.push('模型配置')
  if (p.status === 'fulfilled') providers.value = p.value.items; else errors.value.push('模型服务')
  if (h.status === 'fulfilled') harnesses.value = h.value.items; else errors.value.push('执行方式')
  loading.value = false
}
onMounted(load); onBeforeUnmount(() => generation++)
</script>

<template>
  <section class="connections-page">
    <div class="page-heading"><div><h2>{{ t('连接与配置') }}</h2></div><button class="secondary-button" :disabled="loading" @click="load">{{ t('重新读取配置') }}</button></div>
    <p v-if="loading" class="loading-state" role="status">{{ t('正在读取连接与配置…') }}</p>
    <div v-if="errors.length" class="error-state" role="alert">{{ t('以下信息读取失败，相关状态保留未知：') }}{{ errors.map(label => t(label)).join(' / ') }}</div>
    <LocalModelConfigurations :profiles="profiles" :harnesses="harnesses" :providers="providers" @changed="load" />
  </section>
</template>
