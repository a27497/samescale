import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: () => import('@/views/OverviewView.vue') },
    {
      path: '/experiments',
      name: 'experiments',
      component: () => import('@/views/ExperimentsView.vue'),
    },
    {
      path: '/experiments/:id',
      name: 'experiment-detail',
      component: () => import('@/views/ExperimentDetailView.vue'),
    },
    {
      path: '/runs/:runId',
      name: 'run-detail',
      component: () => import('@/views/RunDetailView.vue'),
    },
    {
      path: '/regression',
      name: 'regression',
      component: () => import('@/views/RegressionView.vue'),
    },
    {
      path: '/judgelab',
      name: 'judgelab',
      component: () => import('@/views/JudgeLabView.vue'),
    },
    {
      path: '/judgelab/:calibrationId',
      name: 'judge-detail',
      component: () => import('@/views/JudgeDetailView.vue'),
    },
    {
      path: '/core-readiness',
      name: 'core-readiness',
      component: () => import('@/views/CoreReadinessView.vue'),
    },
  ],
})

export default router
