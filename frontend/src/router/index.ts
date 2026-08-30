import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'overview',
      component: () => import('@/views/OverviewView.vue'),
      meta: { title: 'Overview', section: 'Workspace' },
    },
    {
      path: '/experiments',
      name: 'experiments',
      component: () => import('@/views/ExperimentsView.vue'),
      meta: { title: 'Experiments', section: 'Workspace' },
    },
    {
      path: '/experiments/new',
      name: 'experiment-new',
      component: () => import('@/views/ExperimentBuilderView.vue'),
      meta: { title: 'New experiment plan', section: 'Workspace' },
    },
    {
      path: '/run-control',
      name: 'run-control',
      component: () => import('@/views/RunControlView.vue'),
      meta: { title: 'Run Control', section: 'Workspace' },
    },
    { path: '/models', name: 'models', component: () => import('@/views/ModelsView.vue'), meta: { title: 'Model Registry', section: 'Registry' } },
    {
      path: '/providers',
      name: 'providers',
      component: () => import('@/views/ProvidersView.vue'),
      meta: { title: 'Provider Registry', section: 'Registry' },
    },
    {
      path: '/harnesses',
      name: 'harnesses',
      component: () => import('@/views/HarnessesView.vue'),
      meta: { title: 'Harness Registry', section: 'Registry' },
    },
    {
      path: '/capabilities',
      name: 'capabilities',
      component: () => import('@/views/CapabilitiesView.vue'),
      meta: { title: 'Capability Registry', section: 'Registry' },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { title: 'Settings', section: 'System' },
    },
    {
      path: '/experiments/:id',
      name: 'experiment-detail',
      component: () => import('@/views/ExperimentDetailView.vue'),
      meta: { title: 'Experiment evidence', section: 'Evidence' },
    },
    {
      path: '/runs/:runId',
      name: 'run-detail',
      component: () => import('@/views/RunDetailView.vue'),
      meta: { title: 'Run evidence', section: 'Evidence' },
    },
    {
      path: '/regression',
      name: 'regression',
      component: () => import('@/views/RegressionView.vue'),
      meta: { title: 'Regression', section: 'Evidence' },
    },
    {
      path: '/judgelab',
      name: 'judgelab',
      component: () => import('@/views/JudgeLabView.vue'),
      meta: { title: 'JudgeLab', section: 'Evidence' },
    },
    {
      path: '/judgelab/:calibrationId',
      name: 'judge-detail',
      component: () => import('@/views/JudgeDetailView.vue'),
      meta: { title: 'Judge calibration', section: 'Evidence' },
    },
    {
      path: '/core-readiness',
      name: 'core-readiness',
      component: () => import('@/views/CoreReadinessView.vue'),
      meta: { title: 'Core Readiness', section: 'Evidence' },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
      meta: { title: 'Page not found', section: 'Workbench' },
    },
  ],
})

export default router
