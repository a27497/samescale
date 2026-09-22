<script setup lang="ts">
import { t } from '@/composables/i18n'
import type { TraceResponse } from '@/types/workbench'
import StatusBadge from '@/components/StatusBadge.vue'

defineProps<{ trace: TraceResponse }>()
</script>

<template>
  <div v-if="trace.status === 'NOT_REPORTED'" class="empty-state">
    <StatusBadge value="NOT_REPORTED" />
    <p>{{ t('轨迹尚未报告，没有已保存的标准化事件流。') }}</p>
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
          {{ event.type === 'REASONING_PRESENT' ? t('检测到推理过程；不展示私有内容。') : event.summary }}
        </div>
      </div>
    </div>
  </div>
</template>
