<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { configName, taskName } from '@/utils/displayIdentity'
import { copy as c } from '@/composables/visualLocale'
import { init, type ECharts } from '@/charts/echarts'
import { escapeTooltipText } from '@/charts/safeTooltip'
import type { MatrixMetricKey, MatrixResponse } from '@/types/workbench'

const props = defineProps<{ matrix: MatrixResponse; metric: MatrixMetricKey; localized?: boolean }>()
const chartElement = ref<HTMLDivElement | null>(null)
let chart: ECharts | null = null

const textualSummary = computed(() =>
  props.matrix.points.map((point) => {
    const evidence = point.metrics[props.metric]
    const value = evidence.status === 'REPORTED' ? String(evidence.value) : 'NOT_REPORTED'
    return props.localized
      ? `${point.task_id} / ${point.cell_id}: ${c('数值', 'value')}=${value}; ${c('样本量', 'n')}=${point.n}; ${c('证据层级', 'tier')}=${point.tier}; ${c('可比性', 'comparability')}=${point.comparability}`
      : `${point.task_id} / ${point.cell_id}: ${value}; n=${point.n}; ${point.tier}; ${point.comparability}`
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
    grid: { left: 150, right: 28, top: 34, bottom: 88 },
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
    xAxis: { type: 'category', data: props.localized ? props.matrix.cells.map(cell => configName(cell, props.matrix.cells)) : props.matrix.cells, axisLabel: { rotate: 18, fontSize: 12 } },
    yAxis: { type: 'category', data: props.localized ? props.matrix.tasks.map(taskName) : props.matrix.tasks, axisLabel: { fontSize: 12 } },
    visualMap: {
      min: 0,
      max,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 2,
      inRange: { color: ['#edf4f3', '#84c9c1', '#126f68'] },
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
          fontSize: 12,
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
onMounted(renderChart)
onBeforeUnmount(() => chart?.dispose())
</script>

<template>
  <div>
    <div ref="chartElement" class="chart" role="img" :aria-label="`${localized ? c('任务矩阵', 'Matrix heatmap') : 'Matrix heatmap'}: ${metric}`" />
    <details class="matrix-source"><summary>{{ localized ? c('矩阵原始数据', 'Matrix source data') : 'Matrix source data' }}</summary><ul class="chart-summary" :aria-label="localized ? c('矩阵原始数据摘要', 'Matrix textual summary') : 'Matrix textual summary'">
      <li v-for="item in textualSummary" :key="item">{{ item }}</li>
    </ul></details>
  </div>
</template>
