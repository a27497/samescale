import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AcceptancePlansView from '@/views/AcceptancePlansView.vue'
import { acceptancePlansApi as api, type PlanDetail, type PlanEvent } from '@/api/acceptancePlans'

vi.mock('@/api/acceptancePlans', () => ({ acceptancePlansApi: { status: vi.fn(), snapshots: vi.fn(), list: vi.fn(), detail: vi.fn(), create: vi.fn(), change: vi.fn() } }))
const snapshot = { identity: 'a'.repeat(64), status: 'INTACT', content_digest: `sha256:${'b'.repeat(64)}`, file_count: 1 }
function event(status: 'DRAFT' | 'CONFIRMED' | 'FROZEN' = 'DRAFT', version = 1): PlanEvent {
  return { digest: `sha256:${status}-${version}`, sequence: version, action: 'CREATE', at: '2026-10-18T01:00:00Z', reason: 'fixture', actor: 'LOCAL_OPERATOR', state: {
    plan_id: 'c'.repeat(64), version, status, original_prompt: '给我做一个轻量电商系统，命名为 MiniShop',
    snapshot: { identity: snapshot.identity, content_digest: snapshot.content_digest },
    clauses: [
      { id: 'c1', text: '系统命名为 MiniShop', source: 'EXPLICIT_IN_PROMPT', decision: 'PENDING', origin: { kind: 'rule:minishop-sentence-v1', source: 'EXPLICIT_IN_PROMPT', text: '系统命名为 MiniShop', quote: '命名为 MiniShop' }, reviewed_at: null, review_reason: null },
      { id: 'c2', text: '约定购物车行为', source: 'SUGGESTED_ONLY', decision: 'PENDING', origin: { kind: 'template:commerce-v1', source: 'SUGGESTED_ONLY', text: '约定购物车行为', quote: null }, reviewed_at: null, review_reason: null },
    ], uncovered: ['尚未覆盖其他行为'], confirmed_at: null, frozen_at: null, parent_frozen_digest: null,
    verifier_status: 'NO_QUALIFIED_BOUND_VERIFIER', acceptance_result: 'NOT_RUN', execution_authorized: false, taskstore_admitted: false, audit_context: 'POST_DELIVERY_AUDIT',
  } }
}
const response = (e: PlanEvent): PlanDetail => ({ current: e, history: [e], snapshot_binding: 'INTACT' })
async function setup(path = '/acceptance-plans') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/acceptance-plans', component: AcceptancePlansView },
    { path: '/acceptance-plans/:acceptanceId', component: AcceptancePlansView },
    { path: '/plans', component: { template: '<div />' } },
    { path: '/code-snapshots/:snapshotIdentity', component: { template: '<div />' } },
  ] })
  await router.push(path); await router.isReady()
  const wrapper = mount(AcceptancePlansView, { global: { plugins: [router] } })
  await flushPromises(); return { wrapper, router }
}
async function unlock(wrapper: Awaited<ReturnType<typeof setup>>['wrapper']) {
  await wrapper.get('[data-test=operator]').setValue('synthetic-operator')
  await wrapper.get('form').trigger('submit'); await flushPromises()
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.status).mockResolvedValue({ enabled: true, execution_enabled: false })
  vi.mocked(api.list).mockResolvedValue({ items: [] })
  vi.mocked(api.snapshots).mockResolvedValue({ items: [structuredClone(snapshot)] })
  vi.mocked(api.detail).mockResolvedValue(response(event()))
  vi.mocked(api.create).mockResolvedValue(event())
  vi.mocked(api.change).mockResolvedValue(event())
})
describe('private acceptance scope', () => {
  it('creates from an existing selected snapshot without persisting Prompt in URL or browser storage', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem')
    const { wrapper, router } = await setup(`/acceptance-plans?snapshot=${snapshot.identity}`); await unlock(wrapper)
    await wrapper.get('[data-test=prompt]').setValue(event().state.original_prompt)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create).toHaveBeenCalledWith(expect.objectContaining({ snapshot_identity: snapshot.identity, snapshot_content_digest: snapshot.content_digest, original_prompt: event().state.original_prompt }), 'synthetic-operator')
    expect(router.currentRoute.value.fullPath).toBe(`/acceptance-plans/${event().state.plan_id}`)
    expect(wrapper.text()).toContain('尚不能进行权威验收'); expect(wrapper.text()).toContain('未执行 · NOT_RUN')
    expect(storage).not.toHaveBeenCalled(); storage.mockRestore(); wrapper.unmount()
  })
  it('requires explicit per-clause review, leaving suggestions out and recording edited approval reasons', async () => {
    const { wrapper } = await setup(`/acceptance-plans/${event().state.plan_id}`); await unlock(wrapper)
    expect(wrapper.get('[data-test=transition]').attributes('disabled')).toBeDefined()
    const row = wrapper.get('[data-clause=c2]')
    await row.get('textarea').setValue('购物车显示选定商品数量')
    await row.get('select').setValue('APPROVED')
    await row.get('input').setValue('我决定增加购物车范围')
    await row.get('button').trigger('click'); await flushPromises()
    expect(api.change).toHaveBeenCalledWith(event().state.plan_id, expect.objectContaining({ action: 'REVIEW', clause_id: 'c2', text: '购物车显示选定商品数量', decision: 'APPROVED', reason: '我决定增加购物车范围', expected_digest: event().digest }), 'synthetic-operator')
    expect(api.change).toHaveBeenCalledTimes(1); wrapper.unmount()
  })
  it('preserves other unsaved edits while saving one row', async () => {
    const { wrapper } = await setup(`/acceptance-plans/${event().state.plan_id}`); await unlock(wrapper)
    await wrapper.get('[data-clause=c2] textarea').setValue('unsaved second row')
    await wrapper.get('[data-clause=c1] input').setValue('reason')
    await wrapper.get('[data-clause=c1] button').trigger('click'); await flushPromises()
    expect((wrapper.get('[data-clause=c2] textarea').element as HTMLTextAreaElement).value).toBe('unsaved second row')
    expect(wrapper.get('[data-test=transition]').attributes('disabled')).toBeDefined(); wrapper.unmount()
  })
  it.each(['PENDING', 'REJECTED'] as const)('saves %s without treating it as approved', async decision => {
    const { wrapper } = await setup(`/acceptance-plans/${event().state.plan_id}`); await unlock(wrapper)
    const row = wrapper.get('[data-clause=c2]'); await row.get('select').setValue(decision); await row.get('input').setValue('defer or reject')
    await row.get('button').trigger('click'); await flushPromises()
    expect(api.change).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ decision }), expect.any(String))
    expect(wrapper.get('[data-test=transition]').attributes('disabled')).toBeDefined(); wrapper.unmount()
  })
  it('renders ambiguous manual fallback and adds only a candidate', async () => {
    const e = event(); e.state.clauses[0]!.source = 'AMBIGUOUS'; e.state.clauses[0]!.origin.kind = 'manual-fallback-v1'
    vi.mocked(api.detail).mockResolvedValue(response(e))
    const { wrapper } = await setup(`/acceptance-plans/${e.state.plan_id}`); await unlock(wrapper)
    expect(wrapper.text()).toContain('待澄清')
    await wrapper.get('[data-test=manual]').setValue('人工候选'); await wrapper.get('[data-test=manual-reason]').setValue('人工补充')
    await wrapper.get('.manual-clause').trigger('submit'); await flushPromises()
    expect(api.change).toHaveBeenCalledWith(e.state.plan_id, expect.objectContaining({ action: 'ADD', text: '人工候选', reason: '人工补充' }), expect.any(String)); wrapper.unmount()
  })
  it('requires explicit acknowledgement for confirmation and freeze, then revises without editing frozen content', async () => {
    const e = event(); e.state.clauses[0]!.decision = 'APPROVED'
    vi.mocked(api.detail).mockResolvedValue(response(e))
    const { wrapper } = await setup(`/acceptance-plans/${e.state.plan_id}`); await unlock(wrapper)
    await wrapper.get('[data-test=transition-reason]').setValue('approved scope')
    expect(wrapper.get('[data-test=transition]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test=acknowledge]').setValue(true)
    vi.mocked(api.detail).mockResolvedValue(response(event('CONFIRMED')))
    await wrapper.get('[data-test=transition]').trigger('submit'); await flushPromises()
    expect(api.change).toHaveBeenLastCalledWith(e.state.plan_id, expect.objectContaining({ action: 'CONFIRM', acknowledgement: 'SCOPE_ONLY_NO_EXECUTION' }), expect.any(String))
    expect(wrapper.find('[data-clause=c1] textarea').exists()).toBe(false)
    for (const [next, action] of [['FROZEN', 'FREEZE'], ['DRAFT', 'REVISE']] as const) {
      await wrapper.get('[data-test=transition-reason]').setValue('next step'); await wrapper.get('[data-test=acknowledge]').setValue(true)
      vi.mocked(api.detail).mockResolvedValue(response(event(next, next === 'DRAFT' ? 2 : 1)))
      await wrapper.get('[data-test=transition]').trigger('submit'); await flushPromises()
      expect(api.change).toHaveBeenLastCalledWith(e.state.plan_id, expect.objectContaining({ action }), expect.any(String))
    }
    expect(wrapper.text()).toContain('v2'); wrapper.unmount()
  })
  it('distinguishes inherited approval from current version review across revision, reload and history', async () => {
    const frozen = event('FROZEN')
    Object.assign(frozen.state.clauses[1]!, { source: 'USER_APPROVED_ADDITION', decision: 'APPROVED', reviewed_at: '2026-10-18T02:00:00Z', review_reason: 'v1 approval' })
    const revised = structuredClone(frozen); revised.digest = 'revised-v2'; revised.action = 'REVISE'
    Object.assign(revised.state, { version: 2, status: 'DRAFT', parent_frozen_digest: frozen.digest })
    revised.state.clauses.forEach(c => { c.decision = 'PENDING'; c.reviewed_at = null; c.review_reason = null })
    vi.mocked(api.detail).mockResolvedValue(response(frozen))
    let view = await setup(`/acceptance-plans/${frozen.state.plan_id}`); await unlock(view.wrapper)
    vi.mocked(api.detail).mockResolvedValue({ current: revised, history: [frozen, revised], snapshot_binding: 'INTACT' })
    await view.wrapper.get('[data-test=transition-reason]').setValue('new review')
    await view.wrapper.get('[data-test=acknowledge]').setValue(true)
    await view.wrapper.get('[data-test=transition]').trigger('submit'); await flushPromises()
    expect(api.change).toHaveBeenLastCalledWith(frozen.state.plan_id, expect.objectContaining({ action: 'REVISE' }), expect.any(String))
    const row = () => view.wrapper.get('[data-clause=c2]')
    expect(row().text()).toContain('历史批准的新增范围（本版本未批准）')
    expect(row().text()).toContain('本版本决定：未批准 · 待澄清 / 暂不纳入')
    expect(row().text()).toContain('初始来源：仅建议')
    expect(row().text()).not.toContain('本版本已批准的新增范围')
    expect(row().text()).not.toContain('2026-10-18T02:00:00Z')
    expect(view.wrapper.text()).toContain('本版本已批准 0 项')
    expect(view.wrapper.get('[data-test=transition]').attributes('disabled')).toBeDefined()
    view.wrapper.unmount()
    view = await setup(`/acceptance-plans/${frozen.state.plan_id}`); await unlock(view.wrapper)
    expect(row().text()).toContain('历史批准的新增范围（本版本未批准）')
    const renewed = structuredClone(revised); renewed.digest = 'renewed-v2'; renewed.action = 'REVIEW'
    Object.assign(renewed.state.clauses[1]!, { decision: 'APPROVED', reviewed_at: '2026-10-19T02:00:00Z', review_reason: 'v2 approval' })
    vi.mocked(api.detail).mockResolvedValue({ current: renewed, history: [frozen, revised, renewed], snapshot_binding: 'INTACT' })
    await row().get('select').setValue('APPROVED'); await row().get('input').setValue('v2 approval')
    await row().get('button').trigger('click'); await flushPromises()
    expect(row().text()).toContain('本版本已批准的新增范围')
    expect(row().text()).toContain('本版本决定：确认纳入范围')
    expect(row().text()).toContain('本版本审查：2026-10-19T02:00:00Z · v2 approval')
    expect(view.wrapper.text()).toContain('本版本已批准 1 项')
    await view.wrapper.get('[data-test=history]').setValue(frozen.digest)
    expect(row().text()).toContain('本版本已批准的新增范围')
    expect(row().text()).toContain('本版本审查：2026-10-18T02:00:00Z · v1 approval')
    expect(view.wrapper.find('[data-clause=c2] textarea').exists()).toBe(false)
    await view.wrapper.get('[data-test=history]').setValue(revised.digest)
    expect(row().text()).toContain('历史批准的新增范围（本版本未批准）')
    await view.wrapper.get('[data-test=history]').setValue(renewed.digest)
    expect(row().text()).toContain('本版本已批准的新增范围')
    view.wrapper.unmount()
  })
  it('does not display inherited provenance as approval when the version decision is rejected', async () => {
    const e = event('DRAFT', 2)
    Object.assign(e.state.clauses[1]!, { source: 'USER_APPROVED_ADDITION', decision: 'REJECTED' })
    vi.mocked(api.detail).mockResolvedValue(response(e))
    const { wrapper } = await setup(`/acceptance-plans/${e.state.plan_id}`); await unlock(wrapper)
    expect(wrapper.get('[data-clause=c2]').text()).toContain('历史批准的新增范围（本版本未批准）')
    expect(wrapper.get('[data-clause=c2]').text()).toContain('本版本决定：拒绝 / 不纳入')
    expect(wrapper.get('[data-clause=c2]').text()).not.toContain('本版本已批准的新增范围')
    wrapper.unmount()
  })
  it('reads frozen history separately and restores after remount with reauthentication', async () => {
    const old = event('FROZEN'); const current = event('DRAFT', 2)
    vi.mocked(api.detail).mockResolvedValue({ current, history: [old, current], snapshot_binding: 'INTACT' })
    let view = await setup(`/acceptance-plans/${current.state.plan_id}`); await unlock(view.wrapper)
    await view.wrapper.get('[data-test=history]').setValue(old.digest)
    expect(view.wrapper.text()).toContain('正在读取历史事件'); expect(view.wrapper.find('[data-test=transition]').exists()).toBe(false)
    view.wrapper.unmount()
    view = await setup(`/acceptance-plans/${current.state.plan_id}`)
    expect(view.wrapper.find('[data-test=operator]').exists()).toBe(true); await unlock(view.wrapper)
    expect(view.wrapper.text()).toContain('v2'); view.wrapper.unmount()
  })
  it.each(['ACCEPTANCE_SNAPSHOT_MISMATCH', 'ACCEPTANCE_SNAPSHOT_UNAVAILABLE', 'ACCEPTANCE_STALE'])('shows %s without inventing a saved result', async code => {
    vi.mocked(api.create).mockRejectedValue({ response: { data: { error: { code } } } })
    const { wrapper, router } = await setup(); await unlock(wrapper)
    await wrapper.get('[data-test=snapshot]').setValue(snapshot.identity); await wrapper.get('[data-test=prompt]').setValue('synthetic private prompt')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain(code); expect(router.currentRoute.value.path).toBe('/acceptance-plans')
    expect(wrapper.text()).not.toContain('验收方案已确认'); if (code.startsWith('ACCEPTANCE_SNAPSHOT_')) expect(wrapper.get('[data-test=create]').attributes('disabled')).toBeDefined(); wrapper.unmount()
  })
  it('reuses request ID after uncertain network response and excludes secrets from errors', async () => {
    vi.mocked(api.create).mockRejectedValue(new Error('synthetic-private-secret'))
    const { wrapper } = await setup(); await unlock(wrapper)
    await wrapper.get('[data-test=snapshot]').setValue(snapshot.identity); await wrapper.get('[data-test=prompt]').setValue('prompt')
    for (let i = 0; i < 2; i++) { await wrapper.get('form').trigger('submit'); await flushPromises() }
    expect(vi.mocked(api.create).mock.calls[0]![0].request_id).toBe(vi.mocked(api.create).mock.calls[1]![0].request_id)
    expect(wrapper.get('[role=alert]').text()).not.toContain('synthetic-private-secret'); wrapper.unmount()
  })
  it('disables edits for a damaged bound snapshot', async () => {
    vi.mocked(api.detail).mockResolvedValue({ ...response(event()), snapshot_binding: 'UNAVAILABLE_OR_CHANGED' })
    const { wrapper } = await setup(`/acceptance-plans/${event().state.plan_id}`); await unlock(wrapper)
    expect(wrapper.get('[role=alert]').text()).toContain('修改与冻结被阻止'); expect(wrapper.find('[data-test=transition]').exists()).toBe(false)
    expect(wrapper.find('[data-clause=c1] textarea').exists()).toBe(false); wrapper.unmount()
  })
  it('denies invalid credentials and public Demo', async () => {
    vi.mocked(api.list).mockRejectedValue({ response: { data: { error: { code: 'LOCAL_OPERATOR_REQUIRED' } } } })
    let view = await setup(); await unlock(view.wrapper)
    expect(view.wrapper.get('[role=alert]').text()).toContain('操作员凭据不正确'); expect(api.create).not.toHaveBeenCalled(); view.wrapper.unmount()
    vi.mocked(api.status).mockResolvedValue({ enabled: false, execution_enabled: false })
    view = await setup(); expect(view.wrapper.text()).toContain('公开 Demo 不支持此流程'); expect(view.wrapper.find('form').exists()).toBe(false); view.wrapper.unmount()
  })
})
