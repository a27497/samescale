from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import Field, ValidationError

from harnesslab.analyst.backend import ANALYST_SYSTEM_CONTRACT
from harnesslab.analyst.models import (
    AnalysisRequest,
    AnalysisScope,
    BackendDecision,
    CompletedToolCall,
    EvidenceEntry,
    FactAssertion,
    FinalizationRejectionCode,
    StrictModel,
    ToolName,
    safe_public_text,
)
from harnesslab.budget.estimator import _call_cost
from harnesslab.budget.models import (
    AnalystSpendLimits,
    CallResourceCeiling,
    ExpectedCallUsage,
    PricingAvailability,
    ProviderPricing,
)
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Sha256Digest
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.model_lane.models import (
    ProviderAdapter,
    ProviderFailureCategory,
    ProviderIncompleteReason,
    ProviderInvocationError,
    ProviderJSONSchema,
    ProviderReadTimeoutStage,
    ProviderRequest,
    ProviderTimeoutPhase,
    ProviderUsage,
)
from harnesslab.model_lane.providers import adapter_for_profile
from harnesslab.registry.models import RegistryCatalog
from harnesslab.registry.service import _direct_runtime_source


class DecisionEnvelope(StrictModel):
    decision: BackendDecision


def decision_json_schema() -> dict[str, object]:
    """Provider-compatible strict subset: factual assertions select scalar leaf values."""
    schema = DecisionEnvelope.model_json_schema()
    schema["$defs"]["JsonValue"] = {"type": ["string", "number", "boolean", "null"]}

    def strict(node: object) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            node.pop("discriminator", None)
            if "oneOf" in node:
                node["anyOf"] = node.pop("oneOf")
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for value in node.values():
                strict(value)
        elif isinstance(node, list):
            for value in node:
                strict(value)

    strict(schema)
    return schema


def valid_fact_assertions(
    evidence: tuple[EvidenceEntry, ...], *, limit: int = 128
) -> tuple[FactAssertion, ...]:
    """Return a bounded deterministic catalog of exact scalar evidence assertions."""

    assertions: list[FactAssertion] = []

    def visit(
        *, evidence_ref: str, tool: ToolName, value: object, path: tuple[str | int, ...]
    ) -> None:
        if len(assertions) >= limit or len(path) > 16:
            return
        if value is None or isinstance(value, str | int | float | bool):
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
            if len(encoded.encode("utf-8")) > 512:
                return
            assertions.append(
                FactAssertion(
                    evidence_ref=evidence_ref,
                    tool=tool,
                    field_path=path,
                    expected_value=value,
                )
            )
            return
        if isinstance(value, dict):
            for key in sorted(value):
                if len(assertions) >= limit:
                    return
                visit(
                    evidence_ref=evidence_ref,
                    tool=tool,
                    value=value[key],
                    path=(*path, key),
                )
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                if len(assertions) >= limit:
                    return
                visit(
                    evidence_ref=evidence_ref,
                    tool=tool,
                    value=item,
                    path=(*path, index),
                )

    for entry in sorted(evidence, key=lambda item: item.ref.id):
        for tool in sorted(entry.tools, key=lambda item: item.value):
            data = entry.data_by_tool.get(tool.value)
            if data is not None:
                visit(evidence_ref=entry.ref.id, tool=tool, value=data, path=())
            if len(assertions) >= limit:
                break
        if len(assertions) >= limit:
            break
    return tuple(assertions)


class FailureResponseStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    IN_PROGRESS = "in_progress"
    QUEUED = "queued"
    CANCELLED = "cancelled"


class DecisionFailure(StrictModel):
    """Allowlisted facts only; IDs are fingerprinted, never copied from headers/body."""

    category: ProviderFailureCategory
    status_code: int | None = Field(default=None, ge=100, le=599)
    request_id_sha256: Sha256Digest | None = None
    response_status: FailureResponseStatus | None = None
    timeout_phase: ProviderTimeoutPhase | None = None
    read_timeout_stage: ProviderReadTimeoutStage | None = None
    incomplete_reason: ProviderIncompleteReason | None = None


def decision_failure(exc: Exception) -> DecisionFailure:
    # Do not serialize exceptions, their chains, messages, headers or response bodies.
    if isinstance(exc, ProviderInvocationError):
        category = (
            exc.category
            if isinstance(exc.category, ProviderFailureCategory)
            else ProviderFailureCategory.PROVIDER_ERROR
        )
        request_id = exc.request_id
        fingerprint = None
        if isinstance(request_id, str) and 0 < len(request_id) <= 300:
            fingerprint = (
                "sha256:" + hashlib.sha256(request_id.encode("utf-8", errors="replace")).hexdigest()
            )
        status = (
            FailureResponseStatus(exc.response_status)
            if isinstance(exc.response_status, str) and exc.response_status in FailureResponseStatus
            else None
        )
        return DecisionFailure(
            category=category,
            status_code=exc.status_code
            if type(exc.status_code) is int and 100 <= exc.status_code <= 599
            else None,
            request_id_sha256=fingerprint,
            response_status=status,
            timeout_phase=exc.timeout_phase
            if category is ProviderFailureCategory.TIMEOUT
            and isinstance(exc.timeout_phase, ProviderTimeoutPhase)
            else None,
            read_timeout_stage=exc.read_timeout_stage
            if category is ProviderFailureCategory.TIMEOUT
            and exc.timeout_phase is ProviderTimeoutPhase.READ
            and isinstance(exc.read_timeout_stage, ProviderReadTimeoutStage)
            else None,
            incomplete_reason=exc.incomplete_reason
            if category is ProviderFailureCategory.INCOMPLETE_RESPONSE
            and isinstance(exc.incomplete_reason, ProviderIncompleteReason)
            else None,
        )
    if isinstance(exc, TimeoutError):
        return DecisionFailure(
            category=ProviderFailureCategory.TIMEOUT, timeout_phase=ProviderTimeoutPhase.UNKNOWN
        )
    return DecisionFailure(
        category=ProviderFailureCategory.MALFORMED_RESPONSE
        if isinstance(exc, ValidationError)
        else ProviderFailureCategory.PROVIDER_ERROR
    )


class DecisionUsage(StrictModel):
    iteration: int = Field(ge=1, le=8)
    status: str = "RESERVED"
    invocation_started: bool | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    tokens: ProviderUsage = Field(default_factory=ProviderUsage)
    cost_usd: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    observed_model: str | None = None
    input_bytes: int | None = None
    reserved_resources: CallResourceCeiling | None = None
    reserved_cost_usd: Decimal | None = None
    failure: DecisionFailure | None = None


class AnalystProfile(StrictModel):
    profile_id: str
    profile_digest: str
    runtime: ModelProfile
    pricing: ProviderPricing | None = None
    context_window_tokens: int | None = Field(default=None, gt=0)

    @property
    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


def resolve_analyst_profile(
    catalog: RegistryCatalog, profile_id: str, root: Path
) -> AnalystProfile:
    profile = next((p for p in catalog.provider_model_profiles if p.profile_id == profile_id), None)
    if profile is None:
        raise ValueError("Analyst requires a registered provider/model profile")
    provider = next(p for p in catalog.providers if p.provider_id == profile.provider_id)
    if not all(
        (provider.enabled, provider.automation_allowed, profile.enabled, profile.automation_allowed)
    ):
        raise ValueError("Analyst provider/model profile is disabled or disallows automation")
    source = _direct_runtime_source(provider, profile)
    runtime = ModelProfile(
        **source.model_dump(exclude={"reasoning_effort"}),
        reasoning=ReasoningProfile(
            effort=profile.reasoning_effort, max_output_tokens=profile.max_output_tokens
        ),
    )
    pricing = None
    if profile.pricing_snapshot_reference:
        path = (root / profile.pricing_snapshot_reference).resolve()
        if path.is_relative_to(root.resolve()) and path.is_file():
            try:
                candidate = ProviderPricing.model_validate_json(path.read_bytes())
                if candidate.route_identity == profile.provider_route_identity:
                    pricing = candidate
            except (ValidationError, OSError):
                pass  # Historical non-price snapshots do not establish a dollar rate.
    model = next(m for m in catalog.models if m.model_id == profile.model_id)
    return AnalystProfile(
        profile_id=profile.profile_id,
        profile_digest=profile.profile_identity,
        runtime=runtime,
        pricing=pricing,
        context_window_tokens=model.context_window_tokens
        if model.context_metadata_status == "KNOWN"
        else None,
    )


def request_input_bytes(request: ProviderRequest) -> int:
    # Exact UTF-8 of the host-controlled input envelope, including instructions and schema.
    # This is a byte ceiling, never a tokenizer or billable-token estimate.
    return len(
        json.dumps(
            {
                "instructions": request.instructions,
                "input": request.input,
                "output_json_schema": request.output_json_schema.value
                if request.output_json_schema
                else None,
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def known_pricing(profile: AnalystProfile) -> bool:
    return (
        profile.pricing is not None
        and profile.pricing.availability is PricingAvailability.KNOWN
        and profile.pricing.route_identity == profile.runtime.provider_route_identity
    )


def spend_reasons(
    profile: AnalystProfile,
    budget: AnalystSpendLimits | None,
    usage: tuple[DecisionUsage, ...],
    request: ProviderRequest,
) -> tuple[str, ...]:
    if budget is None:
        return ("SPEND_LIMITS_MISSING",)
    reasons: list[str] = []
    if len(usage) >= budget.provider_requests:
        reasons.append("REQUEST_CEILING_REACHED")
    if budget.output_tokens_per_request > (profile.runtime.reasoning.max_output_tokens or 0):
        reasons.append("OUTPUT_CEILING_EXCEEDS_PROFILE")
    if budget.timeout_seconds > profile.runtime.request_timeout_seconds:
        reasons.append("TIMEOUT_CEILING_EXCEEDS_PROFILE")
    if request_input_bytes(request) > budget.input_bytes_per_request:
        reasons.append("INPUT_BYTE_CEILING_EXCEEDED")
    if any(
        item.input_bytes is not None and item.input_bytes >= budget.input_bytes_per_request
        for item in usage
    ):
        reasons.append("INPUT_BYTE_CEILING_REACHED")
    if any(
        item.tokens.output_tokens is not None
        and item.tokens.output_tokens >= budget.output_tokens_per_request
        for item in usage
    ):
        reasons.append("OUTPUT_TOKEN_CEILING_REACHED")
    if any(
        item.latency_ms is not None and item.latency_ms >= budget.timeout_seconds * 1000
        for item in usage
    ):
        reasons.append("TIMEOUT_CEILING_REACHED")
    context = profile.context_window_tokens
    if context is None:
        reasons.append("INPUT_TOKEN_BOUND_UNKNOWN")
    totals = [item.tokens.total_tokens for item in usage]
    if any(
        item.tokens.input_tokens is None
        or item.tokens.output_tokens is None
        or item.tokens.total_tokens is None
        or item.tokens.total_tokens != item.tokens.input_tokens + item.tokens.output_tokens
        for item in usage
    ):
        reasons.append("TOKEN_USAGE_UNKNOWN_OR_INCONSISTENT")
    elif (
        context is not None
        and sum(t for t in totals if t is not None) + context + budget.output_tokens_per_request
        > budget.cumulative_tokens
    ):
        reasons.append("TOKEN_CEILING_INSUFFICIENT_FOR_NEXT_REQUEST")
    if any(
        item.reserved_resources is not None
        and (
            (
                item.tokens.input_tokens is not None
                and item.tokens.input_tokens > item.reserved_resources.input_tokens
            )
            or (
                item.tokens.output_tokens is not None
                and item.tokens.output_tokens > item.reserved_resources.output_tokens
            )
        )
        for item in usage
    ):
        reasons.append("OBSERVED_PROVIDER_BOUND_VIOLATION")
    if budget.usd is not None:
        if not known_pricing(profile):
            reasons.append("USD_PRICING_UNKNOWN_OR_ROUTE_MISMATCH")
        elif any(item.cost_usd is None for item in usage):
            reasons.append("COST_USAGE_UNKNOWN")
        elif context is not None:
            assert profile.pricing is not None
            next_cost = _call_cost(
                1,
                CallResourceCeiling(
                    input_tokens=context, output_tokens=budget.output_tokens_per_request
                ),
                profile.pricing,
            )
            if (
                sum((item.cost_usd for item in usage if item.cost_usd is not None), Decimal(0))
                + next_cost
                > budget.usd
            ):
                reasons.append("USD_CEILING_INSUFFICIENT_FOR_NEXT_REQUEST")
    return tuple(reasons)


class RealAnalystBackend:
    """One ProviderAdapter invocation per decision, no retries or Fake fallback."""

    def __init__(
        self,
        profile: AnalystProfile,
        *,
        environment: Mapping[str, str],
        adapter: ProviderAdapter | None = None,
        completed_calls: tuple[CompletedToolCall, ...] = (),
        decision_limit: int = 8,
        budget: AnalystSpendLimits | None = None,
        previous_usage: tuple[DecisionUsage, ...] = (),
        reserve: Callable[[DecisionUsage], Awaitable[None]] | None = None,
    ) -> None:
        self.profile = profile
        self.environment = environment
        self.adapter = adapter
        self.completed_calls = completed_calls
        self.decision_limit = decision_limit
        self.last_usage: DecisionUsage | None = None
        self.budget = budget
        self.previous_usage = previous_usage
        self.reserve = reserve

    def prepare(
        self,
        *,
        request: AnalysisRequest,
        scope: AnalysisScope,
        evidence: tuple[EvidenceEntry, ...],
        iteration: int,
        remaining_tool_calls: int,
        finalization_rejections: tuple[FinalizationRejectionCode, ...] = (),
    ) -> ProviderRequest:
        if self.budget is None:
            raise ValueError("SPEND_LIMITS_MISSING")
        schema = decision_json_schema()
        payload = json.dumps(
            {
                "goal": request.question,
                "scope": scope.model_dump(mode="json"),
                "evidence": [entry.model_dump(mode="json") for entry in evidence],
                "completed_calls": [call.model_dump(mode="json") for call in self.completed_calls],
                "iteration": iteration,
                "remaining_decisions": max(0, self.decision_limit - iteration),
                "remaining_tool_calls": remaining_tool_calls,
                "finalization_rejections": [item.value for item in finalization_rejections],
                "valid_fact_assertions": [
                    item.model_dump(mode="json") for item in valid_fact_assertions(evidence)
                ],
                "valid_proposal_scope": {
                    "task_ids": list(scope.task_ids),
                    "cell_ids": list(scope.cell_ids),
                    "evidence_refs": [entry.ref.id for entry in evidence],
                },
                "output_contract": schema,
            },
            ensure_ascii=False,
            allow_nan=False,
        )
        invocation = ProviderRequest(
            profile=self.profile.runtime.model_copy(
                update={
                    "reasoning": self.profile.runtime.reasoning.model_copy(
                        update={"max_output_tokens": self.budget.output_tokens_per_request}
                    ),
                    "request_timeout_seconds": self.budget.timeout_seconds,
                }
            ),
            instructions=ANALYST_SYSTEM_CONTRACT
            + (
                " Return only a JSON object with one decision property conforming exactly to "
                "the supplied schema. Select tools dynamically from observed evidence. "
                "Abstain when evidence is insufficient. Do not repeat completed calls. "
                "For facts, select scalar leaf values with field_path. "
                "A proposed regression plan is review-only and never execution authorization. "
                "finalization_rejections are trusted host validation codes from earlier final "
                "drafts; "
                "correct them without weakening citations or inventing evidence. "
                "For VERIFIED_FACT claims, copy assertion objects exactly from "
                "valid_fact_assertions; "
                "never invent an evidence_ref, field_path, tool, or expected_value. "
                "If proposing a regression plan, use only subsets from valid_proposal_scope."
            ),
            input=payload,
            output_json_schema=ProviderJSONSchema(value=schema),
        )
        return invocation

    async def decide(
        self,
        *,
        request: AnalysisRequest,
        scope: AnalysisScope,
        evidence: tuple[EvidenceEntry, ...],
        iteration: int,
        remaining_tool_calls: int,
        finalization_rejections: tuple[FinalizationRejectionCode, ...] = (),
    ) -> BackendDecision:
        self.last_usage = DecisionUsage(
            iteration=iteration, status="STARTED", invocation_started=False
        )
        started = time.monotonic()
        try:
            invocation = self.prepare(
                request=request,
                scope=scope,
                evidence=evidence,
                iteration=iteration,
                remaining_tool_calls=remaining_tool_calls,
                finalization_rejections=finalization_rejections,
            )
            reasons = spend_reasons(self.profile, self.budget, self.previous_usage, invocation)
            if reasons or self.reserve is None:
                raise ValueError("SPEND_PREFLIGHT_BLOCKED")
            if any(item.iteration >= iteration for item in self.previous_usage):
                raise ValueError("decision reservation cannot be reused")
            assert self.budget is not None and self.profile.context_window_tokens is not None
            resources = CallResourceCeiling(
                input_tokens=self.profile.context_window_tokens,
                output_tokens=self.budget.output_tokens_per_request,
                harness_turns=0,
            )
            self.last_usage = self.last_usage.model_copy(
                update={
                    "status": "RESERVED",
                    "invocation_started": None,
                    "input_bytes": request_input_bytes(invocation),
                    "reserved_resources": resources,
                    "reserved_cost_usd": _call_cost(1, resources, self.profile.pricing)
                    if known_pricing(self.profile) and self.profile.pricing is not None
                    else None,
                }
            )
            await self.reserve(
                self.last_usage
            )  # Must commit successfully before adapter invocation.
            self.previous_usage = (*self.previous_usage, self.last_usage)
            adapter = self.adapter or adapter_for_profile(invocation, environment=self.environment)
            self.last_usage = self.last_usage.model_copy(update={"invocation_started": True})
            result = await asyncio.wait_for(
                adapter.invoke(invocation), invocation.profile.request_timeout_seconds
            )
            cost = None
            pricing = self.profile.pricing
            if (
                pricing is not None
                and known_pricing(self.profile)
                and result.usage.input_tokens is not None
                and result.usage.output_tokens is not None
            ):
                assert pricing.input_usd_per_million_tokens is not None
                assert (
                    pricing.output_usd_per_million_tokens is not None
                    and pricing.request_usd is not None
                )
                cost = _call_cost(
                    1,
                    ExpectedCallUsage(
                        input_tokens=Decimal(result.usage.input_tokens),
                        output_tokens=Decimal(result.usage.output_tokens),
                    ),
                    pricing,
                )
            credential = self.environment.get(self.profile.runtime.credential_reference or "")
            leaked_credential = (
                credential is not None
                and credential != ""
                and (
                    credential in result.public_output_text
                    or credential in (result.observed_model or "")
                )
            )
            self.last_usage = DecisionUsage(
                iteration=iteration,
                input_bytes=self.last_usage.input_bytes,
                reserved_resources=self.last_usage.reserved_resources,
                reserved_cost_usd=self.last_usage.reserved_cost_usd,
                status="RECEIVED",
                invocation_started=True,
                latency_ms=result.latency_ms,
                tokens=result.usage,
                cost_usd=cost,
                observed_model=safe_public_text(result.observed_model, limit=200)
                if result.observed_model and not leaked_credential
                else None,
            )
            if leaked_credential:
                raise ValueError("provider response echoed a credential")
            if result.incomplete_reason is not None:
                raise ProviderInvocationError(
                    ProviderFailureCategory.INCOMPLETE_RESPONSE,
                    "provider returned an incomplete Analyst decision",
                    request_id=result.request_id,
                    response_status=result.response_status,
                    incomplete_reason=result.incomplete_reason,
                    latency_ms=result.latency_ms,
                )
            if result.refused:
                raise ProviderInvocationError(
                    ProviderFailureCategory.PROVIDER_ERROR,
                    "provider refused the Analyst decision",
                    request_id=result.request_id,
                    response_status=result.response_status,
                    latency_ms=result.latency_ms,
                )
            if (
                result.provider != self.profile.runtime.provider
                or result.requested_model != self.profile.runtime.requested_model
                or result.protocol != self.profile.runtime.protocol
                or result.endpoint_identity != self.profile.runtime.provider_route_identity
            ):
                raise ValueError("provider result does not match the frozen Analyst profile")
            decision = DecisionEnvelope.model_validate_json(
                result.public_output_text, strict=True
            ).decision
            self.last_usage = self.last_usage.model_copy(update={"status": "COMPLETED"})
            return decision
        except Exception as exc:
            assert self.last_usage is not None
            self.last_usage = self.last_usage.model_copy(
                update={
                    "status": "FAILED",
                    "failure": decision_failure(exc),
                    "latency_ms": self.last_usage.latency_ms
                    if self.last_usage.latency_ms is not None
                    else int((time.monotonic() - started) * 1000),
                }
            )
            raise
        finally:
            if self.last_usage is not None:
                self.previous_usage = tuple(
                    self.last_usage if item.iteration == iteration else item
                    for item in self.previous_usage
                )
