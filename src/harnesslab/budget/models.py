from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BudgetMode(StrEnum):
    """Evaluation sizes supported by the pre-spend estimator."""

    QUICK = "QUICK"
    INFORMAL = "INFORMAL"
    COMPARE = "COMPARE"
    FORMAL = "FORMAL"

    @property
    def repeat_count(self) -> int:
        return {
            BudgetMode.QUICK: 1,
            BudgetMode.INFORMAL: 3,
            BudgetMode.COMPARE: 3,
            BudgetMode.FORMAL: 5,
        }[self]


class PricingAvailability(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


class AnalystSpendLimits(BaseModel):
    """Explicit immutable limits in the Analyst session's existing journal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_requests: int = Field(ge=1, le=8)
    output_tokens_per_request: int = Field(gt=0)
    input_bytes_per_request: int = Field(gt=0, le=256_000)
    cumulative_tokens: int = Field(gt=0)
    usd: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    timeout_seconds: float = Field(gt=0, le=600)


class BudgetCeilingStatus(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    WITHIN_CEILING = "WITHIN_CEILING"
    EXCEEDS_CEILING = "EXCEEDS_CEILING"
    INDETERMINATE = "INDETERMINATE"


class CallResourceCeiling(BaseModel):
    """Frozen maximum resources consumed by one logical provider-backed call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    provider_requests: int = Field(default=1, ge=1)
    harness_turns: int = Field(default=1, ge=0)


class ExpectedCallUsage(BaseModel):
    """Evidence-backed expected usage per call; decimals permit measured averages."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: Decimal = Field(ge=0, allow_inf_nan=False)
    output_tokens: Decimal = Field(ge=0, allow_inf_nan=False)
    provider_requests: Decimal = Field(default=Decimal(1), ge=0, allow_inf_nan=False)
    harness_turns: Decimal = Field(default=Decimal(1), ge=0, allow_inf_nan=False)


class ProviderPricing(BaseModel):
    """Immutable planning prices for one route, or an explicit unknown marker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    route_identity: str = Field(min_length=1, max_length=500)
    availability: PricingAvailability
    input_usd_per_million_tokens: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_usd_per_million_tokens: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    request_usd: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    evidence_reference: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def availability_matches_rates(self) -> ProviderPricing:
        rates = (
            self.input_usd_per_million_tokens,
            self.output_usd_per_million_tokens,
            self.request_usd,
        )
        if self.availability is PricingAvailability.UNKNOWN:
            if any(rate is not None for rate in rates):
                raise ValueError("UNKNOWN pricing cannot contain rates")
            if self.evidence_reference is not None:
                raise ValueError("UNKNOWN pricing cannot cite price evidence")
        elif any(rate is None for rate in rates):
            raise ValueError("KNOWN pricing requires input, output, and request rates")
        return self


class BudgetEstimateRequest(BaseModel):
    """All inputs needed for a deterministic, keyless pre-spend calculation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: BudgetMode
    task_count: int = Field(ge=1, le=1_000_000)
    subject_cell_count: int = Field(ge=1, le=1_000_000)
    judge_calls_per_subject: int = Field(default=1, ge=0, le=1_000_000)
    subject_ceiling: CallResourceCeiling
    judge_ceiling: CallResourceCeiling
    subject_pricing: ProviderPricing
    judge_pricing: ProviderPricing
    budget_ceiling_usd: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    expected_subject_usage: ExpectedCallUsage | None = None
    expected_judge_usage: ExpectedCallUsage | None = None
    expected_case_justification: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def expected_usage_is_complete_and_bounded(self) -> BudgetEstimateRequest:
        active_expected = [self.expected_subject_usage]
        if self.judge_calls_per_subject:
            active_expected.append(self.expected_judge_usage)
        supplied = [usage is not None for usage in active_expected]
        if any(supplied) and not all(supplied):
            raise ValueError("expected usage must cover every active call type")
        if any(supplied) and self.expected_case_justification is None:
            raise ValueError("expected usage requires a justification")
        if not any(supplied) and self.expected_case_justification is not None:
            raise ValueError("expected-case justification requires expected usage")

        self._require_within_ceiling("subject", self.expected_subject_usage, self.subject_ceiling)
        if self.judge_calls_per_subject:
            self._require_within_ceiling("judge", self.expected_judge_usage, self.judge_ceiling)
        elif self.expected_judge_usage is not None:
            raise ValueError("judge expected usage is invalid when Judge calls are disabled")
        return self

    @staticmethod
    def _require_within_ceiling(
        label: str,
        usage: ExpectedCallUsage | None,
        ceiling: CallResourceCeiling,
    ) -> None:
        if usage is None:
            return
        for field_name in (
            "input_tokens",
            "output_tokens",
            "provider_requests",
            "harness_turns",
        ):
            if getattr(usage, field_name) > getattr(ceiling, field_name):
                raise ValueError(f"expected {label} {field_name} exceeds its ceiling")


class TokenCeilings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_input: int = Field(ge=0)
    subject_output: int = Field(ge=0)
    judge_input: int = Field(ge=0)
    judge_output: int = Field(ge=0)
    total: int = Field(ge=0)

    @model_validator(mode="after")
    def total_matches_components(self) -> TokenCeilings:
        expected = self.subject_input + self.subject_output + self.judge_input + self.judge_output
        if self.total != expected:
            raise ValueError("token ceiling total does not match components")
        return self


class CostProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    availability: PricingAvailability
    amount_usd: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    unknown_route_identities: tuple[str, ...] = ()

    @model_validator(mode="after")
    def availability_matches_amount(self) -> CostProjection:
        if self.unknown_route_identities != tuple(sorted(set(self.unknown_route_identities))):
            raise ValueError("unknown route identities must be unique and sorted")
        if self.availability is PricingAvailability.KNOWN:
            if self.amount_usd is None:
                raise ValueError("KNOWN cost projection requires an amount")
            if self.unknown_route_identities:
                raise ValueError("KNOWN cost projection cannot contain unknown routes")
        else:
            if self.amount_usd is not None:
                raise ValueError("UNKNOWN cost projection cannot contain an amount")
            if not self.unknown_route_identities:
                raise ValueError("UNKNOWN cost projection requires an unknown route")
        return self


class BudgetEstimate(BaseModel):
    """Deterministic aggregate used by preflight before any provider call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    mode: BudgetMode
    repeat_count: Literal[1, 3, 5]
    expected_subject_calls: int = Field(ge=1)
    expected_judge_calls: int = Field(ge=0)
    token_ceiling: TokenCeilings
    provider_request_ceiling: int = Field(ge=1)
    harness_turn_ceiling: int = Field(ge=0)
    estimated_cost_availability: PricingAvailability
    projected_worst_case: CostProjection
    projected_expected_case: CostProjection | None
    expected_case_justification: str | None
    budget_ceiling_usd: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    budget_ceiling_status: BudgetCeilingStatus

    @model_validator(mode="after")
    def projection_metadata_is_coherent(self) -> BudgetEstimate:
        if self.repeat_count != self.mode.repeat_count:
            raise ValueError("repeat count does not match the evaluation mode")
        if self.estimated_cost_availability is not self.projected_worst_case.availability:
            raise ValueError("estimated cost availability must match the worst-case projection")
        if (self.projected_expected_case is None) != (self.expected_case_justification is None):
            raise ValueError("expected projection and justification must be present together")
        if self.budget_ceiling_usd is None:
            if self.budget_ceiling_status is not BudgetCeilingStatus.NOT_CONFIGURED:
                raise ValueError("missing budget ceiling requires NOT_CONFIGURED status")
        elif self.budget_ceiling_status is BudgetCeilingStatus.NOT_CONFIGURED:
            raise ValueError("configured budget ceiling requires an evaluated status")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode()).hexdigest()


class MatrixCellBudget(BaseModel):
    """Heterogeneous frozen budget for one subject cell."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cell_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=100)
    planned_run_count: int = Field(ge=1, le=1_000_000)
    route_identity: str = Field(min_length=1, max_length=500)
    resource_ceiling: CallResourceCeiling
    pricing: ProviderPricing

    @model_validator(mode="after")
    def pricing_matches_route(self) -> MatrixCellBudget:
        if self.pricing.route_identity != self.route_identity:
            raise ValueError("cell pricing route must match the frozen route identity")
        return self


class JudgeCampaignBudget(BaseModel):
    """Fixed Judge campaign, represented separately from subject cells."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=100)
    planned_call_count: int = Field(ge=0, le=1_000_000)
    route_identity: str = Field(min_length=1, max_length=500)
    resource_ceiling: CallResourceCeiling
    pricing: ProviderPricing

    @model_validator(mode="after")
    def pricing_matches_route(self) -> JudgeCampaignBudget:
        if self.pricing.route_identity != self.route_identity:
            raise ValueError("Judge pricing route must match the frozen route identity")
        return self


class MatrixBudgetEstimateRequest(BaseModel):
    """Additive heterogeneous Matrix budget; legacy requests remain unchanged."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    subject_cells: tuple[MatrixCellBudget, ...] = Field(min_length=1)
    judge_campaign: JudgeCampaignBudget
    budget_ceiling_usd: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def cells_are_unique(self) -> MatrixBudgetEstimateRequest:
        identities = [cell.cell_id for cell in self.subject_cells]
        if len(set(identities)) != len(identities):
            raise ValueError("Matrix subject cell IDs must be unique")
        return self


class MatrixBudgetComponent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    component_id: str = Field(min_length=1, max_length=100)
    kind: Literal["SUBJECT", "JUDGE"]
    call_count: int = Field(ge=0)
    route_identity: str = Field(min_length=1, max_length=500)
    input_token_ceiling: int = Field(ge=0)
    output_token_ceiling: int = Field(ge=0)
    provider_request_ceiling: int = Field(ge=0)
    harness_turn_ceiling: int = Field(ge=0)
    projected_worst_case: CostProjection


class MatrixBudgetEstimate(BaseModel):
    """Deterministic aggregate retaining every heterogeneous component."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    expected_subject_calls: int = Field(ge=1)
    expected_judge_calls: int = Field(ge=0)
    components: tuple[MatrixBudgetComponent, ...] = Field(min_length=2)
    token_ceiling: TokenCeilings
    provider_request_ceiling: int = Field(ge=1)
    harness_turn_ceiling: int = Field(ge=0)
    estimated_cost_availability: PricingAvailability
    projected_worst_case: CostProjection
    budget_ceiling_usd: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    budget_ceiling_status: BudgetCeilingStatus

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode()).hexdigest()
