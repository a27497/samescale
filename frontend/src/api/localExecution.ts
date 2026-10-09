import axios from 'axios'
import type { SavedPlan, PlanRequest } from './localPlans'

export interface ExecutionResult {
  status: string; reason_code: string; acceptance: string; run_id: string; digest: string; episode_id: string | null
  model_calls: 0; model_cost_usd: 0
  episode: { event_count: number; changed_file_count: number; verifier_check_count: number; trace_digest: string; workspace_output_digest: string; acceptance: string } | null
}
export interface ExecutionState {
  status: string; mode: 'FAKE_CODEX'; real_execution_enabled: false; result: ExecutionResult | null
  attempt: { run_id: string; attempt_number: number; cancellation_requested: boolean; authorization: { expires_at: string; digest: string } } | null
}
export interface ExecutionStatus { enabled: boolean; mode: 'FAKE_CODEX'; real_execution_enabled: false; reason_codes: string[]; model_calls_allowed: 0 }
const client = axios.create({ baseURL: '/api/local-execution', timeout: 30000 })
const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } })
// Canonical JSON follows the existing Python canonical_digest contract for one slot.
async function slotDigest(slot: unknown) {
  function ordered(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(ordered)
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([k, v]) => [k, ordered(v)]))
    return value
  }
  const data = new TextEncoder().encode(JSON.stringify(ordered(slot)))
  const digest = await crypto.subtle.digest('SHA-256', data)
  return 'sha256:' + Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
}
export const localExecutionApi = {
  status: async (token: string) => (await client.get<ExecutionStatus>('/status', auth(token))).data,
  state: async (id: string, token: string) => (await client.get<ExecutionState>(`/plans/${encodeURIComponent(id)}`, auth(token))).data,
  authorize: async (plan: SavedPlan, key: string, token: string) => {
    const material = plan.preflight.material
    if (!material || material.custom_plan.run_slots.length !== 1) throw new Error('Single immutable slot required')
    const payload = { plan_digest: plan.plan_digest, run_slot_digest: await slotDigest(material.custom_plan.run_slots[0]), idempotency_key: key, mode: 'FAKE_CODEX', confirmed_budget: material.request.budget as PlanRequest['budget'], max_model_cost_usd: 0, confirm_one_attempt: true, acknowledge_reference_budgets: true }
    return (await client.post<ExecutionState>(`/plans/${encodeURIComponent(plan.plan_id)}/authorize`, payload, auth(token))).data
  },
  cancel: async (id: string, token: string) => (await client.post<ExecutionState>(`/plans/${encodeURIComponent(id)}/cancel`, { action: 'CANCEL' }, auth(token))).data,
}
