<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { init, type ECharts } from '@/charts/echarts'
import EvidenceValue from '@/components/EvidenceValue.vue'
import type { EvidenceValue as EvidenceValueType } from '@/types/workbench'

const props = defineProps<{
  title: string
  items: Array<{ label: string; evidence: EvidenceValueType }>
}>()
const target = ref<HTMLDivElement | null>(null)
let chart: ECharts | null = null

function render() {
  if (!target.value) return
  chart ??= init(target.value)
  chart.setOption({
    animation: false,
    grid: { left: 92, right: 20, top: 18, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: props.items.map((item) => item.label) },
    series: [{ type: 'bar', data: props.items.map((item) => item.evidence.value), itemStyle: { color: '#268f86' } }],
  })
}

watch(() => props.items, () => nextTick(render), { deep: true })
onMounted(render)
onBeforeUnmount(() => chart?.dispose())
</script>

<template>
  <div>
    <div ref="target" class="chart" role="img" :aria-label="title" />
    <div class="chart-summary">
      <span v-for="item in items" :key="item.label" style="margin-right: 16px">
        {{ item.label }}: <EvidenceValue :evidence="item.evidence" />
      </span>
    </div>
  </div>
</template>
