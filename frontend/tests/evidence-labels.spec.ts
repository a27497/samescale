import { beforeEach, expect, it } from 'vitest'
import { setLocale } from '@/composables/visualLocale'
import { evidenceLabel, sourceExplanation } from '@/utils/evidenceLabels'
beforeEach(() => setLocale('zh-CN'))
it('translates checked codes and leaves unknown evidence unchanged', () => {
  expect(evidenceLabel('OBSERVED_MODEL_MISSING')).toBe('未报告实际观察模型')
  expect(evidenceLabel('RESOURCE_ENVELOPE_MISSING')).toBe('缺少资源约束记录')
  expect(evidenceLabel('No Modification')).toBe('最终工作区无修改')
  expect(evidenceLabel('unknown original evidence')).toBe('unknown original evidence')
})
it('provides source explanations only for an exact backend statement', () => {
  const source = 'Trace correlation is not causality; a controlled ablation is required to strengthen attribution.'
  expect(sourceExplanation(source)).toContain('不证明因果')
  expect(sourceExplanation(source + ' Extra source content.')).toBeNull()
  expect(sourceExplanation('Agent claims the cause was found.')).toBeNull()
  setLocale('en-US')
  expect(sourceExplanation(source)).toBe(source)
})
