import { apiClient } from '@/api/client'
import type { InvestigationExample, AnalystSession, AnalystSpendLimits, AnalystPreflight, RegressionProposal } from '@/types/analyst'

const path = (id: string) => `/analyst/sessions/${encodeURIComponent(id)}`
export const analystApi = {
  offline: async () => (await apiClient.post<InvestigationExample>('/analyst/examples/offline')).data,
  historical: async () => (await apiClient.get<InvestigationExample>('/analyst/examples/historical')).data,
  list: async (experimentId: string) => (await apiClient.get<{ items: AnalystSession[] }>('/analyst/sessions', { params: { experiment_id: experimentId } })).data,
  get: async (id: string) => (await apiClient.get<AnalystSession>(path(id))).data,
  create: async (body: { experiment_id: string; question: string; backend: 'fake' | 'real'; provider_profile_id: string | null; decision_limit: number; tool_limit: number; spend_limits: AnalystSpendLimits | null }) =>
    (await apiClient.post<AnalystSession>('/analyst/sessions', body)).data,
  preflight: async (id: string) => (await apiClient.get<AnalystPreflight>(`${path(id)}/preflight`)).data,
  resume: async (id: string, confirmReal: boolean) => (await apiClient.post<AnalystSession>(`${path(id)}/resume`, { confirm_real: confirmReal }, { timeout: 700_000 })).data,
  propose: async (id: string, proposal: RegressionProposal) => (await apiClient.put<AnalystSession>(`${path(id)}/proposal`, proposal)).data,
  approve: async (id: string, body: { scope_digest: string; proposal_digest: string; reviewed_by: string }) =>
    (await apiClient.post<AnalystSession>(`${path(id)}/approval`, body)).data,
}
