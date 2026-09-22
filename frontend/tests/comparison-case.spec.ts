import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it } from 'vitest'
import ComparisonCase from '@/components/ComparisonCase.vue'
import { comparisonFixture } from './fixtures/comparison'
import { preferences } from '@/composables/preferences'

beforeEach(() => { preferences.language = 'zh-CN' })
it('separates individual, paired, infrastructure and billing denominators', () => {
  const wrapper = mount(ComparisonCase, { props: { example: comparisonFixture } })
  const cards = wrapper.findAll('.result-card')
  expect(cards[0]!.get('.pass-count').text()).toContain('83 / 86')
  expect(cards[1]!.get('.pass-count').text()).toContain('65 / 86')
  expect(wrapper.get('.paired-result').text()).toContain('82 / 90')
  expect(wrapper.get('.paired-result').text()).toContain('部分可比')
  expect(wrapper.text()).toContain('基础设施失败与取消另计')
  expect(wrapper.get('.cost-table').text()).toContain('实际账单未知未知')
  expect(wrapper.get('.cost-table').text()).toContain('已采集 77/90')
  expect(wrapper.text()).toContain('不是实际账单')
  expect(wrapper.text()).toContain('请求输出上限不代表整个 Codex 任务的总输出上限')
})
it('explains the actual retry-ledger failure and preserves specification uncertainty', () => {
  const wrapper = mount(ComparisonCase, { props: { example: comparisonFixture } })
  expect(wrapper.get('.failure-example').text()).toContain('record_success("", "x")')
  expect(wrapper.get('.failure-example').text()).toContain('ValueError')
  expect(wrapper.get('.failure-example').text()).toContain('True')
  expect(wrapper.findAll('.verifier-checks .failed')).toHaveLength(1)
  expect(wrapper.get('.specification-note').text()).toContain('没有明确要求拒绝空键')
  expect(wrapper.text()).toContain('配对另一侧的文件完整性有限')
  expect(wrapper.text()).toContain('不重建推理或操作过程')
  expect(wrapper.find('details[open]').exists()).toBe(false)
})
it('opens exact citations, safely renders evidence and restores keyboard focus', async () => {
  const wrapper = mount(ComparisonCase, { props: { example: comparisonFixture }, attachTo: document.body })
  const origin = wrapper.get('[aria-label="核对结果证据 · 直接调用"]')
  await origin.trigger('click'); await flushPromises()
  expect(wrapper.get('dialog').attributes('open')).toBeDefined()
  expect(wrapper.get('dialog .evidence-path').text()).toBe('release/fixture.json#/cells/direct')
  expect(wrapper.get('dialog pre').text()).toContain('"capability_evaluable": 86')
  expect(document.activeElement).toBe(wrapper.get('dialog button').element)
  await wrapper.get('dialog').trigger('keydown', { key: 'Escape' }); await flushPromises()
  expect(document.activeElement).toBe(origin.element)
  await wrapper.findAll('button').find(b => b.text() === '核对失败证据 ↗')!.trigger('click'); await flushPromises()
  expect(wrapper.get('dialog pre').text()).toContain('<img src=x onerror=alert(1)>')
  expect(wrapper.find('dialog img').exists()).toBe(false)
  await wrapper.setProps({ example: { ...comparisonFixture, sources: [] } })
  expect(wrapper.get('dialog').attributes('open')).toBeUndefined()
  expect(wrapper.text()).not.toContain('<img src=x onerror=alert(1)>')
  wrapper.unmount()
})
it('moves keyboard focus to the chosen case section', async () => {
  const wrapper = mount(ComparisonCase, { props: { example: comparisonFixture }, attachTo: document.body })
  await wrapper.findAll('.case-nav button')[2]!.trigger('click')
  expect(document.activeElement).toBe(wrapper.get('[data-case-section="2"]').element)
  wrapper.unmount()
})
it('does not zero-fill missing cost or timing and localizes the interface', () => {
  preferences.language = 'en'
  const example = structuredClone(comparisonFixture)
  example.cells[0].primary_latency_ms = null; example.cells[0].estimated_cost_usd = null
  const wrapper = mount(ComparisonCase, { props: { example } })
  expect(wrapper.get('.cost-table').text()).toContain('Unacquired')
  expect(wrapper.get('.cost-table').text()).toContain('Unknown')
  expect(wrapper.get('.case-heading').text()).toContain('Direct vs. Codex')
  expect(wrapper.get('.verifier-checks').text()).toContain('Empty operation key is rejected')
  preferences.language = 'zh-CN'
})
