<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { externalEvidenceApi, type ApprovedEvidenceSource, type EvidenceDetail, type EvidenceSummary } from '@/api/externalEvidence'
import { copy as c } from '@/composables/visualLocale'

const route = useRoute(); const router = useRouter()
const token = ref(''); const unlocked = ref(false); const busy = ref(false); const error = ref('')
const sources = ref<ApprovedEvidenceSource[]>([]); const records = ref<EvidenceSummary[]>([])
const selected = ref(''); const consent = ref(false); const detail = ref<EvidenceDetail | null>(null)
const exportDigest = ref(''); let generation = 0; let alive = true
function report(e: unknown) {
  const code = (e as { response?: { data?: { error?: { code?: string } } } }).response?.data?.error?.code
  error.value = `${c('证据读取失败；请检查本地权限或完整性。', 'Evidence unavailable; check local access or integrity.')} ${code ?? ''}`
}
async function loadDetail() {
  const current = ++generation; detail.value = null; exportDigest.value = ''
  const id = route.params.identity
  if (!id || !unlocked.value) return
  try { const data = await externalEvidenceApi.detail(String(id), token.value); if (alive && current === generation) detail.value = data }
  catch (e) { if (alive && current === generation) report(e) }
}
async function unlock() {
  busy.value = true; error.value = ''; const current = ++generation
  try {
    const [a, b] = await Promise.all([externalEvidenceApi.sources(token.value), externalEvidenceApi.records(token.value)])
    if (!alive || current !== generation) return
    sources.value = a.items; records.value = b.items; unlocked.value = true; await loadDetail()
  } catch (e) { if (alive && current === generation) report(e) }
  finally { if (alive) busy.value = false }
}
async function ingest() {
  if (!consent.value || !selected.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    const data = await externalEvidenceApi.ingest(selected.value, token.value)
    if (!alive) return
    records.value = (await externalEvidenceApi.records(token.value)).items
    consent.value = false; await router.push(`/external-runs/${data.identity}`); await loadDetail()
  } catch (e) { if (alive) report(e) } finally { if (alive) busy.value = false }
}
async function download() {
  if (!detail.value || busy.value) return
  const id = detail.value.identity; const current = generation
  busy.value = true; error.value = ''
  try {
    const result = await externalEvidenceApi.export(id, token.value)
    if (!alive || current !== generation) return
    const url = URL.createObjectURL(result.blob); const link = document.createElement('a')
    link.href = url; link.download = `saved-evidence-${id.slice(0, 12)}.json`; link.click()
    URL.revokeObjectURL(url); exportDigest.value = result.digest
  } catch (e) { if (alive) report(e) } finally { if (alive) busy.value = false }
}
watch(selected, () => { consent.value = false })
watch(() => route.params.identity, () => { if (unlocked.value) loadDetail() })
onBeforeUnmount(() => { alive = false; generation++; token.value = ''; detail.value = null })
</script>

<template>
  <section class="external-evidence-page">
    <div class="page-heading"><div><h2>{{ c('外部 Codex 运行证据', 'Saved external Codex evidence') }}</h2><p>{{ c('导入已保存记录与最终工程快照，读取独立验收与诊断。', 'Import saved records and final workspaces; read independent verification and diagnosis.') }}</p></div></div>
    <p>{{ c('不会重新运行 Agent 或接管订阅登录。只接入操作员明确批准的脱敏来源；摘要验证完整性，不认证来源。', 'No Agent rerun or subscription login takeover. Only explicitly approved sanitized sources; hashes verify integrity, not origin.') }}</p>
    <p v-if="error" class="error-state" role="alert">{{ error }}</p>
    <form v-if="!unlocked" class="panel builder-form" @submit.prevent="unlock">
      <label>{{ c('本地操作员凭据', 'Local operator credential') }}<input v-model="token" data-test="operator" type="password" autocomplete="off" required /></label>
      <p>{{ c('凭据仅留在当前页面内存。公开 Demo 无权读取或导入。', 'Credential stays in page memory. Public Demo cannot read or import these records.') }}</p>
      <button class="primary-button" :disabled="busy || !token">{{ c('解锁并读取', 'Unlock and load') }}</button>
    </form>
    <template v-else>
      <form class="panel builder-form" @submit.prevent="ingest">
        <h3>{{ c('接入已批准来源', 'Import an approved source') }}</h3>
        <label>{{ c('来源', 'Source') }}<select v-model="selected" data-test="source"><option value="">{{ c('选择来源', 'Choose a source') }}</option><option v-for="source in sources" :key="source.source_id" :value="source.source_id">{{ source.source_id }} · {{ source.source_kind }} · {{ source.format }}</option></select></label>
        <p v-if="!sources.length">{{ c('暂无批准来源。请由操作员逐项审查、脱敏并固定摘要；不会扫描私人会话。', 'No approved sources. The operator must review, sanitize and pin individual items; private sessions are never scanned.') }}</p>
        <label><input v-model="consent" data-test="consent" type="checkbox" />{{ c('我批准接入所选保存证据和工程快照；这不授权运行 Agent。', 'I approve intake of this saved evidence and workspace; this does not authorize Agent execution.') }}</label>
        <button class="primary-button" data-test="import" :disabled="busy || !selected || !consent">{{ c('导入并检查完整性', 'Import and check integrity') }}</button>
      </form>
      <div class="panel"><h3>{{ c('已接入记录', 'Saved records') }}</h3><p v-if="!records.length">{{ c('暂无记录', 'No records') }}</p><ul><li v-for="record in records" :key="record.identity"><RouterLink :to="`/external-runs/${record.identity}`">{{ record.source_id }}</RouterLink> · {{ record.source_kind }} · {{ record.acceptance }}</li></ul></div>
      <div v-if="detail" class="panel" data-test="detail">
        <h3>{{ detail.record.source.source_id }} · {{ detail.record.source.source_kind }}</h3>
        <p data-test="acceptance">{{ c('独立 Workspace 验收', 'Independent Workspace acceptance') }}：{{ detail.diagnosis.workspace_acceptance }} · {{ detail.diagnosis.independent_verification.passed_checks }}/{{ detail.diagnosis.independent_verification.checks }}</p>
        <p>{{ detail.record.episode_identity ? c('原 Episode 保留', 'Original Episode retained') : c('未提供可导入的原 Episode；验收状态', 'No importable original Episode supplied; acceptance') }}：{{ detail.diagnosis.original_episode_acceptance }}</p>
        <p v-if="detail.diagnosis.workspace_acceptance === 'NOT_VERIFIED'">{{ c('缺少可信任务或独立验收，保持未验证。新的验收须由操作员在隔离 Verifier 中单独授权，随后刷新读取。', 'Without a trusted task or independent result, acceptance stays unverified. New checks require separate operator authorization in the isolated Verifier; reload afterwards.') }}</p>
        <p>{{ detail.record.completeness.integrity }} · {{ detail.record.completeness.coverage }} · {{ detail.record.completeness.origin }}</p>
        <p>{{ c('缺失字段', 'Missing fields') }}：{{ detail.record.completeness.missing_fields.join(', ') }}</p>
        <h4>{{ c('诊断观察', 'Diagnostic observations') }}</h4>
        <p>{{ c('Agent 自报事件', 'Agent report events') }}：{{ detail.diagnosis.agent_self_reports.join(', ') || '—' }} · {{ c('工具失败事件', 'Failed tool events') }}：{{ detail.diagnosis.observed_failed_tools.join(', ') || '—' }}</p>
        <p>{{ c('基础设施状态', 'Infrastructure status') }}：{{ detail.diagnosis.infrastructure.status }} · {{ c('根因未确立', 'Root cause not established') }}</p>
        <p>{{ c('文件变化', 'File changes') }}：{{ detail.diagnosis.file_changes.status }} · {{ detail.diagnosis.file_changes.paths.join(', ') || '—' }}</p>
        <div class="table-scroll"><table><caption>{{ c('脱敏 Trace；工具成功不等于任务通过', 'Sanitized Trace; tool success is not task acceptance') }}</caption><thead><tr><th>#</th><th>{{ c('事件', 'Event') }}</th><th>{{ c('状态', 'Status') }}</th><th>Exit</th></tr></thead><tbody><tr v-for="event in detail.record.trace" :key="event.ordinal"><td>{{ event.ordinal }}</td><td>{{ event.type }}</td><td>{{ event.status }}</td><td>{{ event.exit_code ?? 'UNKNOWN' }}</td></tr></tbody></table></div>
        <ul><li v-for="limit in detail.diagnosis.limits" :key="limit">{{ limit }}</li></ul>
        <button class="secondary-button" type="button" :disabled="busy" @click="loadDetail">{{ c('刷新独立验收', 'Reload independent verification') }}</button>
        <button class="secondary-button" data-test="export" type="button" :disabled="busy" @click="download">{{ c('导出脱敏证据与 Workspace', 'Export sanitized evidence and workspace') }}</button>
        <p v-if="exportDigest">{{ c('单独保存可信导出摘要供离线核验', 'Retain this trusted digest separately for offline replay') }}：<code>{{ exportDigest }}</code></p>
        <details><summary>{{ c('记录与 Workspace 身份', 'Record and Workspace identities') }}</summary><p><code>{{ detail.identity }}</code></p><p><code>{{ detail.record.workspace_digest }}</code></p><ul><li v-for="(digest, path) in detail.record.workspace_files" :key="path">{{ path }} · <code>{{ digest }}</code></li></ul></details>
      </div>
    </template>
  </section>
</template>

<style scoped>
.external-evidence-page .builder-form label:has(input[type="checkbox"]) { display: flex; align-items: flex-start; gap: .6rem; }
.external-evidence-page input[type="checkbox"] { width: auto; min-height: 0; flex-shrink: 0; margin-top: .25rem; }
.table-scroll { max-width: 100%; overflow-x: auto; }
th, td { text-align: left; padding: .35rem; white-space: nowrap; }
caption { white-space: normal; }
.external-evidence-page code { overflow-wrap: anywhere; }
</style>
