<script setup lang="ts">
import ResultImage from './ResultImage.vue'
defineProps<{
  original?: string
  enhanced?: string
  leftLabel?: string
  rightLabel?: string
  downloadName?: string
}>()
</script>
<template>
  <div class="compare-grid">
    <ResultImage
      :src="original"
      :label="leftLabel || '原始图像'"
      empty-text="上传图片后查看原始图像"
    />
    <ResultImage
      :src="enhanced"
      :label="rightLabel || '增强结果'"
      :filename="downloadName || 'lumiface-enhanced.png'"
      :download-label="'下载' + (rightLabel || '增强图像')"
      empty-text="运行处理后查看对比结果"
    />
  </div>
</template>
