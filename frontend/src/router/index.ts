import { createRouter, createWebHistory } from 'vue-router'
import { installNavigationRecovery } from './recovery'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, top: 100 }
    if (to.path !== from.path) return { top: 0 }
  },
  routes: [
    { path: '/', redirect: '/analyst' },
    {
      path: '/overview',
      name: 'overview',
      component: () => import('@/views/OverviewView.vue'),
      meta: { title: '评测概览', section: 'Workspace' },
    },
    {
      path: '/experiments',
      name: 'experiments',
      component: () => import('@/views/ExperimentsView.vue'),
      meta: { title: '实验记录', section: 'Workspace' },
    },
    {
      path: '/experiments/new',
      name: 'experiment-new',
      component: () => import('@/views/ExperimentBuilderView.vue'),
      meta: { title: '创建评测计划', section: 'Workspace' },
    },
    { path: '/tasks', name: 'tasks', component: () => import('@/views/TasksView.vue'), meta: { title: '任务集', section: 'Workspace' } },
    {
      path: '/run-control',
      name: 'run-control',
      component: () => import('@/views/RunControlView.vue'),
      meta: { title: '运行记录', section: 'Workspace' },
    },
    { path: '/connections', name: 'connections', component: () => import('@/views/ConnectionsView.vue'), meta: { title: '连接总览', section: 'Registry' } },
    { path: '/models', name: 'models', component: () => import('@/views/ModelsView.vue'), meta: { title: '模型配置', section: 'Registry' } },
    {
      path: '/providers',
      name: 'providers',
      component: () => import('@/views/ProvidersView.vue'),
      meta: { title: '模型服务', section: 'Registry' },
    },
    {
      path: '/harnesses',
      name: 'harnesses',
      component: () => import('@/views/HarnessesView.vue'),
      meta: { title: 'Agent 运行时', section: 'Registry' },
    },
    {
      path: '/capabilities',
      name: 'capabilities',
      component: () => import('@/views/CapabilitiesView.vue'),
      meta: { title: '兼容性检查', section: 'Registry' },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { title: '项目设置', section: 'System' },
    },
    {
      path: '/experiments/:id',
      name: 'experiment-detail',
      component: () => import('@/views/ExperimentDetailView.vue'),
      meta: { title: '实验证据', section: 'Evidence' },
    },
    {
      path: '/runs/:runId',
      name: 'run-detail',
      component: () => import('@/views/RunDetailView.vue'),
      meta: { title: '运行证据', section: 'Evidence' },
    },
    {
      path: '/regression',
      name: 'regression',
      component: () => import('@/views/RegressionView.vue'),
      meta: { title: '回归对比', section: 'Evidence' },
    },
    { path: '/examples', name: 'examples', component: () => import('@/views/ExamplesView.vue'), meta: { title: '示例', section: 'Workspace' } },
    { path: '/analyst', name: 'analyst', component: () => import('@/views/AnalystHomeView.vue'), meta: { title: '首页', section: 'Workspace' } },
    { path: '/analyst/sessions', name: 'analyst-sessions', component: () => import('@/views/AnalystView.vue'), meta: { title: '已保存调查', section: 'Investigation' } },
    {
      path: '/diagnosis',
      name: 'diagnosis',
      component: () => import('@/views/DiagnosisView.vue'),
      meta: { title: '失败诊断', section: 'Evidence' },
    },
    {
      path: '/judgelab',
      name: 'judgelab',
      component: () => import('@/views/JudgeLabView.vue'),
      meta: { title: '评审校准', section: 'Evidence' },
    },
    {
      path: '/judgelab/:calibrationId',
      name: 'judge-detail',
      component: () => import('@/views/JudgeDetailView.vue'),
      meta: { title: '校准详情', section: 'Evidence' },
    },
    {
      path: '/core-readiness',
      name: 'core-readiness',
      component: () => import('@/views/CoreReadinessView.vue'),
      meta: { title: '就绪检查', section: 'Evidence' },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
      meta: { title: '页面不存在', section: 'Workbench' },
    },
  ],
})

router.beforeEach(to => {
  if (to.path === '/analyst' && ['comparison', 'offline', 'historical'].includes(String(to.query.example))) {
    return { path: '/examples', query: to.query, hash: to.hash, replace: true }
  }
})

export const navigationFailure = installNavigationRecovery(router)

export default router
