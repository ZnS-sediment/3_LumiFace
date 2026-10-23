<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Sunny, User, Aim, DataAnalysis, Refresh, ArrowRight } from '@element-plus/icons-vue'
import { get, post, useTask } from '../api/client'
const overview = ref<any>(null)
const experiments = ref<any[]>([])
const { busy, run } = useTask()
async function load() {
  const [system, records] = await Promise.all([get('/system/overview'), get<any[]>('/experiment')])
  overview.value = system
  experiments.value = records.slice(0, 5)
}
function refresh() {
  return run(load)
}
onMounted(refresh)
const stats = [
  { label: '已注册身份', key: 'persons', unit: '人' },
  { label: '检测记录', key: 'detections', unit: '次' },
  { label: '实验任务', key: 'experiments', unit: '组' },
  { label: '评估数据集', key: 'datasets', unit: '个' },
]
const entries = [
  { to: '/enhance', label: '图像增强', description: '调整参数，比较处理前后的图像', icon: Sunny },
  { to: '/detect', label: '人脸检测', description: '查看人脸位置、关键点与对齐裁剪', icon: Aim },
  { to: '/persons', label: '身份注册', description: '上传参考照片，管理身份样本', icon: User },
  {
    to: '/experiments',
    label: '批量评估',
    description: '多图测试识别正确率，查看对照实验',
    icon: DataAnalysis,
  },
]
const steps = [
  { title: '注册参考身份', detail: '准备同一身份的参考照片', to: '/persons' },
  { title: '导入标注数据', detail: '图库、校准与测试保持独立', to: '/experiments' },
  { title: '校准并冻结阈值', detail: '使用校准数据选择决策阈值', to: '/experiments' },
  { title: '运行测试与导出', detail: '查看分组计数和逐样本结果', to: '/experiments' },
]
const statusLabels: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
}
function time(value: string) {
  return new Date(value + 'Z').toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>
<template>
  <div class="dashboard-toolbar">
    <h2>运行概况</h2>
    <div class="toolbar-actions">
      <el-button :icon="Refresh" :loading="busy" @click="refresh">刷新</el-button
      ><RouterLink to="/enhance" class="primary-link"
        >图像增强 <el-icon><ArrowRight /></el-icon
      ></RouterLink>
    </div>
  </div>
  <div class="stats-grid" v-loading="busy">
    <div v-for="s in stats" :key="s.key" class="stat-card">
      <span>{{ s.label }}</span
      ><strong
        >{{ overview ? overview[s.key] : '—' }}<small>{{ s.unit }}</small></strong
      >
    </div>
  </div>
  <div class="overview-grid">
    <section class="card recent-tasks">
      <div class="section-heading">
        <h2>最近实验</h2>
        <RouterLink to="/experiments" class="text-link"
          >全部记录 <el-icon><ArrowRight /></el-icon
        ></RouterLink>
      </div>
      <el-table :data="experiments" v-loading="busy"
        ><el-table-column label="任务" min-width="170"
          ><template #default="{ row }"
            ><span class="task-id">#{{ row.id }}</span
            >{{ row.config.dataset.name }}</template
          ></el-table-column
        ><el-table-column label="状态" width="90"
          ><template #default="{ row }"
            ><el-tag
              size="small"
              :type="
                row.status === 'failed' ? 'danger' : row.status === 'completed' ? 'success' : 'info'
              "
              >{{ statusLabels[row.status] || row.status }}</el-tag
            ></template
          ></el-table-column
        ><el-table-column label="完成进度" width="95"
          ><template #default="{ row }"
            >{{ row.progress }} / {{ row.total }}</template
          ></el-table-column
        ><el-table-column label="创建时间" width="115"
          ><template #default="{ row }">{{ time(row.created_at) }}</template></el-table-column
        ><template #empty
          ><div class="table-empty">
            <p>暂无实验任务</p>
            <span>导入标注数据后，可在实验评估中创建任务。</span
            ><RouterLink to="/experiments" class="text-link"
              >创建实验 <el-icon><ArrowRight /></el-icon
            ></RouterLink></div></template
      ></el-table>
    </section>
    <section class="card model-panel">
      <div class="section-heading">
        <h2>模型状态</h2>
        <span v-if="overview" :class="['status-label', { 'is-ready': overview.model.ready }]"
          ><span :class="['live-dot', { warning: !overview.model.ready }]"></span
          >{{ overview.model.ready ? '已加载' : '待加载' }}</span
        >
      </div>
      <template v-if="overview"
        ><dl class="model-details">
          <div>
            <dt>模型</dt>
            <dd>{{ overview.model.model }}</dd>
          </div>
          <div>
            <dt>权重文件</dt>
            <dd>{{ overview.model.weights_present ? '已就绪' : '未安装' }}</dd>
          </div>
          <div>
            <dt>执行设备</dt>
            <dd>{{ overview.model.providers.join(' / ') || '加载后显示' }}</dd>
          </div>
          <div>
            <dt>检测输入</dt>
            <dd>{{ overview.model.detection_size }} × {{ overview.model.detection_size }}</dd>
          </div>
        </dl>
        <p class="muted">
          将人脸检测和身份特征提取模型载入内存，无需重新训练；图像增强无需加载模型。
        </p>
        <p class="muted">
          {{
            overview.model.ready
              ? '本次服务运行期间可直接使用；后端重启后需重新加载。'
              : '首次检测或注册时会自动加载，也可提前点击下方按钮。'
          }}
        </p>
        <el-button
          v-if="!overview.model.ready"
          type="primary"
          :loading="busy"
          @click="
            run(async () => {
              await post('/system/model/load')
              await load()
            })
          "
          >加载模型</el-button
        ><RouterLink v-else to="/detect" class="text-link"
          >进入人脸检测 <el-icon><ArrowRight /></el-icon></RouterLink
      ></template>
      <p v-else class="muted">等待后端连接</p>
    </section>
    <section class="card">
      <div class="section-heading"><h2>功能入口</h2></div>
      <div class="entry-list">
        <RouterLink v-for="entry in entries" :key="entry.to" :to="entry.to" class="entry-row"
          ><el-icon><component :is="entry.icon" /></el-icon>
          <div>
            <strong>{{ entry.label }}</strong>
            <p>{{ entry.description }}</p>
          </div>
          <el-icon class="entry-arrow"><ArrowRight /></el-icon
        ></RouterLink>
      </div>
    </section>
    <section class="card">
      <div class="section-heading">
        <h2>评估步骤</h2>
        <RouterLink to="/experiments" class="text-link">开始评估</RouterLink>
      </div>
      <ol class="evaluation-steps">
        <li v-for="step in steps" :key="step.title">
          <RouterLink :to="step.to">{{ step.title }}</RouterLink>
          <p>{{ step.detail }}</p>
        </li>
      </ol>
      <p class="workflow-hint">性能目标与实测结果请在实验评估中核对。</p>
    </section>
  </div>
</template>
