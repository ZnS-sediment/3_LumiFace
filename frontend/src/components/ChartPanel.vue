<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as echarts from 'echarts'
const props = defineProps<{option:echarts.EChartsOption}>()
const root = ref<HTMLDivElement>()
let chart:echarts.ECharts | undefined
let observer:ResizeObserver | undefined
onMounted(()=>{chart=echarts.init(root.value!);chart.setOption(props.option);observer=new ResizeObserver(()=>chart?.resize());observer.observe(root.value!)})
watch(()=>props.option, value=>chart?.setOption(value,true),{deep:true})
onBeforeUnmount(()=>{observer?.disconnect();chart?.dispose()})
</script>
<template><div ref="root" class="chart" role="img" aria-label="实验数据可视化图表"></div></template>
