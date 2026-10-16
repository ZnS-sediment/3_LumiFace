<script setup lang="ts">
defineProps<{original?:string;enhanced?:string;leftLabel?:string;rightLabel?:string}>()
</script>
<template><div class="compare-grid"><div class="image-panel"><div class="panel-label"><span>{{leftLabel || '原始图像'}}</span><small>BEFORE</small></div><img v-if="original" :src="original" :alt="leftLabel || '原始图像'"><div v-else class="image-empty"><span>⌗</span>上传图片后查看原始图像</div></div><div class="image-panel"><div class="panel-label"><span>{{rightLabel || '增强结果'}}</span><small>AFTER</small></div><img v-if="enhanced" :src="enhanced" :alt="rightLabel || '增强结果'"><div v-else class="image-empty"><span>✧</span>运行处理后查看对比结果</div></div></div></template>
