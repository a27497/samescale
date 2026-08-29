from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Protocol, Sha256Digest
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.experiment.methodology import (
    BudgetContract,
    BudgetDimensionStatus,
    BudgetScope,
)
from harnesslab.model_lane.profiles import (
    effective_model_profile_identity,
    model_profile_control_identity,
)


class DirectRuntimeContractError(ValueError):
    """A frozen Direct runtime source or resource envelope is not executable."""


class DirectRuntimeProfileSource(BaseModel):
    """Secret-free provider facts required to resolve one Direct runtime profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(min_length=1, max_length=100)
    requested_model: str = Field(min_length=1, max_length=200)
    protocol: Protocol
    route: str = Field(min_length=1, max_length=300)
    base_url: str | None = Field(
        default=None, min_length=1, max_length=500, exclude_if=lambda value: value is None
    )
    base_url_reference: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]*$",
        exclude_if=lambda value: value is None,
    )
    credential_reference: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    reasoning_effort: str | None = Field(default=None, max_length=50)
    request_timeout_seconds: int = Field(gt=0, le=600)

    @model_validator(mode="after")
    def exactly_one_base_url_source(self) -> DirectRuntimeProfileSource:
        if (self.base_url is None) == (self.base_url_reference is None):
            raise ValueError("exactly one Direct runtime base URL source is required")
        return self


class DirectResourceEnvelope(BaseModel):
    """The executable Direct limits not fully represented by BudgetContract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    budget_contract: BudgetContract
    provider_request_timeout_seconds: int = Field(gt=0, le=600)

    @property
    def identity(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class ResolvedDirectRuntimeProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    profile: ModelProfile
    profile_control_identity: Sha256Digest
    effective_profile_identity: Sha256Digest
    resource_envelope: DirectResourceEnvelope
    resource_envelope_identity: Sha256Digest


def direct_harness_control_identity() -> str:
    """Identify the Direct runner contract without provider/model contamination."""

    return canonical_digest(
        {
            "runner_contract": "direct-model-v1",
            "execution_implementation": "harnesslab-direct-runner-v1",
            "prompt_scaffold": "direct-patch-v1",
            "evidence_schema": "evidence-schema-1",
            "provider_requests_per_logical_run": 1,
            "model_turns_per_logical_run": 1,
            "tool_calls_per_logical_run": 0,
        }
    )


def _require_direct_budget(budget: BudgetContract) -> int:
    expected = (
        (
            budget.max_wall_time,
            (BudgetScope.PER_LOGICAL_RUN,),
            "max_wall_time",
        ),
        (
            budget.max_output_tokens,
            (BudgetScope.PER_PROVIDER_REQUEST, BudgetScope.PER_LOGICAL_RUN),
            "max_output_tokens",
        ),
        (
            budget.max_model_turns,
            (BudgetScope.PER_LOGICAL_RUN,),
            "max_model_turns",
        ),
        (
            budget.max_tool_calls,
            (BudgetScope.PER_LOGICAL_RUN,),
            "max_tool_calls",
        ),
        (
            budget.max_provider_requests,
            (BudgetScope.PER_LOGICAL_RUN,),
            "max_provider_requests",
        ),
    )
    for dimension, scopes, name in expected:
        if dimension.status is not BudgetDimensionStatus.ENFORCED or dimension.scopes != scopes:
            raise DirectRuntimeContractError(f"Direct {name} must use its enforced scope")
    if budget.max_model_turns.value != 1:
        raise DirectRuntimeContractError("Direct runtime requires exactly one model turn")
    if budget.max_provider_requests.value != 1:
        raise DirectRuntimeContractError("Direct runtime requires exactly one provider request")
    if budget.max_tool_calls.value != 0:
        raise DirectRuntimeContractError("Direct runtime requires zero tool calls")
    value = budget.max_output_tokens.value
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DirectRuntimeContractError("Direct max_output_tokens must be a positive integer")
    return value


def resolve_direct_runtime_profile(
    source: DirectRuntimeProfileSource,
    budget: BudgetContract,
) -> ResolvedDirectRuntimeProfile:
    """Canonical planner/loader/preflight/runtime resolution for Direct M-Lane."""

    max_output_tokens = _require_direct_budget(budget)
    profile = ModelProfile(
        requested_model=source.requested_model,
        provider=source.provider,
        base_url=source.base_url,
        base_url_reference=source.base_url_reference,
        route=source.route,
        protocol=source.protocol,
        reasoning=ReasoningProfile(
            effort=source.reasoning_effort,
            max_output_tokens=max_output_tokens,
        ),
        request_timeout_seconds=source.request_timeout_seconds,
        credential_reference=source.credential_reference,
    )
    envelope = DirectResourceEnvelope(
        budget_contract=budget,
        provider_request_timeout_seconds=source.request_timeout_seconds,
    )
    return ResolvedDirectRuntimeProfile(
        profile=profile,
        profile_control_identity=model_profile_control_identity(profile),
        effective_profile_identity=effective_model_profile_identity(profile),
        resource_envelope=envelope,
        resource_envelope_identity=envelope.identity,
    )
