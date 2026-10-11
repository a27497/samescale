import { copy as c } from '@/composables/visualLocale'
import type { RunDetail, TraceResponse } from '@/types/workbench'
import type { EvidenceDetail } from '@/api/externalEvidence'

export interface AcceptanceRow { key: 'original' | 'checked' | 'unverified' | 'replay'; label: string; status: string; detail: string }

const labels = () => ({
  original: c('原运行状态', 'Original run state'),
  checked: c('独立检查的要求与结果', 'Independently checked requirements'),
  unverified: c('未验证 / 未知', 'Not verified / unknown'),
  replay: c('离线复核', 'Offline re-review'),
})

export function runAcceptanceRows(run: RunDetail, trace: TraceResponse | null): AcceptanceRow[] {
  const l = labels()
  const claim = trace?.events.find(event => event.type === 'AGENT_MESSAGE')?.summary ?? null
  const verdict = run.verifier_passed === true ? 'VERIFIED_PASS' : run.verifier_passed === false ? 'VERIFIED_FAIL' : 'NOT_VERIFIED'
  const unknown: string[] = []
  if (run.verifier_passed === null) unknown.push(c('任务验收结论', 'task verdict'))
  if (!trace) unknown.push(c('运行事件', 'trace events'))
  if (!claim) unknown.push(c('Agent 自报', 'agent self-report'))
  if (!run.evidence_digest) unknown.push(c('证据摘要', 'evidence digest'))
  return [
    { key: 'original', label: l.original, status: run.status, detail: `${c('终态', 'Terminal state')}：${run.status} · ${c('Agent 自报', 'Agent self-report')}：${claim ?? c('未报告', 'not reported')}` },
    { key: 'checked', label: l.checked, status: verdict, detail: run.verifier_passed === null ? c('没有已保存的独立验收结论；不视为通过。', 'No saved independent verdict; not treated as a pass.') : `${c('独立 Verifier', 'Independent verifier')}：${run.summary ?? c('未报告摘要', 'no summary reported')}` },
    { key: 'unverified', label: l.unverified, status: unknown.length ? 'NOT_VERIFIED' : 'NOT_REPORTED', detail: unknown.length ? unknown.join('、') : c('记录未标出其他未验证项；未覆盖的要求仍可能存在。', 'No other unverified items flagged; uncovered requirements may still exist.') },
    { key: 'replay', label: l.replay, status: run.evidence_digest ? 'AVAILABLE' : 'NOT_REPORTED', detail: run.evidence_digest ? c('可下载安全证据 JSON，并按摘要离线核对。', 'Download safe evidence JSON and check it offline against the digest.') : c('缺少证据摘要，离线复核无法确认完整性。', 'No evidence digest; offline integrity cannot be confirmed.') },
  ]
}

export function externalAcceptanceRows(detail: EvidenceDetail): AcceptanceRow[] {
  const l = labels(); const d = detail.diagnosis; const v = d.independent_verification
  const unknown = [...detail.record.completeness.missing_fields]
  if (d.workspace_acceptance === 'NOT_VERIFIED') unknown.unshift(c('工作区验收', 'workspace acceptance'))
  if (v.checks > v.passed_checks && d.workspace_acceptance !== 'NOT_VERIFIED') unknown.push(`${v.checks - v.passed_checks} ${c('项检查未通过', 'checks did not pass')}`)
  const corrupt = /FAIL|CORRUPT|MISMATCH/.test(detail.record.completeness.integrity)
  return [
    { key: 'original', label: l.original, status: d.original_episode_acceptance, detail: `${c('原运行验收', 'Original acceptance')}：${d.original_episode_acceptance} · ${c('Agent 自报事件', 'Agent report events')}：${d.agent_self_reports.length ? d.agent_self_reports.join(', ') : c('无', 'none')}` },
    { key: 'checked', label: l.checked, status: d.workspace_acceptance, detail: v.checks > 0 ? `${c('独立检查', 'Independent checks')} ${v.passed_checks}/${v.checks} ${c('通过', 'passed')}` : `${c('未执行独立检查（0 项）', 'No independent checks run (0)')}${v.reason ? ` · ${v.reason}` : ''}` },
    { key: 'unverified', label: l.unverified, status: unknown.length ? 'NOT_VERIFIED' : 'NOT_REPORTED', detail: unknown.length ? unknown.join('、') : c('记录未标出其他未验证项。', 'No other unverified items flagged.') },
    { key: 'replay', label: l.replay, status: corrupt ? 'CORRUPT' : 'AVAILABLE', detail: corrupt ? `${c('完整性', 'Integrity')}：${detail.record.completeness.integrity}；${c('不可作为复核依据', 'not usable for re-review')}` : c('可导出脱敏证据与工作区，按摘要离线复核。', 'Export sanitized evidence and workspace; replay offline against the digest.') },
  ]
}
