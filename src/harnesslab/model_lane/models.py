from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Literal
from typing import Protocol as TypingProtocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harnesslab.contracts.common import Identifier, Protocol, Sha256Digest
from harnesslab.contracts.model import ModelProfile
from harnesslab.contracts.task import ResourceBudget
from harnesslab.sandbox.models import SandboxArtifactManifest, SandboxStatus

MAX_PUBLIC_OUTPUT_BYTES = 1_100_000


class ProviderFailureCategory(StrEnum):
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    PROVIDER_ERROR = "provider_error"
    MALFORMED_RESPONSE = "malformed_response"
    INCOMPLETE_RESPONSE = "incomplete_response"


class ProviderTimeoutPhase(StrEnum):
    CONNECT = "connect"
    READ = "read"
    WRITE = "write"
    POOL = "pool"
    UNKNOWN = "unknown"


class ProviderReadTimeoutStage(StrEnum):
    WAITING_FOR_RESPONSE_HEADERS = "waiting_for_response_headers"
    READING_RESPONSE_BODY = "reading_response_body"


class ProviderInvocationError(RuntimeError):
    """Safe provider failure that never includes response bodies or credentials."""

    def __init__(
        self,
        category: ProviderFailureCategory,
        detail: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        response_status: str | None = None,
        latency_ms: int | None = None,
        timeout_phase: ProviderTimeoutPhase | None = None,
        read_timeout_stage: ProviderReadTimeoutStage | None = None,
        response_header_latency_ms: int | None = None,
        response_body_bytes_received: int | None = None,
    ) -> None:
        if category is not ProviderFailureCategory.TIMEOUT and timeout_phase is not None:
            raise ValueError("timeout phase requires a timeout provider failure")
        _validate_read_timeout_diagnostics(
            category=category,
            timeout_phase=timeout_phase,
            read_timeout_stage=read_timeout_stage,
            response_header_latency_ms=response_header_latency_ms,
            response_body_bytes_received=response_body_bytes_received,
            status_code=status_code,
            request_id=request_id,
        )
        super().__init__(detail)
        self.category = category
        self.status_code = status_code
        self.request_id = request_id
        self.response_status = response_status
        self.latency_ms = latency_ms
        self.timeout_phase = timeout_phase
        self.read_timeout_stage = read_timeout_stage
        self.response_header_latency_ms = response_header_latency_ms
        self.response_body_bytes_received = response_body_bytes_received


def _validate_read_timeout_diagnostics(
    *,
    category: ProviderFailureCategory,
    timeout_phase: ProviderTimeoutPhase | None,
    read_timeout_stage: ProviderReadTimeoutStage | None,
    response_header_latency_ms: int | None,
    response_body_bytes_received: int | None,
    status_code: int | None,
    request_id: str | None,
) -> None:
    diagnostics = (
        read_timeout_stage,
        response_header_latency_ms,
        response_body_bytes_received,
    )
    if any(value is not None for value in diagnostics) and (
        category is not ProviderFailureCategory.TIMEOUT
        or timeout_phase is not ProviderTimeoutPhase.READ
    ):
        raise ValueError("read-timeout diagnostics require a read timeout provider failure")
    if read_timeout_stage is None:
        if response_header_latency_ms is not None or response_body_bytes_received is not None:
            raise ValueError("read-timeout metrics require a read timeout stage")
        return
    if read_timeout_stage is ProviderReadTimeoutStage.WAITING_FOR_RESPONSE_HEADERS:
        if response_header_latency_ms is not None or response_body_bytes_received is not None:
            raise ValueError("pre-header read timeout cannot contain response metrics")
        if status_code is not None or request_id is not None:
            raise ValueError("pre-header read timeout cannot contain response metadata")
        return
    if response_header_latency_ms is None or response_body_bytes_received is None:
        raise ValueError("body read timeout requires response timing and byte count")
    if response_header_latency_ms < 0 or response_body_bytes_received < 0:
        raise ValueError("body read timeout diagnostics must be nonnegative")


class ProviderError(BaseModel):
    """Safe normalized failure facts; never raw response data or headers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: ProviderFailureCategory
    timeout_phase: ProviderTimeoutPhase | None = None
    read_timeout_stage: ProviderReadTimeoutStage | None = None
    response_header_latency_ms: int | None = Field(default=None, ge=0)
    response_body_bytes_received: int | None = Field(default=None, ge=0)
    status_code: int | None = Field(default=None, ge=100, le=599)
    request_id: str | None = Field(default=None, max_length=300)
    response_status: str | None = Field(default=None, max_length=200)
    latency_ms: int | None = Field(default=None, ge=0)
    attempt_count: Literal[1] = 1

    @model_validator(mode="after")
    def timeout_phase_matches_category(self) -> ProviderError:
        if self.category is not ProviderFailureCategory.TIMEOUT and self.timeout_phase is not None:
            raise ValueError("timeout phase requires a timeout provider failure")
        _validate_read_timeout_diagnostics(
            category=self.category,
            timeout_phase=self.timeout_phase,
            read_timeout_stage=self.read_timeout_stage,
            response_header_latency_ms=self.response_header_latency_ms,
            response_body_bytes_received=self.response_body_bytes_received,
            status_code=self.status_code,
            request_id=self.request_id,
        )
        return self


class ProviderUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)


class ProviderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: ModelProfile
    instructions: str = Field(min_length=1)
    input: str = Field(min_length=1)


class GenerationSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    effort: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    request_timeout_seconds: float = Field(gt=0)
    attempt_count: Literal[1] = 1


class ProviderResult(BaseModel):
    """Normalized public response and safe reproducibility facts only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_model: str
    observed_model: str | None = None
    provider: str
    endpoint_identity: str = Field(min_length=1, max_length=800)
    protocol: Protocol
    request_id: str | None = Field(default=None, max_length=300)
    public_output_text: str
    refused: bool = False
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    stop_reason: str | None = Field(default=None, max_length=200)
    response_status: str | None = Field(default=None, max_length=200)
    latency_ms: int = Field(ge=0)
    attempt_count: Literal[1] = 1

    @field_validator("public_output_text")
    @classmethod
    def public_output_is_utf8(cls, value: str) -> str:
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("public output text must be UTF-8 encodable") from exc
        if len(encoded) > MAX_PUBLIC_OUTPUT_BYTES:
            raise ValueError("public output text exceeds the evidence byte limit")
        return value


class ProviderAdapter(TypingProtocol):
    async def invoke(self, request: ProviderRequest) -> ProviderResult: ...


class DirectModelOutcome(StrEnum):
    VERIFIED_PASS = "verified_pass"
    VERIFIED_FAIL = "verified_fail"
    SUBJECT_REFUSAL = "subject_refusal"
    SUBJECT_OUTPUT_ERROR = "subject_output_error"
    PROVIDER_ERROR = "provider_error"
    INFRA_ERROR = "infra_error"
    ARTIFACT_ERROR = "artifact_error"


class DirectModelEvidence(BaseModel):
    """Immutable Phase D evidence; deliberately excludes raw HTTP and private reasoning."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    run_id: Identifier
    task_id: Identifier
    task_version: str
    task_digest: Sha256Digest
    verifier_definition_digest: Sha256Digest
    resource_budget: ResourceBudget
    workspace_input_digest: Sha256Digest
    workspace_output_digest: Sha256Digest | None = None
    context_digest: Sha256Digest | None = None
    prompt_template_version: str
    prompt_hash: Sha256Digest
    requested_model: str
    observed_model: str | None = None
    provider: str
    endpoint_identity: str = Field(min_length=1, max_length=800)
    protocol: Protocol
    generation_settings: GenerationSettings
    provider_result: ProviderResult | None = None
    provider_failure: ProviderFailureCategory | None = None
    provider_error: ProviderError | None = None
    public_response_digest: Sha256Digest | None = None
    public_response_text: str | None = None
    parsed_patch_digest: Sha256Digest | None = None
    verifier_sandbox_manifest: SandboxArtifactManifest | None = None
    verifier_artifact_namespace: Literal["verifier"] | None = None
    verifier_artifact_digest: Sha256Digest | None = None
    verifier_passed: bool | None = None
    verifier_score: float | None = Field(default=None, ge=0.0, le=1.0)
    outcome: DirectModelOutcome
    summary: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def evidence_is_coherent(self) -> DirectModelEvidence:
        if self.provider_result is not None:
            if self.provider_failure is not None or self.provider_error is not None:
                raise ValueError("provider result and provider failure are mutually exclusive")
            if self.public_response_text != self.provider_result.public_output_text:
                raise ValueError("public response must match the normalized provider result")
            identity_pairs = (
                ("requested_model", self.requested_model, self.provider_result.requested_model),
                ("observed_model", self.observed_model, self.provider_result.observed_model),
                ("provider", self.provider, self.provider_result.provider),
                (
                    "endpoint_identity",
                    self.endpoint_identity,
                    self.provider_result.endpoint_identity,
                ),
                ("protocol", self.protocol, self.provider_result.protocol),
            )
            mismatches = [name for name, expected, actual in identity_pairs if expected != actual]
            if mismatches:
                raise ValueError(f"provider result identity mismatch: {mismatches}")
        if (self.public_response_text is None) != (self.public_response_digest is None):
            raise ValueError("public response text and digest must be present together")
        if self.public_response_text is not None and self.public_response_digest is not None:
            actual_digest = (
                "sha256:" + hashlib.sha256(self.public_response_text.encode("utf-8")).hexdigest()
            )
            if actual_digest != self.public_response_digest:
                raise ValueError("public response digest does not match public text")
        if self.outcome is DirectModelOutcome.PROVIDER_ERROR:
            if self.provider_failure is None or self.provider_error is None:
                raise ValueError("provider_error outcome requires normalized failure evidence")
            if self.provider_error.category is not self.provider_failure:
                raise ValueError("provider failure category mismatch")
        if self.outcome is DirectModelOutcome.SUBJECT_REFUSAL:
            if self.provider_result is None or not self.provider_result.refused:
                raise ValueError("subject_refusal outcome requires a refused provider result")
            refusal_forbidden_fields = (
                self.workspace_output_digest,
                self.parsed_patch_digest,
                self.verifier_sandbox_manifest,
                self.verifier_artifact_namespace,
                self.verifier_artifact_digest,
                self.verifier_passed,
                self.verifier_score,
            )
            if any(value is not None for value in refusal_forbidden_fields):
                raise ValueError(
                    "subject_refusal outcome cannot contain subject execution evidence"
                )
        elif self.provider_result is not None and self.provider_result.refused:
            raise ValueError("refused provider result requires subject_refusal outcome")
        verifier_artifact_fields = (
            self.verifier_sandbox_manifest,
            self.verifier_artifact_namespace,
            self.verifier_artifact_digest,
        )
        if any(value is not None for value in verifier_artifact_fields) and not all(
            value is not None for value in verifier_artifact_fields
        ):
            raise ValueError("verifier manifest and artifact namespace must be complete")
        if self.outcome in {
            DirectModelOutcome.VERIFIED_PASS,
            DirectModelOutcome.VERIFIED_FAIL,
        }:
            if (
                self.verifier_passed is None
                or self.verifier_score is None
                or self.verifier_sandbox_manifest is None
                or self.verifier_artifact_namespace is None
                or self.verifier_artifact_digest is None
            ):
                raise ValueError("verified outcomes require complete verifier evidence")
            if self.verifier_sandbox_manifest.status is not SandboxStatus.SUCCEEDED:
                raise ValueError("verified outcome requires a successful verifier sandbox")
            if (
                self.verifier_sandbox_manifest.task_id != self.task_id
                or self.verifier_sandbox_manifest.task_version != self.task_version
                or self.verifier_sandbox_manifest.task_digest != self.task_digest
            ):
                raise ValueError("verifier sandbox task identity mismatch")
            if (
                self.verifier_sandbox_manifest.workspace_input_digest
                != self.workspace_output_digest
            ):
                raise ValueError("verifier sandbox workspace identity mismatch")
            if (
                self.provider_result is None
                or self.public_response_text is None
                or self.parsed_patch_digest is None
                or self.workspace_output_digest is None
            ):
                raise ValueError("verified outcome requires complete subject evidence")
            if self.outcome is DirectModelOutcome.VERIFIED_PASS and not self.verifier_passed:
                raise ValueError("verified_pass outcome requires verifier_passed=true")
            if self.outcome is DirectModelOutcome.VERIFIED_FAIL and self.verifier_passed:
                raise ValueError("verified_fail outcome requires verifier_passed=false")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )


class DirectModelRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    artifact_directory: Path
    evidence: DirectModelEvidence
