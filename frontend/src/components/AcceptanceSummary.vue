<script setup lang="ts">
import StatusBadge from '@/components/StatusBadge.vue'
import { copy as c } from '@/composables/visualLocale'
import type { AcceptanceRow } from '@/utils/acceptanceSummary'
defineProps<{ rows: AcceptanceRow[] }>()
</script>
<template>
  <article class="panel acceptance-summary" data-test="acceptance-summary" :aria-label="c('验收摘要', 'Acceptance summary')">
    <div class="panel-header"><h3>{{ c('验收摘要', 'Acceptance summary') }}</h3><span class="muted">{{ c('仅展示已保存记录；缺失即为未知，不推断通过', 'Saved records only; missing data stays unknown, never an inferred pass') }}</span></div>
    <dl class="acceptance-rows">
      <div v-for="row in rows" :key="row.key" class="acceptance-row" :data-test="`acceptance-${row.key}`">
        <dt>{{ row.label }}</dt>
        <dd><StatusBadge :value="row.status" localized /><span class="acceptance-detail">{{ row.detail }}</span></dd>
      </div>
    </dl>
  </article>
</template>
<style scoped>
.acceptance-summary { border-left: 4px solid #4263D5; }
.acceptance-rows { display: grid; gap: 0; margin: 0; }
.acceptance-row { display: grid; grid-template-columns: 220px 1fr; gap: 1rem; padding: .75rem 0; border-top: 1px solid #e6e8ef; }
.acceptance-row:first-child { border-top: 0; }
.acceptance-row dt { font-weight: 600; color: #1f2430; }
.acceptance-row dd { margin: 0; display: flex; gap: .75rem; align-items: baseline; flex-wrap: wrap; }
.acceptance-detail { color: #4a5160; }
</style>
