<script setup lang="ts">
import { Download } from '@element-plus/icons-vue'
defineProps<{
  src?: string
  label: string
  filename?: string
  downloadLabel?: string
  emptyText?: string
}>()
</script>
<template>
  <div class="image-panel">
    <div class="panel-label">
      <span>{{ label }}</span
      ><a
        v-if="src && filename"
        class="image-download"
        :href="src"
        :download="filename"
        :aria-label="downloadLabel || '下载' + label"
        ><el-icon aria-hidden="true"><Download /></el-icon>下载图片</a
      >
    </div>
    <img v-if="src" :src="src" :alt="label" />
    <div v-else class="image-empty">{{ emptyText || '上传图片并开始处理' }}</div>
  </div>
</template>
