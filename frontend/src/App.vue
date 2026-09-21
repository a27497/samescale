<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => String(route.meta.title ?? route.name ?? 'Workbench'))
const section = computed(() => String(route.meta.section ?? 'Workbench'))
const mobileNavOpen = ref(false)
const advancedOpen = ref(false)
const isInvestigation = computed(() => route.meta.section === 'Investigation')

const navigation = [
  { label: '调查工作区', items: [
    { to: '/analyst', label: '开始调查', mark: '01' },
    { to: '/analyst/sessions', label: '已保存调查', mark: '02' },
  ] },
  {
    label: '评测实验 · Advanced',
    items: [
      { to: '/overview', label: 'Overview', mark: 'OV' },
      { to: '/experiments', label: 'Experiments', mark: 'EX' },
      { to: '/run-control', label: 'Run Control', mark: 'RC' },
    ],
  },
  {
    label: 'Registry',
    items: [
      { to: '/connections', label: '连接与配置', mark: 'CO' },
      { to: '/models', label: 'Models', mark: 'MO' },
      { to: '/providers', label: 'Providers', mark: 'PR' },
      { to: '/harnesses', label: 'Harnesses', mark: 'HA' },
      { to: '/capabilities', label: 'Capabilities', mark: 'CA' },
    ],
  },
  {
    label: '评测证据 · Advanced',
    items: [
      { to: '/regression', label: 'Regression', mark: 'RG' },
      { to: '/diagnosis', label: 'Diagnosis', mark: 'DX' },
      { to: '/judgelab', label: 'JudgeLab', mark: 'JL' },
      { to: '/core-readiness', label: 'Core Readiness', mark: 'CR' },
    ],
  },
  { label: 'System', items: [{ to: '/settings', label: 'Settings', mark: 'SE' }] },
]

watch(
  () => route.fullPath,
  () => {
    mobileNavOpen.value = false
    advancedOpen.value = !isInvestigation.value
    document.title = `${title.value} · SameScale`
  },
  { immediate: true },
)
</script>

<template>
  <a class="skip-link" href="#main-content">Skip to content</a>
  <div class="workbench-shell" :class="{ 'nav-open': mobileNavOpen }" @keydown.esc="mobileNavOpen = false">
    <button
      v-if="mobileNavOpen"
      class="nav-scrim"
      aria-label="Close navigation"
      @click="mobileNavOpen = false"
    />
    <aside id="workbench-navigation" class="sidebar" aria-label="Workbench navigation">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">S=</span>
        <div>
          <strong>SameScale</strong>
          <small>EVIDENCE → INSIGHT</small>
        </div>
      </div>
      <nav aria-label="Product areas">
        <div class="nav-group">
          <span class="nav-group-label">{{ navigation[0]!.label }}</span>
          <RouterLink v-for="item in navigation[0]!.items" :key="item.to" :to="item.to" class="nav-link" exact-active-class="nav-current" active-class="nav-parent">
            <span class="nav-mark">{{ item.mark }}</span><span>{{ item.label }}</span>
          </RouterLink>
        </div>
        <details :open="advancedOpen" class="advanced-nav" @toggle="advancedOpen = ($event.target as HTMLDetailsElement).open">
          <summary>评测工具 · Advanced</summary>
          <div v-for="group in navigation.slice(1)" :key="group.label" class="nav-group">
            <span class="nav-group-label">{{ group.label }}</span>
            <RouterLink v-for="item in group.items" :key="item.to" :to="item.to" class="nav-link">
              <span class="nav-mark">{{ item.mark }}</span><span>{{ item.label }}</span>
            </RouterLink>
          </div>
        </details>
      </nav>
      <div class="sidebar-foot">
        <div><span class="readonly-dot" />LOCAL WORKBENCH</div>
        <small>Secrets stay server-side</small>
      </div>
    </aside>
    <main id="main-content" class="main-panel" tabindex="-1">
      <header class="topbar">
        <div class="topbar-heading">
          <button
            class="mobile-menu-button"
            aria-label="Open navigation"
            aria-controls="workbench-navigation"
            :aria-expanded="mobileNavOpen"
            @click="mobileNavOpen = true"
          >
            <span /><span /><span />
          </button>
          <div>
          <span class="eyebrow">SAMESCALE / {{ section.toUpperCase() }}</span>
          <h1>{{ title }}</h1>
          </div>
        </div>
        <div v-if="!isInvestigation" class="topbar-status">
          <span class="status-pill neutral">SERVER AUTHORITY</span>
          <span class="status-pill info">EXPLICIT EXECUTION</span>
        </div>
      </header>
      <div class="page-container">
        <ElTooltip v-if="!isInvestigation" content="Registry planning is backend-validated; credentials and runtime URLs never enter browser state." placement="bottom">
          <span class="readonly-context">BACKEND-VALIDATED · NO SECRET MATERIAL</span>
        </ElTooltip>
        <RouterView />
      </div>
    </main>
  </div>
</template>
