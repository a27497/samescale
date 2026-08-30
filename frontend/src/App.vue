<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => String(route.meta.title ?? route.name ?? 'Workbench'))
const section = computed(() => String(route.meta.section ?? 'Workbench'))
const mobileNavOpen = ref(false)

const navigation = [
  {
    label: 'Workspace',
    items: [
      { to: '/', label: 'Overview', mark: 'OV' },
      { to: '/experiments', label: 'Experiments', mark: 'EX' },
      { to: '/run-control', label: 'Run Control', mark: 'RC' },
    ],
  },
  {
    label: 'Registry',
    items: [
      { to: '/models', label: 'Models', mark: 'MO' },
      { to: '/providers', label: 'Providers', mark: 'PR' },
      { to: '/harnesses', label: 'Harnesses', mark: 'HA' },
      { to: '/capabilities', label: 'Capabilities', mark: 'CA' },
    ],
  },
  {
    label: 'Evidence',
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
  () => { mobileNavOpen.value = false },
)
</script>

<template>
  <a class="skip-link" href="#main-content">Skip to content</a>
  <div class="workbench-shell" :class="{ 'nav-open': mobileNavOpen }">
    <button
      v-if="mobileNavOpen"
      class="nav-scrim"
      aria-label="Close navigation"
      @click="mobileNavOpen = false"
    />
    <aside id="workbench-navigation" class="sidebar" aria-label="Workbench navigation">
      <div class="brand">
        <span class="brand-mark">HL</span>
        <div>
          <strong>HarnessLab</strong>
          <small>CONTROLLED EVIDENCE</small>
        </div>
      </div>
      <nav aria-label="Product areas">
        <div v-for="group in navigation" :key="group.label" class="nav-group">
          <span class="nav-group-label">{{ group.label }}</span>
          <RouterLink v-for="item in group.items" :key="item.to" :to="item.to" class="nav-link">
            <span class="nav-mark">{{ item.mark }}</span>
            <span>{{ item.label }}</span>
          </RouterLink>
        </div>
      </nav>
      <div class="sidebar-foot">
        <div><span class="readonly-dot" />KEYLESS CONTROL PLANE</div>
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
          <span class="eyebrow">HARNESSLAB / {{ section.toUpperCase() }}</span>
          <h1>{{ title }}</h1>
          </div>
        </div>
        <div class="topbar-status">
          <span class="status-pill neutral">SERVER AUTHORITY</span>
          <span class="status-pill info"><span class="readonly-dot" /> KEYLESS</span>
        </div>
      </header>
      <div class="page-container">
        <ElTooltip content="Registry planning is backend-validated; credentials and runtime URLs never enter browser state." placement="bottom">
          <span class="readonly-context">BACKEND-VALIDATED · NO SECRET MATERIAL</span>
        </ElTooltip>
        <RouterView />
      </div>
    </main>
  </div>
</template>
