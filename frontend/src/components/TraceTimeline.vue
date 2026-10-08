<script setup lang="ts">
import type { TraceResponse } from '@/types/workbench'
import StatusBadge from '@/components/StatusBadge.vue'
import { copy as c } from '@/composables/visualLocale'
withDefaults(defineProps<{ trace: TraceResponse; localized?: boolean }>(), { localized: false })
</script>
<template>
  <div v-if="trace.status === 'NOT_REPORTED'" class="empty-state"><StatusBadge value="NOT_REPORTED" :localized="localized" /><p>{{ localized ? c('未报告标准化事件流。缺失记录不代表事件一定没有发生。', 'No normalized event stream was reported. Missing evidence does not imply no events occurred.') : 'TRACE = NOT_REPORTED. No normalized event stream was persisted.' }}</p></div>
  <div v-else><div class="trace-meta toolbar"><StatusBadge value="REPORTED" :localized="localized" /><StatusBadge v-if="trace.coverage" :value="trace.coverage" :localized="localized" /><code class="technical">{{ trace.trace_digest }}</code></div><div class="trace-list"><div v-for="event in trace.events" :key="event.ordinal" class="trace-event"><span class="trace-ordinal">#{{ event.ordinal }}</span><StatusBadge :value="event.type" :localized="localized" /><div class="trace-summary">{{ event.type === 'REASONING_PRESENT' ? (localized ? c('记录中含推理；私有内容不公开。', 'Reasoning was present; private content is withheld.') : 'Reasoning was present; private content is withheld.') : event.summary ?? 'NOT_REPORTED' }}</div><div class="trace-event-state"><code v-if="event.exit_code !== null">exit_code: {{ event.exit_code }}</code><code v-if="event.status">{{ event.status }}</code></div></div></div></div>
</template>
