<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ value: string }>()
const human: Record<string, string> = {
  failed_subject: 'Failed verification',
  capability_fail: 'Task failed',
  capability_pass: 'Task passed',
  infra_failure: 'Infrastructure failure',
  completed: 'Completed',
  FAIL: 'Verifier failed',
  PASS: 'Verifier passed',
  VERIFIED_FAIL: 'Verified failure',
  VERIFIED_PASS: 'Verified pass',
  FIXTURE_OFFLINE: 'Offline fixture',
  PERSISTED_EXECUTION_UNVERIFIED: 'Saved execution · source unverified',
  UNVERIFIED_SOURCE: 'Source unverified',
}
const label = computed(() => human[props.value] ?? props.value)

const tone = computed(() => {
  if (['COMPARABLE', 'FORMAL', 'QUALIFIED_FOR_SUITE', 'READY', 'completed', 'capability_pass'].includes(props.value)) return 'good'
  if (['NOT_COMPARABLE', 'NOT_QUALIFIED', 'NOT_READY', 'BLOCKED', 'failed', 'failed_subject', 'capability_fail', 'infra_failure', 'VERIFIED_FAIL', 'FAIL'].includes(props.value)) return 'bad'
  if (['PARTIALLY_COMPARABLE', 'INFORMAL', 'NOT_VERIFIED', 'NOT_REPORTED', 'NOT_RUN'].includes(props.value)) return 'warn'
  if (['FULL_STREAM', 'FINAL_OUTPUT_ONLY', 'SMOKE', 'FIXTURE_OFFLINE'].includes(props.value)) return 'info'
  return 'neutral'
})
</script>

<template>
  <span class="status-pill" :class="tone" :title="value">{{ label }}</span>
</template>
