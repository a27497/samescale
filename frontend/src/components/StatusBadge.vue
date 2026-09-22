<script setup lang="ts">
import { computed } from 'vue'
import { statusLabel } from '@/composables/labels'

const props = defineProps<{ value: string }>()

const tone = computed(() => {
  if (['COMPARABLE', 'FORMAL', 'QUALIFIED_FOR_SUITE', 'READY', 'completed', 'capability_pass'].includes(props.value)) return 'good'
  if (['NOT_COMPARABLE', 'NOT_QUALIFIED', 'NOT_READY', 'BLOCKED', 'failed', 'infra_failure'].includes(props.value)) return 'bad'
  if (['PARTIALLY_COMPARABLE', 'INFORMAL', 'NOT_VERIFIED', 'NOT_REPORTED', 'NOT_RUN'].includes(props.value)) return 'warn'
  if (['FULL_STREAM', 'FINAL_OUTPUT_ONLY', 'SMOKE'].includes(props.value)) return 'info'
  return 'neutral'
})
</script>

<template>
  <span class="status-pill" :class="tone" :title="value" :data-status="value">{{ statusLabel(value) }}</span>
</template>
