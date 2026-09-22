<script setup lang="ts">
import { t } from '@/composables/i18n'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { init, type ECharts } from '@/charts/echarts'
import { escapeTooltipText } from '@/charts/safeTooltip'
import type { MatrixMetricKey, MatrixResponse } from '@/types/workbench'

const props = defineProps<{ matrix: MatrixResponse; metric: MatrixMetricKey }>()
const chartElement = ref<HTMLDivElement | null>(null)
let chart: ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const textualSummary = computed(() =>
  props.matrix.points.map((point) => {
    const evidence = point.metrics[props.metric]
    const value = evidence.status === 'REPORTED' ? String(evidence.value) : 'NOT_REPORTED'
    return `${point.task_id} / ${point.cell_id}: ${value}; n=${point.n}; ${point.tier}; ${point.comparability}`
  }),
)

function renderChart() {
  if (!chartElement.value) return
  chart ??= init(chartElement.value)
  const numericValues = props.matrix.points
    .map((point) => point.metrics[props.metric].value)
    .filter((value): value is number => value !== null)
  const max = numericValues.length ? Math.max(...numericValues) : 1
  chart.setOption({
    animation: false,
    textStyle: { fontFamily: getComputedStyle(document.documentElement).fontFamily, fontSize: 13 },
    grid: { left: 150, right: 28, top: 34, bottom: 64 },
    tooltip: {
      formatter: (raw: unknown) => {
        const params = raw as { dataIndex: number }
        const point = props.matrix.points[params.dataIndex]
        if (!point) return ''
        const evidence = point.metrics[props.metric]
        return [
          `<strong>${escapeTooltipText(point.cell_id)}</strong> × ${escapeTooltipText(point.task_id)}`,
          `${escapeTooltipText(props.metric)}: ${evidence.status === 'REPORTED' ? evidence.value : 'NOT_REPORTED'}`,
          `n=${point.n} · tier=${escapeTooltipText(point.tier)}`,
          `comparability=${escapeTooltipText(point.comparability)}`,
        ].join('<br/>')
      },
    },
    xAxis: { type: 'category', data: props.matrix.cells, axisLabel: { rotate: 18 } },
    yAxis: { type: 'category', data: props.matrix.tasks },
    visualMap: {
      min: 0,
      max,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 2,
      inRange: { color: ['#f0f2f5', '#b1bfce', '#536b86'] },
    },
    series: [
      {
        type: 'heatmap',
        data: props.matrix.points.map((point) => [
          props.matrix.cells.indexOf(point.cell_id),
          props.matrix.tasks.indexOf(point.task_id),
          point.metrics[props.metric].value,
        ]),
        label: {
          show: true,
          formatter: (raw: unknown) => {
            const params = raw as { dataIndex: number }
            const evidence = props.matrix.points[params.dataIndex]?.metrics[props.metric]
            return evidence?.status === 'REPORTED' && evidence.value !== null
              ? evidence.value.toFixed(2)
              : 'N/R'
          },
        },
      },
    ],
  })
}

watch(() => [props.matrix, props.metric], () => nextTick(renderChart), { deep: true })
onMounted(() => {
  renderChart()
  if (typeof ResizeObserver !== 'undefined' && chartElement.value) { resizeObserver = new ResizeObserver(() => chart?.resize()); resizeObserver.observe(chartElement.value) }
})
onBeforeUnmount(() => { resizeObserver?.disconnect(); chart?.dispose() })
</script>

<template>
  <div>
    <div ref="chartElement" class="chart" role="img" :aria-label="`矩阵热图：${metric}`" />
    <ul class="chart-summary" :aria-label="t('矩阵文字摘要')">
      <li v-for="item in textualSummary" :key="item">{{ item }}</li>
    </ul>
  </div>
</template>
