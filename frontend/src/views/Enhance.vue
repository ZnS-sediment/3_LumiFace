<script setup lang="ts">
import RequiredLabel from '../components/RequiredLabel.vue'
import { validateRequired } from '../utils/validation'
import { ref, reactive, computed } from 'vue'
import ImageUpload from '../components/ImageUpload.vue'
import CompareImages from '../components/CompareImages.vue'
import ChartPanel from '../components/ChartPanel.vue'
import MethodSelect from '../components/MethodSelect.vue'
import { post, imageForm, useTask, number, percent, scenes } from '../api/client'
const file = ref<File>(),
  result = ref<any>(null)
const options = reactive({ method: 'gamma', gamma: 0.65, clip_limit: 2, sigma: 30, strength: 0.6 })
const { busy, run } = useTask()
function execute() {
  if (!validateRequired([['输入图像', file.value]])) return
  run(async () => {
    result.value = await post('/enhance/process', imageForm(file.value!, options))
  })
}
const chart = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  legend: { data: ['原始图像', '增强图像'], bottom: 0 },
  grid: { left: 45, right: 20, top: 20, bottom: 50 },
  xAxis: {
    type: 'category' as const,
    data: Array.from({ length: 256 }, (_, i) => i),
    axisLabel: { interval: 63 },
  },
  yAxis: { type: 'value' as const, splitLine: { lineStyle: { color: '#edf1ee' } } },
  series: [
    {
      name: '原始图像',
      type: 'line' as const,
      data: result.value?.before.histogram || [],
      showSymbol: false,
      lineStyle: { color: '#536b85' },
      itemStyle: { color: '#536b85' },
    },
    {
      name: '增强图像',
      type: 'line' as const,
      data: result.value?.after.histogram || [],
      showSymbol: false,
      areaStyle: { color: '#d2eee4' },
      lineStyle: { color: '#245baf' },
      itemStyle: { color: '#245baf' },
    },
  ],
}))
</script>
<template>
  <div class="workbench">
    <section class="card controls">
      <div class="section-heading">
        <h2>输入与增强策略</h2>
        <span class="step-label">01</span>
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
          ><MethodSelect v-model="options.method" /></el-form-item
        ><el-form-item v-if="options.method === 'gamma'" label="Gamma 系数（小于 1 提亮）"
          ><el-slider
            v-model="options.gamma"
            :min="0.15"
            :max="4"
            :step="0.05"
            show-input /></el-form-item
        ><el-form-item v-if="options.method === 'clahe'" label="对比度限制"
          ><el-slider
            v-model="options.clip_limit"
            :min="0.1"
            :max="8"
            :step="0.1"
            show-input /></el-form-item
        ><el-form-item v-if="options.method === 'retinex'" label="光照平滑尺度 Sigma"
          ><el-slider v-model="options.sigma" :min="3" :max="100" show-input /></el-form-item
        ><el-form-item v-if="options.method === 'retinex'" label="处理强度"
          ><el-slider
            v-model="options.strength"
            :min="0"
            :max="1"
            :step="0.05" /></el-form-item></el-form
      ><el-button type="primary" class="full-width" :loading="busy" @click="execute"
        >分析并增强</el-button
      ><a
        v-if="result"
        class="download-link"
        :href="result.enhanced"
        download="lumiface-enhanced.png"
        >下载增强图像 ↓</a
      >
    </section>
    <section class="card result-panel" v-loading="busy">
      <div class="section-heading">
        <h2>增强前后对比</h2>
        <span class="pill">{{ result ? number(result.elapsed_ms) + ' ms' : '等待输入' }}</span>
      </div>
      <CompareImages :original="result?.original" :enhanced="result?.enhanced" />
      <div v-if="result" class="steps">
        <el-tag v-for="step in result.steps" :key="step" type="success" effect="plain">{{
          step
        }}</el-tag>
      </div>
      <div class="section-heading">
        <h3>亮度直方图</h3>
        <span>0 黑 → 255 白</span>
      </div>
      <ChartPanel :option="chart" />
    </section>
  </div>
  <section v-if="result" class="card quality-card">
    <div class="section-heading">
      <h2>光照质量分析</h2>
      <el-tag>{{ scenes[result.before.scene] }}</el-tag>
    </div>
    <el-table
      :data="[
        { label: '平均亮度', key: 'mean_brightness' },
        { label: '亮度对比度', key: 'contrast' },
        { label: '光照不均匀度', key: 'illumination_unevenness' },
        { label: '清晰度（Laplacian 方差）', key: 'sharpness' },
        { label: '欠曝比例', key: 'underexposed_ratio' },
        { label: '过曝比例', key: 'overexposed_ratio' },
      ]"
      ><el-table-column prop="label" label="评估项" /><el-table-column label="原始图像"
        ><template #default="{ row }">{{
          row.key.endsWith('ratio')
            ? percent(result.before[row.key])
            : number(result.before[row.key], 3)
        }}</template></el-table-column
      ><el-table-column label="增强图像"
        ><template #default="{ row }">{{
          row.key.endsWith('ratio')
            ? percent(result.after[row.key])
            : number(result.after[row.key], 3)
        }}</template></el-table-column
      ></el-table
    >
    <p class="muted">{{ result.before.scene_note }}</p>
  </section>
</template>
