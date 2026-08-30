from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harnesslab.budget import (
    BudgetEstimate,
    BudgetEstimateRequest,
    MatrixBudgetEstimate,
    MatrixBudgetEstimateRequest,
)
from harnesslab.contracts.common import EvaluationLane, NetworkPolicy, Sha256Digest


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PreflightStatus(StrEnum):
    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    BLOCKED = "BLOCKED"


class CheckStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


class ConfigurationKind(StrEnum):
    CREDENTIAL = "CREDENTIAL"
    HTTPS_URL = "HTTPS_URL"
    NON_EMPTY = "NON_EMPTY"


class TraceSupport(StrEnum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    FINAL_OUTPUT_ONLY = "FINAL_OUTPUT_ONLY"
    FULL_STREAM = "FULL_STREAM"

    @property
    def level(self) -> int:
        return {
            TraceSupport.NOT_AVAILABLE: 0,
            TraceSupport.FINAL_OUTPUT_ONLY: 1,
            TraceSupport.FULL_STREAM: 2,
        }[self]


class PreflightAuthorizationLevel(StrEnum):
    CANARY_PREFLIGHT = "CANARY_PREFLIGHT"
    FULL_MATRIX_PREFLIGHT = "FULL_MATRIX_PREFLIGHT"


class ObservedModelExposure(StrEnum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    RUN_EVIDENCE_ONLY = "RUN_EVIDENCE_ONLY"


class ConfigurationRequirement(_FrozenModel):
    reference: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    kind: ConfigurationKind
    required: bool = True


class ProviderRouteRequirement(_FrozenModel):
    route_identity: str = Field(min_length=1, max_length=800)
    expected_identity: str | None = Field(default=None, min_length=1, max_length=800)
    configuration_references: tuple[ConfigurationRequirement, ...] = ()
    requires_network: bool = True


class HarnessRequirement(_FrozenModel):
    harness_id: str = Field(min_length=1, max_length=100)
    executable: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._+-]+$")
    requested_model: str = Field(min_length=1, max_length=300)
    compatible_models: frozenset[str] = Field(default_factory=frozenset)
    supported_lanes: frozenset[EvaluationLane] = Field(min_length=1)
    selected_lane: EvaluationLane
    trace_support: TraceSupport
    required_trace_support: TraceSupport


class TaskRequirement(_FrozenModel):
    package_path: str = Field(min_length=1, max_length=500)
    selected_lane: EvaluationLane

    @field_validator("package_path")
    @classmethod
    def package_path_is_safe(cls, value: str) -> str:
        from harnesslab.tasks.models import validate_relative_path

        normalized = validate_relative_path(value)
        if not normalized.startswith("tasks/"):
            raise ValueError("task package must live under tasks/")
        return normalized


class ComparabilityControl(_FrozenModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    expected_identity: str = Field(min_length=1, max_length=800)
    actual_identity: str = Field(min_length=1, max_length=800)
    blocking: bool = False


class FrozenResourceEnvelope(_FrozenModel):
    frozen: bool = True
    expected_identity: Sha256Digest
    actual_identity: Sha256Digest | None = None


class PreflightSpecification(_FrozenModel):
    """Secret-free declaration of everything that must be ready before spend."""

    schema_version: Literal[1] = 1
    docker_required: bool = True
    database_required: bool = True
    minimum_free_bytes: int = Field(default=1_073_741_824, ge=0)
    required_images: tuple[str, ...] = ()
    configurations: tuple[ConfigurationRequirement, ...] = ()
    provider_routes: tuple[ProviderRouteRequirement, ...] = ()
    harnesses: tuple[HarnessRequirement, ...] = ()
    tasks: tuple[TaskRequirement, ...] = ()
    network_policy: NetworkPolicy = NetworkPolicy.DENY
    comparability_controls: tuple[ComparabilityControl, ...] = ()
    resource_envelope: FrozenResourceEnvelope | None = None
    budget: BudgetEstimateRequest | None = None

    @field_validator("required_images")
    @classmethod
    def images_are_safe(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("required images must be unique")
        if any(
            not value.strip() or any(character.isspace() for character in value) for value in values
        ):
            raise ValueError("image references must be non-empty and contain no whitespace")
        return values

    @model_validator(mode="after")
    def identities_are_unique(self) -> PreflightSpecification:
        references = [item.reference for item in self.configurations]
        references.extend(
            item.reference
            for route in self.provider_routes
            for item in route.configuration_references
        )
        if len(set(references)) != len(references):
            raise ValueError("configuration references must be declared exactly once")
        harness_ids = [item.harness_id for item in self.harnesses]
        if len(set(harness_ids)) != len(harness_ids):
            raise ValueError("harness requirements must be unique")
        task_paths = [item.package_path for item in self.tasks]
        if len(set(task_paths)) != len(task_paths):
            raise ValueError("task requirements must be unique")
        return self

    @property
    def digest(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


class TaskObservation(_FrozenModel):
    valid: bool
    supported_lanes: frozenset[EvaluationLane] = Field(default_factory=frozenset)


class PreflightObservations(_FrozenModel):
    docker_available: bool | None = None
    database_ready: bool | None = None
    disk_free_bytes: int | None = Field(default=None, ge=0)
    image_available: dict[str, bool] = Field(default_factory=dict)
    configuration_present: dict[str, bool] = Field(default_factory=dict)
    configuration_valid: dict[str, bool] = Field(default_factory=dict)
    harness_runtime_available: dict[str, bool] = Field(default_factory=dict)
    tasks: dict[str, TaskObservation] = Field(default_factory=dict)


class PreflightFinding(_FrozenModel):
    check_id: str = Field(min_length=1, max_length=200)
    status: CheckStatus
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=100)
    detail: str = Field(min_length=1, max_length=500)
    remediation: str = Field(min_length=1, max_length=500)


class PreflightReport(_FrozenModel):
    status: PreflightStatus
    specification_digest: Sha256Digest
    findings: tuple[PreflightFinding, ...] = Field(min_length=1)
    budget_estimate: BudgetEstimate | None = None
    provider_calls: Literal[0] = 0
    judge_calls: Literal[0] = 0

    @model_validator(mode="after")
    def status_matches_findings(self) -> PreflightReport:
        expected = (
            PreflightStatus.BLOCKED
            if any(item.status is CheckStatus.BLOCKED for item in self.findings)
            else PreflightStatus.READY_WITH_WARNINGS
            if any(item.status is CheckStatus.WARNING for item in self.findings)
            else PreflightStatus.READY
        )
        if self.status is not expected:
            raise ValueError("preflight status does not match its findings")
        return self


class MatrixCellRequirement(_FrozenModel):
    """Exact model/harness/route binding checked before Matrix spend."""

    cell_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=100)
    roles: tuple[Literal["M", "H", "P"], ...] = Field(min_length=1)
    route_identity: str = Field(min_length=1, max_length=800)
    requested_model: str = Field(min_length=1, max_length=300)
    harness_id: str = Field(min_length=1, max_length=100)
    runtime_profile_identity: str = Field(min_length=1, max_length=800)
    image_reference: str | None = Field(default=None, min_length=1, max_length=500)
    trace_support: TraceSupport
    required_trace_support: TraceSupport
    observed_model_exposure: ObservedModelExposure
    observed_model_required: bool = True
    resource_envelope: FrozenResourceEnvelope

    @model_validator(mode="after")
    def roles_are_unique(self) -> MatrixCellRequirement:
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("Matrix cell roles must be unique")
        return self


class MatrixPreflightSpecification(_FrozenModel):
    """Additive authorization layer over the backward-compatible Phase M checks."""

    schema_version: Literal[1] = 1
    authorization_level: PreflightAuthorizationLevel
    prerequisites: PreflightSpecification
    cells: tuple[MatrixCellRequirement, ...] = Field(min_length=1)
    matrix_budget: MatrixBudgetEstimateRequest
    fixed_subject_call_count: int = Field(ge=1)
    fixed_judge_call_count: int = Field(ge=0)
    spend_authorized: bool = False

    @model_validator(mode="after")
    def bindings_are_complete(self) -> MatrixPreflightSpecification:
        if self.prerequisites.budget is not None:
            raise ValueError(
                "Matrix preflight uses matrix_budget, not the legacy homogeneous budget"
            )
        cell_ids = [cell.cell_id for cell in self.cells]
        if len(set(cell_ids)) != len(cell_ids):
            raise ValueError("Matrix cell IDs must be unique")
        budgets = {cell.cell_id: cell for cell in self.matrix_budget.subject_cells}
        if set(cell_ids) != set(budgets):
            raise ValueError("every Matrix cell must have exactly one heterogeneous budget")
        routes = {route.route_identity for route in self.prerequisites.provider_routes}
        harnesses = {harness.harness_id for harness in self.prerequisites.harnesses}
        images = set(self.prerequisites.required_images)
        for cell in self.cells:
            budget = budgets[cell.cell_id]
            if budget.route_identity != cell.route_identity:
                raise ValueError("Matrix cell and budget route identities must match")
            if cell.route_identity not in routes:
                raise ValueError("Matrix cell route must be declared in prerequisites")
            if cell.harness_id not in harnesses:
                raise ValueError("Matrix cell harness must be declared in prerequisites")
            if cell.image_reference is not None and cell.image_reference not in images:
                raise ValueError("Matrix cell image must be declared in prerequisites")
        subject_calls = sum(item.planned_run_count for item in budgets.values())
        if subject_calls != self.fixed_subject_call_count:
            raise ValueError("fixed subject call count must match the Matrix budget")
        if self.matrix_budget.judge_campaign.planned_call_count != self.fixed_judge_call_count:
            raise ValueError("fixed Judge call count must match the Matrix budget")
        if self.authorization_level is PreflightAuthorizationLevel.CANARY_PREFLIGHT:
            if any(item.planned_run_count != 1 for item in budgets.values()):
                raise ValueError("CANARY_PREFLIGHT requires exactly one launch per cell")
            if self.fixed_judge_call_count > 1:
                raise ValueError("CANARY_PREFLIGHT permits at most one Judge launch")
        return self

    @property
    def digest(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


class MatrixPreflightReport(_FrozenModel):
    status: PreflightStatus
    authorization_level: PreflightAuthorizationLevel
    specification_digest: Sha256Digest
    findings: tuple[PreflightFinding, ...] = Field(min_length=1)
    matrix_budget_estimate: MatrixBudgetEstimate
    provider_calls: Literal[0] = 0
    judge_calls: Literal[0] = 0

    @model_validator(mode="after")
    def status_matches_findings(self) -> MatrixPreflightReport:
        expected = (
            PreflightStatus.BLOCKED
            if any(item.status is CheckStatus.BLOCKED for item in self.findings)
            else PreflightStatus.READY_WITH_WARNINGS
            if any(item.status is CheckStatus.WARNING for item in self.findings)
            else PreflightStatus.READY
        )
        if self.status is not expected:
            raise ValueError("Matrix preflight status does not match its findings")
        return self
