<script setup lang="ts">
import { t } from '@/composables/i18n'
import ProductStatus from '@/components/ProductStatus.vue'
import BrandMark from '@/components/BrandMark.vue'
import { navigationFailure } from '@/router'
import { useSidebarResize } from '@/composables/sidebarResize'
import { productModeKey, type ProductMode } from '@/composables/productContext'
import { provide } from 'vue'
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Setting, Plus, House, Document, FolderOpened, Connection } from '@element-plus/icons-vue'

const route = useRoute()
const productMode = ref<ProductMode>('unknown')
provide(productModeKey, productMode)
const sidebarResize = useSidebarResize()
const homeLabel = computed(() => productMode.value === 'workspace' ? '新建计划' : '首页')
const title = computed(() => route.path === '/analyst' ? homeLabel.value : String(route.meta.title ?? route.name ?? 'Workbench'))
const sectionLabels: Record<string, string> = { Investigation: '证据分析', Workspace: '评测与比较', Registry: '连接与配置', Evidence: '评测证据', System: '项目设置' }
const section = computed(() => sectionLabels[String(route.meta.section)] ?? '工作区')
const mobileNavOpen = ref(false)
const mobileMenu = ref<HTMLButtonElement | null>(null)
const navigationNotice = ref<HTMLElement | null>(null)
watch(navigationFailure, async failure => {
  if (!failure) return
  mobileNavOpen.value = false
  await nextTick()
  navigationNotice.value?.focus()
  navigationNotice.value?.scrollIntoView({ block: 'nearest' })
})
async function closeNavigation() {
  mobileNavOpen.value = false
  await nextTick()
  mobileMenu.value?.focus()
}
watch(mobileNavOpen, async open => {
  if (open) { await nextTick(); document.querySelector<HTMLAnchorElement>('.brand')?.focus() }
})
function trapNavigation(event: KeyboardEvent) {
  if (!mobileNavOpen.value || event.key !== 'Tab') return
  const links = [...document.querySelectorAll<HTMLElement>('.sidebar a, .sidebar summary, .sidebar button:not(:disabled)')].filter(item => item.getClientRects().length)
  const first = links[0]; const last = links.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
const desktopQuery = window.matchMedia?.('(min-width: 861px)')
function closeOnDesktop() { if (desktopQuery?.matches) mobileNavOpen.value = false }
onMounted(() => desktopQuery?.addEventListener('change', closeOnDesktop))
onBeforeUnmount(() => desktopQuery?.removeEventListener('change', closeOnDesktop))
const isHome = computed(() => route.path === '/analyst')
const recordNavigation = [
  { to: '/experiments', label: '实验记录' }, { to: '/overview', label: '概览' },
  { to: '/run-control', label: '运行记录' }, { to: '/analyst/sessions', label: '调查' },
  { to: '/diagnosis', label: '失败诊断' }, { to: '/regression', label: '回归对比' },
  { to: '/judgelab', label: '评审校准' }, { to: '/core-readiness', label: '就绪检查' },
]
const configNavigation = [
  { to: '/connections', label: '连接总览' },
  { to: '/models', label: '模型' }, { to: '/harnesses', label: 'Agent 运行时' },
  { to: '/providers', label: '模型服务' }, { to: '/capabilities', label: '兼容性' },
]
const isNew = computed(() => isHome.value || ['/examples', '/experiments/new'].includes(route.path))
const isConfig = computed(() => configNavigation.some(item => item.to === route.path))
const isRecord = computed(() => !isNew.value && (recordNavigation.some(item => item.to === route.path) || route.path.startsWith('/experiments/') || route.path.startsWith('/runs/') || route.path.startsWith('/judgelab/')))
const navigation = computed(() => [
  { to: '/analyst', label: homeLabel.value, icon: productMode.value === 'workspace' ? Plus : House },
  { to: '/experiments', label: '实验记录', icon: Document },
  { to: '/tasks', label: '任务集', icon: FolderOpened },
  { to: '/connections', label: '连接与配置', icon: Connection },
])
const visibleNavigation = computed(() => navigation.value.filter(item => productMode.value === 'workspace' || item.to === '/analyst' || (productMode.value === 'demo' && item.to === '/tasks')))
const secondaryNavigation = computed(() => productMode.value !== 'workspace' ? [] : isConfig.value ? configNavigation : isRecord.value ? recordNavigation : [])
function isCurrent(to: string) {
  return to === '/analyst' ? isNew.value : to === '/experiments' ? isRecord.value : to === '/connections' ? isConfig.value : route.path === to
}
function isSecondaryCurrent(to: string) {
  return route.path === to || (to === '/run-control' && route.path.startsWith('/runs/')) || (['/experiments', '/judgelab'].includes(to) && route.path.startsWith(`${to}/`))
}

watch(
  () => [route.fullPath, t(title.value)],
  () => {
    mobileNavOpen.value = false
    document.title = `${t(title.value)} · SameScale`
    document.querySelector('meta[name="description"]')?.setAttribute('content', `SameScale · ${t('AI 编程评测与诊断工作台')}`)
  },
  { immediate: true },
)
</script>

<template>
  <a class="skip-link" href="#main-content">{{ t('跳至主要内容') }}</a>
  <div class="workbench-shell" :class="{ 'home-shell': isHome, 'nav-open': mobileNavOpen, 'resizing-sidebar': sidebarResize.resizing.value }" :style="{ '--sidebar-width': `${sidebarResize.width.value}px` }" @keydown.esc="mobileNavOpen && closeNavigation()">
    <button
      v-if="mobileNavOpen"
      class="nav-scrim"
      :aria-label="t('关闭导航')"
      @click="closeNavigation"
    />
    <aside id="workbench-navigation" class="sidebar" @keydown="trapNavigation" :aria-label="t('工作区导航')">
      <RouterLink class="brand" to="/analyst" :aria-label="t('SameScale 首页')">
        <BrandMark />
        <div>
          <strong>SameScale</strong>
        </div>
      </RouterLink>
      <nav :aria-label="t('产品导航')">
        <div class="nav-group">
          <RouterLink v-for="item in visibleNavigation" :key="item.to" :to="item.to" class="nav-link" :class="{ 'nav-current': isCurrent(item.to) }" :aria-current="isCurrent(item.to) ? 'page' : undefined" active-class="nav-parent">
            <component :is="item.icon" class="nav-icon" aria-hidden="true" /><span>{{ t(item.label) }}</span>
          </RouterLink>
        </div>
      </nav>
      <div class="sidebar-foot">
        <RouterLink to="/settings" class="nav-link"><Setting class="nav-icon" aria-hidden="true" />{{ t('设置') }}</RouterLink>
        <ProductStatus @mode="productMode = $event" />
      </div>
    </aside>
    <div
      class="sidebar-resizer" role="separator" tabindex="0" aria-orientation="vertical"
      aria-controls="workbench-navigation" :aria-label="t('调整侧栏宽度')"
      :aria-valuemin="sidebarResize.minimum" :aria-valuemax="sidebarResize.maxWidth.value"
      :aria-valuenow="sidebarResize.width.value" :title="t('拖动调整宽度，双击恢复默认')"
      @pointerdown="sidebarResize.start" @pointermove="sidebarResize.move"
      @pointerup="sidebarResize.end" @pointercancel="sidebarResize.end" @lostpointercapture="sidebarResize.end"
      @keydown="sidebarResize.keydown" @dblclick="sidebarResize.reset"
    />
    <main :inert="mobileNavOpen" id="main-content" class="main-panel" tabindex="-1">
      <header class="topbar">
        <div class="topbar-heading">
          <button
            ref="mobileMenu"
            class="mobile-menu-button"
            :aria-label="t('打开导航')"
            aria-controls="workbench-navigation"
            :aria-expanded="mobileNavOpen"
            @click="mobileNavOpen = true"
          >
            <span /><span /><span />
          </button>
          <div v-if="!isHome">
          <span v-if="section !== title" class="eyebrow">{{ t(section) }}</span>
          <h1>{{ t(title) }}</h1>
          </div>
        </div>
        <RouterLink v-if="!isHome" class="workspace-context table-link" to="/analyst">{{ t('返回首页') }}</RouterLink>
      </header>
      <div class="page-container">
        <section v-if="navigationFailure" ref="navigationNotice" class="notice" role="alert" tabindex="-1">
          <strong>{{ t('页面加载失败') }}</strong>
          <p>{{ t('服务可能已更新或网络暂时中断。请先保存当前页面的未提交内容，再重新加载。') }}</p>
          <a :href="navigationFailure.href" class="table-link">{{ t('重新加载并打开目标页面') }}</a>
        </section>
        <nav v-if="secondaryNavigation.length" class="secondary-navigation" :aria-label="t(isConfig ? '配置导航' : '实验与分析导航')">
          <RouterLink v-for="item in secondaryNavigation" :key="item.to" :to="item.to" :aria-current="isSecondaryCurrent(item.to) ? 'page' : undefined">{{ t(item.label) }}</RouterLink>
        </nav>
        <RouterLink v-if="route.path.startsWith('/experiments/')" class="back-link" to="/experiments">{{ t('返回实验列表') }}</RouterLink>
        <RouterLink v-else-if="route.path.startsWith('/judgelab/')" class="back-link" to="/judgelab">{{ t('返回评审校准') }}</RouterLink>
        <RouterView :key="route.path" />
      </div>
    </main>
  </div>
</template>

<style scoped>
.home-shell .main-panel { background: #fff; }
.home-shell .topbar { display: none; }
.secondary-navigation { display: flex; flex-wrap: wrap; gap: 4px 16px; margin: 0 0 24px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
.secondary-navigation a { padding: 6px 0; text-decoration: none; color: var(--muted); font: var(--type-control); }
.secondary-navigation a[aria-current] { color: var(--ink); text-decoration: underline; text-underline-offset: 8px; }
@media (max-width: 860px) { .home-shell .topbar { display: flex; min-height: 64px; border-bottom: 0; background: #fff; } }
</style>
