from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harnesslab.contracts.common import Identifier, NetworkPolicy, Sha256Digest
from harnesslab.contracts.provider import ProviderProvenance, validate_provider_base_url
from harnesslab.contracts.task import ResourceBudget
from harnesslab.harness_lane.models import (
    ChangedPathEvidence,
    CodexTokenUsage,
    HarnessFailureCategory,
    HarnessLaneOutcome,
    NormalizedTrace,
    ObservedModelStatus,
    SanitizedNativeEvent,
    TraceEventType,
)
from harnesslab.sandbox.models import ImageIdentity, SandboxArtifactManifest, SandboxStatus


class HarnessKind(StrEnum):
    CLAUDE_CODE = "claude-code"
    DEEPSEEK = "deepseek-harness"


class TraceCoverage(StrEnum):
    FULL_STREAM = "FULL_STREAM"
    FINAL_OUTPUT_ONLY = "FINAL_OUTPUT_ONLY"


class ClaudeCredentialTransport(StrEnum):
    ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
    ANTHROPIC_AUTH_TOKEN = "ANTHROPIC_AUTH_TOKEN"


class DeepSeekSessionExtraction(StrEnum):
    DEFERRED_NOT_VERIFIED = "DEFERRED_NOT_VERIFIED"


class ProcessDiagnosticCategory(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    EMPTY = "EMPTY"
    PRESENT = "PRESENT"
    TRUNCATED = "TRUNCATED"
    READ_FAILED = "READ_FAILED"


class StartupFailureCategory(StrEnum):
    CLI_USAGE_ERROR = "CLI_USAGE_ERROR"
    PERMISSION_CONFIGURATION_ERROR = "PERMISSION_CONFIGURATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    PROVIDER_BOOTSTRAP_ERROR = "PROVIDER_BOOTSTRAP_ERROR"
    UNKNOWN = "UNKNOWN"


class MultiHarnessProfile(BaseModel):
    """Frozen identity of either Phase F subject harness profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    harness: HarnessKind
    cli_version: str = Field(min_length=1, max_length=100)
    package_integrity: str = Field(min_length=1, max_length=300)
    requested_model: str = Field(min_length=1, max_length=300)
    provider_route: str = Field(min_length=1, max_length=300)
    provider_provenance: ProviderProvenance | None = None
    provider_base_url_reference: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    provider_fixed_base_url: str | None = None
    provider_credential_reference: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    provider_credential_transport: ClaudeCredentialTransport | None = None
    prompt_template_version: str = Field(min_length=1, max_length=100)
    tool_profile: tuple[str, ...]
    network_policy: NetworkPolicy = NetworkPolicy.DENY
    output_format: str = Field(min_length=1, max_length=100)
    trace_coverage: TraceCoverage
    image: ImageIdentity
    subject_toolchain_profile: str = Field(min_length=1, max_length=200)
    execution_timeout_seconds: float = Field(gt=0, le=3600)
    isolated_home: Literal[True] = True
    fresh_workspace: Literal[True] = True
    mcp_profile: Literal["none"] = "none"
    plugin_profile: Literal["none"] = "none"
    skill_profile: Literal["none"] = "none"
    config_digest: Sha256Digest | None = None
    developer_preview: bool = False
    session_extraction: DeepSeekSessionExtraction | None = None
    attempt_count: Literal[1] = 1

    @field_validator("provider_fixed_base_url")
    @classmethod
    def fixed_provider_url_is_safe(cls, value: str | None) -> str | None:
        return validate_provider_base_url(value) if value is not None else None

    @model_validator(mode="after")
    def canonical_profile(self) -> MultiHarnessProfile:
        if self.image.image_id == "sha256:" + "0" * 64:
            raise ValueError("image identity must come from an inspected image")
        if self.harness is HarnessKind.CLAUDE_CODE:
            if self.cli_version != "2.1.241":
                raise ValueError("Claude Code CLI must be pinned to 2.1.241")
            if self.trace_coverage is not TraceCoverage.FULL_STREAM:
                raise ValueError("Claude Code requires full stream trace coverage")
            if self.tool_profile != ("Read", "Edit", "Write", "Bash"):
                raise ValueError("Claude Code tool profile is not canonical")
            if self.config_digest is not None or self.session_extraction is not None:
                raise ValueError("Claude Code cannot claim DeepSeek config/session evidence")
            provider_values = (
                self.provider_provenance,
                self.provider_base_url_reference,
                self.provider_fixed_base_url,
                self.provider_credential_reference,
                self.provider_credential_transport,
            )
            if any(value is not None for value in provider_values) and (
                self.provider_provenance is None
                or (self.provider_base_url_reference is None)
                == (self.provider_fixed_base_url is None)
                or self.provider_credential_reference is None
                or self.provider_credential_transport is None
            ):
                raise ValueError("Claude provider configuration must be complete")
        else:
            if self.cli_version != "0.1.1-rc.2":
                raise ValueError("DeepSeek Harness CLI must be pinned to 0.1.1-rc.2")
            if self.trace_coverage is not TraceCoverage.FINAL_OUTPUT_ONLY:
                raise ValueError("DeepSeek E1 exposes final-output-only trace coverage")
            if self.config_digest is None:
                raise ValueError("DeepSeek profile requires a dumped-config digest")
            if self.session_extraction is not DeepSeekSessionExtraction.DEFERRED_NOT_VERIFIED:
                raise ValueError("DeepSeek E2 must remain explicitly deferred")
            if not self.developer_preview:
                raise ValueError("DeepSeek Harness must be marked developer preview")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    @property
    def fingerprint(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode()).hexdigest()


@dataclass(frozen=True)
class HarnessProcessCapture:
    stdout_lines: tuple[str, ...]
    stderr_text: str
    exit_code: int | None
    duration_ms: int
    timed_out: bool = False
    cancelled: bool = False
    stderr_category: ProcessDiagnosticCategory | None = None


@dataclass(frozen=True)
class MultiHarnessCollection:
    sanitized_events: tuple[SanitizedNativeEvent, ...]
    sanitized_jsonl: str
    native_digest: str
    trace: NormalizedTrace
    trace_digest: str
    terminal_event: str | None
    observed_model: str | None
    observed_model_status: ObservedModelStatus
    usage: CodexTokenUsage | None
    retry_count: int
    failure_category: HarnessFailureCategory | None


class MultiHarnessEvidence(BaseModel):
    """Immutable Phase F H-Lane evidence; only the Hidden Verifier decides correctness."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    run_id: Identifier
    task_id: Identifier
    task_version: str
    task_digest: Sha256Digest
    verifier_definition_digest: Sha256Digest
    resource_budget: ResourceBudget
    workspace_input_digest: Sha256Digest
    workspace_output_digest: Sha256Digest
    changed_paths: tuple[ChangedPathEvidence, ...]
    context_digest: Sha256Digest | None = None
    prompt_template_version: str
    prompt_hash: Sha256Digest
    harness: HarnessKind
    profile: MultiHarnessProfile
    profile_hash: Sha256Digest
    requested_model: str
    observed_model: str | None = None
    observed_model_status: ObservedModelStatus
    provider_route: str
    native_transcript_digest: Sha256Digest
    normalized_trace_version: Literal[1] = 1
    normalized_trace_digest: Sha256Digest
    trace_coverage: TraceCoverage
    trace_event_count: int = Field(ge=0)
    trace_event_types: tuple[TraceEventType, ...]
    terminal_native_event: str | None = None
    stderr_category: ProcessDiagnosticCategory
    stderr_digest: Sha256Digest | None
    stdout_line_count: int = Field(ge=0)
    startup_failure_category: StartupFailureCategory | None = None
    process_exit_code: int | None = None
    duration_ms: int = Field(ge=0)
    timed_out: bool = False
    cancelled: bool = False
    retry_count: int = Field(ge=0)
    usage: CodexTokenUsage | None = None
    harness_failure: HarnessFailureCategory | None = None
    verifier_sandbox_manifest: SandboxArtifactManifest | None = None
    verifier_artifact_namespace: Literal["verifier"] | None = None
    verifier_artifact_digest: Sha256Digest | None = None
    verifier_passed: bool | None = None
    verifier_score: float | None = Field(default=None, ge=0.0, le=1.0)
    outcome: HarnessLaneOutcome
    summary: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def evidence_is_coherent(self) -> MultiHarnessEvidence:
        if self.harness is not self.profile.harness:
            raise ValueError("harness identity mismatch")
        if self.profile_hash != self.profile.fingerprint:
            raise ValueError("harness profile fingerprint mismatch")
        if self.requested_model != self.profile.requested_model:
            raise ValueError("requested model does not match harness profile")
        if self.provider_route != self.profile.provider_route:
            raise ValueError("provider route does not match harness profile")
        if self.trace_coverage is not self.profile.trace_coverage:
            raise ValueError("trace coverage does not match harness profile")
        digest_unavailable = self.stderr_category in {
            ProcessDiagnosticCategory.UNAVAILABLE,
            ProcessDiagnosticCategory.READ_FAILED,
        }
        if digest_unavailable == (self.stderr_digest is not None):
            raise ValueError("stderr diagnostic availability and digest disagree")
        has_classifiable_stderr = self.stderr_category in {
            ProcessDiagnosticCategory.PRESENT,
            ProcessDiagnosticCategory.TRUNCATED,
        }
        if self.startup_failure_category is not None and not has_classifiable_stderr:
            raise ValueError("stderr category and startup failure classification disagree")
        if self.observed_model_status is ObservedModelStatus.NOT_EXPOSED:
            if self.observed_model is not None:
                raise ValueError("unexposed observed model must remain null")
        elif self.observed_model is None:
            raise ValueError("exposed observed model status requires an observed model")
        verifier_fields = (
            self.verifier_sandbox_manifest,
            self.verifier_artifact_namespace,
            self.verifier_artifact_digest,
            self.verifier_passed,
            self.verifier_score,
        )
        if self.outcome in {HarnessLaneOutcome.VERIFIED_PASS, HarnessLaneOutcome.VERIFIED_FAIL}:
            if self.harness_failure is not None or any(value is None for value in verifier_fields):
                raise ValueError("verified outcomes require complete verifier evidence")
            assert self.verifier_sandbox_manifest is not None
            if self.verifier_sandbox_manifest.status is not SandboxStatus.SUCCEEDED:
                raise ValueError("verified outcome requires successful verifier sandbox")
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
                raise ValueError("verifier input must equal final subject workspace identity")
            if self.outcome is HarnessLaneOutcome.VERIFIED_PASS and not self.verifier_passed:
                raise ValueError("verified_pass requires verifier_passed=true")
            if self.outcome is HarnessLaneOutcome.VERIFIED_FAIL and self.verifier_passed:
                raise ValueError("verified_fail requires verifier_passed=false")
        elif self.outcome is HarnessLaneOutcome.HARNESS_ERROR:
            if self.harness_failure is None or any(value is not None for value in verifier_fields):
                raise ValueError("harness_error requires only a harness failure")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )


class MultiHarnessRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    artifact_directory: Path
    evidence: MultiHarnessEvidence
