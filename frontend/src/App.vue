<script setup lang="ts">
import { useRoute } from 'vue-router'
import { computed, ref } from 'vue'
import { House, Sunny, Aim, User, CircleCheck, DataAnalysis, ArrowRight, Menu } from '@element-plus/icons-vue'
const route = useRoute()
const expanded = ref(false)
const nav = [{to:'/',label:'系统概览',icon:House,n:'01'}, {to:'/enhance',label:'图像增强实验室',icon:Sunny,n:'02'}, {to:'/detect',label:'人脸检测',icon:Aim,n:'03'}, {to:'/persons',label:'身份库管理',icon:User,n:'04'}, {to:'/recognition',label:'身份确认',icon:CircleCheck,n:'05'}, {to:'/experiments',label:'实验评估',icon:DataAnalysis,n:'06'}]
const title = computed(()=>route.meta.title)
</script>
<template>
  <div class="app-shell">
    <aside :class="['sidebar',{expanded}]">
      <RouterLink to="/" class="brand"><span class="brand-mark">L<span>✦</span></span><span>LumiFace<small>LIGHT · FACE · INSIGHT</small></span></RouterLink>
      <div class="nav-label">研究工作台 <span>WORKSPACE</span></div>
      <nav><RouterLink v-for="item in nav" :key="item.to" :to="item.to" class="nav-item" :class="{active:route.path===item.to}" @click="expanded=false"><el-icon><component :is="item.icon"/></el-icon><span>{{item.label}}</span><small>{{item.n}}</small></RouterLink></nav>
      <div class="sidebar-bottom"><span class="live-dot"></span> 本地研究环境<p>复杂光照条件下<br>人脸检测增强算法及系统实现</p><div class="version">本科实训项目 <span>v1.0</span></div></div>
    </aside>
    <div class="main-shell">
      <header class="topbar"><div class="breadcrumb"><el-button class="mobile-menu" text :icon="Menu" aria-label="打开导航" @click="expanded=!expanded"/><span>工作台</span><el-icon><ArrowRight/></el-icon><strong>{{title}}</strong></div><div class="topbar-right"><span class="local-badge"><span class="live-dot"></span> LOCAL RESEARCH</span><span class="avatar">LF</span></div></header>
      <main><div class="page-heading"><div><div class="eyebrow">LUMIFACE / RESEARCH PLATFORM</div><h1>{{title}}</h1><p>{{route.meta.description}}</p></div><span class="page-index">{{nav.find(x=>x.to===route.path)?.n}} <span>/ 06</span></span></div><RouterView/></main>
      <footer>© LumiFace · 复杂光照人脸增强实验平台 <span>本地教学与研究演示 · 指标以真实实验为准</span></footer>
    </div>
  </div>
</template>
