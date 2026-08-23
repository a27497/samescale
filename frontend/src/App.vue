<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => String(route.meta.title ?? route.name ?? 'Workbench'))

const navigation = [
  { to: '/', label: 'Overview', mark: 'OV' },
  { to: '/experiments', label: 'Experiments', mark: 'EX' },
  { to: '/regression', label: 'Regression', mark: 'RG' },
  { to: '/judgelab', label: 'JudgeLab', mark: 'JL' },
  { to: '/core-readiness', label: 'Core Readiness', mark: 'CR' },
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
        READ-ONLY OPERATOR UI
      </div>
    </aside>
    <main class="main-panel">
      <header class="topbar">
        <div>
          <span class="eyebrow">PHASE I / WORKBENCH</span>
          <h1>{{ title }}</h1>
        </div>
        <div class="topbar-status">
          <span class="status-pill neutral">POSTGRES EVIDENCE</span>
          <span class="status-pill warn">REAL_* NOT_RUN</span>
        </div>
      </header>
      <div class="page-container">
        <ElTooltip content="Evidence is read from PostgreSQL and immutable artifacts; execution stays in operator CLI paths." placement="bottom">
          <span class="readonly-context">READ_ONLY EVIDENCE SURFACE</span>
        </ElTooltip>
        <RouterView />
      </div>
    </main>
  </div>
</template>
