import { copy as c } from '@/composables/visualLocale'

// Exact code/enum mappings only. Evidence strings and unknown values stay unchanged.
const labels: Record<string, [string, string]> = {
  'No Modification': ['最终工作区无修改', 'No Modification'],
  'Provider Failure': ['Provider 执行失败', 'Provider Failure'],
  'Wrong Files': ['修改文件不符合任务要求', 'Wrong Files'],
  'Test Failure': ['测试未通过', 'Test Failure'],
  'Verifier Failure': ['验收执行失败', 'Verifier Failure'],
  'Timeout': ['超时', 'Timeout'],
  'Tool Failure': ['工具执行失败', 'Tool Failure'],
  'Compile Failure': ['编译失败', 'Compile Failure'],
  'Dependency Failure': ['依赖失败', 'Dependency Failure'],
  'Protected File Mutation': ['受保护文件被修改', 'Protected File Mutation'],
  'Artifact Failure': ['产物异常', 'Artifact Failure'],
  'Harness Protocol Failure': ['Harness 协议异常', 'Harness Protocol Failure'],
  'Unknown Failure': ['未分类失败', 'Unknown Failure'],
  no_modification: ['最终工作区无修改', 'No modification'],
  'no-modification': ['最终工作区无修改', 'No persisted workspace modification'],
  'content-changed;paths-not-reported': ['内容摘要有变化，未报告路径', 'Content changed; paths not reported'],
  'not-reported': ['未报告', 'Not reported'],
  FULL_STREAM: ['完整事件流', 'Full event stream'], FINAL_OUTPUT_ONLY: ['仅最终输出', 'Final output only'], NOT_REPORTED: ['未报告', 'Not reported'],
  succeeded: ['执行完成', 'Execution completed'], completed: ['执行完成', 'Execution completed'],
  failed: ['执行失败', 'Execution failed'], cancelled: ['已取消', 'Cancelled'], timeout: ['执行超时', 'Execution timed out'],
  'OBSERVED_MODEL_MISSING': ['未报告实际观察模型', 'Observed model missing'],
  'RESOURCE_ENVELOPE_MISSING': ['缺少资源约束记录', 'Resource envelope missing'],
  'MISSING_CONTROL_MANIFEST': ['缺少控制条件清单', 'Control manifest missing'],
  'CONTROL_MANIFEST_MISMATCH': ['控制条件清单不一致', 'Control manifests differ'],
  'INFORMAL_EVIDENCE': ['证据未达到正式比较要求', 'Evidence is informal'],
  'INSUFFICIENT_EVIDENCE': ['证据不足', 'Insufficient evidence'],
}
export function evidenceLabel(value: string | null | undefined): string {
  if (!value) return c('未报告', 'Not reported')
  const pair = labels[value]
  return pair ? c(...pair) : value
}

// Translate only exact, checked backend guidance. Never infer from free-form evidence.
const explanations: Record<string, string> = {
  'Check the task contract against the final workspace and verifier failure; use trace/tool patterns to choose the next inspection, not as a root-cause verdict.': '对照任务要求、最终工作区和验收失败记录，再用 Trace 与工具模式选择下一项检查；这些模式不构成根因结论。',
  'Review the preregistered ablation contrast and its verifier outcomes before attributing this failure.': '归因前，先检查预先登记的消融对照及其验收结果。',
  'Trace correlation is not causality; a controlled ablation is required to strengthen attribution.': 'Trace 的相关性不证明因果；更强的归因需要受控消融证据。',
  'Controlled ablation strengthens association but does not by itself prove causality.': '受控消融可以加强关联证据，但本身仍不证明因果。',
}
export function sourceExplanation(text: string): string | null {
  const translation = explanations[text]
  return translation ? c(translation, text) : null
}
