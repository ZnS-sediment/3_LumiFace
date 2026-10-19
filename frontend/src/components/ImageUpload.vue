<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import { UploadFilled, Picture } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import RequiredLabel from './RequiredLabel.vue'
const props = defineProps<{ multiple?: boolean; required?: boolean }>()
const emit = defineEmits<{ change: [files: File[]] }>()
const preview = ref('')
const names = ref<string[]>([])
const input = ref<HTMLInputElement>()
function choose(files: FileList | File[] | null) {
  if (!files?.length) return
  const list = Array.from(files)
  if (
    list.length > (props.multiple ? 10 : 1) ||
    list.some(
      (f) => !['image/jpeg', 'image/png'].includes(f.type) || !f.size || f.size > 12 * 1024 * 1024,
    )
  ) {
    ElMessage.error(`请选择有效 JPG/PNG 图片，每张 ≤12 MB，最多 ${props.multiple ? 10 : 1} 张`)
    return
  }
  URL.revokeObjectURL(preview.value)
  preview.value = URL.createObjectURL(list[0]!)
  names.value = list.map((x) => x.name)
  emit('change', list)
}
function chooseFile() {
  if (input.value) {
    input.value.value = ''
    input.value.click()
  }
}
function dropped(event: DragEvent) {
  choose(event.dataTransfer?.files || null)
}
onBeforeUnmount(() => URL.revokeObjectURL(preview.value))
</script>
<template>
  <p v-if="required" class="upload-field-label"><RequiredLabel>输入图像</RequiredLabel></p>
  <div class="upload-area" @dragover.prevent @drop.prevent="dropped">
    <input
      ref="input"
      class="sr-only"
      type="file"
      :multiple="multiple"
      accept="image/jpeg,image/png"
      aria-label="上传图片"
      @change="choose(($event.target as HTMLInputElement).files)"
    /><button type="button" class="upload-button" @click="chooseFile">
      <img v-if="preview" :src="preview" alt="已选原始图像预览" /><template v-else
        ><span class="upload-icon"
          ><el-icon><UploadFilled /></el-icon></span
        ><strong>拖拽图像到此处，或点击上传</strong><span>JPG / PNG · 单张不超过 12 MB</span
        ><span v-if="multiple">支持 1–10 张参考照片</span></template
      >
    </button>
    <div v-if="names.length" class="file-caption">
      <el-icon><Picture /></el-icon><span>{{ names.join('、') }}</span
      ><el-button text size="small" @click="chooseFile">重新选择</el-button>
    </div>
  </div>
</template>
