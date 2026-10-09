import { copy as c } from '@/composables/visualLocale'
import type { AnalystSession } from '@/types/analyst'
type Fact = NonNullable<AnalystSession['report']>['verified_facts'][number]
// Read only exact structured assertion paths. No parsing or inference from source prose.
export function factOverview(fact: Fact): string | null {
  const values = new Map<string, unknown>()
  for (const item of fact.assertions ?? []) {
    const key = `${item.tool}:${item.field_path.join('.')}`
    if (values.has(key) && values.get(key) !== item.expected_value) return null
    values.set(key, item.expected_value)
  }
  const get = (tool: string, path: string) => values.get(`${tool}:${path}`)
  const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0
  const total = get('get_ablation', 'total_capability_pairs'), comparable = get('get_ablation', 'comparable_pairs'), missing = get('get_ablation', 'not_comparable_pairs')
  if (number(total) && number(comparable) && number(missing) && comparable + missing === total && get('get_ablation', 'evidence_tier') === 'INSUFFICIENT' && get('get_ablation', 'formal_eligible') === false) {
    return c(`消融对照共 ${total} 对能力结果，其中 ${comparable} 对可比、${missing} 对不可比；证据不足，未达到正式比较条件。`, `The ablation has ${total} capability pairs: ${comparable} comparable and ${missing} incomparable. Evidence is insufficient for formal comparison.`)
  }
  const complete = get('compare_cells', 'statistics.completed_capability_runs'), pass = get('compare_cells', 'statistics.capability_passes'), fail = get('compare_cells', 'statistics.capability_failures')
  if (number(complete) && number(pass) && number(fail) && pass + fail === complete) {
    return c(`该配置已收集 ${complete} 条能力结果：${pass} 条通过，${fail} 条未通过。${get('compare_cells', 'statistics.formal_eligible') === false ? '未达到正式比较条件。' : ''}`, `This configuration has ${complete} capability outcomes: ${pass} passed and ${fail} failed.${get('compare_cells', 'statistics.formal_eligible') === false ? ' Not eligible for formal comparison.' : ''}`)
  }
  return null
}
export function historicalOverview(facts: Fact[]): string | null {
  const ablation = facts.map(factOverview).find(text => text?.includes(c('消融对照', 'The ablation')))
  return ablation ?? null
}
