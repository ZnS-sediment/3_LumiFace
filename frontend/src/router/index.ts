import { createRouter, createWebHistory } from 'vue-router'
export default createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('../views/Dashboard.vue'),
      meta: { title: '系统概览', description: '查看任务统计、模型状态和常用功能。' },
    },
    {
      path: '/enhance',
      component: () => import('../views/Enhance.vue'),
      meta: { title: '图像增强实验室', description: '上传图片，调整增强参数并比较处理效果。' },
    },
    {
      path: '/detect',
      component: () => import('../views/Detect.vue'),
      meta: { title: '人脸检测', description: '比较原图与增强图的人脸检测结果。' },
    },
    {
      path: '/persons',
      component: () => import('../views/Persons.vue'),
      meta: { title: '身份库管理', description: '注册、查看和管理人脸参考样本。' },
    },
    {
      path: '/recognition',
      component: () => import('../views/Recognition.vue'),
      meta: { title: '身份确认', description: '支持 1:1 验证与 1:N 检索，保留未知身份拒识。' },
    },
    {
      path: '/experiments',
      component: () => import('../views/Experiments.vue'),
      meta: { title: '实验评估', description: '管理标注数据、运行消融实验并查看评估结果。' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
