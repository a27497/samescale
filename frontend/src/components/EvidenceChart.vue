<script setup lang="ts">
import { t } from '@/composables/i18n'
import EvidenceValue from '@/components/EvidenceValue.vue'
import type { EvidenceValue as EvidenceValueType } from '@/types/workbench'

defineProps<{
  title: string
  items: Array<{ label: string; evidence: EvidenceValueType }>
}>()
</script>

<template>
  <dl class="usage-evidence" :aria-label="title">
    <div v-for="item in items" :key="item.label"><dt>{{ t(item.label) }}</dt><dd><EvidenceValue :evidence="item.evidence" /></dd></div>
  </dl>
</template>

<style scoped>
.usage-evidence { margin: 0; }
.usage-evidence > div { display: flex; align-items: baseline; justify-content: space-between; gap: 24px; padding: 12px 0; border-bottom: 1px solid var(--line); }
.usage-evidence dt { color: var(--muted); font: var(--type-caption); }
.usage-evidence dd { margin: 0; font: var(--type-code); }
</style>
