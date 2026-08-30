<script setup lang="ts">
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
      <div><h2>Harness Registry</h2><p>Immutable runtime, image, profile, tool, network, and evidence-surface metadata.</p></div>
      <span class="status-pill neutral">READ ONLY</span>
    </div>
    <div v-if="loading" class="loading-state">Loading Harness registry…</div>
    <div v-else-if="error" class="error-state">Harness registry is unavailable.</div>
    <div v-else-if="!items.length" class="empty-state">No Harness definitions are reported.</div>
    <div v-else class="registry-card-grid">
      <article v-for="item in items" :key="item.harness_id" class="panel registry-card harness-card">
        <div class="panel-title">
          <div><span class="panel-kicker">HARNESS · {{ item.harness_id }}</span><h3>{{ item.display_name }} <span class="muted">v{{ item.version }}</span></h3></div>
          <StatusBadge :value="item.runtime_health" />
        </div>
        <div class="harness-facts">
          <div><span>TRACE</span><StatusBadge :value="item.trace_coverage" /></div>
          <div><span>NETWORK</span><strong>{{ item.network_capability }}</strong></div>
          <div><span>OBSERVED MODEL</span><strong>{{ item.observed_model_exposure }}</strong></div>
        </div>
        <dl class="definition-list compact-definitions">
          <dt>Image</dt><dd class="technical">{{ item.image_reference }}</dd>
          <dt>Image digest</dt><dd class="technical">{{ item.image_digest ?? 'NOT_REPORTED' }}</dd>
          <dt>Runtime identity</dt><dd class="technical">{{ item.cli_runtime_identity }}</dd>
          <dt>Runner contract</dt><dd class="technical">{{ item.runner_contract }}</dd>
          <dt>Protocols</dt><dd>{{ item.supported_protocols.join(', ') || 'NONE_REPORTED' }}</dd>
          <dt>Tool surface</dt><dd><span v-for="tool in item.tool_surface" :key="tool" class="metadata-chip">{{ tool }}</span><span v-if="!item.tool_surface.length">NONE</span></dd>
          <dt>Execution surface</dt><dd>native_tools={{ item.native_tools }} · mcp={{ item.mcp_capability }} · workspace_mutation={{ item.workspace_mutation }}</dd>
        </dl>
        <div class="subsection-heading"><span>Profiles & supported provider-model treatments</span><b>{{ item.profiles.length }}</b></div>
        <div class="profile-stack">
          <div v-for="profile in item.profiles" :key="profile.profile_id" class="provider-profile">
            <div class="provider-profile-head"><strong class="technical">{{ profile.profile_id }}</strong><span class="muted">effort={{ profile.reasoning_effort ?? 'NOT_AVAILABLE' }}</span></div>
            <div class="supported-models"><span>Supported profiles</span><code v-for="supported in profile.supported_provider_profile_ids" :key="supported">{{ supported }}</code><em v-if="!profile.supported_provider_profile_ids.length">NONE_REPORTED</em></div>
            <small class="technical">{{ profile.harness_config_identity }}</small>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>
