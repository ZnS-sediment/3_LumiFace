import { createRouter, createWebHistory } from 'vue-router'
export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/enhance' },
    {
      path: '/enhance',
      component: () => import('../views/Enhance.vue'),
      meta: { title: '图像增强' },
    },
    {
      path: '/detect',
      component: () => import('../views/Detect.vue'),
      meta: { title: '人脸检测' },
    },
    {
      path: '/persons',
      component: () => import('../views/Persons.vue'),
      meta: { title: '身份库管理' },
    },
    {
      path: '/recognition',
      component: () => import('../views/Recognition.vue'),
      meta: { title: '身份确认' },
    },
    {
      path: '/experiments',
      component: () => import('../views/Experiments.vue'),
      meta: { title: '实验评估' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
