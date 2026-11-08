<script setup lang="ts">
import RequiredLabel from '../components/RequiredLabel.vue'
import { validateRequired } from '../utils/validation'
import { ref } from 'vue'
import ImageUpload from '../components/ImageUpload.vue'
import CompareImages from '../components/CompareImages.vue'
import MethodSelect from '../components/MethodSelect.vue'
import { post, imageForm, useTask, number } from '../api/client'
const file = ref<File>(),
  result = ref<any>(null)
const method = ref('gamma')
const { busy, run } = useTask()
function execute() {
  if (!validateRequired([['输入图像', file.value]])) return
  run(async () => {
    result.value = await post(
      '/enhance/process',
      imageForm(file.value!, { method: method.value, auto_parameters: true }),
    )
  })
}
</script>
<template>
  <div class="workbench">
    <section class="card controls">
      <div class="section-heading">
        <h2>图像处理</h2>
      </div>
      <ImageUpload
        required
        @change="
          (files) => {
            file = files[0]
            result = null
          }
        "
      /><el-form label-position="top"
        ><el-form-item
          ><template #label><RequiredLabel>增强算法</RequiredLabel></template
          ><MethodSelect v-model="method" /></el-form-item></el-form
      ><el-button type="primary" class="full-width" :loading="busy" @click="execute"
        >分析并增强</el-button
      >
    </section>
    <section class="card result-panel" v-loading="busy">
      <div class="section-heading">
        <h2>处理预览</h2>
        <span class="pill">{{ result ? number(result.elapsed_ms) + ' ms' : '等待输入' }}</span>
      </div>
      <CompareImages :original="result?.original" :enhanced="result?.enhanced" />
      <div v-if="result" class="result-facts">
        <span
          >原图亮度 <b>{{ number(result.before.mean_brightness) }}</b></span
        ><span
          >处理后亮度 <b>{{ number(result.after.mean_brightness) }}</b></span
        >
      </div>
      <p v-if="result" class="method-description">{{ result.steps.join('；') }}</p>
    </section>
  </div>
</template>
