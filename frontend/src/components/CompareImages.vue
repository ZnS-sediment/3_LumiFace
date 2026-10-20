<script setup lang="ts">
import { Download, Picture } from '@element-plus/icons-vue'
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
    <div class="image-panel">
      <div class="panel-label">
        <span>{{ leftLabel || '原始图像' }}</span>
      </div>
      <img v-if="original" :src="original" :alt="leftLabel || '原始图像'" />
      <div v-else class="image-empty">
        <el-icon aria-hidden="true"><Picture /></el-icon>上传图片后查看原始图像
      </div>
    </div>
    <div class="image-panel">
      <div class="panel-label">
        <span>{{ rightLabel || '增强结果' }}</span>
        <a
          v-if="enhanced"
          class="image-download"
          :href="enhanced"
          :download="downloadName || 'lumiface-enhanced.png'"
          :aria-label="'下载' + (rightLabel || '增强图像')"
          ><el-icon aria-hidden="true"><Download /></el-icon>下载图片</a
        >
      </div>
      <img v-if="enhanced" :src="enhanced" :alt="rightLabel || '增强结果'" />
      <div v-else class="image-empty">
        <el-icon aria-hidden="true"><Picture /></el-icon>运行处理后查看对比结果
      </div>
    </div>
  </div>
</template>
