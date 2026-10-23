<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened, Upload, Refresh } from '@element-plus/icons-vue'
import { experimentMethods, get, post, scenes, useTask } from '../api/client'
import type { PersonSummary } from '../api/persons'
import RequiredLabel from './RequiredLabel.vue'
import { validateRequired } from '../utils/validation'

interface ImageRow {
  file: File
  path: string
  preview: string
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
const rows = ref<ImageRow[]>([])
const filesInput = ref<HTMLInputElement>()
const directoryInput = ref<HTMLInputElement>()
const methods = ref(['original'])
const threshold = ref(0.45)
const applyPerson = ref<number | null>()
const applyScene = ref('normal')
const pendingLabels = computed(() => rows.value.filter((row) => row.personId === undefined).length)
const { busy, run } = useTask()
async function refreshPeople() {
  persons.value = await get<PersonSummary[]>('/person')
}
onMounted(() => run(refreshPeople))
function clear() {
  rows.value.forEach((row) => URL.revokeObjectURL(row.preview))
  rows.value = []
}
onBeforeUnmount(clear)
function choose(input: HTMLInputElement | undefined) {
  if (!input || busy.value) return
  input.value = ''
  input.click()
}
function select(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || []).filter((file) => /\.(png|jpe?g)$/i.test(file.name))
  input.value = ''
  if (!files.length) return
  if (
    files.length > 500 ||
    files.some((file) => !file.size || file.size > 12 * 1024 * 1024) ||
    files.reduce((sum, file) => sum + file.size, 0) > 100 * 1024 * 1024 ||
    files.some((file) => (file.webkitRelativePath || file.name).length > 200)
  ) {
    ElMessage.error(
      '最多选择 500 张 JPG/PNG，单张不超过 12 MB、合计不超过 100 MB，文件路径不超过 200 字',
    )
    return
  }
  clear()
  const normalize = (name: string) => name.trim().toLocaleLowerCase().replace(/[ _]+/g, '_')
  rows.value = files.map((file) => {
    const path = file.webkitRelativePath || file.name
    const folders = path.split('/').slice(0, -1).map(normalize)
    const people = persons.value.filter((person) => folders.includes(normalize(person.name)))
    let scene = 'normal'
    if (/低照|暗光|low[_ -]?light/i.test(path)) scene = 'low_light'
    else if (/逆光|backlight/i.test(path)) scene = 'backlight'
    else if (/光照不均|uneven/i.test(path)) scene = 'uneven'
    return {
      file,
      path,
      preview: URL.createObjectURL(file),
      personId: people.length === 1 ? people[0].id : undefined,
      scene,
    }
  })
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
  if (props.running || busy.value) return
  if (
    !validateRequired([
      ['测试图片', rows.value.length],
      ['实验组', methods.value.length],
      ['每张图片的真实身份', !rows.value.length || !pendingLabels.value],
      ['相似度阈值', Number.isFinite(threshold.value)],
    ])
  )
    return
  run(async () => {
    const form = new FormData()
    form.append(
      'labels',
      JSON.stringify({
        threshold: threshold.value,
        methods: methods.value,
        items: rows.value.map((row) => ({
          filename: row.path,
          person_id: row.personId === 0 ? null : row.personId,
          scene: row.scene,
        })),
      }),
    )
    rows.value.forEach((row) => form.append('files', row.file, row.path))
    const record = await post('/experiment/images', form)
    emit('created', record)
    ElMessage.success('多图测试已提交，结果完成后自动更新；本次记录会保留')
  })
}
</script>

<template>
  <section class="card image-batch-card">
    <div class="section-heading">
      <div>
        <h2>多图识别测试</h2>
        <p class="muted">一次测试多张查询照片，自动汇总正确识别率，保留每次实验记录。</p>
      </div>
      <el-button text :icon="Refresh" :loading="busy" @click="run(refreshPeople)"
        >刷新身份库</el-button
      >
    </div>
    <p class="note">
      每张图应为同一个人的单人照片。真实身份由你确认；按姓名分文件夹时自动匹配，未匹配的标签需要选择。请使用
      query 查询图，勿使用已注册的 gallery 参考图。
    </p>
    <p><RequiredLabel>测试图片</RequiredLabel></p>
    <div class="toolbar-actions image-batch-actions">
      <input
        ref="filesInput"
        type="file"
        multiple
        accept="image/jpeg,image/png"
        class="sr-only"
        aria-label="选择多张测试图片"
        :disabled="busy"
        @change="select"
      />
      <input
        ref="directoryInput"
        type="file"
        multiple
        webkitdirectory
        class="sr-only"
        aria-label="选择测试图片目录"
        :disabled="busy"
        @change="select"
      />
      <el-button :icon="Upload" :disabled="busy" @click="choose(filesInput)"
        >选择多张图片</el-button
      >
      <el-button :icon="FolderOpened" :disabled="busy" @click="choose(directoryInput)"
        >选择查询目录</el-button
      >
      <span class="muted" role="status"
        >已选择 {{ rows.length }} 张<span v-if="pendingLabels">
          · {{ pendingLabels }} 张待标注</span
        ></span
      >
      <el-button v-if="rows.length" text :disabled="busy" @click="clear">清空图片</el-button>
    </div>
    <p class="muted">
      支持 JPG/PNG，每次最多 500 张、合计 100 MB。文件夹示例：query / ATT_s01 / 04.png。
    </p>
    <div v-if="rows.length" class="image-batch-labels">
      <el-select-v2
        v-model="applyPerson"
        :options="personOptions"
        placeholder="统一设置真实身份"
        filterable
        :disabled="busy"
        aria-label="统一真实身份"
      />
      <el-button :disabled="busy" @click="setPerson">应用到全部图片</el-button>
      <el-select v-model="applyScene" aria-label="统一测试场景" :disabled="busy">
        <el-option v-for="(label, value) in scenes" :key="value" :label="label" :value="value" />
      </el-select>
      <el-button
        :disabled="busy"
        @click="
          rows.forEach((row) => {
            row.scene = applyScene
          })
        "
        >应用场景</el-button
      >
    </div>
    <el-table v-if="rows.length" :data="rows" max-height="340" class="image-batch-inputs">
      <el-table-column type="index" label="编号" width="65" />
      <el-table-column label="照片" width="65"
        ><template #default="{ row }"
          ><img
            :src="row.preview"
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
            :disabled="busy"
            :aria-label="'真实身份：' + row.path"
          /> </template
      ></el-table-column>
      <el-table-column label="场景" min-width="150"
        ><template #default="{ row }">
          <el-select v-model="row.scene" :disabled="busy" :aria-label="'场景：' + row.path"
            ><el-option v-for="(label, value) in scenes" :key="value" :label="label" :value="value"
          /></el-select> </template
      ></el-table-column>
    </el-table>
    <el-form label-position="top" class="image-batch-settings">
      <el-form-item
        ><template #label><RequiredLabel>实验组</RequiredLabel></template>
        <el-checkbox-group v-model="methods" :disabled="busy"
          ><el-checkbox
            v-for="method in experimentMethods"
            :key="method.value"
            :value="method.value"
            >{{ method.label }}</el-checkbox
          ></el-checkbox-group
        >
      </el-form-item>
      <el-form-item
        ><template #label><RequiredLabel>相似度阈值</RequiredLabel></template
        ><el-input-number v-model="threshold" :min="-1" :max="1" :step="0.01" :disabled="busy"
      /></el-form-item>
    </el-form>
    <el-button type="primary" :loading="busy || props.running" @click="start"
      >开始多图测试</el-button
    >
    <p class="muted">
      正确识别率 = 正确确认的已知图片数 ÷
      全部已知图片数；漏检、拒识、认错均计为未正确。未知身份另统计误接受率。没有独立人脸框标注，不计算定位准确率。
    </p>
    <p class="batch-download">
      <a href="/api/person/lfw-dataset" download="lfw_120_demo.zip">下载 LFW 扩充数据包（120 人）</a
      ><span>先注册 gallery，再选择 query 批量测试。</span>
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
.image-batch-settings {
  margin-top: 20px;
}
.image-batch-inputs :is(.el-select, .el-select-v2) {
  width: 100%;
}
</style>
