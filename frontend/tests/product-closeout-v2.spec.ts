import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { preferences } from '@/composables/preferences'
import { configName, experimentOption, identityKey, runName } from '@/utils/displayIdentity'
import { factOverview, historicalOverview } from '@/utils/reportOverview'
import InvestigationReport from '@/components/InvestigationReport.vue'
import TechnicalDetails from '@/components/TechnicalDetails.vue'
import ExperimentPicker from '@/components/ExperimentPicker.vue'
import type { ExperimentSummary } from '@/types/workbench'

beforeEach(() => { preferences.language = 'zh-CN' })
const record = (id: string): ExperimentSummary => ({ experiment_id: id, name: '同名实验', provenance: 'UNVERIFIED_SOURCE', status: 'completed', plan_digest: 'sha256:original', cell_count: 1, task_count: 1, planned_run_count: 2, completed_capability_count: 2, infra_count: 0, created_at: '2026-10-09', started_at: null, finished_at: null })
const assertions = (values: Record<string, unknown>, tool = 'get_ablation') => ({ statement: 'SOURCE_TEXT_WITH_NO_INFERENCE', evidence_refs: ['ablation:original-id'], assertions: Object.entries(values).map(([key, value]) => ({ tool, field_path: key.split('.'), expected_value: value })) })
const ablation = assertions({ total_capability_pairs: 60, comparable_pairs: 29, not_comparable_pairs: 31, evidence_tier: 'INSUFFICIENT', formal_eligible: false })

describe('Presentation identities retain original keys', () => {
  it('distinguishes runs with identical tasks, repeats, attempts and matching short prefixes', () => {
    const a = `run-${'a'.repeat(8)}1${'0'.repeat(55)}`, b = `run-${'a'.repeat(8)}2${'0'.repeat(55)}`
    const peers = [a, b], source = { task_id: 'micro-typescript-clamp', repeat_index: 2, attempt: 1 }
    expect(identityKey(a, peers)).not.toBe(identityKey(b, peers))
    expect(runName({ ...source, run_id: a }, peers)).not.toBe(runName({ ...source, run_id: b }, peers))
    expect(runName({ ...source, run_id: a }, peers)).toContain('第 3 次 · 尝试 1')
    expect(runName({ ...source, run_id: a }, peers)).not.toContain(a)
  })
  it('distinguishes same-named experiments even when their final eight characters match', () => {
    const a = record('saved-a-common-suffix'), b = record('saved-b-common-suffix')
    expect(experimentOption(a, [a, b])).not.toBe(experimentOption(b, [a, b]))
    expect(a.experiment_id).toBe('saved-a-common-suffix')
    expect(experimentOption(a, [a])).toBe('同名实验')
  })
  it('does not authenticate unknown configurations or create a model name from an ID', () => {
    expect(configName('custom-provider-sensitive-configuration')).toContain('配置')
    expect(configName('custom-provider-sensitive-configuration')).not.toContain('custom-provider-sensitive')
    expect(configName('custom-provider-sensitive-configuration')).not.toContain('真实')
  })
  it('keeps a prefilled identity selected while the bounded list omits it', async () => {
    const wrapper = mount(ExperimentPicker, { props: { modelValue: 'outside-page-identity', experiments: [record('listed')], label: '基线实验' } })
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('outside-page-identity')
    expect(wrapper.get('select').text()).toContain('已预填实验')
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('outside-page-identity')
    await wrapper.get('input').setValue('another-full-identity')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['another-full-identity'])
    expect(wrapper.emitted('change')).toHaveLength(1)
  })
})

describe('Chinese report overview is a bounded projection', () => {
  it('reads counts and formal eligibility from exact structured fields without rewriting source', () => {
    const snapshot = JSON.stringify(ablation)
    expect(factOverview(ablation)).toContain('60 对能力结果，其中 29 对可比、31 对不可比')
    expect(historicalOverview([ablation])).toContain('未达到正式比较条件')
    expect(JSON.stringify(ablation)).toBe(snapshot)
  })
  it.each([
    { total_capability_pairs: 60, comparable_pairs: 29, not_comparable_pairs: 30, evidence_tier: 'INSUFFICIENT', formal_eligible: false },
    { total_capability_pairs: 60, comparable_pairs: 29, not_comparable_pairs: 31, evidence_tier: 'INSUFFICIENT' },
    { total_capability_pairs: '60', comparable_pairs: 29, not_comparable_pairs: 31, evidence_tier: 'INSUFFICIENT', formal_eligible: false },
  ])('declines incomplete, contradictory or mistyped evidence: %j', value => {
    expect(factOverview(assertions(value))).toBeNull()
  })
  it('does not parse causal conclusions or numbers from free-form text', () => {
    expect(factOverview({ statement: '60 pairs, 29 comparable; the candidate is best', evidence_refs: [] })).toBeNull()
    expect(historicalOverview([])).toBeNull()
    expect(factOverview(assertions({ total_capability_pairs: 60, comparable_pairs: 29, not_comparable_pairs: 31, evidence_tier: 'INSUFFICIENT', formal_eligible: false }, 'unrecognized_tool'))).toBeNull()
  })
  it('rejects conflicting duplicate assertions and reports saved outcomes without a ranking', () => {
    const inconsistent = { ...ablation, assertions: [...ablation.assertions, { tool: 'get_ablation', field_path: ['comparable_pairs'], expected_value: 30 }] }
    expect(factOverview(inconsistent)).toBeNull()
    const summary = factOverview(assertions({ 'statistics.completed_capability_runs': 88, 'statistics.capability_passes': 68, 'statistics.capability_failures': 20, 'statistics.formal_eligible': false }, 'compare_cells'))
    expect(summary).toContain('68 条通过，20 条未通过')
    expect(summary).not.toMatch(/更优|胜出|因果/)
  })
})

describe('Inspectable technical details', () => {
  it('copies the entire source value and keeps the disclosure closed by default', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const original = `sha256:${'a'.repeat(64)}`
    const wrapper = mount(TechnicalDetails, { props: { fields: [{ label: 'SHA256', value: original }] } })
    expect(wrapper.attributes('open')).toBeUndefined()
    expect(wrapper.get('code').text()).toBe(original)
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(writeText).toHaveBeenCalledWith(original)
    expect(wrapper.get('[role="status"]').text()).toContain('已复制完整原值')
  })
  it('reports clipboard failure, retains the source and never claims success', async () => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } })
    const wrapper = mount(TechnicalDetails, { props: { fields: [{ label: 'Run ID', value: 'original-complete-id' }] } })
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('手动复制')
    expect(wrapper.get('code').text()).toBe('original-complete-id')
    expect(wrapper.get('button').text()).toBe('复制')
  })
})

it('withholds the specific historical overview when its cited source is absent and preserves the orphan reference', () => {
  const report = { summary: 'Original source summary', verified_facts: [ablation], hypotheses: [], limitations: [] }
  const wrapper = mount(InvestigationReport, { props: { report, evidence: [], sourceKind: 'historical_real' } })
  expect(wrapper.get('.conclusion').text()).not.toContain('60 对能力结果')
  expect(wrapper.get('.missing-reference > span').text()).toBe('来源不可用：引用 1')
  expect(wrapper.get('.missing-reference code').text()).toBe('ablation:original-id')
  expect(wrapper.text()).toContain(report.summary)
})
