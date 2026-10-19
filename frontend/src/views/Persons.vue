<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { TableInstance } from 'element-plus'
import { Plus, Search, FolderOpened } from '@element-plus/icons-vue'
import ImageUpload from '../components/ImageUpload.vue'
import BatchPersonImport from '../components/BatchPersonImport.vue'
import RequiredLabel from '../components/RequiredLabel.vue'
import { validateRequired } from '../utils/validation'
import { api, get, post, useTask, number } from '../api/client'
import {
  registrationForm,
  type PersonSummary,
  type PersonDetail,
  type PersonDeletion,
} from '../api/persons'
const batchImport = ref<InstanceType<typeof BatchPersonImport>>()
const persons = ref<PersonSummary[]>([]),
  query = ref(''),
  dialog = ref(false),
  detail = ref<PersonDetail | null>(null),
  edit = ref<PersonSummary | null>(null)
const name = ref(''),
  note = ref(''),
  capture = ref(''),
  files = ref<File[]>([])
const { busy, run } = useTask()
const table = ref<TableInstance>()
const selected = ref<PersonSummary[]>([]),
  deleting = ref(false)
async function load() {
  persons.value = await get<PersonSummary[]>('/person?q=' + encodeURIComponent(query.value))
  table.value?.clearSelection()
  selected.value = []
}
onMounted(() => run(load))
function refreshAfterImport() {
  query.value = ''
  run(load)
}
function resetRegistration() {
  name.value = ''
  note.value = ''
  capture.value = ''
  files.value = []
}
function updateSelection(rows: PersonSummary[]) {
  selected.value = rows
}
function create() {
  if (
    !validateRequired([
      ['姓名', name.value.trim()],
      ['采集会话编号', capture.value.trim()],
      ['参考照片', files.value.length],
    ])
  )
    return
  run(async () => {
    const form = registrationForm({
      name: name.value,
      note: note.value,
      captureId: capture.value,
      files: files.value,
    })
    await post('/person/register', form)
    dialog.value = false
    await load()
    ElMessage.success('身份已注册，特征保存在本地')
  })
}
function saveEdit() {
  const current = edit.value
  if (!current || !validateRequired([['姓名', current.name.trim()]])) return
  run(async () => {
    await api.patch('/person/' + current.id, { name: current.name, note: current.note })
    edit.value = null
    await load()
  })
}
async function confirmDelete(rows: PersonSummary[], batch = false) {
  if (busy.value || deleting.value || !rows.length) return
  if (rows.length > 1000) {
    ElMessage.warning('每次最多删除 1000 个身份，请减少勾选人数')
    return
  }
  const ids = rows.map((row) => row.id)
  const names =
    rows
      .slice(0, 5)
      .map((row) => `“${row.name}”`)
      .join('、') + (rows.length > 5 ? ' 等' : '')
  deleting.value = true
  try {
    await ElMessageBox.confirm(
      `确定删除${batch ? `所选 ${ids.length} 个身份：` : ''}${names}？导入生成的参考照片、特征和关联查询记录将一并删除，无法恢复。下载的演示包和原始照片保留，历史实验标签保留为编号。`,
      batch ? '批量删除身份' : '删除身份',
      {
        type: 'warning',
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
        closeOnClickModal: false,
      },
    )
    await run(async () => {
      const result: PersonDeletion = batch
        ? await post<PersonDeletion>('/person/batch-delete', { person_ids: ids })
        : (await api.delete('/person/' + ids[0])).data.data
      if (detail.value && ids.includes(detail.value.id)) detail.value = null
      if (edit.value && ids.includes(edit.value.id)) edit.value = null
      if (result.cleanup?.pending_files)
        ElMessage.warning(
          `已删除 ${ids.length} 个身份；${result.cleanup?.pending_files} 张照片待清理，系统将在下次删除或后端重启时重试。`,
        )
      else ElMessage.success(`已删除 ${ids.length} 个身份，导入照片和特征已清理`)
      await load()
    })
  } catch {
    /* user cancelled */
  } finally {
    deleting.value = false
  }
}
</script>
<template>
  <section class="card">
    <div class="toolbar">
      <div>
        <h2>
          已注册身份 <span class="count-badge">{{ persons.length }}</span>
        </h2>
        <p class="muted">多参考照片注册 · 归一化特征 · 余弦相似度</p>
      </div>
      <div class="toolbar-actions">
        <el-input
          v-model="query"
          placeholder="搜索姓名"
          :prefix-icon="Search"
          clearable
          :disabled="busy || deleting"
          @input="run(load)"
        /><el-button :icon="FolderOpened" :disabled="busy || deleting" @click="batchImport?.open()"
          >批量导入身份</el-button
        ><el-button type="primary" :icon="Plus" :disabled="busy || deleting" @click="dialog = true"
          >注册新身份</el-button
        >
      </div>
    </div>
    <div class="person-selection">
      <span class="muted"
        >已选择 {{ selected.length }} 个身份<span v-if="query">（当前搜索结果）</span></span
      ><el-button
        type="danger"
        plain
        :disabled="!selected.length || busy || deleting"
        :loading="busy && deleting"
        @click="confirmDelete([...selected], true)"
        >批量删除<span v-if="selected.length">（{{ selected.length }}）</span></el-button
      >
    </div>
    <el-table
      ref="table"
      row-key="id"
      :data="persons"
      v-loading="busy"
      @selection-change="updateSelection"
      empty-text="身份库为空，点击“注册新身份”开始"
      ><el-table-column
        type="selection"
        width="48"
        :selectable="() => !busy && !deleting"
      /><el-table-column prop="id" label="编号" width="80" /><el-table-column
        label="人员姓名"
        min-width="130"
        ><template #default="{ row }"
          ><div class="person-name">
            <span class="person-avatar" aria-hidden="true">{{ row.name.slice(0, 1) }}</span
            ><span>{{ row.name }}</span>
          </div></template
        ></el-table-column
      ><el-table-column prop="sample_count" label="参考样本" width="110" /><el-table-column
        prop="note"
        label="备注"
        min-width="160"
      /><el-table-column label="注册时间" min-width="180"
        ><template #default="{ row }">{{
          new Date(row.created_at + 'Z').toLocaleString('zh-CN')
        }}</template></el-table-column
      ><el-table-column label="操作" width="200"
        ><template #default="{ row }"
          ><el-button
            link
            type="primary"
            :disabled="busy || deleting"
            @click="
              run(async () => {
                detail = await get<PersonDetail>('/person/' + row.id)
              })
            "
            >查看</el-button
          ><el-button link :disabled="busy || deleting" @click="edit = { ...row }">编辑</el-button
          ><el-button link type="danger" :disabled="busy || deleting" @click="confirmDelete([row])"
            >删除</el-button
          ></template
        ></el-table-column
      ></el-table
    >
    <div class="note">
      注册照片须恰有一张可检测人脸。请为同一采集会话使用一致编号；校准和测试使用独立会话。照片仅保存在本机。
    </div>
  </section>
  <el-dialog
    v-model="dialog"
    title="注册新身份"
    width="560px"
    destroy-on-close
    :close-on-click-modal="false"
    @closed="resetRegistration"
    ><el-form label-position="top"
      ><el-form-item
        ><template #label><RequiredLabel>姓名</RequiredLabel></template
        ><el-input v-model="name" maxlength="80" /></el-form-item
      ><el-form-item
        ><template #label><RequiredLabel>采集会话编号</RequiredLabel></template
        ><el-input
          v-model="capture"
          maxlength="120"
          placeholder="例如 enroll-20261016-session01" /></el-form-item
      ><el-form-item label="备注"
        ><el-input v-model="note" maxlength="500" type="textarea" /></el-form-item
      ><el-form-item
        ><template #label><RequiredLabel>参考照片（1–10 张，原始图像注册）</RequiredLabel></template
        ><ImageUpload multiple @change="(value) => (files = value)" /></el-form-item></el-form
    ><template #footer
      ><el-button @click="dialog = false">取消</el-button
      ><el-button type="primary" :loading="busy" @click="create"
        >提取特征并注册</el-button
      ></template
    ></el-dialog
  >
  <el-dialog :model-value="!!edit" title="编辑身份" width="460px" @close="edit = null"
    ><el-form v-if="edit" label-position="top"
      ><el-form-item
        ><template #label><RequiredLabel>姓名</RequiredLabel></template
        ><el-input v-model="edit.name" maxlength="80" /></el-form-item
      ><el-form-item label="备注"
        ><el-input v-model="edit.note" type="textarea" maxlength="500" /></el-form-item></el-form
    ><template #footer
      ><el-button type="primary" :loading="busy" @click="saveEdit">保存修改</el-button></template
    ></el-dialog
  >
  <el-drawer :model-value="!!detail" title="身份与参考样本" size="540px" @close="detail = null"
    ><template v-if="detail"
      ><h2>{{ detail.name }}</h2>
      <p class="muted">{{ detail.note || '暂无备注' }}</p>
      <div v-for="sample in detail.samples" :key="sample.id" class="sample-detail">
        <img :src="sample.image_url" alt="注册参考照片" />
        <div>
          <h3>参考样本 #{{ sample.id }}</h3>
          <p>{{ sample.dimensions }} 维归一化特征</p>
          <p>
            平均亮度 {{ number(sample.quality.mean_brightness) }} · 清晰度
            {{ number(sample.quality.sharpness) }}
          </p>
          <p class="muted">会话：{{ sample.capture_id }}</p>
          <el-tag size="small" type="success"
            >检测置信度 {{ number(sample.quality.detection_confidence, 3) }}</el-tag
          >
        </div>
      </div>
      <p class="muted">特征向量不通过普通查询接口公开。</p></template
    ></el-drawer
  >
  <BatchPersonImport ref="batchImport" @imported="refreshAfterImport" />
</template>
