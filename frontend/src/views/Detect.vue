<script setup lang="ts">
import RequiredLabel from '../components/RequiredLabel.vue'
import { validateRequired } from '../utils/validation'
import { ref } from 'vue'
import ImageUpload from '../components/ImageUpload.vue'
import ResultImage from '../components/ResultImage.vue'
import MethodSelect from '../components/MethodSelect.vue'
import { post, imageForm, useTask, number } from '../api/client'
const file = ref<File>(),
  enabled = ref(false),
  method = ref('gamma'),
  result = ref<any>(null)
const { busy, run } = useTask()
function execute() {
  if (!validateRequired([['输入图像', file.value]])) return
  run(async () => {
    result.value = await post(
      '/face/detect',
      imageForm(file.value!, {
        method: enabled.value ? method.value : 'original',
        auto_parameters: true,
      }),
    )
  })
}
</script>
<template>
  <div class="workbench">
    <section class="card controls">
      <div class="section-heading"><h2>检测设置</h2></div>
      <ImageUpload
        required
        @change="
          (files) => {
            file = files[0]
            result = null
          }
        "
      />
      <el-form label-position="top">
        <el-form-item label="检测前增强"
          ><el-switch v-model="enabled" active-text="开启" inactive-text="关闭"
        /></el-form-item>
        <el-form-item v-if="enabled"
          ><template #label><RequiredLabel>增强算法</RequiredLabel></template
          ><MethodSelect v-model="method"
        /></el-form-item>
      </el-form>
      <el-button type="primary" class="full-width" :loading="busy" @click="execute"
        >开始检测</el-button
      >
      <p class="muted">支持单图多人脸。绿色框标记人脸，彩色点标记五点关键点。</p>
    </section>
    <section class="card result-panel" v-loading="busy">
      <div class="section-heading">
        <h2>检测结果</h2>
        <span class="pill">SCRFD</span>
      </div>
      <ResultImage :src="result?.image" label="人脸检测图像" filename="lumiface-detection.png" />
      <div v-if="result" class="result-facts">
        <span
          >人脸数量 <b>{{ result.count }}</b></span
        ><span
          >总耗时 <b>{{ number(result.total_ms) }} ms</b></span
        >
      </div>
    </section>
  </div>
  <section v-if="result" class="card quality-card">
    <div class="section-heading">
      <h2>人脸明细与对齐裁剪</h2>
      <span>112 × 112</span>
    </div>
    <el-table :data="result.faces" empty-text="未检测到人脸">
      <el-table-column label="对齐人脸" width="130"
        ><template #default="{ row }"
          ><img :src="row.aligned_crop" class="face-thumb" alt="对齐人脸裁剪" /></template
      ></el-table-column>
      <el-table-column label="检测置信度"
        ><template #default="{ row }">{{ number(row.confidence, 4) }}</template></el-table-column
      >
      <el-table-column label="位置 [x1,y1,x2,y2]"
        ><template #default="{ row }">{{
          row.bbox.map((n: number) => Math.round(n)).join(', ')
        }}</template></el-table-column
      >
    </el-table>
  </section>
</template>
