import { copy as c } from '@/composables/visualLocale'
import type { ApprovedEvidenceSource } from '@/api/externalEvidence'

// Only legacy Codex formats imply a harness when metadata is absent.
export function sourceHarness(source: ApprovedEvidenceSource): string | undefined {
  return source.harness?.name ?? (source.format.startsWith('codex-') || ['native-hook-v1', 'verified-hook-v1'].includes(source.format) ? 'codex' : undefined)
}

export function matchesSourceFilter(source: ApprovedEvidenceSource, filter: string): boolean {
  if (filter === 'all') return true
  if (source.format === 'code-only-v1') return filter === 'code-only'
  const harness = sourceHarness(source)
  // An approved auto source is identified only at intake, so it can be either adapter.
  if (source.format === 'auto-v1' && !harness) return ['codex', 'claude-code'].includes(filter)
  return harness === filter
}

export function evidenceFieldLabel(field: string): string {
  const labels: Record<string, [string, string]> = {
    run_record: ['运行记录', 'Run record'],
    actual_model: ['实际使用的模型', 'Actual model'],
    provider_route: ['模型服务路由', 'Provider route'],
    request_count: ['模型请求次数', 'Model request count'],
    usage: ['用量记录', 'Usage records'],
    cost: ['费用记录', 'Cost records'],
    wall_clock_order: ['事件时间顺序', 'Event time order'],
    process_exit_code: ['进程退出码', 'Process exit code'],
    trusted_task_contract: ['可信任务验收条件', 'Trusted task acceptance conditions'],
    independent_verifier: ['独立验收结果', 'Independent verification result'],
    native_completion: ['运行结束记录', 'Run completion record'],
    unmapped_events: ['未解析的运行事件', 'Unmapped run events'],
    tool_call_links: ['工具调用关联', 'Tool call links'],
    tool_exit_codes: ['工具退出码', 'Tool exit codes'],
    paired_hook_lifecycle: ['配对的运行生命周期记录', 'Paired run lifecycle records'],
  }
  const pair = labels[field]
  return pair ? c(...pair) : c('其他未报告信息（见技术细节）', 'Other unreported information (see technical details)')
}

export function verificationReasonLabel(reason: string): string {
  const labels: Record<string, [string, string]> = {
    VERIFIER_INFRASTRUCTURE_FAILURE: ['独立验收基础设施异常；本次检查未建立结论', 'Independent verification infrastructure failed; this attempt established no verdict'],
    TRUSTED_TASK_OR_VERIFIER_MISSING: ['缺少可信任务绑定或独立验收结果', 'Trusted task mapping or independent verification is missing'],
    RECORDED_RESULT_ONLY_REQUIRES_TRUSTED_INDEPENDENT_ADMISSION: ['仅有保存结果，仍需可信的独立验收准入', 'Saved result only; trusted independent admission is still required'],
  }
  const pair = labels[reason]
  return pair ? c(...pair) : c('独立验收尚不可用；原因见技术细节', 'Independent verification unavailable; see technical details for the reason')
}
