import { createRouter, createWebHistory } from 'vue-router'
export default createRouter({history: createWebHistory(), routes:[
  {path:'/',component:()=>import('../views/Dashboard.vue'),meta:{title:'系统概览',description:'让每一种光照，都有清晰的答案。'}},
  {path:'/enhance',component:()=>import('../views/Enhance.vue'),meta:{title:'图像增强实验室',description:'从光照分析到细节恢复，探索更合适的增强策略。'}},
  {path:'/detect',component:()=>import('../views/Detect.vue'),meta:{title:'人脸检测',description:'在同一模型下，观察增强前后真实的检测变化。'}},
  {path:'/persons',component:()=>import('../views/Persons.vue'),meta:{title:'身份库管理',description:'用高质量参考样本，建立可追溯的身份库。'}},
  {path:'/recognition',component:()=>import('../views/Recognition.vue'),meta:{title:'身份确认',description:'支持 1:1 验证与 1:N 检索，保留未知身份拒识。'}},
  {path:'/experiments',component:()=>import('../views/Experiments.vue'),meta:{title:'实验评估',description:'相同模型、相同数据、固定阈值，让结果可复现。'}},
  {path:'/:pathMatch(.*)*',redirect:'/'}
]})
