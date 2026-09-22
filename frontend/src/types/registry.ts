export type ProviderHealthStatus = 'AVAILABLE' | 'UNAVAILABLE' | 'QUOTA_EXHAUSTED' | 'UNKNOWN'
export type CompatibilityStatus = 'SUPPORTED' | 'UNSUPPORTED' | 'PARTIALLY_SUPPORTED'
export type EvaluationMode = 'QUICK' | 'INFORMAL' | 'FORMAL_EXHAUSTIVE'
export type ComparisonType =
  | 'END_TO_END_SYSTEM_COMPARISON'
  | 'MODEL_COMPARISON'
  | 'HARNESS_UPLIFT'
  | 'CONTROLLED_ABLATION'

export interface ProviderDefinition {
  provider_id: string
  display_name: string
  provider_family: string
  region: string
  protocols: string[]
  endpoint_class: string
  base_url_reference: string | null
  credential_ref: string
  billing_mode: string
  automation_allowed: boolean
  enabled: boolean
  health_status: ProviderHealthStatus
  capabilities: string[]
  pricing_snapshot_reference: string | null
  runtime_endpoint_fingerprint: string | null
  configuration_reason_codes: string[]
}

export interface ProviderModelProfile {
  purpose?: 'SUBJECT' | 'ANALYST' | 'JUDGE'
  temperature?: number | null
  max_output_tokens_limit?: number | null
  profile_id: string
  model_id: string
  provider_id: string
  requested_model: string
  protocol: string
  route: string
  provider_route_identity: string
  credential_ref: string
  reasoning_effort: string | null
  max_output_tokens: number
  request_timeout_seconds: number
  observed_model_capability: string
  automation_allowed: boolean
  enabled: boolean
  pricing_snapshot_reference: string | null
  runtime_endpoint_fingerprint: string | null
  profile_identity: string
}

export interface ModelDefinition {
  model_id: string
  display_name: string
  model_family: string
  capabilities: string[]
  context_window_tokens: number | null
  context_metadata_status: string
  reasoning_controls: { effort: boolean; temperature: boolean; thinking_toggle: boolean }
  supported_protocols: string[]
}

export interface HarnessProfile {
  enabled?: boolean
  profile_id: string
  profile_reference: string
  supported_provider_profile_ids: string[]
  reasoning_effort: string | null
  harness_config_identity: string
}

export interface HarnessDefinition {
  harness_id: string
  display_name: string
  version: string
  image_reference: string
  image_digest: string | null
  cli_runtime_identity: string
  profiles: HarnessProfile[]
  supported_protocols: string[]
  tool_surface: string[]
  trace_coverage: string
  observed_model_exposure: string
  network_capability: string
  mcp_capability: boolean
  workspace_mutation: boolean
  native_tools: boolean
  runtime_health: ProviderHealthStatus
  runner_contract: string
}

export interface CapabilityAssessment {
  provider_profile_id: string
  harness_profile_id: string
  status: CompatibilityStatus
  reason_codes: string[]
  protocol_compatible: boolean
  model_provider_compatible: boolean
  observed_model: string
  trace_coverage: string
  native_tools: boolean
  workspace_mutation: boolean
  network_requirement: string
  reasoning_control_supported: boolean
  harness_uplift_eligible: boolean
  judge_eligible: boolean
}

export interface TaskRegistryItem {
  task_id: string
  task_version: string
  task_digest: string
  package_path: string
  tier: 'TIER_A_MICRO_CONTRACT'
}

export interface RegistrySettings {
  defaults: {
    default_provider_profile_id: string
    default_evaluation_mode: EvaluationMode
    default_schedule_seed: number
    default_concurrency: number
    default_cost_budget: number | null
  }
  credentials: { credential_ref: string; status: 'SET' | 'MISSING' }[]
  provider_enabled: Record<string, boolean>
  secret_editing_supported: false
}

export interface MethodologyRegistryItem {
  methodology_id: string
  methodology_digest: string
  active: boolean
  evaluation_modes: EvaluationMode[]
  repeat_counts: Record<EvaluationMode, 1 | 3 | 5>
  scheduling_policy: 'BLOCKED_INTERLEAVED_SCHEDULING'
}

export interface BudgetDimension {
  status: 'ENFORCED' | 'OBSERVED_ONLY' | 'NOT_AVAILABLE'
  value: number | null
  unit: string
  scopes?: ('PER_PROVIDER_REQUEST' | 'PER_LOGICAL_RUN' | 'PER_MODEL_TURN' | 'OBSERVED_ONLY' | 'NOT_AVAILABLE')[]
}

export interface BudgetContract {
  max_wall_time: BudgetDimension
  max_output_tokens: BudgetDimension
  max_model_turns: BudgetDimension
  max_tool_calls: BudgetDimension
  max_provider_requests: BudgetDimension
  max_cost: BudgetDimension
}

export interface ExperimentBuilderRequest {
  name: string
  methodology_id: string
  methodology_digest: string
  evaluation_mode: EvaluationMode
  comparison_type: ComparisonType
  task_ids: string[]
  cells: {
    cell_id: string
    provider_model_profile_id: string
    harness_profile_id: string
  }[]
  budget: BudgetContract
  schedule_seed: number
  max_parallel_runs: number
  billing_modes: Record<string, string>
}

export interface ExperimentPreflight {
  status: 'READY' | 'READY_WITH_WARNINGS' | 'BLOCKED'
  checks: { key: string; status: 'PASS' | 'WARNING' | 'BLOCKED'; reason_code: string; detail: string }[]
  estimated_logical_slots: number
  estimated_maximum_wall_time_seconds: number | null
  evaluation_mode: EvaluationMode
  repeat_count: 1 | 3 | 5
  max_parallel_runs: number
  cost_estimate: { status: 'PLANNING_ONLY' | 'NOT_AVAILABLE'; value: number | null; currency: 'USD'; evidence_reference: string | null }
  schedule_preview: { block_identity: string; task_id: string; repeat_index: number; cell_execution_order: string[]; provider_status: string }[]
  candidate_experiment_id: string | null
  candidate_plan_digest: string | null
}

export interface ExperimentSnapshotSummary {
  snapshot_id: string
  snapshot_digest: string
  name: string
  created_at: string
}

export interface ExperimentSnapshot {
  snapshot_id: string
  snapshot_digest: string
  plan: { name: string; evaluation_mode: EvaluationMode; [key: string]: unknown }
  methodology_id: string
  methodology_digest: string
  comparison_type: ComparisonType
  provider_selections: {
    cell_id: string
    provider_profile_id: string
    provider_profile_identity: string
    harness_profile_id: string
    effective_runtime_profile_identity?: string | null
    resource_envelope_identity?: string | null
  }[]
  preflight: ExperimentPreflight
}
