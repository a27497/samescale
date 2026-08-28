<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { registryApi } from '@/api/client'
import type { HarnessDefinition } from '@/types/registry'

const items = ref<HarnessDefinition[]>([])
const loading = ref(true)
const error = ref(false)
onMounted(async () => { try { items.value = (await registryApi.harnesses()).items } catch { error.value = true } finally { loading.value = false } })
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>Harness Registry</h2><p>Canonical runtime/profile identities derived from backend implementations.</p></div></div>
    <div v-if="loading" class="loading-state">Loading Harness registry…</div>
    <div v-else-if="error" class="error-state">Harness registry is unavailable.</div>
    <div v-else class="registry-card-grid">
      <article v-for="item in items" :key="item.harness_id" class="panel registry-card">
        <div class="panel-title"><h3>{{ item.display_name }}</h3><span class="status-pill neutral">{{ item.trace_coverage }}</span></div>
        <dl class="definition-list"><dt>Version</dt><dd>{{ item.version }}</dd><dt>Image</dt><dd class="technical">{{ item.image_reference }}</dd><dt>Protocols</dt><dd>{{ item.supported_protocols.join(', ') }}</dd><dt>Tools</dt><dd>{{ item.tool_surface.join(', ') || 'NONE' }}</dd><dt>Network</dt><dd>{{ item.network_capability }}</dd><dt>MCP</dt><dd>{{ item.mcp_capability ? 'SUPPORTED' : 'NOT_SUPPORTED' }}</dd></dl>
        <div class="profile-stack"><div v-for="profile in item.profiles" :key="profile.profile_id" class="profile-line"><strong class="technical">{{ profile.profile_id }}</strong><span>{{ profile.supported_provider_profile_ids.join(', ') }}</span></div></div>
      </article>
    </div>
  </section>
</template>
