<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { externalEvidenceApi, type ApprovedEvidenceSource, type EvidenceDetail, type EvidenceSummary } from '@/api/externalEvidence'
import { copy as c } from '@/composables/visualLocale'

const route = useRoute(); const router = useRouter()
const token = ref(''); const unlocked = ref(false); const busy = ref(false); const error = ref('')
const sources = ref<ApprovedEvidenceSource[]>([]); const records = ref<EvidenceSummary[]>([])
const selected = ref(''); const consent = ref(false); const detail = ref<EvidenceDetail | null>(null)
const listError = ref(''); const checkStatus = ref(''); const configurationNotice = ref('')
const exportDigest = ref(''); let generation = 0; let alive = true
const globalCodes = ['EXTERNAL_EVIDENCE_DISABLED', 'EVIDENCE_POLICY_PERMISSION', 'EVIDENCE_POLICY_INVALID', 'EVIDENCE_STORAGE_UNSAFE', 'LOCAL_CONFIGURATION_DISABLED', 'LOCAL_OPERATOR_REQUIRED', 'LOCAL_ORIGIN_REQUIRED']
const guidance: Record<string, string> = {
  EXTERNAL_EVIDENCE_DISABLED: c('尚未配置证据策略。按下方 Quickstart 设置策略后重启私有 API。', 'Evidence policy is unset. Follow the Quickstart and restart the private API.'),
  EVIDENCE_POLICY_PERMISSION: c('策略权限错误。检查文件归属与 0600 权限；不要读取认证文件。', 'Check policy ownership and mode 0600; never use authentication files.'),
  EVIDENCE_POLICY_INVALID: c('策略或路径无效。运行只读配置检查，检查格式、独立目录和路径。', 'Run the read-only configuration check; review policy schema and separate canonical paths.'),
  EVIDENCE_STORAGE_UNSAFE: c('全局存储安全检查失败；拒绝整个请求。由操作员检查目录权限、链接与容量。', 'Global storage safety failed; access is refused. Review permissions, links and limits.'),
  LOCAL_CONFIGURATION_DISABLED: c('未配置私有操作员权限。按 Quickstart 配置独立本地凭据。', 'Configure private local operator access using the Quickstart.'),
  LOCAL_OPERATOR_REQUIRED: c('操作员凭据不正确；请重新输入。', 'The operator credential is incorrect; enter it again.'),
  LOCAL_ORIGIN_REQUIRED: c('请从同源 loopback 私有产品地址访问。', 'Use the same-origin private loopback address.'),
  SOURCE_LOCATION_UNAVAILABLE: c('批准来源或 Workspace 不可访问；操作员应检查配置位置。', 'An approved source or Workspace location is unavailable.'),
  EVIDENCE_PIN_MISMATCH: c('保存的摘要与批准来源或 Workspace 不匹配。停止接入并重新审查；不要盲目重算摘要覆盖旧 pin。', 'Retained source/Workspace pins do not match. Stop and review; do not blindly replace approved pins.'),
  EVIDENCE_SENSITIVE_INPUT: c('拒绝含敏感内容或受保护路径的输入。人工脱敏审查后才能批准。', 'Sensitive content or protected paths were rejected. Manual privacy review is required.'),
  EVIDENCE_INPUT_UNSUPPORTED: c('输入格式或文件类型不支持；请检查支持的 JSONL/Hook 格式与 UTF-8 快照要求。', 'Check the supported JSONL/Hook formats and UTF-8 snapshot limits.'),
  EVIDENCE_SOURCE_NOT_APPROVED: c('来源未在策略中明确批准。请由操作员逐项审查。', 'The source is not explicitly approved in the policy.'),
  EVIDENCE_IMPORT_REJECTED: c('来源未通过安全或结构检查；检查支持格式和批准绑定。未生成替代结果。', 'Source safety or structure failed. Review supported formats and approved bindings; no replacement result was created.'),
  EVIDENCE_INTEGRITY_ERROR: c('该记录、Workspace 或验收摘要已损坏；拒绝详情与导出，健康记录仍可访问。', 'This record, Workspace or receipt failed integrity checks. Detail/export are refused; healthy records remain accessible.'),
  EVIDENCE_RECORD_CORRUPT: c('记录、Workspace 或验收摘要未通过完整性检查；没有可用验收结果。', 'Record, Workspace or receipt integrity failed; no acceptance result is available.'),
}
function errorCode(e: unknown) {
  const code = (e as { response?: { data?: { error?: { code?: string } } } }).response?.data?.error?.code
  return code && code in guidance ? code : 'EVIDENCE_READ_FAILED'
}
function report(e: unknown) {
  const code = errorCode(e)
  error.value = `${guidance[code] ?? c('读取暂时失败，请重试；没有补造结果。', 'Read temporarily failed; retry. No result was invented.')} ${code}`
  if (globalCodes.includes(code) || (e as { response?: { status?: number } }).response?.status === 403) {
    unlocked.value = false; detail.value = null; records.value = []; sources.value = []
  }
}
async function loadDetail() {
  const current = ++generation; detail.value = null; exportDigest.value = ''; error.value = ''
  const id = route.params.identity
  if (!id || !unlocked.value) return
  try { const data = await externalEvidenceApi.detail(String(id), token.value); if (alive && current === generation) detail.value = data }
  catch (e) { if (alive && current === generation) report(e) }
}
async function unlock() {
  busy.value = true; error.value = ''; listError.value = ''; const current = ++generation
  try {
    const checked = await externalEvidenceApi.check(token.value)
    if (!alive || current !== generation) return
    checkStatus.value = checked.status
    configurationNotice.value = checked.issues.includes('SOURCE_LOCATION_UNAVAILABLE') ? guidance.SOURCE_LOCATION_UNAVAILABLE : ''
    if (checked.status === 'NOT_CONFIGURED' || (checked.status === 'NEEDS_ATTENTION' && checked.issues.some(code => code !== 'SOURCE_LOCATION_UNAVAILABLE'))) {
      report({ response: { data: { error: { code: checked.issues[0] } } } }); return
    }
    const [a, b] = await Promise.allSettled([externalEvidenceApi.sources(token.value), externalEvidenceApi.records(token.value)])
    if (!alive || current !== generation) return
    if (a.status === 'rejected') throw a.reason
    if (b.status === 'rejected' && (globalCodes.includes(errorCode(b.reason)) || b.reason?.response?.status === 403)) throw b.reason
    sources.value = a.value.items
    records.value = b.status === 'fulfilled' ? b.value.items : []
    if (b.status === 'rejected') listError.value = c('列表暂不可读；并非空列表。可尝试直接打开已知健康记录，或重新解锁重试。', 'List unavailable, not empty. Try a known healthy record URL or unlock again to retry.')
    unlocked.value = true; await loadDetail()
  } catch (e) { if (alive && current === generation) report(e) }
  finally { if (alive) busy.value = false }
}
async function ingest() {
  if (!consent.value || !selected.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    const data = await externalEvidenceApi.ingest(selected.value, token.value)
    if (!alive) return
    try { records.value = (await externalEvidenceApi.records(token.value)).items; listError.value = '' }
    catch (e) { if (globalCodes.includes(errorCode(e)) || (e as { response?: { status?: number } }).response?.status === 403) throw e; listError.value = c('记录已接入，列表暂不可读；不是空列表。', 'Record imported; list is unavailable, not empty.') }
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
  } catch (e) { if (alive) { if (errorCode(e) === 'EVIDENCE_INTEGRITY_ERROR') detail.value = null; report(e) } } finally { if (alive) busy.value = false }
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
    <details class="panel" data-test="quickstart">
      <summary>{{ c('首次私有接入 Quickstart（不执行 Agent / Verifier）', 'First private intake Quickstart (no Agent / Verifier execution)') }}</summary>
      <ol>
        <li>{{ c('在独立 checkout 安装锁定依赖并构建 UI；只使用新隔离数据库和未占用 loopback 端口。', 'Install locked dependencies/build the UI in a separate checkout; use a new isolated database and unused loopback port.') }}</li>
        <li>{{ c('人工审查单条已保存记录和最终 UTF-8 Workspace，移除敏感材料，再独立保存 source / Workspace 摘要。不会扫描私人会话。', 'Review one supplied saved record and final UTF-8 Workspace, remove sensitive material and retain source/Workspace pins independently. No private-session discovery.') }}</li>
        <li>{{ c('在仓库外创建 0600 策略与独立 0700 存储目录；策略逐项列出批准来源。', 'Create an owned 0600 policy and separate 0700 store outside the checkout; explicitly list each approved source.') }} <code>HARNESSLAB_EXTERNAL_EVIDENCE_POLICY</code></li>
        <li>{{ c('设置独立本地操作员凭据（至少 32 字符），运行只读检查；它不证明 pin 或任务通过。', 'Set a separate local operator credential (at least 32 characters) and run the read-only check; it does not validate pins or task acceptance.') }} <code>uv run --locked harnesslab external-evidence check</code></li>
        <li>{{ c('按仓库 docs/EXTERNAL_EVIDENCE_QUICKSTART.md 的完整命令启动 host API；解锁、选来源并明确同意接入。', 'Start the host API with the complete commands in docs/EXTERNAL_EVIDENCE_QUICKSTART.md; unlock, select a source and explicitly approve intake.') }}</li>
        <li>{{ c('下载脱敏导出，单独保存显示的摘要，在终端执行两次离线复核；不会重跑 Agent 或历史 Verifier。', 'Download the sanitized export, retain the displayed pin separately and replay twice in a terminal; no Agent or historical Verifier rerun.') }}</li>
      </ol>
      <p>{{ c('标准 Compose 目前不自动传递操作员/证据策略或挂载来源；本路径使用私有 host API，不宣称开箱即用。', 'Standard Compose does not forward operator/evidence policy settings or mount sources. This path uses a private host API; it is not automatic distribution setup.') }}</p>
      <p>{{ c('支持的 exec JSONL / Hook / H-Lane 输入、摘要命令与完整步骤见随版本附带的 Quickstart。没有新增获批真实记录：FRESH_CASE_PENDING。', 'Use supported exec JSONL / Hook / H-Lane inputs; see the bundled Quickstart for pin commands and full steps. No fresh approved real record: FRESH_CASE_PENDING.') }}</p>
    </details>
    <form v-if="!unlocked" class="panel builder-form" @submit.prevent="unlock">
      <label>{{ c('本地操作员凭据', 'Local operator credential') }}<input v-model="token" data-test="operator" type="password" autocomplete="off" required /></label>
      <p>{{ c('凭据仅留在当前页面内存。公开 Demo 无权读取或导入。', 'Credential stays in page memory. Public Demo cannot read or import these records.') }}</p>
      <button class="primary-button" :disabled="busy || !token">{{ c('解锁并读取', 'Unlock and load') }}</button>
    </form>
    <template v-else>
      <p data-test="configuration-check">{{ c('只读配置检查', 'Read-only configuration check') }}：{{ checkStatus }} · {{ c('未读取来源内容、未验证摘要或执行任务。', 'Source contents/pins/task acceptance were not checked; no execution.') }}</p>
      <p v-if="configurationNotice" role="status">{{ configurationNotice }} {{ c('已保存的健康记录仍可读取。', 'Healthy saved records remain readable.') }}</p>
      <form class="panel builder-form" @submit.prevent="ingest">
        <h3>{{ c('接入已批准来源', 'Import an approved source') }}</h3>
        <label>{{ c('来源', 'Source') }}<select v-model="selected" data-test="source"><option value="">{{ c('选择来源', 'Choose a source') }}</option><option v-for="source in sources" :key="source.source_id" :value="source.source_id">{{ source.source_id }} · {{ source.source_kind }} · {{ source.format }}</option></select></label>
        <p v-if="!sources.length">{{ c('暂无批准来源。请由操作员逐项审查、脱敏并固定摘要；不会扫描私人会话。', 'No approved sources. The operator must review, sanitize and pin individual items; private sessions are never scanned.') }}</p>
        <label><input v-model="consent" data-test="consent" type="checkbox" />{{ c('我批准接入所选保存证据和工程快照；这不授权运行 Agent。', 'I approve intake of this saved evidence and workspace; this does not authorize Agent execution.') }}</label>
        <button class="primary-button" data-test="import" :disabled="busy || !selected || !consent">{{ c('导入并检查完整性', 'Import and check integrity') }}</button>
      </form>
      <div class="panel"><h3>{{ c('已接入记录', 'Saved records') }}</h3>
        <p v-if="listError" role="status" data-test="list-error">{{ listError }}</p>
        <p v-else-if="!records.length">{{ c('暂无记录', 'No records') }}</p>
        <ul><li v-for="record in records" :key="record.identity" :data-test="record.status === 'CORRUPT' ? 'corrupt-record' : 'healthy-record'">
          <template v-if="record.status === 'AVAILABLE'"><RouterLink :to="`/external-runs/${record.identity}`">{{ record.source_id }}</RouterLink> · {{ record.source_kind }} · {{ record.acceptance }}</template>
          <template v-else><RouterLink :to="`/external-runs/${record.identity}`">{{ c('损坏记录', 'Corrupt record') }} {{ record.identity }}</RouterLink> · {{ record.error_code }}<p>{{ guidance.EVIDENCE_RECORD_CORRUPT }}</p></template>
        </li></ul>
      </div>
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
.external-evidence-page li { overflow-wrap: anywhere; }
</style>
