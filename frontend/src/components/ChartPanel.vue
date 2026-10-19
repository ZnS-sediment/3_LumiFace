<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { init, use, type ECharts } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])
const props = defineProps<{ option: EChartsOption }>()
const root = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined
onMounted(() => {
  chart = init(root.value!, {
    textStyle: {
      color: '#374151',
      fontFamily: 'Microsoft YaHei, PingFang SC, sans-serif',
      fontSize: 13,
    },
    legend: { textStyle: { color: '#374151', fontSize: 13 } },
    categoryAxis: {
      axisLabel: { color: '#4b5563', fontSize: 12 },
      axisLine: { lineStyle: { color: '#8995a5' } },
    },
    valueAxis: {
      axisLabel: { color: '#4b5563', fontSize: 12 },
      splitLine: { lineStyle: { color: '#e5e7eb' } },
    },
    tooltip: { textStyle: { color: '#1f2937', fontSize: 13 } },
  })
  chart.setOption(props.option)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(root.value!)
})
watch(
  () => props.option,
  (value) => chart?.setOption(value, true),
)
onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>
<template><div ref="root" class="chart" role="img" aria-label="实验数据可视化图表"></div></template>
