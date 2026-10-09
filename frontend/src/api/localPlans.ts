import axios from 'axios'

export interface TaskInspection {
  reference: string; task_owner: string; task_category: string
  task_identity: string; workspace_identity: string; verifier_identity: string; oracle_identity: string
  managed_snapshot_identity: string; source_root_id: string; source_relative_path: string; source_identity: string
  structural_validation: 'PASS'; behavioral_validation: 'TRUSTED_PRIOR_RESULT' | 'NOT_VERIFIED'
  qualification_identity: string | null; eligible_for_planning: boolean; reason_codes: string[]; verifier_executed: false
}
export interface CodexConfiguration {
  provider_profile_id: string; harness_profile_id: string; requested_model: string; reasoning_effort: string
  runtime_version: string; image_reference: string; enabled: boolean; configuration_label: string
}
export interface PlanRequest {
  name: string; task_reference: string; provider_profile_id: string; harness_profile_id: string
  budget: { wall_time_seconds: number; output_tokens_estimate: number; cost_budget_usd: number }
}
export interface PlanningCheck { code: string; passed: boolean }
export interface PlanMaterial {
  request: PlanRequest; task: TaskInspection; material_digest: string; policy_identity: string
  configuration: { application_version: string; application_code_identity: string; image_identity: string; configuration_identity: string
    model: { requested_model: string; credential_reference: string }; harness: { version: string }; harness_profile: { reasoning_effort: string } }
  custom_plan: { targets: unknown[]; tasks: unknown[]; run_slots: unknown[]; repeat_count: number }
  budget_semantics: Record<string, string>; workspace_policy: string
}
export interface PreflightReceipt {
  receipt_id: string; receipt_digest: string; status: 'READY_TO_SAVE' | 'BLOCKED'; checks: PlanningCheck[]
  created_at: string; expires_at: string; material: PlanMaterial | null; execution_authorized: false; provider_calls: 0; verifier_calls: 0
}
export interface SavedPlan {
  plan_id: string; plan_digest: string; created_at: string; preflight: PreflightReceipt
  status: 'SAVED_PLAN_ONLY'; execution_authorized: false; runs_created: 0; episodes_created: 0
}
export interface PlanDetail { plan: SavedPlan; current_status: 'UNCHANGED_RECHECK_REQUIRED' | 'STALE'; checks: PlanningCheck[]; execution_enabled: false }
export interface PlanSummary { plan_id: string; name: string; task_reference: string; created_at: string; status: 'SAVED_PLAN_ONLY' }
// A private operator token is used per request, never in URL/default headers/browser storage.
const client = axios.create({ baseURL: '/api/local-plans', timeout: 30000 })
const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } })
export const localPlansApi = {
  status: async () => (await client.get<{ enabled: boolean; execution_enabled: false }>('/status')).data,
  sources: async (token: string) => (await client.get<{ root_ids: string[]; candidates: { root_id: string; relative_path: string }[] }>('/sources', auth(token))).data,
  tasks: async (token: string) => (await client.get<{ items: TaskInspection[] }>('/tasks', auth(token))).data,
  importTask: async (root_id: string, relative_path: string, token: string) => (await client.post<TaskInspection>('/tasks/import', { root_id, relative_path }, auth(token))).data,
  inspect: async (reference: string, token: string) => (await client.get<TaskInspection>(`/tasks/${encodeURIComponent(reference)}`, auth(token))).data,
  configurations: async (token: string) => (await client.get<{ items: CodexConfiguration[] }>('/configurations', auth(token))).data,
  preflight: async (payload: PlanRequest, token: string) => (await client.post<PreflightReceipt>('/preflight', payload, auth(token))).data,
  save: async (receipt: PreflightReceipt, idempotency_key: string, token: string) => (await client.post<SavedPlan>('/plans', { receipt_id: receipt.receipt_id, receipt_digest: receipt.receipt_digest, idempotency_key, confirm_plan_only: true }, auth(token))).data,
  plans: async (token: string, offset = 0) => (await client.get<{ items: PlanSummary[]; total: number; limit: number; offset: number }>('/plans', { ...auth(token), params: { offset } })).data,
  plan: async (id: string, token: string) => (await client.get<PlanDetail>(`/plans/${encodeURIComponent(id)}`, auth(token))).data,
}
