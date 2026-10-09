<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { TraceResponse } from '@/types/workbench'
import StatusBadge from '@/components/StatusBadge.vue'
import TechnicalDetails from '@/components/TechnicalDetails.vue'
import { copy as c } from '@/composables/visualLocale'
const props = withDefaults(defineProps<{ trace: TraceResponse; localized?: boolean }>(), { localized: false })
const expanded = ref(false)
watch(() => props.trace.run_id, () => { expanded.value = false })
const shown = computed(() => expanded.value ? props.trace.events : props.trace.events.slice(0, 8))
</script>
<template>
  <div v-if="trace.status === 'NOT_REPORTED'" class="empty-state"><StatusBadge value="NOT_REPORTED" :localized="localized" /><p>{{ localized ? c('未报告标准化事件流。缺失记录不代表事件一定没有发生。', 'No normalized event stream was reported. Missing evidence does not imply no events occurred.') : 'TRACE = NOT_REPORTED. No normalized event stream was persisted.' }}</p></div>
  <div v-else><div class="trace-meta toolbar"><StatusBadge value="REPORTED" :localized="localized" /><StatusBadge v-if="trace.coverage" :value="trace.coverage" :localized="localized" /><span>{{ trace.events.length }} {{ c('条事件', 'events') }}</span></div>
    <div class="trace-list"><details v-for="event in shown" :key="event.ordinal" class="trace-event"><summary><span class="trace-ordinal">#{{ event.ordinal }}</span><StatusBadge :value="event.type" :localized="localized" /><span class="trace-summary">{{ event.type === 'REASONING_PRESENT' ? c('私有推理不公开', 'Private reasoning withheld') : event.type === 'AGENT_MESSAGE' ? c('查看消息原文', 'View original message') : event.type === 'FILE_CHANGE' ? c('查看原始记录', 'View original record') : c('查看保存的事件记录', 'View saved event record') }}</span><StatusBadge v-if="event.status" :value="event.status" context="event" :localized="localized" /></summary><div class="trace-event-body"><p class="trace-source">{{ event.type === 'REASONING_PRESENT' ? (localized ? c('记录中含推理；私有内容不公开。', 'Reasoning was present; private content is withheld.') : 'Reasoning was present; private content is withheld.') : event.summary ?? c('未报告', 'Not reported') }}</p><TechnicalDetails :fields="[{ label: c('事件类型', 'Event type'), value: event.type }, { label: c('机器状态', 'Machine state'), value: event.status }, { label: 'exit_code', value: event.exit_code }]" /></div></details></div>
    <button v-if="trace.events.length > 8" class="table-link trace-expand" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? c('收起事件', 'Show fewer events') : c(`查看全部 ${trace.events.length} 条事件`, `View all ${trace.events.length} events`) }}</button>
    <TechnicalDetails :fields="[{ label: 'Run ID', value: trace.run_id }, { label: c('Trace SHA256', 'Trace SHA256'), value: trace.trace_digest }]" :summary="c('Trace 身份与摘要', 'Trace identity & digest')" />
  </div>
</template>
