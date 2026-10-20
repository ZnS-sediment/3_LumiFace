<script setup lang="ts">
import RequiredLabel from '../components/RequiredLabel.vue'
import { validateRequired } from '../utils/validation'
import { ref, onMounted } from 'vue'
import ImageUpload from '../components/ImageUpload.vue'
import CompareImages from '../components/CompareImages.vue'
import MethodSelect from '../components/MethodSelect.vue'
import { get, post, imageForm, useTask, number } from '../api/client'
import type { PersonSummary } from '../api/persons'
const persons = ref<PersonSummary[]>([]),
  mode = ref('identify'),
  person = ref<number>(),
  enabled = ref(true),
  method = ref('gamma'),
  threshold = ref(0.45)
const file = ref<File>(),
  result = ref<any>(null)
const { busy, run } = useTask()
onMounted(() =>
  run(async () => {
    persons.value = await get<PersonSummary[]>('/person')
  }),
)
function execute() {
  if (
    !validateRequired([
      ['输入图像', file.value],
      ['目标身份', mode.value !== 'verify' || person.value],
      ['余弦相似度阈值', Number.isFinite(threshold.value)],
    ])
  )
    return
  run(async () => {
    const data = imageForm(file.value!, { method: enabled.value ? method.value : 'original' })
    data.append('threshold', String(threshold.value))
    if (mode.value === 'verify') data.append('person_id', String(person.value))
    result.value = await post('/recognition/' + mode.value, data)
  })
}
</script>
<template>
  <div class="workbench">
    <section class="card controls">
      <div class="section-heading">
        <h2>确认设置</h2>
        <span class="step-label">01</span>
      </div>
      <el-segmented
        v-model="mode"
        :options="[
          { label: '1:N 身份检索', value: 'identify' },
          { label: '1:1 身份验证', value: 'verify' },
        ]"
        block
      /><el-form label-position="top"
        ><el-form-item v-if="mode === 'verify'"
          ><template #label><RequiredLabel>目标身份</RequiredLabel></template
          ><el-select v-model="person" placeholder="选择待验证人员" filterable
            ><el-option
              v-for="p in persons"
              :key="p.id"
              :value="p.id"
              :label="p.name" /></el-select></el-form-item></el-form
      ><ImageUpload
        required
        @change="
          (files) => {
            file = files[0]
            result = null
          }
        "
      /><el-form label-position="top"
        ><el-form-item label="图像增强"
          ><el-switch v-model="enabled" active-text="开启" inactive-text="关闭" /></el-form-item
        ><el-form-item v-if="enabled"
          ><template #label><RequiredLabel>增强算法</RequiredLabel></template
          ><MethodSelect v-model="method" /></el-form-item
        ><el-form-item
          ><template #label><RequiredLabel>余弦相似度阈值</RequiredLabel></template
          ><el-input-number
            v-model="threshold"
            :min="-1"
            :max="1"
            :step="0.01"
            :precision="3" /></el-form-item></el-form
      ><el-button type="primary" class="full-width" :loading="busy" @click="execute"
        >开始身份确认</el-button
      >
      <div class="note">
        低于阈值返回“未知身份”。默认 0.45 尚未经你的数据校准，不代表实际身份认证保障。
      </div>
    </section>
    <section class="card result-panel" v-loading="busy">
      <div class="section-heading">
        <h2>身份确认结果</h2>
        <span class="pill">{{ mode === 'verify' ? '1:1 验证' : '1:N 检索' }}</span>
      </div>
      <CompareImages
        :original="result?.original"
        :enhanced="result?.enhanced"
        right-label="处理结果与人脸定位"
        download-name="lumiface-recognition-result.png"
      /><template v-if="result"
        ><div :class="['recognition-result', result.confirmed ? 'accepted' : 'rejected']">
          <span class="decision-icon">{{ result.confirmed ? '✓' : '?' }}</span>
          <div>
            <small>{{ result.confirmed ? '身份确认成功' : '未确认身份' }}</small>
            <h2>{{ result.name }}</h2>
            <p>{{ result.diagnostic }}</p>
          </div>
          <div class="decision-score">
            <strong>{{ number(result.similarity, 4) }}</strong
            ><span>余弦相似度</span>
          </div>
        </div>
        <div class="result-facts">
          <span
            >决策阈值 <b>{{ number(result.threshold, 3) }}</b></span
          ><span
            >处理耗时 <b>{{ number(result.elapsed_ms) }} ms</b></span
          ><span
            >检测人脸 <b>{{ result.faces.length }}</b></span
          >
        </div>
        <div class="steps">
          <el-tag v-for="s in result.steps" :key="s">{{ s }}</el-tag>
        </div>
        <el-table :data="result.candidates" empty-text="身份库为空"
          ><el-table-column prop="name" label="候选身份（不代表确认结果）" /><el-table-column
            label="相似度"
            ><template #default="{ row }">{{
              number(row.similarity, 4)
            }}</template></el-table-column
          ></el-table
        ></template
      ><el-empty v-else description="上传单人脸图像，开始身份确认" :image-size="65" />
    </section>
  </div>
</template>
