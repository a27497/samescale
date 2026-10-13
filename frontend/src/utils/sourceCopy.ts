import { copy as c } from '@/composables/visualLocale'
// Exact fixture translations only, never inferred claims from arbitrary Agent or verifier text.
export function sourceCopy(text: string): string {
  const known: Record<string, string> = {
    'Implemented successfully; tests pass.': 'Agent 自称已完成修改，测试通过（尚未核验的自报）。',
    'isolated Hidden Verifier rejected the final workspace': '隔离的独立验收检查未通过最终工作区。',
  }
  if (Object.hasOwn(known, text)) return c(known[text], text)
  return c('已保存来源文本，可展开核对原文。', 'Saved source text; expand to inspect it.')
}
