<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { FolderOpened, Upload, Refresh } from '@element-plus/icons-vue'
import { experimentMethods, get, post, scenes, useTask } from '../api/client'
import type { PersonSummary } from '../api/persons'
import RequiredLabel from './RequiredLabel.vue'
import { validateRequired } from '../utils/validation'

interface ImageRow {
  file: File
  path: string
  personId: number | null | undefined
  scene: string
}
const emit = defineEmits<{ created: [record: any] }>()
const props = defineProps<{ running?: boolean }>()
const persons = ref<PersonSummary[]>([])
const personOptions = computed(() => [
  { label: '未知身份（不在身份库）', value: 0 },
  ...persons.value.map((person) => ({ label: person.name, value: person.id })),
])
const normalizeName = (name: string) => name.trim().toLocaleLowerCase().replace(/[ _]+/g, '_')
const personNameIndex = computed(() => {
  const index = new Map<string, number[]>()
  for (const person of persons.value) {
    const key = normalizeName(person.name)
    index.set(key, [...(index.get(key) || []), person.id])
  }
  return index
})
const rows = ref<ImageRow[]>([])
const imagePage = ref(1)
const pageSize = 25
const pageRows = computed(() => rows.value.slice((imagePage.value - 1) * pageSize, imagePage.value * pageSize))
const rowNumber = (index: number) => (imagePage.value - 1) * pageSize + index + 1
const selecting = ref(false)
const previewUrls = new Map<File, string>()
let selectionVersion = 0
function releasePreviews() {
  previewUrls.forEach((url) => URL.revokeObjectURL(url))
  previewUrls.clear()
}
function previewFor(file: File) {
  let url = previewUrls.get(file)
  if (!url) {
    url = URL.createObjectURL(file)
    previewUrls.set(file, url)
  }
  return url
}
watch(pageRows, releasePreviews)
const filesInput = ref<HTMLInputElement>()
const directoryInput = ref<HTMLInputElement>()
const methods = ref(['original'])
const testName = ref('')
const applyPerson = ref<number | null>()
const applyScene = ref('normal')
const pendingLabels = computed(() => rows.value.filter((row) => row.personId === undefined).length)
const { busy, run } = useTask()
const locked = computed(() => busy.value || selecting.value || props.running)
async function refreshPeople() {
  persons.value = await get<PersonSummary[]>('/person')
}
onMounted(() => run(refreshPeople))
function clear() {
  selectionVersion++
  releasePreviews()
  rows.value = []
  imagePage.value = 1
  selecting.value = false
}
onBeforeUnmount(clear)
function choose(input: HTMLInputElement | undefined) {
  if (!input || locked.value) return
  input.value = ''
  input.click()
}
async function select(event: Event) {
  if (locked.value) return
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || []).filter((file) => /\.(png|jpe?g)$/i.test(file.name))
  input.value = ''
  if (!files.length) return
  if (
    files.length > 1500 ||
    files.some((file) => !file.size || file.size > 12 * 1024 * 1024) ||
    files.reduce((sum, file) => sum + file.size, 0) > 100 * 1024 * 1024 ||
    files.some((file) => (file.webkitRelativePath || file.name).length > 200)
  ) {
    ElMessage.error(
      '最多选择 1500 张 JPG/PNG，单张不超过 12 MB、合计不超过 100 MB，文件路径不超过 200 字',
    )
    return
  }
  clear()
  const version = selectionVersion
  const index = personNameIndex.value
  const prepared: ImageRow[] = []
  selecting.value = true
  try {
    for (let offset = 0; offset < files.length; offset += 100) {
      // Let the browser paint and handle input between batches.
      await new Promise<void>((resolve) => setTimeout(resolve, 0))
      if (version !== selectionVersion) return
      for (const file of files.slice(offset, offset + 100)) {
        const path = file.webkitRelativePath || file.name
        const people = new Set<number>()
        for (const folder of path.split('/').slice(0, -1))
          for (const id of index.get(normalizeName(folder)) || []) people.add(id)
        let scene = 'normal'
        if (/低照|暗光|low[_ -]?light/i.test(path)) scene = 'low_light'
        else if (/逆光|backlight/i.test(path)) scene = 'backlight'
        else if (/光照不均|uneven/i.test(path)) scene = 'uneven'
        prepared.push({
          file,
          path,
          personId: people.size === 1 ? people.values().next().value : undefined,
          scene,
        })
      }
    }
    rows.value = prepared
  } finally {
    if (version === selectionVersion) selecting.value = false
  }
}
function setPerson() {
  if (applyPerson.value === undefined) {
    ElMessage.error('请先选择要应用的真实身份')
    return
  }
  rows.value.forEach((row) => {
    row.personId = applyPerson.value
  })
}
function start() {
  if (locked.value) return
  if (
    !validateRequired([
      ['测试图片', rows.value.length],
      ['测试方法', methods.value.length],
      ['每张图片的真实身份', !rows.value.length || !pendingLabels.value],
    ])
  )
    return
  run(async () => {
    const form = new FormData()
    form.append(
      'labels',
      JSON.stringify({
        name: testName.value.trim(),
        methods: methods.value,
        auto_parameters: true,
        items: rows.value.map((row) => ({
          filename: row.path,
          person_id: row.personId === 0 ? null : row.personId,
          scene: row.scene,
        })),
      }),
    )
    rows.value.forEach((row) => form.append('files', row.file, row.path))
    const record = await post('/experiment/images', form)
    testName.value = ''
    emit('created', record)
    ElMessage.success('多图测试已提交，结果完成后自动更新；本次记录会保留')
  })
}
</script>

<template>
  <section class="card image-batch-card">
    <div class="section-heading">
      <h2>多图识别测试</h2>
      <el-button text :icon="Refresh" :loading="busy" :disabled="locked" @click="run(refreshPeople)"
        >刷新身份库</el-button
      >
    </div>
    <el-form label-position="top">
      <el-form-item label="测试名称">
        <el-input
          v-model="testName"
          aria-label="测试名称"
          maxlength="100"
          placeholder="留空自动命名"
          :disabled="locked"
        />
      </el-form-item>
    </el-form>
    <p><RequiredLabel>测试图片</RequiredLabel></p>
    <div class="toolbar-actions image-batch-actions">
      <input
        ref="filesInput"
        type="file"
        multiple
        accept="image/jpeg,image/png"
        class="sr-only"
        aria-label="选择多张测试图片"
        :disabled="locked"
        @change="select"
      />
      <input
        ref="directoryInput"
        type="file"
        multiple
        webkitdirectory
        class="sr-only"
        aria-label="选择测试图片目录"
        :disabled="locked"
        @change="select"
      />
      <el-button :icon="Upload" :disabled="locked" @click="choose(filesInput)"
        >选择多张图片</el-button
      >
      <el-button :icon="FolderOpened" :disabled="locked" @click="choose(directoryInput)"
        >选择查询目录</el-button
      >
      <span class="muted" role="status"
        ><template v-if="selecting">正在读取图片目录…</template>
        <template v-else>已选择 {{ rows.length }} 张<span v-if="pendingLabels">
          · {{ pendingLabels }} 张待标注</span></template
        ></span
      >
      <el-button v-if="rows.length" text :disabled="locked" @click="clear">清空图片</el-button>
    </div>
    <p class="muted">
      支持 JPG/PNG，每次最多 1500 张、合计 100 MB。文件夹示例：query / 01_逆光_CLAHE / LFW_人员姓名 /
      照片.png。
    </p>
    <div v-if="rows.length" class="image-batch-labels">
      <el-select-v2
        v-model="applyPerson"
        :options="personOptions"
        placeholder="统一设置真实身份"
        filterable
        :disabled="locked"
        aria-label="统一真实身份"
      />
      <el-button :disabled="locked" @click="setPerson">应用到全部图片</el-button>
      <el-select v-model="applyScene" aria-label="统一测试场景" :disabled="locked">
        <el-option v-for="(label, value) in scenes" :key="value" :label="label" :value="value" />
      </el-select>
      <el-button
        :disabled="locked"
        @click="
          rows.forEach((row) => {
            row.scene = applyScene
          })
        "
        >应用场景</el-button
      >
    </div>
    <el-table v-if="rows.length" :data="pageRows" max-height="340" class="image-batch-inputs">
      <el-table-column type="index" :index="rowNumber" label="编号" width="65" />
      <el-table-column label="照片" width="65"
        ><template #default="{ row }"
          ><img
            :src="previewFor(row.file)"
            alt="测试图片预览"
            class="batch-face-preview"
            loading="lazy" /></template
      ></el-table-column>
      <el-table-column prop="path" label="文件" min-width="190" />
      <el-table-column min-width="200"
        ><template #header><RequiredLabel>真实身份</RequiredLabel></template
        ><template #default="{ row }">
          <el-select-v2
            v-model="row.personId"
            :options="personOptions"
            placeholder="选择实际人员"
            filterable
            :disabled="locked"
            :aria-label="'真实身份：' + row.path"
          /> </template
      ></el-table-column>
      <el-table-column label="场景" min-width="150"
        ><template #default="{ row }">
          <el-select v-model="row.scene" :disabled="locked" :aria-label="'场景：' + row.path"
            ><el-option v-for="(label, value) in scenes" :key="value" :label="label" :value="value"
          /></el-select> </template
      ></el-table-column>
    </el-table>
    <el-pagination
      v-if="rows.length > pageSize"
      v-model:current-page="imagePage"
      :total="rows.length"
      :page-size="pageSize"
      :pager-count="5"
      class="image-batch-pagination"
      layout="total, prev, pager, next"
      aria-label="测试图片分页"
    />
    <el-form label-position="top" class="image-batch-settings">
      <el-form-item
        ><template #label><RequiredLabel>测试方法</RequiredLabel></template>
        <el-checkbox-group v-model="methods" :disabled="locked"
          ><el-checkbox
            v-for="method in experimentMethods"
            :key="method.value"
            :value="method.value"
            >{{ method.label }}</el-checkbox
          ></el-checkbox-group
        >
      </el-form-item>

    </el-form>
    <el-button type="primary" :loading="busy" :disabled="selecting || props.running" @click="start"
      >开始多图测试</el-button
    >
    <p class="muted">
      正确识别率 = 正确确认的已知图片数 ÷
      全部已知图片数；漏检、拒识、认错均计为未正确。未知身份另统计误接受率。没有独立人脸框标注，不计算定位准确率。
    </p>
  </section>
</template>

<style scoped>
.image-batch-actions {
  margin-top: 18px;
  flex-wrap: wrap;
}
.image-batch-labels {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 16px 0;
}
.image-batch-labels :is(.el-select, .el-select-v2) {
  width: 220px;
  max-width: 100%;
}
.image-batch-pagination {
  margin-top: 12px;
  flex-wrap: wrap;
}
.image-batch-settings {
  margin-top: 20px;
}
.image-batch-inputs :is(.el-select, .el-select-v2) {
  width: 100%;
}
</style>
