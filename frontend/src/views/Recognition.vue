<script setup lang="ts">
import RequiredLabel from '../components/RequiredLabel.vue'
import { validateRequired } from '../utils/validation'
import { ref, onMounted } from 'vue'
import ImageUpload from '../components/ImageUpload.vue'
import ResultImage from '../components/ResultImage.vue'
import MethodSelect from '../components/MethodSelect.vue'
import { get, post, imageForm, useTask, number } from '../api/client'
import type { PersonSummary } from '../api/persons'
const persons = ref<PersonSummary[]>([]),
  mode = ref('identify'),
  person = ref<number>(),
  enabled = ref(true),
  method = ref('gamma')
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
    ])
  )
    return
  run(async () => {
    const data = imageForm(file.value!, {
      method: enabled.value ? method.value : 'original',
      auto_parameters: true,
    })
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
        ></el-form
      ><el-button type="primary" class="full-width" :loading="busy" @click="execute"
        >开始身份确认</el-button
      >
    </section>
    <section class="card result-panel" v-loading="busy">
      <div class="section-heading">
        <h2>身份确认结果</h2>
        <span class="pill">{{ mode === 'verify' ? '1:1 验证' : '1:N 检索' }}</span>
      </div>
      <ResultImage
        :src="result?.enhanced"
        label="身份确认图像"
        filename="lumiface-recognition-result.png"
      /><template v-if="result"
        ><div :class="['recognition-result', result.confirmed ? 'accepted' : 'rejected']">
          <span class="decision-icon">{{ result.confirmed ? '✓' : '?' }}</span>
          <div class="recognition-identities">
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
            >处理耗时 <b>{{ number(result.elapsed_ms) }} ms</b></span
          ><span
            >检测人脸 <b>{{ result.faces.length }}</b></span
          >
        </div>
        <div class="steps">
          <el-tag v-for="s in result.steps" :key="s">{{ s }}</el-tag>
        </div>
        <el-table v-if="result.faces.length > 1" :data="result.faces" class="face-decisions">
          <el-table-column type="index" label="人脸" width="70" />
          <el-table-column label="面部" width="85">
            <template #default="{ row }">
              <img :src="row.aligned_crop" alt="检测到的人脸" width="56" height="56" />
            </template>
          </el-table-column>
          <el-table-column prop="match.name" label="确认身份" min-width="140" />
          <el-table-column label="相似度" min-width="100">
            <template #default="{ row }">{{ number(row.match.similarity, 4) }}</template>
          </el-table-column>
          <el-table-column prop="match.diagnostic" label="判定" min-width="130" />
        </el-table>
        <el-table v-else :data="result.candidates" empty-text="身份库为空"
          ><el-table-column prop="name" label="候选身份（不代表确认结果）" /><el-table-column
            label="相似度"
            ><template #default="{ row }">{{
              number(row.similarity, 4)
            }}</template></el-table-column
          ></el-table
        ></template
      ><el-empty v-else description="上传图像，开始身份确认" :image-size="65" />
    </section>
  </div>
</template>
