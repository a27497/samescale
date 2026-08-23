from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.contracts.common import Identifier, NetworkPolicy, Sha256Digest
from harnesslab.sandbox.models import ImageIdentity, SandboxArtifactManifest, SandboxStatus


class HarnessFailureCategory(StrEnum):
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PROCESS_ERROR = "process_error"
    PROTOCOL_ERROR = "protocol_error"
    MODEL_TURN_FAILED = "model_turn_failed"
    PROFILE_VIOLATION = "profile_violation"
    ARTIFACT_ERROR = "artifact_error"


class HarnessLaneOutcome(StrEnum):
    VERIFIED_PASS = "verified_pass"
    VERIFIED_FAIL = "verified_fail"
    HARNESS_ERROR = "harness_error"
    INFRA_ERROR = "infra_error"
    ARTIFACT_ERROR = "artifact_error"


class ObservedModelStatus(StrEnum):
    EXPOSED = "exposed"
    NOT_EXPOSED = "not_exposed"


class ChangedPathStatus(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


class TraceEventType(StrEnum):
    THREAD_STARTED = "THREAD_STARTED"
    TURN_STARTED = "TURN_STARTED"
    AGENT_MESSAGE = "AGENT_MESSAGE"
    REASONING_PRESENT = "REASONING_PRESENT"
    COMMAND_EXECUTION = "COMMAND_EXECUTION"
    FILE_CHANGE = "FILE_CHANGE"
    MCP_TOOL_CALL = "MCP_TOOL_CALL"
    WEB_SEARCH = "WEB_SEARCH"
    TODO_LIST = "TODO_LIST"
    API_RETRY = "API_RETRY"
    ITEM_ERROR = "ITEM_ERROR"
    TURN_COMPLETED = "TURN_COMPLETED"
    TURN_FAILED = "TURN_FAILED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class CodexTokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    cache_write_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_output_tokens: int | None = Field(default=None, ge=0)


class NativeFileChange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1, max_length=1000)
    kind: str | None = Field(default=None, max_length=100)


class SanitizedNativeEvent(BaseModel):
    """Safe native structure. Raw Codex lines and private reasoning are never represented."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ordinal: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=200)
    item_type: str | None = Field(default=None, max_length=200)
    item_id: str | None = Field(default=None, max_length=300)
    status: str | None = Field(default=None, max_length=200)
    thread_id: str | None = Field(default=None, max_length=300)
    observed_model: str | None = Field(default=None, max_length=300)
    text: str | None = Field(default=None, max_length=131_072)
    command: str | None = Field(default=None, max_length=16_384)
    public_output: str | None = Field(default=None, max_length=65_536)
    exit_code: int | None = None
    file_changes: tuple[NativeFileChange, ...] = ()
    usage: CodexTokenUsage | None = None
    reasoning_present: bool = False
    error_code: str | None = Field(default=None, max_length=200)

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


class NormalizedTraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ordinal: int = Field(ge=1)
    type: TraceEventType
    native_event_type: str
    item_type: str | None = None
    item_id: str | None = None
    status: str | None = None
    text: str | None = None
    command: str | None = None
    public_output: str | None = None
    exit_code: int | None = None
    file_changes: tuple[NativeFileChange, ...] = ()
    usage: CodexTokenUsage | None = None


class NormalizedTrace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    events: tuple[NormalizedTraceEvent, ...]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


class WorkspaceFileEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1, max_length=1000)
    digest: Sha256Digest


class ChangedPathEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1, max_length=1000)
    status: ChangedPathStatus
    before_digest: Sha256Digest | None = None
    after_digest: Sha256Digest | None = None


class CodexHarnessProfile(BaseModel):
    """Frozen reproducibility identity for the one Phase E Codex harness profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    harness: Literal["codex"] = "codex"
    codex_cli_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    requested_model: str = Field(min_length=1, max_length=300)
    reasoning_effort: str = Field(min_length=1, max_length=50)
    sandbox_mode: Literal["workspace-write"] = "workspace-write"
    approval_policy: Literal["never"] = "never"
    tool_network_policy: NetworkPolicy = NetworkPolicy.DENY
    web_search_policy: Literal["disabled"] = "disabled"
    ephemeral: Literal[True] = True
    ignore_user_config: Literal[True] = True
    ignore_rules: Literal[True] = True
    mcp_profile: Literal["none"] = "none"
    external_skill_plugin_profile: Literal["none"] = "none"
    built_in_behavior_profile: str = Field(min_length=1, max_length=200)
    execution_timeout_seconds: float = Field(gt=0, le=3600)
    codex_image: ImageIdentity
    subject_toolchain_profile: str = Field(min_length=1, max_length=200)
    shell_tool_environment_policy: str = Field(min_length=1, max_length=300)
    attempt_count: Literal[1] = 1

    @model_validator(mode="after")
    def canonical_phase_e_policy(self) -> CodexHarnessProfile:
        required = (
            self.tool_network_policy is NetworkPolicy.DENY,
            self.ephemeral,
            self.ignore_user_config,
            self.ignore_rules,
            self.mcp_profile == "none",
            self.external_skill_plugin_profile == "none",
            self.attempt_count == 1,
        )
        if not all(required):
            raise ValueError("Phase E Codex profile violates the canonical isolation policy")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    @property
    def fingerprint(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CodexProcessCapture:
    lines: tuple[str, ...]
    exit_code: int | None
    duration_ms: int
    timed_out: bool = False
    cancelled: bool = False


@dataclass(frozen=True)
class CodexCollection:
    sanitized_events: tuple[SanitizedNativeEvent, ...]
    sanitized_jsonl: str
    native_digest: str
    trace: NormalizedTrace
    trace_digest: str
    thread_id: str | None
    terminal_event: str | None
    observed_model: str | None
    observed_model_status: ObservedModelStatus
    usage: CodexTokenUsage | None
    failure_category: HarnessFailureCategory | None


class HarnessLaneEvidence(BaseModel):
    """Immutable Phase E evidence. Task correctness is present only from Hidden Verifier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    run_id: Identifier
    task_id: Identifier
    task_version: str
    task_digest: Sha256Digest
    workspace_input_digest: Sha256Digest
    workspace_output_digest: Sha256Digest
    changed_paths: tuple[ChangedPathEvidence, ...]
    context_digest: Sha256Digest | None = None
    prompt_template_version: str
    prompt_hash: Sha256Digest
    harness: Literal["codex"] = "codex"
    profile: CodexHarnessProfile
    profile_hash: Sha256Digest
    requested_model: str
    observed_model: str | None = None
    observed_model_status: ObservedModelStatus
    native_transcript_digest: Sha256Digest
    normalized_trace_version: Literal[1] = 1
    normalized_trace_digest: Sha256Digest
    trace_coverage: Literal["FULL_STREAM"] = "FULL_STREAM"
    trace_event_count: int = Field(ge=0)
    trace_event_types: tuple[TraceEventType, ...]
    thread_id: str | None = None
    terminal_native_event: str | None = None
    process_exit_code: int | None = None
    duration_ms: int = Field(ge=0)
    timed_out: bool = False
    cancelled: bool = False
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
    def evidence_is_coherent(self) -> HarnessLaneEvidence:
        if self.profile_hash != self.profile.fingerprint:
            raise ValueError("Harness profile fingerprint mismatch")
        if self.requested_model != self.profile.requested_model:
            raise ValueError("requested model does not match Harness profile")
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
                raise ValueError("verified H-Lane outcomes require complete verifier evidence")
            assert self.verifier_sandbox_manifest is not None
            if self.verifier_sandbox_manifest.status is not SandboxStatus.SUCCEEDED:
                raise ValueError("verified H-Lane outcome requires successful verifier sandbox")
            if (
                self.verifier_sandbox_manifest.workspace_input_digest
                != self.workspace_output_digest
            ):
                raise ValueError("verifier input must equal the pre-verifier workspace identity")
            if self.outcome is HarnessLaneOutcome.VERIFIED_PASS and not self.verifier_passed:
                raise ValueError("verified_pass requires verifier_passed=true")
            if self.outcome is HarnessLaneOutcome.VERIFIED_FAIL and self.verifier_passed:
                raise ValueError("verified_fail requires verifier_passed=false")
        elif self.outcome is HarnessLaneOutcome.HARNESS_ERROR:
            if self.harness_failure is None:
                raise ValueError("harness_error requires an explicit Harness failure category")
            if any(value is not None for value in verifier_fields):
                raise ValueError("Harness failures cannot contain verifier results")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )


class HarnessLaneRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    artifact_directory: Path
    evidence: HarnessLaneEvidence
