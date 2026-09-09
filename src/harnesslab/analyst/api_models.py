from __future__ import annotations

from typing import Literal

from pydantic import Field

from harnesslab.analyst.models import (
    AnalysisRequest,
    AnalysisScope,
    AttributionReport,
    CompletedToolCall,
    EvidenceEntry,
    FinalizationRejectionCode,
    ProposedRegressionPlan,
    StrictModel,
)
from harnesslab.analyst.real_backend import DecisionUsage
from harnesslab.analyst.sessions import PlanApproval
from harnesslab.budget.models import AnalystSpendLimits, ProviderPricing
from harnesslab.contracts.common import Sha256Digest


class AnalystTotals(StrictModel):
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost_usd: str | None
    latency_ms: int | None


class AnalystSessionView(StrictModel):
    spend_limits: AnalystSpendLimits | None
    session_id: str
    backend: Literal["fake", "real"]
    status: Literal["PAUSED", "RUNNING", "FAILED", "COMPLETED", "ABSTAINED", "LIMIT_REACHED"]
    request: AnalysisRequest
    scope: AnalysisScope
    scope_digest: Sha256Digest
    profile_id: str | None
    profile_digest: Sha256Digest | None
    provider: str | None
    model: str | None
    route: str | None
    decision_iterations: int = Field(ge=0, le=8)
    tool_calls: int = Field(ge=0, le=12)
    decision_limit: int = Field(ge=1, le=8)
    tool_limit: int = Field(ge=1, le=12)
    max_output_tokens_per_request: int | None
    request_timeout_seconds: float | None
    request_count: int | None = Field(ge=0, le=8)
    request_budget_used: int = Field(ge=0, le=8)
    usage: tuple[DecisionUsage, ...]
    totals: AnalystTotals
    evidence: tuple[EvidenceEntry, ...]
    completed_calls: tuple[CompletedToolCall, ...]
    error: str | None
    finalization_rejections: tuple[FinalizationRejectionCode, ...]
    report: AttributionReport | None
    proposed_plan: ProposedRegressionPlan | None
    proposal_digest: Sha256Digest | None
    approval: PlanApproval | None


class AnalystSessionList(StrictModel):
    items: tuple[AnalystSessionView, ...]


class StructuredDecisionContract(StrictModel):
    envelope: Literal["BackendDecision"]
    schema_digest: Sha256Digest
    live_verified: Literal[False]


class AnalystSmokePreflight(StrictModel):
    kind: Literal["REAL_AGENT_SMOKE"]
    session_id: str
    session_digest: Sha256Digest
    preflight_digest: Sha256Digest
    status: Literal["READY", "BLOCKED"]
    reasons: tuple[str, ...]
    profile_id: str | None
    profile_digest: Sha256Digest | None
    frozen_profile_digest: Sha256Digest | None
    provider: str | None
    model: str | None
    route: str | None
    credential_reference_status: Literal["SET", "MISSING"]
    base_url_reference_status: Literal["SET", "MISSING"]
    structured_output_contract: StructuredDecisionContract
    goal: str
    evidence_scope: AnalysisScope
    scope_digest: Sha256Digest
    decision_ceiling: int
    tool_ceiling: int
    spend_limits: AnalystSpendLimits | None
    next_input_bytes: int | None
    input_token_reservation_basis: Literal["KNOWN_REGISTRY_CONTEXT_WINDOW", "UNKNOWN"]
    input_token_upper_bound: int | None
    pricing_basis: ProviderPricing | None
    request_budget_used: int
    observed_totals: AnalystTotals
    server_real_enabled: bool
    per_step_confirmation_required: Literal[True]
    execution_authorized: Literal[False]
