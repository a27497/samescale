import axios from 'axios'

export type Source = 'EXPLICIT_IN_PROMPT' | 'USER_APPROVED_ADDITION' | 'SUGGESTED_ONLY' | 'AMBIGUOUS'
export type Decision = 'PENDING' | 'APPROVED' | 'REJECTED'
export interface Clause {
  id: string; text: string; source: Source; decision: Decision
  origin: { kind: string; source: Source; text: string; quote: string | null }
  reviewed_at: string | null; review_reason: string | null
}
export interface PlanState {
  plan_id: string; version: number; status: 'DRAFT' | 'CONFIRMED' | 'FROZEN'; original_prompt: string
  snapshot: { identity: string; content_digest: string }; clauses: Clause[]; uncovered: string[]
  confirmed_at: string | null; frozen_at: string | null; parent_frozen_digest: string | null
  verifier_status: 'NO_QUALIFIED_BOUND_VERIFIER'; acceptance_result: 'NOT_RUN'
  execution_authorized: false; taskstore_admitted: false; audit_context: 'POST_DELIVERY_AUDIT'
}
export interface PlanEvent {
  digest: string; sequence: number; action: string; at: string; reason: string; actor: string; state: PlanState
}
export interface PlanDetail { current: PlanEvent; history: PlanEvent[]; snapshot_binding: string }
export interface PlanSummary { plan_id: string; version: number; status: string; at: string; snapshot_identity: string }
export interface SnapshotOption { identity: string; status: string; content_digest?: string; file_count?: number }
export interface CreatePlan { request_id: string; snapshot_identity: string; snapshot_content_digest: string; original_prompt: string }
export interface ChangePlan {
  request_id: string; expected_digest: string; action: 'REVIEW' | 'ADD' | 'CONFIRM' | 'FREEZE' | 'REVISE'
  reason: string; clause_id?: string; text?: string; decision?: Decision; acknowledgement?: 'SCOPE_ONLY_NO_EXECUTION'
}
const client = axios.create({ baseURL: '/api/acceptance-plans', timeout: 30000 })
const config = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } })
export const acceptancePlansApi = {
  status: async () => (await client.get<{ enabled: boolean; execution_enabled: false }>('/status')).data,
  snapshots: async (token: string) => (await client.get<{ items: SnapshotOption[] }>('/snapshots', config(token))).data,
  list: async (token: string) => (await client.get<{ items: PlanSummary[] }>('', config(token))).data,
  detail: async (id: string, token: string) => (await client.get<PlanDetail>(`/${encodeURIComponent(id)}`, config(token))).data,
  create: async (request: CreatePlan, token: string) => (await client.post<PlanEvent>('', request, config(token))).data,
  change: async (id: string, request: ChangePlan, token: string) => (await client.post<PlanEvent>(`/${encodeURIComponent(id)}/changes`, request, config(token))).data,
}
