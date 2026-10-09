import { workbenchApi } from '@/api/client'
import type { ExperimentSummary, RunListResponse } from '@/types/workbench'

export interface OutcomeCounts { passed: number | null; failed: number | null }
export const unreportedCounts = (): OutcomeCounts => ({ passed: null, failed: null })
const count = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0

// The existing filtered run endpoint returns a database count across all pages.
// Never derive verdict counts from rates, lifecycle states, or a bounded loaded list.
export function checkedOutcomeCounts(summary: ExperimentSummary, passed: RunListResponse, failed: RunListResponse): OutcomeCounts {
  if (!count(passed.total) || !count(failed.total) || !count(summary.completed_capability_count)
    || passed.total + failed.total !== summary.completed_capability_count
    || !passed.items.every(run => run.experiment_id === summary.experiment_id && run.normalized_outcome === 'capability_pass')
    || !failed.items.every(run => run.experiment_id === summary.experiment_id && run.normalized_outcome === 'capability_fail')) return unreportedCounts()
  return { passed: passed.total, failed: failed.total }
}
export async function loadOutcomeCounts(summary: ExperimentSummary): Promise<OutcomeCounts> {
  // Do not probe inaccessible evidence when the list already reports failed integrity.
  if (summary.integrity_status === 'INTEGRITY_FAILED') return unreportedCounts()
  try {
    const [passed, failed] = await Promise.all([
      workbenchApi.getRuns(summary.experiment_id, { outcome: 'capability_pass', limit: 1 }),
      workbenchApi.getRuns(summary.experiment_id, { outcome: 'capability_fail', limit: 1 }),
    ])
    return checkedOutcomeCounts(summary, passed, failed)
  } catch { return unreportedCounts() }
}
