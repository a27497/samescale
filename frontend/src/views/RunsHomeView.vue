<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { workbenchApi } from '@/api/client'
import PageState from '@/components/PageState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { copy as c } from '@/composables/visualLocale'
import { experimentOption } from '@/utils/displayIdentity'
import type { ExperimentSummary, RunSummary } from '@/types/workbench'

// Product home: only the operator's own saved runs. Offline fixtures and demo records are excluded.
const runs = ref<RunSummary[]>([])
const examples = ref<ExperimentSummary[]>([])
type ExampleEvidence = { listed: number; total: number; verdicts: number; unavailable: number }
const exampleEvidence = ref<Record<string, ExampleEvidence>>({})
const loading = ref(true)
const error = ref<'' | 'unavailable' | 'failed'>('')
let sequence = 0
async function load() {
  const request = ++sequence
  loading.value = true; error.value = ''; runs.value = []; examples.value = []; exampleEvidence.value = {}
  try {
    const listed = (await workbenchApi.listExperiments({ limit: 20 })).items
    if (request !== sequence) return
    examples.value = listed.filter(item => item.provenance === 'FIXTURE_OFFLINE')
    const experiments = listed.filter(item => item.provenance !== 'FIXTURE_OFFLINE')
    const pages = await Promise.all(experiments.map(item => workbenchApi.getRuns(item.experiment_id, { limit: 50 })))
    if (request !== sequence) return
    runs.value = pages.flatMap(page => page.items).filter(item => item.provenance !== 'FIXTURE_OFFLINE')
  } catch (failure) {
    if (request !== sequence) return
    const response = (failure as { response?: { status?: number } }).response
    error.value = !response || (response.status ?? 0) >= 500 ? 'unavailable' : 'failed'
  } finally { if (request === sequence) loading.value = false }
  if (request === sequence && examples.value.length) void loadExampleEvidence(request)
}
// These are read-only projections of saved verdicts, never inferred from lifecycle or scores.
async function loadExampleEvidence(request: number) {
  for (const example of examples.value) {
    if (request !== sequence) return
    const evidence: ExampleEvidence = { listed: 0, total: 0, verdicts: 0, unavailable: 0 }
    try {
      const page = await workbenchApi.getRuns(example.experiment_id, { limit: 50 })
      if (request !== sequence) return
      evidence.listed = page.items.length; evidence.total = page.total
      // Bound concurrent detail reads; only the first API page is described.
      for (let offset = 0; offset < page.items.length; offset += 5) {
        if (request !== sequence) return
        const details = await Promise.allSettled(page.items.slice(offset, offset + 5).map(run => workbenchApi.getRun(run.run_id)))
        for (const result of details) {
          if (result.status === 'rejected') evidence.unavailable++
          else if (typeof result.value.verifier_passed === 'boolean') evidence.verdicts++
        }
      }
    } catch { evidence.unavailable++ }
    if (request === sequence) exampleEvidence.value[example.experiment_id] = evidence
  }
}
function evidenceStatus(evidence: ExampleEvidence) {
  if (evidence.verdicts) return 'REPORTED'
  return evidence.unavailable || !evidence.listed ? 'NOT_REPORTED' : 'NOT_VERIFIED'
}
onMounted(load)
onBeforeUnmount(() => { sequence++ })
</script>
<template>
  <section class="runs-home" :aria-busy="loading">
    <div class="page-heading"><div><h2>{{ c('我的运行', 'My runs') }}</h2><p>{{ c('每次 AI Coding 运行：原运行状态、独立检查结果、未验证项与离线复核。', 'For each AI coding run: original state, independent checks, unverified items and offline re-review.') }}</p></div>
      <RouterLink class="primary-button" to="/external-runs" data-test="import-entry">{{ c('导入运行记录', 'Import run evidence') }}</RouterLink></div>
    <PageState v-if="loading" kind="loading">{{ c('正在读取已保存运行…', 'Loading saved runs…') }}</PageState>
    <PageState v-else-if="error" kind="error"><span>{{ error === 'unavailable' ? c('未连接到后端服务或尚未配置工作区；这不表示证据损坏。', 'The backend is not reachable or the workspace is not configured; this does not indicate corrupted evidence.') : c('运行列表暂不可读；不是空列表。', 'The run list is unavailable; it is not empty.') }}</span><button class="secondary-button" @click="load">{{ c('重试', 'Retry') }}</button></PageState>
    <div v-else-if="!runs.length" class="panel runs-empty" data-test="runs-empty">
      <h3>{{ c('还没有个人运行记录', 'No personal runs yet') }}</h3>
      <p>{{ c('支持多种 Coding Agent。提供最终代码改动与任务验收条件，即使没有运行记录也能验收；Agent 自述与独立结果分开展示，未检查的要求保持“未验证”。', 'Provide final code changes and task acceptance conditions from different Coding Agents, with or without run records. Claims and independent checks remain separate; unchecked requirements stay unverified.') }}</p>
      <details><summary>{{ c('如何接入个人运行', 'How to import personal runs') }}</summary><ol><li>{{ c('准备最终代码 Workspace、任务验收条件与可选运行记录', 'Prepare the final code workspace, acceptance conditions and optional run records') }}</li><li>{{ c('在“导入运行记录”页解锁并选择已批准来源', 'Unlock the Import page and choose an approved source') }}</li><li>{{ c('查看验收摘要，导出证据离线复核', 'Read the acceptance summary and export evidence for offline re-review') }}</li></ol></details>
      <RouterLink class="primary-button" to="/external-runs">{{ c('导入运行记录', 'Import run evidence') }}</RouterLink>
    </div>
    <div v-else class="panel"><div class="table-scroll"><table data-test="runs-table"><thead><tr><th>{{ c('运行', 'Run') }}</th><th>{{ c('任务', 'Task') }}</th><th>{{ c('终态', 'Terminal state') }}</th><th>{{ c('结果', 'Outcome') }}</th><th>{{ c('来源', 'Provenance') }}</th></tr></thead>
      <tbody><tr v-for="run in runs" :key="run.run_id"><td><RouterLink class="table-link" :to="`/runs/${encodeURIComponent(run.run_id)}`">{{ run.run_id }}</RouterLink></td><td>{{ run.task_id }}@{{ run.task_version }}</td><td><StatusBadge :value="run.status" context="run" localized /></td><td><StatusBadge :value="run.normalized_outcome ?? 'NOT_VERIFIED'" localized /></td><td><StatusBadge :value="run.provenance" localized /></td></tr></tbody></table></div>
      <p class="muted">{{ c('外部导入记录在“导入运行记录”页解锁后查看。', 'Imported external records are listed on the Import page after unlocking.') }}</p></div>
    <div v-if="!loading && examples.length" class="panel demo-entry" data-test="example-entry">
      <div class="panel-title"><div><h3>{{ c('已有示例运行', 'Saved example runs') }}</h3><p>{{ c('这些是离线 Fake 示例，与个人运行分开展示，不代表真实模型执行。验收结论以各条运行记录为准。', 'Offline Fake examples are separate from personal runs and do not establish real model execution. Verdicts come from individual saved runs.') }}</p></div><StatusBadge value="FIXTURE_OFFLINE" /></div>
      <div class="toolbar"><RouterLink class="primary-button" to="/demo">{{ c('打开公开演示', 'Open public demo') }}</RouterLink></div>
      <div v-for="item in examples" :key="item.experiment_id" class="example-row" data-test="example-acceptance-row" :data-experiment="item.experiment_id">
        <RouterLink class="table-link" :to="`/experiments/${encodeURIComponent(item.experiment_id)}`">{{ experimentOption(item, examples) }} · {{ item.planned_run_count }} {{ c('次计划运行', 'planned runs') }}</RouterLink>
        <template v-if="exampleEvidence[item.experiment_id]">
          <p><StatusBadge :value="evidenceStatus(exampleEvidence[item.experiment_id]!)" />
            <template v-if="exampleEvidence[item.experiment_id]!.verdicts">{{ c('有已保存的独立验收结论：', 'Saved independent verdicts: ') }}{{ exampleEvidence[item.experiment_id]!.verdicts }} / {{ exampleEvidence[item.experiment_id]!.listed }} {{ c('条已读取记录。有结论不代表全部通过。', 'listed records. Having a verdict does not mean every task passed.') }}</template>
            <template v-else-if="exampleEvidence[item.experiment_id]!.unavailable">{{ c('验收结论暂时无法读取，请打开实验详情核对；不能据此判断是否已核验。', 'Verdicts are unavailable. Inspect experiment details; verification cannot be determined.') }}</template>
            <template v-else-if="exampleEvidence[item.experiment_id]!.listed">{{ c('当前读取的示例记录未提供独立验收结论。运行结束或分数不能替代验收结论。', 'The listed examples have no independent verdict. Completion or a score does not establish acceptance.') }}</template>
            <template v-else>{{ c('暂无已保存的示例运行记录，因此尚无可读取的验收结论。', 'No saved example runs are available, so no verdict can be read.') }}</template>
          </p>
          <p v-if="exampleEvidence[item.experiment_id]!.verdicts && exampleEvidence[item.experiment_id]!.verdicts < exampleEvidence[item.experiment_id]!.listed" class="muted">{{ c('其余已读取记录尚未核验或暂不可读，请查看详情逐项核对。', 'Other listed records are unverified or unavailable. Inspect individual details.') }}</p>
          <p v-if="exampleEvidence[item.experiment_id]!.total > exampleEvidence[item.experiment_id]!.listed" class="muted">{{ c('这里只读取前 50 条运行，剩余记录请在实验详情查看。', 'Only the first 50 runs are read here. Inspect experiment details for the rest.') }}</p>
        </template>
        <p v-else role="status" class="muted">{{ c('正在读取已保存的验收结论…', 'Reading saved verdicts…') }}</p>
      </div>
    </div>
    <p v-else-if="!loading && !error" class="muted"><RouterLink class="table-link" to="/experiments">{{ c('查看实验与运行 →', 'Browse experiments & runs →') }}</RouterLink> · <RouterLink class="table-link" to="/demo">{{ c('查看公开演示 →', 'Open public demo →') }}</RouterLink></p>
  </section>
</template>
<style scoped>
.runs-home .page-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
.runs-empty { max-width: 760px; }
.runs-empty ol { padding-left: 1.2rem; color: #4a5160; }
.example-row { padding-block: 14px; border-top: 1px solid var(--line); margin-top: 14px; }
.example-row p { margin-block: 8px 0; }
.table-scroll { overflow-x: auto; }
th, td { text-align: left; padding: .5rem; }
</style>
