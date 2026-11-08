<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ElMessage } from 'element-plus/es/components/message/index'
import RequiredLabel from '../components/RequiredLabel.vue'
import { validateRequired } from '../utils/validation'
import { Refresh } from '@element-plus/icons-vue'
import BatchImageEvaluation from '../components/BatchImageEvaluation.vue'
import CompareImages from '../components/CompareImages.vue'
import { api, get, methodLabel, number, percent, sceneLabel, scenes, useTask } from '../api/client'

const route = useRoute(),
  router = useRouter()
const view = ref(route.query.run ? 'result' : 'new')
const experiments = ref<any[]>([]),
  selected = ref<any>(null),
  results = ref<any[]>([])
const preview = ref<any>(null),
  page = ref(1),
  summaryScene = ref('all')
const { busy, run } = useTask()
const historyOrder = ref<'asc' | 'desc'>('desc')
const renameTarget = ref<{ id: number; name: string } | null>(null)
try {
  if (localStorage.getItem('lumiface-experiment-order') === 'asc') historyOrder.value = 'asc'
} catch {
  // Sorting also works when browser storage is unavailable.
}
watch(historyOrder, (value) => {
  try {
    localStorage.setItem('lumiface-experiment-order', value)
  } catch {
    // Keep the selection for this page even when it cannot be persisted.
  }
})
const numberedExperiments = computed(() =>
  [...experiments.value]
    .sort((a, b) => a.id - b.id)
    .map((record, index) => ({ ...record, displayNumber: index + 1 })),
)
const historyRows = computed(() =>
  historyOrder.value === 'asc'
    ? numberedExperiments.value
    : [...numberedExperiments.value].reverse(),
)
const selectedNumber = computed(
  () => numberedExperiments.value.find((record) => record.id === selected.value?.id)?.displayNumber,
)
async function saveName() {
  if (!renameTarget.value || !validateRequired([['测试名称', renameTarget.value.name.trim()]]))
    return
  await run(async () => {
    const target = renameTarget.value!
    const updated = (await api.patch('/experiment/' + target.id, { name: target.name.trim() })).data
      .data
    experiments.value = experiments.value.map((record) =>
      record.id === updated.id ? updated : record,
    )
    if (selected.value?.id === updated.id) selected.value = updated
    renameTarget.value = null
    ElMessage.success('测试名称已保存')
  })
}
const activeExperiment = computed(() =>
  experiments.value.find((record) => ['queued', 'running'].includes(record.status)),
)
const running = computed(() => !!activeExperiment.value)
const statusLabels: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
}
const outcomeLabels: Record<string, string> = {
  correct: '识别正确',
  wrong_identity: '识别错误',
  rejected: '已知身份被拒识',
  no_face: '未检测到人脸',
  multiple_faces: '检测到多张人脸',
  unknown_rejected: '正确拒绝未知身份',
  false_accept: '误接受未知身份',
}
const summaryRows = computed(() =>
  Object.entries(selected.value?.summary || {}).map(([method, value]) => ({
    method,
    ...(summaryScene.value === 'all'
      ? (value as any).overall
      : (value as any).scenes[summaryScene.value]),
  })),
)
const errorRows = computed(() =>
  Object.entries(selected.value?.error_summary || {}).map(([method, value]) => {
    const stats =
      summaryScene.value === 'all'
        ? (value as any).overall
        : (value as any).scenes[summaryScene.value]
    return {
      method,
      ...stats,
      types: Object.entries(stats.counts).filter(([, count]) => (count as number) > 0),
    }
  }),
)
const sampleCount = computed(() =>
  selected.value ? selected.value.total / selected.value.config.methods.length : 0,
)
async function load() {
  experiments.value = await get('/experiment')
}
async function loadResults() {
  const id = selected.value?.id
  const resultPage = page.value
  if (!id) return
  const data = await get(`/experiment/${id}/results?offset=${(resultPage - 1) * 50}&limit=50`)
  if (selected.value?.id === id && page.value === resultPage) results.value = data
}
let selectionVersion = 0
async function choose(record: any, open = true) {
  const version = ++selectionVersion
  const detail = await get('/experiment/' + record.id)
  if (version !== selectionVersion) return
  selected.value = detail
  results.value = []
  page.value = 1
  summaryScene.value = 'all'
  await loadResults()
  if (open && version === selectionVersion) {
    view.value = 'result'
    await router.replace({ query: { ...route.query, run: String(record.id) } })
  }
}
async function created(record: any) {
  experiments.value = [record, ...experiments.value.filter((item) => item.id !== record.id)]
  await load()
  await choose(record)
}
watch(view, async (value) => {
  const query = { ...route.query }
  if (value === 'result' && selected.value) query.run = String(selected.value.id)
  else delete query.run
  await router.replace({ query })
})
async function remove(record: any) {
  try {
    await ElMessageBox.confirm('删除这次测试及其逐图结果？', '删除测试')
  } catch {
    return
  }
  await run(async () => {
    await api.delete('/experiment/' + record.id)
    if (selected.value?.id === record.id) {
      selected.value = null
      results.value = []
    }
    await load()
  })
}
let timer: ReturnType<typeof setInterval> | undefined
let polling = false
onMounted(() => {
  run(async () => {
    await load()
    const id = Number(route.query.run)
    const record = Number.isInteger(id) && id > 0 ? { id } : experiments.value[0]
    if (record) await choose(record, false)
  })
  timer = setInterval(async () => {
    if (
      polling ||
      busy.value ||
      (!running.value && !['queued', 'running'].includes(selected.value?.status))
    )
      return
    polling = true
    try {
      await load()
      if (selected.value && ['queued', 'running'].includes(selected.value.status)) {
        const id = selected.value.id
        const version = selectionVersion
        const detail = await get('/experiment/' + id)
        if (selected.value?.id === id && version === selectionVersion) {
          selected.value = detail
          if (['completed', 'failed'].includes(detail.status)) await loadResults()
        }
      }
    } catch {
      /* API client displays errors. */
    } finally {
      polling = false
    }
  }, 2500)
})
onBeforeUnmount(() => clearInterval(timer))
</script>
<template>
  <el-tabs v-model="view" class="evaluation-tabs">
    <el-tab-pane label="新建测试" name="new" lazy>
      <section v-if="activeExperiment" class="card active-experiment" aria-label="当前运行测试">
        <div class="section-heading">
          <h2>{{ activeExperiment.name || activeExperiment.config.dataset.name }}</h2>
          <el-tag>{{ statusLabels[activeExperiment.status] }}</el-tag>
        </div>
        <p>当前测试结束前不能创建新测试，可以查看其他已有测试的详情。</p>
        <p>{{ activeExperiment.config.methods.map(methodLabel).join('、') }}</p>
        <p role="status">已处理 {{ activeExperiment.progress }} / {{ activeExperiment.total }} 项</p>
        <el-progress :percentage="activeExperiment.total ? Math.round(activeExperiment.progress / activeExperiment.total * 100) : 0" />
        <el-button type="primary" text :disabled="busy" @click="run(() => choose(activeExperiment))">查看当前测试</el-button>
      </section>
      <BatchImageEvaluation v-else :running="running" @created="created" />
    </el-tab-pane>
    <el-tab-pane label="测试结果" name="result" lazy>
      <section v-if="selected" class="card current-experiment">
        <div class="section-heading">
          <div>
            <h2>
              {{ selected.name || selected.config.dataset.name }}
              <el-tag size="small">{{ statusLabels[selected.status] }}</el-tag>
            </h2>
            <p class="muted">
              <template v-if="selectedNumber !== undefined">编号 {{ selectedNumber }} · </template>
              {{ sampleCount }} 张图片
            </p>
          </div>
        </div>
        <div
          v-if="['queued', 'running'].includes(selected.status)"
          class="batch-progress"
          role="status"
        >
          <p>已处理 {{ selected.progress }} / {{ selected.total }} 项，完成后自动更新。</p>
          <el-progress
            :percentage="
              selected.total ? Math.round((selected.progress / selected.total) * 100) : 0
            "
          />
        </div>
        <el-alert v-if="selected.error" :title="selected.error" type="error" :closable="false" />
        <template v-if="summaryRows.length">
          <div class="section-heading">
            <h3>识别汇总</h3>
            <el-select v-model="summaryScene" aria-label="汇总场景" class="scene-filter"
              ><el-option label="全部场景" value="all" /><el-option
                v-for="(label, value) in scenes"
                :key="value"
                :label="label"
                :value="value"
            /></el-select>
          </div>
          <el-table :data="summaryRows" class="evaluation-summary">
            <el-table-column label="方法" min-width="190"
              ><template #default="{ row }">{{
                methodLabel(row.method)
              }}</template></el-table-column
            >
            <el-table-column prop="images" label="图片数" width="90" />
            <el-table-column label="已知正确 / 总数" min-width="140"
              ><template #default="{ row }"
                >{{ row.correct }} / {{ row.known }}</template
              ></el-table-column
            >
            <el-table-column label="正确识别率" min-width="120"
              ><template #default="{ row }">{{
                percent(row.confirmation_rate)
              }}</template></el-table-column
            >
            <el-table-column label="未知误接受" min-width="160"
              ><template #default="{ row }"
                >{{ row.false_accept }} / {{ row.unknown }} ·
                {{ percent(row.unknown_far) }}</template
              ></el-table-column
            >
            <el-table-column label="平均耗时" min-width="115"
              ><template #default="{ row }">{{ number(row.mean_ms) }} ms</template></el-table-column
            >
          </el-table>
          <p class="muted">
            正确识别率包含漏检、拒识和认错的已知图片；未知身份另统计误接受率。模拟光照结果仅用于演示。
            <template v-if="['aligned-fusion-v2', 'aligned-fusion-v3', 'face-local-v4'].includes(selected.config.recognition_policy)">
              <template v-if="selected.config.recognition_policy === 'face-local-v4'">CLAHE 使用人脸局部增强及镜像特征融合；Gamma、Retinex 融合原图与增强特征。</template>
              <template v-else>增强组采用原图与增强特征融合。</template>
              <template v-if="['aligned-fusion-v3', 'face-local-v4'].includes(selected.config.recognition_policy)">
                平均耗时包含完整原图推理成本；批量测试复用原图计算以缩短总等待时间。
              </template>
            </template>
          </p>
          <p v-if="selected.config.localization_protocol === 'image_identity_presence'" class="muted">
            多脸图片逐脸识别，任一已确认身份与真实身份一致即判正确；单脸仍须确认是同一身份。
          </p>
          <section v-if="errorRows.length" class="error-summary" aria-label="错误类型统计">
            <div class="section-heading"><h3>错误类型统计</h3></div>
            <div class="error-grid">
              <article
                v-for="row in errorRows"
                :key="row.method"
                class="error-method"
                :aria-label="methodLabel(row.method)"
              >
                <div class="error-method-heading">
                  <h4>{{ methodLabel(row.method) }}</h4>
                  <span :class="{ 'has-errors': row.total_errors > 0 }"
                    >{{ row.total_errors }} 张异常 / {{ row.images }} 张</span
                  >
                </div>
                <dl v-if="row.types.length" class="error-types">
                  <div v-for="[type, count] in row.types" :key="type" class="error-type">
                    <dt>{{ outcomeLabels[type] }}</dt>
                    <dd>{{ count }} 张</dd>
                  </div>
                </dl>
                <p v-if="!row.images" class="muted">该场景没有测试图片</p>
                <p v-else-if="row.unclassified" class="muted">
                  {{ row.unclassified }} 张图片未记录错误分类
                </p>
                <p v-else-if="!row.total_errors" class="muted">未出现错误</p>
              </article>
            </div>
          </section>
        </template>
        <div class="section-heading sample-heading">
          <h3>逐图结果</h3>
        </div>
        <el-table :data="results" empty-text="任务完成后显示逐图结果">
          <el-table-column type="expand" width="45">
            <template #default="{ row }">
              <el-table :data="row.predictions" class="face-results">
                <el-table-column type="index" label="人脸" width="70" />
                <el-table-column prop="match.name" label="确认身份" min-width="160" />
                <el-table-column label="相似度" min-width="100">
                  <template #default="{ row: face }">{{ number(face.match.similarity, 4) }}</template>
                </el-table-column>
                <el-table-column prop="match.diagnostic" label="判定" min-width="160" />
              </el-table>
            </template>
          </el-table-column>
          <el-table-column
            type="index"
            :index="(index: number) => (page - 1) * 50 + index + 1"
            label="编号"
            width="65"
          />
          <el-table-column label="图片" min-width="190"
            ><template #default="{ row }">{{
              row.filename || '样本 ' + (row.item_index + 1)
            }}</template></el-table-column
          >
          <el-table-column label="方法" min-width="180"
            ><template #default="{ row }">{{ methodLabel(row.method) }}</template></el-table-column
          >
          <el-table-column label="场景" min-width="100"
            ><template #default="{ row }">{{ sceneLabel(row.scene) }}</template></el-table-column
          >
          <el-table-column prop="expected_name" label="真实身份" min-width="140" />
          <el-table-column prop="predicted_name" label="识别结果" min-width="140" />
          <el-table-column label="相似度" width="100"
            ><template #default="{ row }">{{
              number(row.similarity, 4)
            }}</template></el-table-column
          >
          <el-table-column label="判定" min-width="160"
            ><template #default="{ row }">{{
              outcomeLabels[row.outcome] || (row.correct ? '正确 ' + row.correct : '未正确确认')
            }}</template></el-table-column
          >
          <el-table-column label="图片" width="100"
            ><template #default="{ row }"
              ><el-button
                link
                type="primary"
                @click="
                  run(async () => {
                    preview = await get(`/experiment/${selected.id}/preview/${row.id}`)
                  })
                "
                >查看图片</el-button
              ></template
            ></el-table-column
          >
        </el-table>
        <el-pagination
          v-model:current-page="page"
          :total="selected.progress"
          :page-size="50"
          layout="prev,pager,next,total"
          @current-change="run(loadResults)"
        />
      </section>
      <el-empty v-else description="完成一次测试后，在这里查看结果" />
    </el-tab-pane>
    <el-tab-pane label="历史记录" name="history" lazy>
      <section class="card experiment-history">
        <div class="section-heading">
          <h2>测试记录</h2>
          <div class="toolbar-actions">
            <el-select v-model="historyOrder" aria-label="编号排序" class="history-sort">
              <el-option label="升序（从小到大）" value="asc" />
              <el-option label="降序（从大到小）" value="desc" />
            </el-select>
            <el-button :icon="Refresh" text :loading="busy" @click="run(load)">刷新</el-button>
          </div>
        </div>
        <el-table :data="historyRows" empty-text="暂无测试记录">
          <el-table-column prop="displayNumber" label="编号" width="75" />
          <el-table-column label="测试数据" min-width="190"
            ><template #default="{ row }">{{
              row.name || row.config.dataset.name
            }}</template></el-table-column
          >
          <el-table-column label="状态" width="105"
            ><template #default="{ row }">{{ statusLabels[row.status] }}</template></el-table-column
          >
          <el-table-column label="进度" width="120"
            ><template #default="{ row }"
              >{{ row.progress }} / {{ row.total }}</template
            ></el-table-column
          >
          <el-table-column label="操作" width="220"
            ><template #default="{ row }"
              ><el-button link type="primary" @click="run(() => choose(row))">查看结果</el-button
              ><el-button
                link
                type="primary"
                :disabled="busy || ['queued', 'running'].includes(row.status)"
                @click="renameTarget = { id: row.id, name: row.name || row.config.dataset.name }"
                >重命名</el-button
              ><el-button
                link
                type="danger"
                :disabled="['queued', 'running'].includes(row.status)"
                @click="remove(row)"
                >删除</el-button
              ></template
            ></el-table-column
          >
        </el-table>
      </section>
    </el-tab-pane>
  </el-tabs>
  <el-dialog
    :model-value="!!renameTarget"
    title="重命名测试"
    width="460px"
    :close-on-click-modal="false"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    @close="renameTarget = null"
  >
    <el-form v-if="renameTarget" label-position="top" @submit.prevent="saveName">
      <el-form-item>
        <template #label><RequiredLabel>测试名称</RequiredLabel></template>
        <el-input
          v-model="renameTarget.name"
          aria-label="测试名称"
          maxlength="100"
          show-word-limit
          :disabled="busy"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button :disabled="busy" @click="renameTarget = null">取消</el-button>
      <el-button type="primary" :loading="busy" @click="saveName">保存</el-button>
    </template>
  </el-dialog>
  <el-dialog :model-value="!!preview" title="测试图片" width="900px" @close="preview = null"
    ><CompareImages :original="preview?.original" :enhanced="preview?.enhanced"
  /></el-dialog>
</template>
<style scoped>
.error-summary {
  margin-top: 24px;
  padding-top: 22px;
  border-top: 1px solid #dce1e7;
}
.error-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.error-method {
  padding: 16px 18px;
  border: 1px solid #dce1e7;
  border-radius: 4px;
}
.error-method-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.error-method-heading h4 {
  margin: 0;
  font-size: 15px;
  overflow-wrap: anywhere;
}
.error-method-heading span {
  color: #526071;
  font-size: 13px;
}
.error-method-heading .has-errors {
  color: #a4372c;
}
.error-types {
  margin: 0;
}
.error-type {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-top: 1px solid #edf0f4;
  font-size: 14px;
}
.error-type dd {
  margin: 0;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.error-method > p {
  margin: 0;
  font-size: 13px;
}
@media (max-width: 700px) {
  .error-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

.history-sort {
  width: 200px;
}
.scene-filter {
  width: 180px;
  max-width: 50%;
}
.sample-heading {
  margin-top: 26px;
}
</style>
