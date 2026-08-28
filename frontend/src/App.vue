<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => String(route.meta.title ?? route.name ?? 'Workbench'))

const navigation = [
  { to: '/', label: 'Overview', mark: 'OV' },
  { to: '/models', label: 'Models', mark: 'MO' },
  { to: '/providers', label: 'Providers', mark: 'PR' },
  { to: '/harnesses', label: 'Harnesses', mark: 'HA' },
  { to: '/capabilities', label: 'Capabilities', mark: 'CA' },
  { to: '/experiments', label: 'Experiments', mark: 'EX' },
  { to: '/regression', label: 'Regression', mark: 'RG' },
  { to: '/judgelab', label: 'JudgeLab', mark: 'JL' },
  { to: '/core-readiness', label: 'Core Readiness', mark: 'CR' },
  { to: '/settings', label: 'Settings', mark: 'SE' },
]
</script>

<template>
  <div class="workbench-shell">
    <aside class="sidebar" aria-label="Workbench navigation">
      <div class="brand">
        <span class="brand-mark">HL</span>
        <div>
          <strong>HarnessLab</strong>
          <small>Evidence Workbench</small>
        </div>
      </div>
      <nav>
        <RouterLink v-for="item in navigation" :key="item.to" :to="item.to" class="nav-link">
          <span class="nav-mark">{{ item.mark }}</span>
          {{ item.label }}
        </RouterLink>
      </nav>
      <div class="sidebar-foot">
        <span class="readonly-dot" />
        KEYLESS CONTROL PLANE
      </div>
    </aside>
    <main class="main-panel">
      <header class="topbar">
        <div>
          <span class="eyebrow">WORKBENCH / REGISTRY LITE</span>
          <h1>{{ title }}</h1>
        </div>
        <div class="topbar-status">
          <span class="status-pill neutral">BACKEND AUTHORITY</span>
          <span class="status-pill warn">REAL_* NOT_RUN</span>
        </div>
      </header>
      <div class="page-container">
        <ElTooltip content="Registry planning is backend-validated; credentials and runtime URLs never enter browser state." placement="bottom">
          <span class="readonly-context">KEYLESS PLANNING SURFACE</span>
        </ElTooltip>
        <RouterView />
      </div>
    </main>
  </div>
</template>
