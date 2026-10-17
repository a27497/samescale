<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { House, View, Document, Files, DataAnalysis, TrendCharts, Operation, Setting, Connection, Cpu, Box, Menu, Close, Collection, CircleCheck, Grid, Tools } from '@element-plus/icons-vue'
import { copy as c, initializeLocale, setLocale } from '@/composables/visualLocale'
import { preferences } from '@/composables/preferences'
import WorkbenchBrand from '@/components/WorkbenchBrand.vue'

initializeLocale()
const route = useRoute()
const titles: Record<string, [string, string]> = {
  runs: ['我的运行', 'My runs'], 'external-evidence': ['导入运行记录', 'Import run evidence'], 'external-evidence-detail': ['已保存外部运行证据', 'Saved external evidence'],
  'local-plans': ['验收任务', 'Acceptance tasks'], 'local-plan-detail': ['已保存验收任务计划', 'Saved acceptance task plan'],
  analyst: ['调查首页', 'Investigation home'], 'public-demo': ['公开演示', 'Public demo'],
  'run-detail': ['运行证据', 'Run evidence'], diagnosis: ['失败诊断', 'Failure diagnosis'],
  regression: ['候选对比', 'Regression comparison'], 'analyst-sessions': ['已保存调查', 'Saved investigations'],
  'run-control': ['运行控制', 'Run control'], experiments: ['实验与运行', 'Experiments & runs'],
  'experiment-detail': ['实验详情', 'Experiment details'], overview: ['总览', 'Overview'], settings: ['设置', 'Settings'],
}
const title = computed(() => { const pair = titles[String(route.name)]; return pair ? c(...pair) : String(route.meta.title ?? route.name ?? 'Workbench') })
const coreRoute = computed(() => ['runs', 'external-evidence', 'external-evidence-detail', 'run-detail', 'settings'].includes(String(route.name)))
const mobileNavOpen = ref(false)
const menuButton = ref<HTMLButtonElement | null>(null)
const navigationPanel = ref<HTMLElement | null>(null)
const advancedOpen = ref(false)
async function openNavigation() {
  mobileNavOpen.value = true
  await nextTick()
  navigationPanel.value?.querySelector<HTMLButtonElement>('.nav-close-button')?.focus()
}
function closeNavigation() { mobileNavOpen.value = false; menuButton.value?.focus() }
function navigationKeydown(event: KeyboardEvent) {
  if (!mobileNavOpen.value || event.key !== 'Tab' || !window.matchMedia('(max-width: 860px)').matches) return
  const controls = Array.from(navigationPanel.value?.querySelectorAll<HTMLElement>('a, button, summary') ?? []).filter(element => {
    const closed = element.closest('details:not([open])')
    return (!closed || element === closed.querySelector('summary')) && element.getClientRects().length > 0 && getComputedStyle(element).visibility !== 'hidden'
  })
  if (document.activeElement === (event.shiftKey ? controls[0] : controls.at(-1))) {
    event.preventDefault(); (event.shiftKey ? controls.at(-1) : controls[0])?.focus()
  }
}
const navigation = computed(() => [
  { label: c('工作台', 'Workbench'), items: [
    { to: '/runs', label: c('我的运行', 'My runs'), icon: House },
    { to: '/external-runs', label: c('导入运行记录', 'Import run evidence'), icon: Files },
    { to: '/acceptance-plans', label: c('验收范围方案', 'Acceptance scope'), icon: Document },
    { to: '/plans', label: c('验收任务', 'Acceptance tasks'), icon: Document },
    { to: '/settings', label: c('设置', 'Settings'), icon: Setting },
  ] },
])
const advanced = computed(() => [
  { to: '/experiments', label: c('实验与运行', 'Experiments & runs'), icon: Files },
  { to: '/diagnosis', label: c('失败诊断', 'Diagnosis'), icon: DataAnalysis },
  { to: '/regression', label: c('候选对比', 'Regression comparison'), icon: TrendCharts },
  { to: '/analyst', label: c('工程问题调查', 'Investigation'), icon: View },
  { to: '/analyst/sessions', label: c('已保存调查', 'Saved investigations'), icon: Document },
  { to: '/overview', label: c('总览', 'Overview'), icon: Grid },
  { to: '/run-control', label: c('运行控制', 'Run control'), icon: Operation },
  { to: '/judgelab', label: c('JudgeLab 校准', 'JudgeLab'), icon: Collection },
  { to: '/connections', label: c('连接与配置', 'Connections'), icon: Connection },
  { to: '/models', label: c('模型注册表', 'Models'), icon: Cpu },
  { to: '/providers', label: c('服务商注册表', 'Providers'), icon: Box },
  { to: '/harnesses', label: c('Harness 注册表', 'Harnesses'), icon: Tools },
  { to: '/capabilities', label: c('兼容能力', 'Capabilities'), icon: CircleCheck },
  { to: '/core-readiness', label: c('核心就绪度', 'Core readiness'), icon: CircleCheck },
])
watch(() => route.fullPath, () => {
  if (mobileNavOpen.value) closeNavigation()
  advancedOpen.value = !coreRoute.value && !['local-plans', 'local-plan-detail', 'acceptance-plans', 'acceptance-plan-detail'].includes(String(route.name))
}, { immediate: true })
watch(title, value => { document.title = `${value} · SameScale — AI Coding 任务验收与证据工作台` }, { immediate: true })
</script>

<template>
  <a class="skip-link" href="#main-content">{{ c('跳到主要内容', 'Skip to main content') }}</a>
  <div class="workbench-shell visual-v1" :class="{ 'nav-open': mobileNavOpen }" @keydown.esc="mobileNavOpen && closeNavigation()">
    <button v-if="mobileNavOpen" class="nav-scrim" :aria-label="c('关闭导航', 'Close navigation')" tabindex="-1" @click="closeNavigation" />
    <aside id="workbench-navigation" ref="navigationPanel" class="sidebar" :aria-label="c('产品导航', 'Product navigation')" @keydown="navigationKeydown">
      <button class="secondary-button nav-close-button" @click="closeNavigation"><Close class="ui-icon" />{{ c('关闭导航', 'Close navigation') }}</button>
      <RouterLink class="brand" to="/runs"><div><WorkbenchBrand /><small>{{ c('AI Coding 任务验收与证据工作台', 'AI Coding task acceptance & evidence workbench') }}</small></div></RouterLink>
      <nav :aria-label="c('产品功能', 'Product features')">
        <div v-for="group in navigation" :key="group.label" class="nav-group">
          <span class="nav-group-label">{{ group.label }}</span>
          <RouterLink v-for="item in group.items" :key="item.to" :to="item.to" class="nav-link" exact-active-class="nav-current" active-class="nav-parent"><component :is="item.icon" class="ui-icon" aria-hidden="true" /><span>{{ item.label }}</span></RouterLink>
        </div>
        <details :open="advancedOpen" class="advanced-nav" @toggle="advancedOpen = ($event.target as HTMLDetailsElement).open">
          <summary>{{ c('高级', 'Advanced') }}<small>{{ c('评测 · 诊断 · 注册', 'Evaluation · diagnosis · registry') }}</small></summary>
          <div class="nav-group"><RouterLink v-for="item in advanced" :key="item.to" :to="item.to" class="nav-link" exact-active-class="nav-current"><component :is="item.icon" class="ui-icon" aria-hidden="true" /><span>{{ item.label }}</span></RouterLink></div>
        </details>
      </nav>
      <div class="sidebar-foot"><small>SAMESCALE</small><strong>{{ c('来源与状态按记录展示', 'Provenance shown per record') }}</strong></div>
    </aside>
    <main id="main-content" class="main-panel" tabindex="-1">
      <header class="topbar"><div class="topbar-heading">
        <button ref="menuButton" class="mobile-menu-button" :aria-label="c('打开导航', 'Open navigation')" aria-controls="workbench-navigation" :aria-expanded="mobileNavOpen" @click="openNavigation"><Menu class="ui-icon" /></button>
        <RouterLink to="/runs" class="breadcrumb-workspace">{{ c('工作区', 'Workspace') }}</RouterLink><span class="breadcrumb-divider">/</span><h1>{{ title }}</h1>
      </div><div class="locale-switch" role="group" :aria-label="c('切换界面语言', 'Change interface language')"><button :aria-pressed="!['en', 'en-US'].includes(preferences.language)" @click="setLocale('zh-CN')">中文</button><button :aria-pressed="['en', 'en-US'].includes(preferences.language)" @click="setLocale('en-US')">English</button></div></header>
      <div class="page-container"><RouterView /></div>

    </main>
  </div>
</template>
