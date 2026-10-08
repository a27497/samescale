import type { TraceResponse, RunDetail, RegressionComparison } from '@/types/workbench'
export function safeTrace(trace: TraceResponse | null): TraceResponse | null {
  return trace && { ...trace, events: trace.events.map(event => event.type === 'REASONING_PRESENT' ? { ...event, summary: 'Private reasoning withheld.' } : event) }
}
export function verifierStatus(run: RunDetail): string {
  return run.verifier_passed === true ? 'VERIFIED_PASS' : run.verifier_passed === false ? 'VERIFIED_FAIL' : 'NOT_VERIFIED'
}
export function eligibleDirection(item: RegressionComparison): string {
  return item.comparability === 'COMPARABLE' && item.eligible_paired_observations > 0 ? item.direction : 'NOT_REPORTED'
}
export function downloadRun(run: RunDetail, trace: TraceResponse | null) {
  const payload = { source: 'SameScale safe normalized API projection', run, trace: safeTrace(trace) }
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }))
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = `samescale-run-${run.run_id}.json`; anchor.click(); URL.revokeObjectURL(url)
}
