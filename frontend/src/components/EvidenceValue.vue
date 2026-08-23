<script setup lang="ts">
import type { EvidenceValue } from '@/types/workbench'
import StatusBadge from '@/components/StatusBadge.vue'

withDefaults(
  defineProps<{
    evidence: EvidenceValue
    digits?: number
    suffix?: string
  }>(),
  { digits: 2, suffix: '' },
)
</script>

<template>
  <span v-if="evidence.status === 'REPORTED' && evidence.value !== null" class="technical">
    {{ evidence.value.toFixed(digits) }}{{ suffix }}
  </span>
  <StatusBadge v-else value="NOT_REPORTED" />
</template>
