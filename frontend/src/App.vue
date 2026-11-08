<script setup lang="ts">
import { ElConfigProvider } from 'element-plus/es/components/config-provider/index'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useRoute } from 'vue-router'
import { computed, ref } from 'vue'
import {
  Sunny,
  Aim,
  User,
  CircleCheck,
  DataAnalysis,
  ArrowRight,
  Menu,
} from '@element-plus/icons-vue'
const route = useRoute()
const expanded = ref(false)
const nav = [
  { to: '/enhance', label: '图像增强', icon: Sunny, group: '图像处理' },
  { to: '/detect', label: '人脸检测', icon: Aim, group: '图像处理' },
  { to: '/persons', label: '身份库管理', icon: User, group: '身份与评估' },
  { to: '/recognition', label: '身份确认', icon: CircleCheck, group: '身份与评估' },
  { to: '/experiments', label: '实验评估', icon: DataAnalysis, group: '身份与评估' },
]
const title = computed(() => route.meta.title)
const group = computed(() => nav.find((item) => item.to === route.path)?.group)
</script>
<template>
  <ElConfigProvider :locale="zhCn">
    <div class="app-shell">
      <button
        v-if="expanded"
        class="nav-backdrop"
        aria-label="关闭导航"
        @click="expanded = false"
      />
      <aside id="app-navigation" :class="['sidebar', { expanded }]" @keydown.esc="expanded = false">
        <RouterLink to="/" class="brand" @click="expanded = false"
          >LumiFace<small>人脸增强实验系统</small></RouterLink
        >
        <nav aria-label="主导航">
          <template v-for="(item, index) in nav" :key="item.to">
            <div v-if="index === 0 || nav[index - 1]?.group !== item.group" class="nav-label">
              {{ item.group }}
            </div>
            <RouterLink
              :to="item.to"
              class="nav-item"
              :class="{ active: route.path === item.to }"
              :aria-current="route.path === item.to ? 'page' : undefined"
              @click="expanded = false"
              ><el-icon><component :is="item.icon" /></el-icon
              ><span>{{ item.label }}</span></RouterLink
            >
          </template>
        </nav>
      </aside>
      <div class="main-shell">
        <header class="topbar">
          <div class="breadcrumb">
            <el-button
              class="mobile-menu"
              text
              :icon="Menu"
              aria-label="打开导航"
              aria-controls="app-navigation"
              :aria-expanded="expanded"
              @click="expanded = !expanded"
            /><span>{{ group }}</span
            ><el-icon><ArrowRight /></el-icon><strong>{{ title }}</strong>
          </div>
        </header>
        <main>
          <div class="page-heading">
            <h1>{{ title }}</h1>
          </div>
          <RouterView />
        </main>
      </div>
    </div>
  </ElConfigProvider>
</template>
