<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { acceptancePlansApi as api, type ChangePlan, type Clause, type PlanDetail, type PlanSummary, type SnapshotOption } from '@/api/acceptancePlans'

const route = useRoute(); const router = useRouter()
const token = ref(''); const enabled = ref(false); const ready = ref(false); const unlocked = ref(false)
const busy = ref(false); const error = ref(''); const snapshots = ref<SnapshotOption[]>([]); const plans = ref<PlanSummary[]>([])
const snapshotId = ref(typeof route.query.snapshot === 'string' ? route.query.snapshot : '')
const prompt = ref(''); const detail = ref<PlanDetail | null>(null); const selectedEvent = ref('')
const edits = ref<Record<string, { text: string; decision: Clause['decision']; reason: string }>>({})
const manual = ref(''); const manualReason = ref(''); const reason = ref(''); const acknowledged = ref(false)
let generation = 0; let alive = true; let pending: { signature: string; id: string } | null = null
const sourceLabels = { EXPLICIT_IN_PROMPT: '原文明确要求', USER_APPROVED_ADDITION: '曾获用户批准的新增范围', SUGGESTED_ONLY: '仅建议', AMBIGUOUS: '待澄清' }
function clauseSourceLabel(clause: Clause) {
  if (clause.source !== 'USER_APPROVED_ADDITION') return sourceLabels[clause.source]
  return clause.decision === 'APPROVED' ? '本版本已批准的新增范围' : '历史批准的新增范围（本版本未批准）'
}
const statusLabels: Record<string, string> = { DRAFT: '草稿 · 待审查', CONFIRMED: '验收方案已确认', FROZEN: '验收方案已确认 · 已冻结' }
const decisionLabels = { PENDING: '未批准 · 待澄清 / 暂不纳入', APPROVED: '确认纳入范围', REJECTED: '拒绝 / 不纳入' }
const event = computed(() => detail.value?.history.find(e => e.digest === selectedEvent.value) ?? detail.value?.current)
const state = computed(() => event.value?.state)
const isCurrent = computed(() => event.value?.digest === detail.value?.current.digest)
const editable = computed(() => isCurrent.value && state.value?.status === 'DRAFT' && detail.value?.snapshot_binding === 'INTACT')
const dirty = computed(() => state.value?.clauses.some(c => edits.value[c.id]?.text !== c.text || edits.value[c.id]?.decision !== c.decision) || !!manual.value)
const approved = computed(() => state.value?.clauses.filter(c => c.decision === 'APPROVED').length ?? 0)
const selectedSnapshot = computed(() => snapshots.value.find(s => s.identity === snapshotId.value))
function failure(e: unknown) {
  const code = (e as { response?: { data?: { error?: { code?: string } } } }).response?.data?.error?.code ?? 'NETWORK_ERROR'
  const messages: Record<string, string> = {
    ACCEPTANCE_STALE: '方案已被另一请求更新。请刷新，核对最新版本后重新审查。',
    LOCAL_OPERATOR_REQUIRED: '操作员凭据不正确，请重新解锁。',
    ACCEPTANCE_SNAPSHOT_UNAVAILABLE: '快照不存在或完整性检查失败，不能绑定或修改方案。',
    ACCEPTANCE_SNAPSHOT_MISMATCH: '快照内容身份失配，不能绑定。',
    ACCEPTANCE_INTEGRITY_ERROR: '方案存储不可用或完整性检查失败。',
    ACCEPTANCE_EMPTY_SCOPE: '请先明确批准至少一项条款。',
  }
  if (code.startsWith('ACCEPTANCE_SNAPSHOT_') && selectedSnapshot.value) selectedSnapshot.value.status = 'UNAVAILABLE_OR_CHANGED'
  error.value = `${messages[code] ?? '操作未完成，请检查权限和输入；网络中断时请刷新核对保存状态。'} (${code})`
}
function resetEditors() {
  edits.value = Object.fromEntries((state.value?.clauses ?? []).map(c => [c.id, { text: c.text, decision: c.decision, reason: '' }]))
  reason.value = ''; acknowledged.value = false; manual.value = ''; manualReason.value = ''
}
watch(event, resetEditors)
watch(token, () => { generation++; unlocked.value = false; busy.value = false; detail.value = null; plans.value = []; snapshots.value = []; prompt.value = ''; error.value = ''; pending = null })
function requestId(payload: unknown) {
  const signature = JSON.stringify(payload)
  if (pending?.signature !== signature) pending = { signature, id: crypto.randomUUID() }
  return pending!.id
}
async function run(work: (current: number) => Promise<void>) {
  if (busy.value) return
  const current = ++generation; busy.value = true; error.value = ''
  try { await work(current) } catch (e) { if (alive && generation === current) failure(e) }
  finally { if (alive && generation === current) busy.value = false }
}
async function readCurrent(current: number, id = String(route.params.acceptanceId ?? '')) {
  detail.value = null
  if (!id) {
    const [list, choices] = await Promise.all([api.list(token.value), api.snapshots(token.value)])
    if (alive && generation === current) { plans.value = list.items; snapshots.value = choices.items }
    return
  }
  const result = await api.detail(id, token.value)
  if (alive && generation === current) { detail.value = result; selectedEvent.value = result.current.digest }
}
async function unlock() {
  await run(async current => {
    const [list, choices] = await Promise.all([api.list(token.value), api.snapshots(token.value)])
    if (!alive || generation !== current) return
    plans.value = list.items; snapshots.value = choices.items; unlocked.value = true
    await readCurrent(current)
  })
}
async function refresh() { await run(readCurrent) }
async function create() {
  const snapshot = selectedSnapshot.value
  if (snapshot?.status !== 'INTACT' || !snapshot.content_digest || !prompt.value.trim()) return
  const payload = { snapshot_identity: snapshot.identity, snapshot_content_digest: snapshot.content_digest, original_prompt: prompt.value }
  await run(async current => {
    const result = await api.create({ ...payload, request_id: requestId(payload) }, token.value)
    if (!alive || generation !== current) return
    pending = null; prompt.value = ''; await router.push(`/acceptance-plans/${result.state.plan_id}`)
  })
}
async function change(payload: Omit<ChangePlan, 'request_id' | 'expected_digest'>) {
  if (!detail.value || !isCurrent.value) return
  const id = detail.value.current.state.plan_id
  const request = { ...payload, expected_digest: detail.value.current.digest }
  const unsaved = Object.fromEntries(Object.entries(edits.value).filter(([id, edit]) => {
    const original = state.value?.clauses.find(c => c.id === id)
    return id !== payload.clause_id && original && (edit.text !== original.text || edit.decision !== original.decision || edit.reason)
  }))
  const manualDraft = { text: manual.value, reason: manualReason.value }
  await run(async current => {
    await api.change(id, { ...request, request_id: requestId(request) }, token.value)
    if (!alive || generation !== current) return
    pending = null; await readCurrent(current, id)
    await nextTick()
    if (alive && generation === current && (payload.action === 'REVIEW' || payload.action === 'ADD')) {
      Object.assign(edits.value, unsaved)
      if (payload.action !== 'ADD') { manual.value = manualDraft.text; manualReason.value = manualDraft.reason }
    }
  })
}
async function review(c: Clause) {
  const edit = edits.value[c.id]
  if (!edit) return
  await change({ action: 'REVIEW', clause_id: c.id, text: edit.text, decision: edit.decision, reason: edit.reason })
}
async function transition(action: 'CONFIRM' | 'FREEZE' | 'REVISE') {
  if (!acknowledged.value) return
  await change({ action, reason: reason.value, acknowledgement: 'SCOPE_ONLY_NO_EXECUTION' })
}
watch(() => route.params.acceptanceId, () => { generation++; busy.value = false; detail.value = null; if (unlocked.value) void refresh() })
onMounted(async () => { try { const s = await api.status(); if (alive) enabled.value = s.enabled } catch (e) { if (alive) failure(e) } finally { if (alive) ready.value = true } })
onBeforeUnmount(() => { alive = false; generation++; token.value = ''; prompt.value = ''; detail.value = null; edits.value = {}; pending = null })
</script>

<template>
  <section class="acceptance-page" :aria-busy="busy">
    <div class="page-heading"><div><h2>验收范围方案</h2><p>原始 Prompt → 来源审查 → 用户确认 → 版本冻结</p></div><RouterLink to="/acceptance-plans" class="secondary-button">新建 / 已保存方案</RouterLink></div>
    <div class="panel scope-boundary"><strong>交付后审计 · 仅管理验收范围</strong><p>已有代码快照之后制定的方案不宣称预注册或盲测。批准条款不等于 Verifier 合格；冻结不授权执行，也不代表验收通过。</p><RouterLink to="/plans">可信任务执行计划（原 /plans）→</RouterLink></div>
    <p v-if="error" role="alert" class="panel error-state">{{ error }}</p>
    <p v-if="!ready" role="status">正在读取工作区状态…</p>
    <div v-else-if="!enabled" class="panel"><h3>私有验收方案未启用</h3><p>需配置独立方案存储、已有快照策略和本地操作员权限。公开 Demo 不支持此流程。</p></div>
    <form v-else-if="!unlocked" class="panel builder-form" @submit.prevent="unlock"><h3>解锁私有工作区</h3><label>本地操作员凭据<input v-model="token" type="password" autocomplete="off" data-test="operator" /></label><p>凭据和输入只在当前页面内存中使用；刷新后重新解锁。Prompt 仅保存于私有服务端，不进入 URL 或浏览器存储。</p><button class="primary-button" :disabled="busy || !token">解锁并读取</button></form>
    <template v-else>
      <template v-if="!route.params.acceptanceId">
        <form class="panel builder-form" @submit.prevent="create">
          <h3>从已有快照创建草稿</h3>
          <label>已保存 CodeSnapshot<select v-model="snapshotId" data-test="snapshot"><option value="">请选择已保存快照</option><option v-for="s in snapshots" :key="s.identity" :value="s.identity" :disabled="s.status !== 'INTACT'">{{ s.identity.slice(0, 16) }}… · {{ s.file_count ?? '?' }} 文件 · {{ s.status }}</option></select></label>
          <button type="button" class="secondary-button" :disabled="busy" @click="refresh">刷新快照列表</button>
          <p v-if="!snapshots.length">暂无已保存快照。可从“导入运行记录”保存源码快照后返回。</p>
          <p v-if="snapshotId" class="technical">快照身份：{{ snapshotId }}</p>
          <label>原始 Prompt<textarea v-model="prompt" data-test="prompt" rows="4" maxlength="16000" autocomplete="off" placeholder="给我做一个轻量电商系统，命名为 MiniShop" /></label>
          <p>使用有限确定性规则和模板。无法可靠提取时请人工编写；不要粘贴凭据。</p>
          <button class="primary-button" data-test="create" :disabled="busy || !prompt.trim() || selectedSnapshot?.status !== 'INTACT'">生成并保存草稿</button>
        </form>
        <div class="panel"><h3>已保存方案</h3><p v-if="!plans.length">暂无方案。</p><ul><li v-for="p in plans" :key="p.plan_id"><RouterLink :to="`/acceptance-plans/${p.plan_id}`">{{ p.plan_id.slice(0, 16) }}… · v{{ p.version }} · {{ statusLabels[p.status] }}</RouterLink></li></ul></div>
      </template>
      <template v-else-if="state && detail">
        <div class="panel">
          <div class="panel-title"><h3>{{ statusLabels[state.status] }} · v{{ state.version }}</h3><button class="secondary-button" :disabled="busy" @click="refresh">刷新已保存状态</button></div>
          <div class="scope-status"><div><strong>范围确认</strong><p>{{ statusLabels[state.status] }}</p><small>本版本已批准 {{ approved }} 项；其余不作为失败标准</small></div><div><strong>Verifier 资格与绑定</strong><p>无合格且正确绑定的 Verifier</p><small>尚不能进行权威验收</small></div><div><strong>实际验收结果</strong><p>未执行 · NOT_RUN</p><small>没有业务 PASS/FAIL 或独立收据</small></div></div>
          <p v-if="detail.snapshot_binding !== 'INTACT'" role="alert" class="scope-warning">快照不可用或已变化：历史范围可读，修改与冻结被阻止。</p>
          <p>绑定快照：<RouterLink :to="`/code-snapshots/${state.snapshot.identity}`" class="technical">{{ state.snapshot.identity }}</RouterLink></p>
          <details open><summary>不可覆盖的原始 Prompt</summary><pre data-test="original-prompt">{{ state.original_prompt }}</pre></details>
          <label>历史版本与审计事件<select v-model="selectedEvent" data-test="history" :disabled="busy"><option v-for="e in detail.history" :key="e.digest" :value="e.digest">#{{ e.sequence }} · v{{ e.state.version }} · {{ e.action }} · {{ e.at }}</option></select></label>
          <p v-if="!isCurrent" class="scope-warning">正在读取历史事件；不可修改。选择最新事件以继续。</p>
          <p class="technical">事件摘要：{{ event?.digest }}</p><p>记录人：{{ event?.actor }}（共享操作员身份） · {{ event?.at }}</p><p>修改 / 确认依据：{{ event?.reason }}</p>
          <p v-if="state.confirmed_at">确认时间：{{ state.confirmed_at }}</p><p v-if="state.frozen_at">冻结时间：{{ state.frozen_at }}</p>
        </div>
        <div class="panel"><h3>逐项来源与歧义审查</h3><p>只有本版本明确批准的条款纳入范围。历史批准来源不代表本版本已批准；修订后须重新逐项审查。修改原文提取条款后再批准，将标为用户新增范围；来源原文始终保留。读取历史事件时，“本版本”指所选事件所属版本。</p>
          <article v-for="c in state.clauses" :key="c.id" class="scope-clause" :data-clause="c.id">
            <div class="panel-title"><strong>{{ c.id }} · {{ clauseSourceLabel(c) }}</strong><span>本版本决定：{{ decisionLabels[c.decision] }}</span></div>
            <p class="technical">来源记录：{{ c.source }} · {{ c.origin.kind }}</p>
            <p>初始来源：{{ sourceLabels[c.origin.source] }}</p>
            <blockquote v-if="c.origin.quote">原文依据：{{ c.origin.quote }}</blockquote>
            <p>初始候选：{{ c.origin.text }}</p>
            <template v-if="editable && edits[c.id]">
              <label :for="`text-${c.id}`">候选验收条件</label><textarea :id="`text-${c.id}`" v-model="edits[c.id]!.text" rows="2" maxlength="2000" :disabled="busy" />
              <div class="scope-edit"><label>审查决定<select v-model="edits[c.id]!.decision" :disabled="busy"><option v-for="(label, key) in decisionLabels" :key="key" :value="key">{{ label }}</option></select></label><label>修改或决定依据<input v-model="edits[c.id]!.reason" maxlength="2000" :disabled="busy" /></label><button class="secondary-button" :disabled="busy || !edits[c.id]!.reason.trim() || !edits[c.id]!.text.trim()" @click="review(c)">保存本项审查</button></div>
            </template>
            <p v-else>{{ c.text }}</p>
            <p v-if="c.reviewed_at">本版本审查：{{ c.reviewed_at }} · {{ c.review_reason }}</p>
          </article>
          <form v-if="editable" class="builder-form manual-clause" @submit.prevent="change({ action: 'ADD', text: manual, reason: manualReason })"><h4>人工补充候选（默认仅建议）</h4><label>候选内容<textarea v-model="manual" maxlength="2000" rows="2" :disabled="busy" data-test="manual" /></label><label>补充依据<input v-model="manualReason" maxlength="2000" :disabled="busy" data-test="manual-reason" /></label><button class="secondary-button" :disabled="busy || !manual.trim() || !manualReason.trim()">添加待审查项</button></form>
        </div>
        <div class="panel"><h3>尚未覆盖的范围</h3><ul><li v-for="item in state.uncovered" :key="item">{{ item }}</li></ul><p>待澄清或拒绝的条款不作为失败标准。范围批准不会自动登记为 admitted TaskStore 任务。</p></div>
        <form v-if="isCurrent && detail.snapshot_binding === 'INTACT'" class="panel builder-form" @submit.prevent="transition(state.status === 'DRAFT' ? 'CONFIRM' : state.status === 'CONFIRMED' ? 'FREEZE' : 'REVISE')">
          <h3>{{ state.status === 'DRAFT' ? '明确确认范围' : state.status === 'CONFIRMED' ? '冻结不可变版本' : '开始后续修订' }}</h3>
          <p v-if="dirty">有未保存的编辑，请先逐项保存。</p><p v-if="state.status === 'FROZEN'">修订会创建新版本，保留旧版本与原 Prompt，并重新审查所有条款。</p>
          <label>本次操作依据<input v-model="reason" maxlength="2000" data-test="transition-reason" :disabled="busy" /></label>
          <label class="scope-consent"><input v-model="acknowledged" type="checkbox" data-test="acknowledge" :disabled="busy" />我确认仅管理已批准的验收范围；其余条款不作为失败标准。此操作不赋予 Verifier 资格、不授权执行、不代表验收通过。</label>
          <button class="primary-button" data-test="transition" :disabled="busy || dirty || !acknowledged || !reason.trim() || (state.status === 'DRAFT' && !approved)">{{ state.status === 'DRAFT' ? '确认验收范围' : state.status === 'CONFIRMED' ? '冻结此版本' : '创建修订版本' }}</button>
        </form>
      </template>
      <p v-else-if="busy" role="status">正在读取方案…</p>
      <button v-else class="secondary-button" @click="refresh">重新读取方案</button>
    </template>
  </section>
</template>

<style scoped>
.acceptance-page { max-width: 1200px; margin: auto; overflow-wrap: anywhere; }
.acceptance-page .panel { margin-bottom: 20px; }
.scope-boundary { border-left: 3px solid var(--accent); }
.scope-status { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; padding: 20px; background: #f5f8fa; border-radius: 10px; margin-bottom: 20px; }
.scope-status small { color: var(--muted); }
.scope-clause { border-top: 1px solid var(--line); padding: 24px 0; }
.scope-clause blockquote { border-left: 3px solid #cad6e2; margin: 12px 0; padding-left: 16px; white-space: pre-wrap; }
.scope-edit { display: grid; grid-template-columns: 220px 1fr auto; align-items: end; gap: 12px; margin-top: 12px; }
.acceptance-page label { display: flex; flex-direction: column; gap: 8px; }
.acceptance-page input:not([type="checkbox"]), .acceptance-page select, .acceptance-page textarea { width: 100%; min-height: 40px; border: 1px solid var(--line); border-radius: 6px; background: white; color: var(--ink); padding: 9px 12px; font: inherit; }
.acceptance-page textarea { resize: vertical; line-height: 1.6; }
.acceptance-page input:focus, .acceptance-page textarea:focus, .acceptance-page select:focus { outline: 2px solid var(--accent); outline-offset: 2px; }
.scope-consent { flex-direction: row !important; align-items: flex-start; }
.scope-consent input { width: auto; min-height: 0; margin-top: 5px; }
.scope-warning { color: #8a5216; background: #fff7e8; padding: 12px; }
pre { white-space: pre-wrap; font-family: inherit; }
.manual-clause { padding-top: 20px; border-top: 1px solid var(--line); }
@media (max-width: 900px) { .scope-status, .scope-edit { grid-template-columns: 1fr; } }
</style>
