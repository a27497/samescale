import axios from 'axios'

export interface ApprovedEvidenceSource {
  source_id: string; format: string; source_kind: 'historical' | 'synthetic' | 'unverified'
  digest: string; workspace_digest: string; task_reference: string | null; task_digest: string | null
}
export interface EvidenceDetail {
  identity: string
  record: {
    source: ApprovedEvidenceSource; episode_identity: string | null; original_acceptance: string
    workspace_digest: string; workspace_files: Record<string, string>
    completeness: { status: string; coverage: string; missing_fields: string[]; integrity: string; origin: string }
    trace: { ordinal: number; type: string; status: string; exit_code: number | null; file_paths: string[]; agent_report: string | null }[]
  }
  diagnosis: {
    original_episode_acceptance: string; workspace_acceptance: string
    independent_verification: { checks: number; passed_checks: number; reason?: string }
    agent_self_reports: number[]; observed_failed_tools: number[]
    file_changes: { status: string; paths: string[] }
    infrastructure: { status: string; root_cause: null }; limits: string[]
  }
}
export interface EvidenceSummary { identity: string; source_id: string; source_kind: string; acceptance: string }
const client = axios.create({ baseURL: '/api/external-evidence', timeout: 30000 })
const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } })
export const externalEvidenceApi = {
  sources: async (token: string) => (await client.get<{ items: ApprovedEvidenceSource[] }>('/sources', auth(token))).data,
  records: async (token: string) => (await client.get<{ items: EvidenceSummary[] }>('/records', auth(token))).data,
  ingest: async (source_id: string, token: string) => (await client.post<EvidenceDetail>('/records', { source_id, consent: 'IMPORT_APPROVED_SAVED_EVIDENCE' }, auth(token))).data,
  detail: async (identity: string, token: string) => (await client.get<EvidenceDetail>(`/records/${encodeURIComponent(identity)}`, auth(token))).data,
  export: async (identity: string, token: string) => {
    const result = await client.get<Blob>(`/records/${encodeURIComponent(identity)}/export`, { ...auth(token), responseType: 'blob' })
    return { blob: result.data, digest: String(result.headers['x-evidence-sha256'] ?? '') }
  },
}
