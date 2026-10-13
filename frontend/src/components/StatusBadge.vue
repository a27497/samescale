<script setup lang="ts">
import { computed } from 'vue'
import { statusLabel, statusTone, type StatusContext } from '@/utils/statusLabels'
const props = withDefaults(defineProps<{ value: string; localized?: boolean; context?: StatusContext }>(), { localized: true, context: 'generic' })
const label = computed(() => statusLabel(props.value, props.context))
const tone = computed(() => statusTone(props.value))
</script>
<template><span class="status-pill" :class="tone" :data-status="value" :data-context="context" :title="value"><span>{{ label }}</span></span></template>
