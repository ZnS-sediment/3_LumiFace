<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened, Download } from '@element-plus/icons-vue'
import { get } from '../api/client'
import { registrationForm, type PersonSummary } from '../api/persons'
import { downloadJson } from '../utils/download'
import RequiredLabel from './RequiredLabel.vue'
import { validateRequired } from '../utils/validation'

type State = 'pending' | 'importing' | 'registered' | 'skipped' | 'failed' | 'uncertain'
interface Row {
  name: string
  files: File[]
  preview: string
  status: State
  message: string
  personId?: number
  captureId?: string
}
const emit = defineEmits<{ imported: [] }>()
const visible = ref(false),
  running = ref(false),
  stopRequested = ref(false)
const input = ref<HTMLInputElement>(),
  rows = ref<Row[]>([]),
  prefix = ref(''),
  note = ref(''),
  selectionError = ref('')
const selectedRoot = ref('')
const labels: Record<State, string> = {
  pending: '待导入',
  importing: '正在导入',
  registered: '已注册',
  skipped: '已跳过',
  failed: '失败',
  uncertain: '待核对',
}
const processed = computed(
  () => rows.value.filter((r) => !['pending', 'importing'].includes(r.status)).length,
)
const count = (state: State) => rows.value.filter((r) => r.status === state).length
const started = computed(() => processed.value > 0)
const totalPhotos = computed(() => rows.value.reduce((sum, r) => sum + r.files.length, 0))
function release() {
  rows.value.forEach((r) => URL.revokeObjectURL(r.preview))
  rows.value = []
  selectedRoot.value = ''
}
onBeforeUnmount(() => {
  stopRequested.value = true
  release()
})
function resetImport() {
  release()
  prefix.value = ''
  note.value = ''
  selectionError.value = ''
  stopRequested.value = false
}
function open() {
  visible.value = true
}
defineExpose({ open })
function chooseDirectory() {
  if (running.value || !input.value) return
  input.value.value = ''
  input.value.click()
}
function ensureBatch() {
  if (!prefix.value.trim())
    prefix.value = `batch-${new Date().toISOString().replace(/\D/g, '').slice(0, 14)}-${crypto.randomUUID().slice(0, 6)}`
}
function select(event: Event) {
  const element = event.target as HTMLInputElement
  const selected = Array.from(element.files || [])
  element.value = ''
  if (running.value || !selected.length) return
  release()
  selectionError.value = ''
  stopRequested.value = false
  const groups = new Map<string, File[]>()
  const originalNames = new Map<string, string>()
  const errors: string[] = []
  for (const file of selected) {
    if (!/\.(jpe?g|png)$/i.test(file.name)) continue
    const parts = file.webkitRelativePath.split('/')
    if (parts.length !== 3 || parts.some((p) => !p || p === '.' || p === '..')) {
      errors.push('照片必须按“所选根目录 / 人员名称 / 照片”存放，请选择正确的根目录。')
      continue
    }
    const name = parts[1].trim()
    if (originalNames.has(name) && originalNames.get(name) !== parts[1])
      errors.push(`去掉首尾空格后姓名重复：${name}，请使用不同的身份编号。`)
    originalNames.set(name, parts[1])
    if (!name || name.length > 80) {
      errors.push(`人员名称须为 1–80 字：${parts[1]}`)
      continue
    }
    if (!file.size || file.size > 12 * 1024 * 1024) {
      errors.push(`${parts[1]} / ${file.name} 为空或超过 12 MB。`)
      continue
    }
    const files = groups.get(name) || []
    files.push(file)
    groups.set(name, files)
  }
  if (!groups.size)
    errors.push('未找到 JPG/PNG。每个人使用一个子文件夹，请不要直接选择单个人员目录。')
  if (groups.size > 200) errors.push('每批最多 200 人，请分批选择。')
  for (const [name, files] of groups)
    if (files.length > 10) errors.push(`${name} 有 ${files.length} 张照片，每人最多 10 张。`)
  if (errors.length) {
    selectionError.value = Array.from(new Set(errors)).join(' ')
    return
  }
  rows.value = Array.from(groups, ([name, files]) => ({
    name,
    files,
    preview: URL.createObjectURL(files[0]),
    status: 'pending' as State,
    message: '',
  })).sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
  selectedRoot.value = selected[0].webkitRelativePath.split('/')[0] + '/'
  ensureBatch()
}
async function register(row: Row): Promise<State> {
  const form = registrationForm({
    name: row.name,
    note: note.value,
    captureId: row.captureId!,
    files: row.files,
  })
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), 300000)
  try {
    const response = await fetch('/api/person/register', {
      method: 'POST',
      body: form,
      signal: controller.signal,
    })
    let payload: any
    try {
      payload = await response.json()
    } catch {
      throw new Error('无法读取服务响应；请先到身份库核对该人员。')
    }
    if (!response.ok) {
      row.status = response.status >= 500 ? 'uncertain' : 'failed'
      row.message =
        typeof payload.message === 'string' ? payload.message : `注册失败（${response.status}）`
      return row.status
    }
    if (!Number.isInteger(payload.data?.id))
      throw new Error('响应缺少身份编号；请先到身份库核对该人员。')
    row.status = 'registered'
    row.personId = payload.data.id
    row.message = `身份编号 ${row.personId}，参考照片 ${payload.data.sample_count} 张`
  } catch (error) {
    row.status = 'uncertain'
    row.message = error instanceof Error ? error.message : '连接中断，请核对身份库；未自动重试。'
  } finally {
    window.clearTimeout(timer)
  }
  return row.status
}
async function start() {
  if (running.value || started.value) return
  if (
    !validateRequired([
      ['照片根目录', rows.value.length],
      ['数据批次', prefix.value.trim()],
    ])
  )
    return
  running.value = true
  stopRequested.value = false
  try {
    const current = await get<PersonSummary[]>('/person')
    const existing = new Set(current.map((person) => person.name))
    for (const row of rows.value) {
      if (stopRequested.value) break
      row.captureId = `${prefix.value.trim()}:${row.name}`
      if (existing.has(row.name)) {
        row.status = 'skipped'
        row.message = '身份库已有同名人员，未覆盖或追加照片'
        continue
      }
      row.status = 'importing'
      row.message = '正在检测人脸并提取特征'
      const result = await register(row)
      if (result === 'registered') existing.add(row.name)
      if (result === 'uncertain') {
        stopRequested.value = true
        break
      }
    }
    if (count('uncertain')) ElMessage.warning('有人员需要核对，已停止后续导入；请查看结果。')
    else if (count('failed')) ElMessage.warning('部分人员未导入，请查看逐人原因。')
    else if (stopRequested.value) ElMessage.info('已停止后续导入，成功注册的人员已保留。')
    else ElMessage.success(`处理完成：注册 ${count('registered')} 人，跳过 ${count('skipped')} 人`)
  } catch {
    /* Shared API client displays connection errors before any registration. */
  } finally {
    running.value = false
    if (count('registered')) emit('imported')
  }
}
function download() {
  const report = {
    created_at: new Date().toISOString(),
    processed: processed.value,
    total: rows.value.length,
    registered: count('registered'),
    skipped: count('skipped'),
    failed: count('failed'),
    uncertain: count('uncertain'),
    rows: rows.value.map((r) => ({
      name: r.name,
      photos: r.files.length,
      capture_id: r.captureId || null,
      status: r.status,
      person_id: r.personId || null,
      message: r.message,
    })),
  }
  downloadJson(report, 'lumiface-identity-import.json')
}
</script>
<template>
  <el-dialog
    v-model="visible"
    title="批量导入身份"
    width="940px"
    :close-on-click-modal="false"
    :close-on-press-escape="!running"
    :show-close="!running"
    class="batch-import-dialog"
    @closed="resetImport"
  >
    <p class="batch-intro">
      选择一个根目录，每个人一个子文件夹。文件夹名作为姓名，每人 1–10 张 JPG/PNG，单张不超过 12 MB。
    </p>
    <div class="batch-example">
      示例：gallery / 人员001 / 1.png、2.png　　gallery / 人员002 / 1.png
    </div>
    <p class="batch-download">
      <a href="/api/person/demo-dataset" download="att_faces_demo.zip"
        >下载 AT&amp;T 演示数据包（40 人）</a
      ><span>Windows 用户下载并解压后，选择其中的 gallery 文件夹。</span>
    </p>
    <p class="batch-download">
      <a href="/api/person/simulated-dataset" download="att_lighting_simulation.zip"
        >下载模拟光照演示包（40 人）</a
      ><span>含模拟暗光、逆光和灰度补光查询图，非真实红外采集。</span>
    </p>
    <div class="batch-directory-label"><RequiredLabel>照片根目录</RequiredLabel></div>
    <div class="batch-selection">
      <input
        ref="input"
        type="file"
        multiple
        webkitdirectory
        class="sr-only"
        aria-label="选择批量身份文件夹"
        :disabled="running"
        @change="select"
      />
      <el-button :icon="FolderOpened" :disabled="running" @click="chooseDirectory"
        >选择照片根目录</el-button
      >
      <div v-if="selectedRoot" class="batch-directory" role="status" aria-live="polite">
        <span class="batch-directory-path" title="浏览器仅提供所选目录名称，不提供本机完整路径"
          >已读取目录：<strong>{{ selectedRoot }}</strong></span
        >
        <span>{{ rows.length }} 人 · {{ totalPhotos }} 张照片</span>
      </div>
      <el-button v-if="rows.length && !running" text @click="chooseDirectory">重新选择</el-button>
    </div>
    <el-alert v-if="selectionError" type="error" :closable="false" :title="selectionError" />
    <el-form label-position="top" class="batch-fields"
      ><el-form-item
        ><template #label><RequiredLabel>数据批次</RequiredLabel></template
        ><el-input
          v-model="prefix"
          :disabled="running || started"
          maxlength="32"
          placeholder="选择目录后自动生成，也可自行填写"
          aria-required="true" /></el-form-item
      ><el-form-item label="统一备注"
        ><el-input
          v-model="note"
          :disabled="running || started"
          maxlength="500"
          placeholder="例如 AT&T 公开样例，仅作功能演示" /></el-form-item
    ></el-form>
    <div class="note">
      同名人员自动跳过。每个人的全部照片必须通过单人脸检查，才会注册该人；其他人员的结果不受影响。文件夹内照片需由你确认属于同一人。
    </div>
    <div v-if="running || started" class="batch-progress">
      <div>
        <strong>已处理 {{ processed }} / {{ rows.length }} 人</strong
        ><span
          >注册 {{ count('registered') }} · 跳过 {{ count('skipped') }} · 失败
          {{ count('failed') }} · 待核对 {{ count('uncertain') }}</span
        >
      </div>
      <el-progress
        :percentage="rows.length ? Math.round((processed / rows.length) * 100) : 0"
        :show-text="false"
      />
      <p v-if="running">导入时请保持页面打开。停止操作会在当前人员处理结束后生效。</p>
      <p v-if="count('uncertain')">
        服务异常或连接中断，可能已提交该人员。请先核对身份库，再重新选择文件夹；未自动重试。
      </p>
    </div>
    <el-table
      :data="rows"
      max-height="340"
      class="batch-preview-table"
      empty-text="选择文件夹后预览人员及照片数量"
      ><el-table-column label="照片" width="72"
        ><template #default="{ row }"
          ><img
            :src="row.preview"
            alt="参考照片预览"
            class="batch-face-preview"
            loading="lazy" /></template></el-table-column
      ><el-table-column prop="name" label="姓名 / 身份标签" min-width="140" /><el-table-column
        label="照片数"
        width="75"
        ><template #default="{ row }">{{ row.files.length }}</template></el-table-column
      ><el-table-column label="状态" width="100"
        ><template #default="{ row }"
          ><el-tag
            size="small"
            :type="
              row.status === 'registered'
                ? 'success'
                : row.status === 'failed'
                  ? 'danger'
                  : row.status === 'uncertain'
                    ? 'warning'
                    : 'info'
            "
            >{{ labels[row.status as State] }}</el-tag
          ></template
        ></el-table-column
      ><el-table-column prop="message" label="导入结果" min-width="240"
    /></el-table>
    <template #footer
      ><el-button v-if="started" :icon="Download" :disabled="running" @click="download"
        >下载导入结果</el-button
      ><el-button v-if="running" :disabled="stopRequested" @click="stopRequested = true">{{
        stopRequested ? '正在停止' : '停止后续导入'
      }}</el-button
      ><el-button v-else @click="visible = false">关闭</el-button
      ><el-button type="primary" :disabled="started" :loading="running" @click="start"
        >开始导入</el-button
      ></template
    >
  </el-dialog>
</template>
