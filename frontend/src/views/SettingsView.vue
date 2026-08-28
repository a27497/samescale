<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { RegistrySettings } from '@/types/registry'

const settings = ref<RegistrySettings | null>(null)
const loading = ref(true)
const error = ref(false)
onMounted(async () => { try { settings.value = await registryApi.settings() } catch { error.value = true } finally { loading.value = false } })
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Settings Lite</h2><p>References and planning preferences only. 浏览器不读取或编辑密钥。</p></div></div>
    <div v-if="loading" class="loading-state">Loading safe settings…</div><div v-else-if="error" class="error-state">Settings are unavailable.</div>
    <template v-else-if="settings"><div class="section-grid"><div class="panel"><div class="panel-title"><h3>Planning defaults</h3></div><dl class="definition-list"><dt>Provider profile</dt><dd class="technical">{{ settings.defaults.default_provider_profile_id }}</dd><dt>Evaluation mode</dt><dd>{{ settings.defaults.default_evaluation_mode }}</dd><dt>Schedule seed</dt><dd>{{ settings.defaults.default_schedule_seed }}</dd><dt>Concurrency</dt><dd>{{ settings.defaults.default_concurrency }}</dd><dt>Cost budget</dt><dd>{{ settings.defaults.default_cost_budget ?? 'NOT_AVAILABLE' }}</dd></dl></div><div class="panel"><div class="panel-title"><h3>Credential references</h3></div><div v-for="item in settings.credentials" :key="item.credential_ref" class="credential-row"><span class="technical">{{ item.credential_ref }}</span><StatusBadge :value="item.status" /></div><div class="notice">Secret editing is intentionally unavailable. Configure credentials through the operator environment.</div></div></div></template>
  </section>
</template>
