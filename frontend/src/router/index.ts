import { nextTick } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

// Ephemeral UI state only; no evidence or credentials are stored.
const disclosureHistory = new Map<string, Array<{ index: number; summary: string }>>()

const router = createRouter({
  history: createWebHistory(),
  async scrollBehavior(to, from, savedPosition) {
    // Query-only selections keep their viewport. History returns wait for async evidence.
    if (!savedPosition && to.path === from.path && !to.hash) return false
    await nextTick()
    if (document.querySelector('.page-container')) {
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
      if (document.querySelector('.page-container [aria-busy="true"], .page-container .loading-state')) {
        await new Promise<void>(resolve => {
          const observer = new MutationObserver(() => {
            if (!document.querySelector('.page-container [aria-busy="true"], .page-container .loading-state')) finish()
          })
          const timer = window.setTimeout(finish, 5000)
          function finish() { observer.disconnect(); window.clearTimeout(timer); resolve() }
          observer.observe(document.querySelector('.page-container')!, { childList: true, subtree: true, attributes: true })
        })
      }
    }
    if (savedPosition) {
      const details = document.querySelectorAll<HTMLDetailsElement>('.page-container details')
      for (const saved of disclosureHistory.get(to.fullPath) ?? []) {
        const detail = details[saved.index]
        if (detail?.querySelector(':scope > summary')?.textContent === saved.summary) detail.open = true
      }
      await nextTick()
    }
    return savedPosition ?? (to.hash ? { el: to.hash, top: 96 } : { left: 0, top: 0 })
  },
  routes: [
    { path: '/', redirect: '/analyst' },
    { path: '/demo', name: 'public-demo', component: () => import('@/views/PublicDemoView.vue'), meta: { title: '公开演示 · Public Demo', section: 'Evidence' } },
    {
      path: '/overview',
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
    { path: '/connections', name: 'connections', component: () => import('@/views/ConnectionsView.vue'), meta: { title: 'Connections', section: 'Registry' } },
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
    { path: '/analyst', name: 'analyst', component: () => import('@/views/AnalystHomeView.vue'), meta: { title: '工程问题调查', section: 'Investigation' } },
    { path: '/analyst/sessions', name: 'analyst-sessions', component: () => import('@/views/AnalystView.vue'), meta: { title: '已保存调查', section: 'Investigation' } },
    {
      path: '/diagnosis',
      name: 'diagnosis',
      component: () => import('@/views/DiagnosisView.vue'),
      meta: { title: 'Failure Diagnosis', section: 'Evidence' },
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

router.beforeEach((_to, from) => {
  disclosureHistory.set(from.fullPath, Array.from(document.querySelectorAll<HTMLDetailsElement>('.page-container details')).flatMap((detail, index) => detail.open ? [{ index, summary: detail.querySelector(':scope > summary')?.textContent ?? '' }] : []))
  if (disclosureHistory.size > 50) disclosureHistory.delete(disclosureHistory.keys().next().value!)
})

export default router
