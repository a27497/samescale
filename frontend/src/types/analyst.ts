export interface AnalystSpendLimits {
  provider_requests: number
  output_tokens_per_request: number
  input_bytes_per_request: number
  cumulative_tokens: number
  timeout_seconds: number
  usd: string | null
}
export interface AnalystPreflight {
  status: 'READY' | 'BLOCKED'
  reasons: string[]
  preflight_digest: string
  execution_authorized: false
  [key: string]: unknown
}

export interface RegressionProposal {
  objective: string
  task_ids: string[]
  cell_ids: string[]
  evidence_refs: string[]
  acceptance_criteria: string[]
  repeat_count: number
}

export interface AnalystSession {
  spend_limits: AnalystSpendLimits | null
  session_id: string
  backend: 'fake' | 'real'
  status: 'PAUSED' | 'RUNNING' | 'FAILED' | 'COMPLETED' | 'ABSTAINED' | 'LIMIT_REACHED'
  request: { experiment_id: string; question: string }
  scope: { experiment_id: string; plan_digest: string; task_ids: string[]; cell_ids: string[]; run_ids: string[]; ablation_ids: string[] }
  scope_digest: string
  profile_id: string | null
  provider: string | null
  model: string | null
  route: string | null
  decision_iterations: number
  tool_calls: number
  decision_limit: number
  tool_limit: number
  max_output_tokens_per_request: number | null
  request_timeout_seconds: number | null
  request_count: number | null
  request_budget_used: number
  totals: { input_tokens: number | null; output_tokens: number | null; total_tokens: number | null; cost_usd: string | null; latency_ms: number | null }
  evidence: { ref: { id: string }; digest_bindings: string[]; data_by_tool: Record<string, unknown> }[]
  completed_calls: { key: string; call: { name: string }; status: string; evidence_refs: string[] }[]
  error: string | null
  report: { summary: string; verified_facts: { statement: string; evidence_refs: string[] }[]; hypotheses: { statement: string; additional_evidence_needed: string }[]; limitations: string[] } | null
  proposed_plan: RegressionProposal | null
  proposal_digest: string | null
  approval: { session_id: string; reviewed_by: string; approved_at: string; proposal_digest: string; scope_digest: string; execution_authorized: false } | null
}
