<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { workbenchApi } from '@/api/client'
import PageState from '@/components/PageState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { copy as c } from '@/composables/visualLocale'
import type { RunSummary } from '@/types/workbench'

// Product home: only the operator's own saved runs. Offline fixtures and demo records are excluded.
const runs = ref<RunSummary[]>([])
const loading = ref(true)
const error = ref<'' | 'unavailable' | 'failed'>('')
let sequence = 0
async function load() {
  const request = ++sequence
  loading.value = true; error.value = ''; runs.value = []
  try {
    const experiments = (await workbenchApi.listExperiments({ limit: 20 })).items.filter(item => item.provenance !== 'FIXTURE_OFFLINE')
    const pages = await Promise.all(experiments.map(item => workbenchApi.getRuns(item.experiment_id, { limit: 50 })))
    if (request !== sequence) return
    runs.value = pages.flatMap(page => page.items).filter(item => item.provenance !== 'FIXTURE_OFFLINE')
  } catch (failure) {
    if (request !== sequence) return
    const response = (failure as { response?: { status?: number } }).response
    error.value = !response || (response.status ?? 0) >= 500 ? 'unavailable' : 'failed'
  } finally { if (request === sequence) loading.value = false }
}
onMounted(load)
</script>
<template>
  <section class="runs-home" :aria-busy="loading">
    <div class="page-heading"><div><h2>{{ c('我的运行', 'My runs') }}</h2><p>{{ c('每次 AI Coding 运行：原运行状态、独立检查结果、未验证项与离线复核。', 'For each AI coding run: original state, independent checks, unverified items and offline re-review.') }}</p></div>
      <RouterLink class="primary-button" to="/external-runs" data-test="import-entry">{{ c('导入一次 Codex 运行', 'Import a Codex run') }}</RouterLink></div>
    <PageState v-if="loading" kind="loading">{{ c('正在读取已保存运行…', 'Loading saved runs…') }}</PageState>
    <PageState v-else-if="error" kind="error"><span>{{ error === 'unavailable' ? c('未连接到后端服务或尚未配置工作区；这不表示证据损坏。', 'The backend is not reachable or the workspace is not configured; this does not indicate corrupted evidence.') : c('运行列表暂不可读；不是空列表。', 'The run list is unavailable; it is not empty.') }}</span><button class="secondary-button" @click="load">{{ c('重试', 'Retry') }}</button></PageState>
    <div v-else-if="!runs.length" class="panel runs-empty" data-test="runs-empty">
      <h3>{{ c('还没有运行记录', 'No runs yet') }}</h3>
      <p>{{ c('把一次已保存的 Codex 运行记录和最终工作区导入进来，SameScale 会把 Agent 自报与独立验收分开展示，未检查的要求保持“未验证”。', 'Import a saved Codex run record and final workspace. SameScale keeps the agent self-report separate from independent checks; unchecked requirements stay not verified.') }}</p>
      <ol><li>{{ c('准备一条已保存的 Codex 运行记录（exec JSONL / Hook）和最终工作区', 'Prepare a saved Codex record (exec JSONL / Hook) and final workspace') }}</li><li>{{ c('在“导入运行”页解锁并选择已批准来源', 'Unlock the Import page and choose an approved source') }}</li><li>{{ c('查看验收摘要，导出证据离线复核', 'Read the acceptance summary and export evidence for offline re-review') }}</li></ol>
      <RouterLink class="primary-button" to="/external-runs">{{ c('导入一次 Codex 运行', 'Import a Codex run') }}</RouterLink>
    </div>
    <div v-else class="panel"><div class="table-scroll"><table data-test="runs-table"><thead><tr><th>{{ c('运行', 'Run') }}</th><th>{{ c('任务', 'Task') }}</th><th>{{ c('终态', 'Terminal state') }}</th><th>{{ c('结果', 'Outcome') }}</th><th>{{ c('来源', 'Provenance') }}</th></tr></thead>
      <tbody><tr v-for="run in runs" :key="run.run_id"><td><RouterLink class="table-link" :to="`/runs/${encodeURIComponent(run.run_id)}`">{{ run.run_id }}</RouterLink></td><td>{{ run.task_id }}@{{ run.task_version }}</td><td><StatusBadge :value="run.status" context="run" localized /></td><td><StatusBadge :value="run.normalized_outcome ?? 'NOT_VERIFIED'" localized /></td><td><StatusBadge :value="run.provenance" localized /></td></tr></tbody></table></div>
      <p class="muted">{{ c('外部导入的 Codex 运行在“导入运行”页解锁后查看。', 'Imported external Codex runs are listed on the Import page after unlocking.') }}</p></div>
  </section>
</template>
<style scoped>
.runs-home .page-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
.runs-empty { max-width: 760px; }
.runs-empty ol { padding-left: 1.2rem; color: #4a5160; }
.table-scroll { overflow-x: auto; }
th, td { text-align: left; padding: .5rem; }
</style>
