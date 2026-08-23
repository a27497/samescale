<script setup lang="ts">
import type { TraceResponse } from '@/types/workbench'
import StatusBadge from '@/components/StatusBadge.vue'

defineProps<{ trace: TraceResponse }>()
</script>

<template>
  <div v-if="trace.status === 'NOT_REPORTED'" class="empty-state">
    <StatusBadge value="NOT_REPORTED" />
    <p>TRACE = NOT_REPORTED. No normalized event stream was persisted.</p>
  </div>
  <div v-else>
    <div class="panel-title">
      <div class="toolbar">
        <StatusBadge value="REPORTED" />
        <StatusBadge v-if="trace.coverage" :value="trace.coverage" />
      </div>
      <span class="technical muted">{{ trace.trace_digest }}</span>
    </div>
    <div class="trace-list">
      <div v-for="event in trace.events" :key="event.ordinal" class="trace-event">
        <span class="trace-ordinal">#{{ event.ordinal }}</span>
        <StatusBadge :value="event.type" />
        <div class="trace-summary">
          {{ event.type === 'REASONING_PRESENT' ? 'Reasoning was present; private content is withheld.' : event.summary }}
        </div>
      </div>
    </div>
  </div>
</template>
