from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harnesslab.contracts.common import Identifier, Protocol, Sha256Digest
from harnesslab.experiment.methodology import BudgetContract, ComparisonType, EvaluationMode
from harnesslab.experiment.plan import MethodologyV2ExperimentPlan
from harnesslab.registry.runtime import (
    DirectRuntimeProfileSource,
    direct_harness_control_identity,
    resolve_direct_runtime_profile,
)


class RegistryError(ValueError):
    """A Registry Lite selection or immutable identity is invalid."""


class RegistryModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BillingMode(StrEnum):
    PAY_AS_YOU_GO = "PAY_AS_YOU_GO"
    CONTRACT = "CONTRACT"
    RELAY_ACCOUNT = "RELAY_ACCOUNT"
    CODING_PLAN = "CODING_PLAN"
    TOKEN_PLAN = "TOKEN_PLAN"


class EndpointClass(StrEnum):
    PRIVATE_RELAY = "PRIVATE_RELAY"
    PUBLIC_SHARED = "PUBLIC_SHARED"
    PUBLIC_OFFICIAL = "PUBLIC_OFFICIAL"
    WORKSPACE_DEDICATED = "WORKSPACE_DEDICATED"


class ProviderHealthStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    UNKNOWN = "UNKNOWN"


class CredentialStatus(StrEnum):
    SET = "SET"
    MISSING = "MISSING"


class CompatibilityStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"


class TraceCoverage(StrEnum):
    FULL_STREAM = "FULL_STREAM"
    FINAL_OUTPUT_ONLY = "FINAL_OUTPUT_ONLY"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class ObservedModelCapability(StrEnum):
    AVAILABLE = "AVAILABLE"
    RUN_EVIDENCE_ONLY = "RUN_EVIDENCE_ONLY"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class PreflightStatus(StrEnum):
    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    BLOCKED = "BLOCKED"


class CheckStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


class CostEstimateStatus(StrEnum):
    PLANNING_ONLY = "PLANNING_ONLY"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class ProviderDefinition(RegistryModel):
    provider_id: Identifier
    display_name: str = Field(min_length=1, max_length=200)
    provider_family: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=100)
    protocols: tuple[Protocol, ...] = Field(min_length=1)
    endpoint_class: EndpointClass
    base_url_reference: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    protocol_base_url_references: dict[Protocol, str] = Field(default_factory=dict)
    credential_reference: str = Field(
        pattern=r"^[A-Z][A-Z0-9_]*$", serialization_alias="credential_ref"
    )
    billing_mode: BillingMode
    automation_allowed: bool
    enabled: bool
    health_status: ProviderHealthStatus
    capabilities: tuple[str, ...]
    pricing_snapshot_reference: str | None = Field(default=None, max_length=300)
    runtime_endpoint_fingerprint: Sha256Digest | None = None
    runtime_endpoint_fingerprints: dict[Protocol, Sha256Digest] = Field(default_factory=dict)
    configuration_reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def alibaba_contract_is_safe(self) -> ProviderDefinition:
        if self.provider_id != "alibaba-bailian":
            return self
        expected = (
            self.region == "cn-beijing",
            self.endpoint_class is EndpointClass.WORKSPACE_DEDICATED,
            self.base_url_reference == "HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL",
            self.protocol_base_url_references
            == {
                Protocol.CHAT_COMPLETIONS: "HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL",
                Protocol.RESPONSES: "HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL",
                Protocol.MESSAGES: "HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL",
            },
            self.credential_reference == "HARNESSLAB_ALIBABA_BAILIAN_API_KEY",
            self.billing_mode is BillingMode.PAY_AS_YOU_GO,
            self.automation_allowed,
        )
        if not all(expected):
            raise ValueError("Alibaba Bailian provider violates the frozen PAYG contract")
        return self


class ReasoningControls(RegistryModel):
    effort: bool = False
    temperature: bool = False
    thinking_toggle: bool = False


class ModelDefinition(RegistryModel):
    model_id: Identifier
    display_name: str = Field(min_length=1, max_length=200)
    model_family: str = Field(min_length=1, max_length=100)
    capabilities: tuple[str, ...]
    context_window_tokens: int | None = Field(default=None, gt=0)
    context_metadata_status: Literal["KNOWN", "NOT_AVAILABLE"]
    reasoning_controls: ReasoningControls
    supported_protocols: tuple[Protocol, ...] = Field(min_length=1)


class ProviderModelProfile(RegistryModel):
    purpose: Literal["SUBJECT", "ANALYST", "JUDGE"] = Field(
        default="SUBJECT", exclude_if=lambda value: value == "SUBJECT"
    )
    temperature: float | None = Field(
        default=None, ge=0, le=2, exclude_if=lambda value: value is None
    )
    max_output_tokens_limit: int | None = Field(
        default=None, gt=0, exclude_if=lambda value: value is None
    )
    profile_id: Identifier
    model_id: Identifier
    provider_id: Identifier
    requested_model: str = Field(min_length=1, max_length=200)
    protocol: Protocol
    route: str = Field(pattern=r"^/[A-Za-z0-9._/-]+$", max_length=300)
    provider_route_identity: str = Field(min_length=1, max_length=800)
    credential_reference: str = Field(
        pattern=r"^[A-Z][A-Z0-9_]*$", serialization_alias="credential_ref"
    )
    reasoning_effort: str | None = Field(default=None, max_length=50)
    max_output_tokens: int = Field(gt=0)
    request_timeout_seconds: int = Field(gt=0, le=600)
    observed_model_capability: ObservedModelCapability
    automation_allowed: bool
    enabled: bool
    pricing_snapshot_reference: str | None = Field(default=None, max_length=300)
    runtime_endpoint_fingerprint: Sha256Digest | None = None
    profile_identity: Sha256Digest

    @property
    def expected_profile_identity(self) -> str:
        raw = self.model_dump(mode="json", exclude={"profile_identity", "enabled"})
        return canonical_digest(raw)

    @property
    def base_provider_profile_identity(self) -> str:
        """Identify registry facts without binding experiment execution limits."""

        raw = self.model_dump(
            mode="json",
            exclude={
                "profile_identity",
                "enabled",
                "max_output_tokens",
                "request_timeout_seconds",
            },
        )
        return canonical_digest(raw)

    @model_validator(mode="after")
    def identity_is_bound(self) -> ProviderModelProfile:
        if self.profile_identity != self.expected_profile_identity:
            raise ValueError("provider model profile identity mismatch")
        return self


class HarnessProfileDefinition(RegistryModel):
    enabled: bool = Field(default=True, exclude_if=lambda value: value is True)
    profile_id: Identifier
    profile_reference: str = Field(pattern=r"^builtin:[a-z0-9._-]+$")
    supported_provider_profile_ids: tuple[Identifier, ...]
    reasoning_effort: str | None = Field(default=None, max_length=50)
    harness_config_identity: Sha256Digest


class HarnessDefinition(RegistryModel):
    harness_id: Identifier
    display_name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    image_reference: str = Field(min_length=1, max_length=300)
    image_digest: Sha256Digest | None = None
    cli_runtime_identity: str = Field(min_length=1, max_length=300)
    profiles: tuple[HarnessProfileDefinition, ...] = Field(min_length=1)
    supported_protocols: tuple[Protocol, ...] = Field(min_length=1)
    tool_surface: tuple[str, ...]
    trace_coverage: TraceCoverage
    observed_model_exposure: ObservedModelCapability
    network_capability: Literal["PROVIDER_ALLOWLIST", "DENY", "RUNTIME_DEPENDENT"]
    mcp_capability: bool
    workspace_mutation: bool
    native_tools: bool
    runtime_health: ProviderHealthStatus
    runner_contract: str = Field(min_length=1, max_length=100)


class CapabilityAssessment(RegistryModel):
    provider_profile_id: Identifier
    harness_profile_id: Identifier
    status: CompatibilityStatus
    reason_codes: tuple[str, ...]
    protocol_compatible: bool
    model_provider_compatible: bool
    observed_model: ObservedModelCapability
    trace_coverage: TraceCoverage
    native_tools: bool
    workspace_mutation: bool
    network_requirement: str
    reasoning_control_supported: bool
    harness_uplift_eligible: bool
    judge_eligible: bool


class RegistryDefaults(RegistryModel):
    default_provider_profile_id: Identifier
    default_evaluation_mode: EvaluationMode
    default_schedule_seed: int
    default_concurrency: int = Field(ge=1, le=64)
    default_cost_budget: float | None = Field(default=None, gt=0)


class CredentialReferenceStatus(RegistryModel):
    credential_reference: str = Field(
        pattern=r"^[A-Z][A-Z0-9_]*$", serialization_alias="credential_ref"
    )
    status: CredentialStatus


class RegistrySettings(RegistryModel):
    defaults: RegistryDefaults
    credentials: tuple[CredentialReferenceStatus, ...]
    provider_enabled: dict[str, bool]
    secret_editing_supported: Literal[False] = False


class TaskRegistryItem(RegistryModel):
    task_id: Identifier
    task_version: str
    task_digest: Sha256Digest
    package_path: str
    tier: Literal["TIER_A_MICRO_CONTRACT"] = "TIER_A_MICRO_CONTRACT"


class RegistryCatalog(RegistryModel):
    schema_version: Literal[1] = 1
    registry_id: Literal["harnesslab-unified-registry-lite-v1"] = (
        "harnesslab-unified-registry-lite-v1"
    )
    providers: tuple[ProviderDefinition, ...]
    models: tuple[ModelDefinition, ...]
    provider_model_profiles: tuple[ProviderModelProfile, ...]
    harnesses: tuple[HarnessDefinition, ...]
    tasks: tuple[TaskRegistryItem, ...]
    defaults: RegistryDefaults

    @model_validator(mode="after")
    def references_are_closed(self) -> RegistryCatalog:
        providers = {item.provider_id for item in self.providers}
        models = {item.model_id for item in self.models}
        profiles = {item.profile_id for item in self.provider_model_profiles}
        if len(providers) != len(self.providers) or len(models) != len(self.models):
            raise ValueError("registry contains duplicate provider or model identities")
        if len(profiles) != len(self.provider_model_profiles):
            raise ValueError("registry contains duplicate provider profile identities")
        for profile in self.provider_model_profiles:
            if profile.provider_id not in providers or profile.model_id not in models:
                raise ValueError("provider model profile references an unknown definition")
        harness_profiles = [profile for item in self.harnesses for profile in item.profiles]
        if len({item.profile_id for item in harness_profiles}) != len(harness_profiles):
            raise ValueError("registry contains duplicate harness profile identities")
        if any(
            provider_profile_id not in profiles
            for item in harness_profiles
            for provider_profile_id in item.supported_provider_profile_ids
        ):
            raise ValueError("harness profile references an unknown provider profile")
        if self.defaults.default_provider_profile_id not in profiles:
            raise ValueError("default provider profile is not registered")
        return self

    @property
    def digest(self) -> str:
        raw = self.model_dump(mode="json")
        for provider in raw["providers"]:
            provider["enabled"] = True
            provider["health_status"] = ProviderHealthStatus.UNKNOWN.value
            provider["configuration_reason_codes"] = []
        for profile in raw["provider_model_profiles"]:
            profile["enabled"] = True
        return canonical_digest(raw)


class ProviderRegistryResponse(RegistryModel):
    registry_id: str
    registry_digest: Sha256Digest
    items: tuple[ProviderDefinition, ...]


class ModelRegistryResponse(RegistryModel):
    registry_id: str
    registry_digest: Sha256Digest
    models: tuple[ModelDefinition, ...]
    provider_profiles: tuple[ProviderModelProfile, ...]


class HarnessRegistryResponse(RegistryModel):
    registry_id: str
    registry_digest: Sha256Digest
    items: tuple[HarnessDefinition, ...]


class CapabilityRegistryResponse(RegistryModel):
    registry_id: str
    registry_digest: Sha256Digest
    items: tuple[CapabilityAssessment, ...]


class TaskRegistryResponse(RegistryModel):
    registry_id: str
    registry_digest: Sha256Digest
    items: tuple[TaskRegistryItem, ...]


class MethodologyRegistryItem(RegistryModel):
    methodology_id: str
    methodology_digest: Sha256Digest
    active: bool
    evaluation_modes: tuple[EvaluationMode, ...]
    repeat_counts: dict[EvaluationMode, Literal[1, 3, 5]]
    scheduling_policy: Literal["BLOCKED_INTERLEAVED_SCHEDULING"]


class MethodologyRegistryResponse(RegistryModel):
    items: tuple[MethodologyRegistryItem, ...]


class ExperimentCellSelection(RegistryModel):
    cell_id: Identifier
    provider_model_profile_id: Identifier
    harness_profile_id: Identifier


class ExperimentBuilderRequest(RegistryModel):
    experiment_id: Identifier | None = Field(default=None, exclude_if=lambda value: value is None)
    name: str = Field(min_length=1, max_length=200)
    methodology_id: str = Field(min_length=1, max_length=100)
    methodology_digest: Sha256Digest
    evaluation_mode: EvaluationMode
    comparison_type: ComparisonType
    task_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=18)
    cells: tuple[ExperimentCellSelection, ...] = Field(min_length=2, max_length=2)
    budget: BudgetContract
    schedule_seed: int
    max_parallel_runs: int = Field(ge=1, le=64)
    billing_modes: dict[Identifier, BillingMode] = Field(default_factory=dict, max_length=4)

    @field_validator("task_ids")
    @classmethod
    def tasks_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate task selection")
        return value

    @model_validator(mode="after")
    def cells_are_unique(self) -> ExperimentBuilderRequest:
        if len({item.cell_id for item in self.cells}) != len(self.cells):
            raise ValueError("duplicate cell identity")
        return self


class PreflightCheck(RegistryModel):
    key: str = Field(min_length=1, max_length=100)
    status: CheckStatus
    reason_code: str = Field(min_length=1, max_length=100)
    detail: str = Field(min_length=1, max_length=500)


class ScheduleBlockPreview(RegistryModel):
    block_identity: Sha256Digest
    task_id: Identifier
    repeat_index: int = Field(ge=0)
    cell_execution_order: tuple[Identifier, ...]
    provider_status: Literal["AVAILABLE", "PROVIDER_UNAVAILABLE"]


class CostEstimate(RegistryModel):
    status: CostEstimateStatus
    value: float | None = Field(default=None, ge=0)
    currency: Literal["USD"] = "USD"
    evidence_reference: str | None = None

    @model_validator(mode="after")
    def status_matches_value(self) -> CostEstimate:
        if self.status is CostEstimateStatus.NOT_AVAILABLE and self.value is not None:
            raise ValueError("unavailable cost estimate cannot contain a value")
        if self.status is CostEstimateStatus.PLANNING_ONLY and self.value is None:
            raise ValueError("planning cost estimate requires a value")
        return self


class ExperimentPreflight(RegistryModel):
    status: PreflightStatus
    checks: tuple[PreflightCheck, ...]
    estimated_logical_slots: int = Field(ge=0)
    estimated_maximum_wall_time_seconds: int | None = Field(default=None, ge=0)
    evaluation_mode: EvaluationMode
    repeat_count: Literal[1, 3, 5]
    max_parallel_runs: int
    cost_estimate: CostEstimate
    schedule_preview: tuple[ScheduleBlockPreview, ...]
    candidate_experiment_id: Identifier | None = None
    candidate_plan_digest: Sha256Digest | None = None


class FrozenProviderSelection(RegistryModel):
    cell_id: Identifier
    provider_id: Identifier
    provider_profile_id: Identifier
    provider_profile_identity: Sha256Digest
    model_id: Identifier
    requested_model: str
    harness_id: Identifier
    harness_profile_id: Identifier
    harness_config_identity: Sha256Digest
    credential_reference: str = Field(
        pattern=r"^[A-Z][A-Z0-9_]*$", serialization_alias="credential_ref"
    )
    safe_route_identity: str
    runtime_endpoint_fingerprint: Sha256Digest | None = None
    billing_mode: BillingMode
    pricing_snapshot_reference: str | None = None
    base_provider_profile_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    runtime_profile_source: DirectRuntimeProfileSource | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    runtime_profile_control_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    effective_runtime_profile_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    resource_envelope_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class ExperimentSnapshot(RegistryModel):
    schema_version: Literal[1] = 1
    snapshot_id: Identifier
    snapshot_digest: Sha256Digest
    registry_id: str
    registry_digest: Sha256Digest
    methodology_id: str
    methodology_digest: Sha256Digest
    comparison_type: ComparisonType
    plan: MethodologyV2ExperimentPlan
    provider_selections: tuple[FrozenProviderSelection, ...]
    preflight: ExperimentPreflight

    @property
    def expected_snapshot_digest(self) -> str:
        return canonical_digest(
            self.model_dump(mode="json", exclude={"snapshot_digest", "preflight"})
        )

    @model_validator(mode="after")
    def immutable_identity_is_bound(self) -> ExperimentSnapshot:
        if self.snapshot_digest != self.expected_snapshot_digest:
            raise ValueError("experiment snapshot digest mismatch")
        if self.methodology_id != self.plan.methodology_id:
            raise ValueError("snapshot methodology ID does not match plan")
        if self.methodology_digest != self.plan.methodology_digest:
            raise ValueError("snapshot methodology digest does not match plan")
        cells = {cell.id: cell for cell in self.plan.cells}
        for selection in self.provider_selections:
            if selection.harness_id != "direct-model":
                continue
            runtime_fields = (
                selection.runtime_profile_source,
                selection.runtime_profile_control_identity,
                selection.effective_runtime_profile_identity,
                selection.resource_envelope_identity,
            )
            if all(value is None for value in runtime_fields):
                # Historical snapshots predate effective-runtime binding. They remain
                # readable but are not upgraded to the executable v2 contract.
                continue
            if any(value is None for value in runtime_fields):
                raise ValueError("Direct selection has an incomplete runtime identity binding")
            if selection.runtime_profile_source is None:
                raise ValueError("Direct selection is missing its runtime profile source")
            resolved = resolve_direct_runtime_profile(
                selection.runtime_profile_source, self.plan.budget_contract
            )
            try:
                cell = cells[selection.cell_id]
            except KeyError as exc:
                raise ValueError("Direct selection is missing its frozen plan cell") from exc
            checks = (
                selection.provider_id == resolved.profile.provider,
                selection.requested_model == resolved.profile.requested_model,
                selection.safe_route_identity == resolved.profile.provider_route_identity,
                selection.runtime_profile_control_identity == resolved.profile_control_identity,
                selection.effective_runtime_profile_identity == resolved.effective_profile_identity,
                selection.resource_envelope_identity == resolved.resource_envelope_identity,
                selection.harness_config_identity == direct_harness_control_identity(),
                cell.requested_model == resolved.profile.requested_model,
                cell.reasoning_effort == resolved.profile.reasoning.effort,
                cell.provider_route == resolved.profile.provider_route_identity,
                cell.profile_identity == resolved.profile_control_identity,
                cell.effective_runtime_profile_identity == resolved.effective_profile_identity,
                cell.resource_envelope_identity == resolved.resource_envelope_identity,
                cell.base_provider_profile_identity == selection.base_provider_profile_identity,
                cell.harness_config_identity == selection.harness_config_identity,
                cell.runner_contract == "direct-model-v1",
            )
            if not all(checks):
                raise ValueError("snapshot Direct runtime identities do not re-resolve")
            for slot in self.plan.run_slots:
                if slot.cell_id != cell.id:
                    continue
                slot_checks = (
                    slot.requested_model == cell.requested_model,
                    slot.provider_route == cell.provider_route,
                    slot.profile_identity == cell.profile_identity,
                    slot.harness_config_identity == cell.harness_config_identity,
                    slot.runner_contract == cell.runner_contract,
                    slot.base_provider_profile_identity == cell.base_provider_profile_identity,
                    slot.effective_runtime_profile_identity
                    == cell.effective_runtime_profile_identity,
                    slot.resource_envelope_identity == cell.resource_envelope_identity,
                )
                if not all(slot_checks):
                    raise ValueError("snapshot Direct slot controls drift from its cell")
        return self


def canonical_digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def freeze_provider_model_profile(**values: object) -> ProviderModelProfile:
    draft = ProviderModelProfile.model_construct(
        profile_identity="sha256:" + "0" * 64,
        **values,  # type: ignore[arg-type]
    )
    identity = draft.model_dump(mode="json", exclude={"profile_identity", "enabled"})
    persisted = draft.model_dump(mode="json", exclude={"profile_identity"})
    return ProviderModelProfile.model_validate(
        {**persisted, "profile_identity": canonical_digest(identity)}
    )


def freeze_experiment_snapshot(**values: object) -> ExperimentSnapshot:
    draft = ExperimentSnapshot.model_construct(
        snapshot_digest="sha256:" + "0" * 64,
        **values,  # type: ignore[arg-type]
    )
    identity = draft.model_dump(mode="json", exclude={"snapshot_digest", "preflight"})
    persisted = draft.model_dump(mode="json", exclude={"snapshot_digest"})
    return ExperimentSnapshot.model_validate(
        {**persisted, "snapshot_digest": canonical_digest(identity)}
    )


class ExperimentSnapshotSummary(RegistryModel):
    snapshot_id: Identifier
    snapshot_digest: Sha256Digest
    name: str
    created_at: datetime


class ExperimentSnapshotList(RegistryModel):
    items: tuple[ExperimentSnapshotSummary, ...]
    total: int
    limit: int
    offset: int
