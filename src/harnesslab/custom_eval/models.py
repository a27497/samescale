from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.contracts.common import EvaluationLane, Identifier, Sha256Digest
from harnesslab.experiment.methodology import EvaluationMode


class SourceType(StrEnum):
    LOCAL_REPOSITORY = "local_repository"
    LOCAL_FOLDER = "local_folder"
    GIT_EXACT_COMMIT = "git_exact_commit"
    PREPARED_PACKAGE = "prepared_package"


class TaskNamespace(StrEnum):
    CUSTOM = "CUSTOM"
    OFFICIAL = "OFFICIAL"


class CriterionKind(StrEnum):
    BUILD = "build"
    UNIT_TEST = "unit_test"
    HIDDEN_TEST = "hidden_test"
    CONTRACT_CHECK = "contract_check"
    SECURITY_CHECK = "security_check"
    PERFORMANCE_THRESHOLD = "performance_threshold"
    DETERMINISTIC_RULE = "deterministic_rule"
    JUDGE_RUBRIC = "judge_rubric"

    @property
    def deterministic(self) -> bool:
        return self is not CriterionKind.JUDGE_RUBRIC


class CriterionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INFRA = "INFRA"
    MISSING = "MISSING"
    NOT_EVALUATED = "NOT_EVALUATED"


class CustomEvaluationPreset(StrEnum):
    QUICK = "Quick"
    COMPARE = "Compare"
    FORMAL = "Formal"

    @property
    def evaluation_mode(self) -> EvaluationMode:
        return {
            CustomEvaluationPreset.QUICK: EvaluationMode.QUICK,
            CustomEvaluationPreset.COMPARE: EvaluationMode.INFORMAL,
            CustomEvaluationPreset.FORMAL: EvaluationMode.FORMAL_EXHAUSTIVE,
        }[self]

    @property
    def repeat_count(self) -> int:
        return self.evaluation_mode.repeat_count


class EvaluationCriterion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Identifier
    kind: CriterionKind
    description: str = Field(min_length=1, max_length=1000)
    required: bool = True
    threshold: float | None = None
    unit: str | None = Field(default=None, max_length=50)
    rubric: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def criterion_contract_is_coherent(self) -> EvaluationCriterion:
        if self.kind is CriterionKind.PERFORMANCE_THRESHOLD and self.threshold is None:
            raise ValueError("performance threshold criteria require a threshold")
        if self.kind is not CriterionKind.PERFORMANCE_THRESHOLD and self.threshold is not None:
            raise ValueError("threshold is only valid for performance criteria")
        if self.kind is CriterionKind.JUDGE_RUBRIC and not self.rubric:
            raise ValueError("Judge rubric criteria require a rubric")
        if self.kind is not CriterionKind.JUDGE_RUBRIC and self.rubric is not None:
            raise ValueError("rubric is only valid for Judge criteria")
        return self


class CustomEvaluationDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    owner: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    criteria: tuple[EvaluationCriterion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def criterion_ids_are_unique(self) -> CustomEvaluationDefinition:
        if len({criterion.id for criterion in self.criteria}) != len(self.criteria):
            raise ValueError("duplicate custom evaluation criterion id")
        return self


class SourceProvenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: SourceType
    source_reference: str = Field(min_length=1, max_length=2000)
    source_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    source_content_identity: Sha256Digest
    imported_at: datetime


class ManagedTaskRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    namespace: Literal[TaskNamespace.CUSTOM] = TaskNamespace.CUSTOM
    task_id: Identifier
    task_version: str
    task_owner: str = Field(min_length=1, max_length=200)
    task_category: str = Field(min_length=1, max_length=100)
    task_identity: Sha256Digest
    workspace_identity: Sha256Digest
    verifier_identity: Sha256Digest
    criteria: tuple[EvaluationCriterion, ...]
    criteria_identity: Sha256Digest
    managed_snapshot_identity: Sha256Digest
    provenance: SourceProvenance

    @property
    def reference(self) -> str:
        return f"{self.task_id}@{self.task_version}"


class CustomTaskBuilderSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    task_id: Identifier
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    domain: str = Field(min_length=1, max_length=100)
    owner: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    instruction_source: str
    workspace_source: str
    verifier_source: str
    oracle_source: str
    verifier_entrypoint: str = "verifier/verify.py"
    verifier_version: str = "1"
    verifier_timeout_seconds: int = Field(default=15, gt=0, le=300)
    timeout_seconds: int = Field(default=90, gt=0, le=86_400)
    max_output_tokens: int | None = Field(default=None, gt=0)
    lane_support: frozenset[EvaluationLane] = frozenset(
        {EvaluationLane.MODEL, EvaluationLane.HARNESS}
    )
    protected_paths: tuple[str, ...] = ()
    metadata: dict[str, str] = Field(default_factory=dict)
    criteria: tuple[EvaluationCriterion, ...] = Field(min_length=1)


class CustomTarget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Identifier
    requested_model: str = Field(min_length=1, max_length=300)
    harness: str = Field(min_length=1, max_length=100)
    harness_version: str = Field(min_length=1, max_length=100)


class CustomPlanRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    evaluation_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    preset: CustomEvaluationPreset
    task_references: tuple[str, ...] = Field(min_length=1)
    targets: tuple[CustomTarget, ...] = Field(min_length=1)
    execution_seed: int = 0

    @model_validator(mode="after")
    def selections_are_unique(self) -> CustomPlanRequest:
        if len(set(self.task_references)) != len(self.task_references):
            raise ValueError("duplicate custom task reference")
        if len({target.id for target in self.targets}) != len(self.targets):
            raise ValueError("duplicate custom target id")
        return self


class CustomPlannedTask(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace: Literal[TaskNamespace.CUSTOM] = TaskNamespace.CUSTOM
    reference: str
    task_id: str
    task_version: str
    task_identity: Sha256Digest
    workspace_identity: Sha256Digest
    verifier_identity: Sha256Digest
    managed_snapshot_identity: Sha256Digest
    criteria: tuple[EvaluationCriterion, ...]


class CustomRunSlot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slot_id: Sha256Digest
    slot_order: int = Field(ge=0)
    evaluation_id: str
    task: CustomPlannedTask
    target: CustomTarget
    repeat_index: int = Field(ge=0)


class CustomEvaluationPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    namespace: Literal[TaskNamespace.CUSTOM] = TaskNamespace.CUSTOM
    official_benchmark_eligible: Literal[False] = False
    evaluation_id: str
    name: str
    preset: CustomEvaluationPreset
    evaluation_mode: EvaluationMode
    repeat_count: Literal[1, 3, 5]
    execution_seed: int
    tasks: tuple[CustomPlannedTask, ...]
    targets: tuple[CustomTarget, ...]
    run_slots: tuple[CustomRunSlot, ...]

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


class CriterionEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion_id: Identifier
    status: CriterionStatus
    detail: str | None = Field(default=None, max_length=1000)
    measured_value: float | None = None
    evidence_identity: Sha256Digest | None = None


class CustomRunEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slot_id: Sha256Digest
    criteria: tuple[CriterionEvidence, ...] = ()
    infrastructure_failure: bool = False
    missing: bool = False
    cost: float | None = Field(default=None, ge=0)
    trace_identity: Sha256Digest | None = None

    @model_validator(mode="after")
    def terminal_state_is_unique(self) -> CustomRunEvidence:
        if self.infrastructure_failure and self.missing:
            raise ValueError("a run cannot be both missing and infrastructure failure")
        if (self.infrastructure_failure or self.missing) and self.criteria:
            raise ValueError("infra/missing runs cannot carry verifier criteria")
        return self


class CriteriaDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal[CriterionStatus.PASS, CriterionStatus.FAIL]
    deterministic_l0_failed: bool
    reason_codes: tuple[str, ...]


class CustomTargetReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: CustomTarget
    planned_runs: int = Field(ge=0)
    capability_passes: int = Field(ge=0)
    capability_failures: int = Field(ge=0)
    infrastructure_failures: int = Field(ge=0)
    missing_runs: int = Field(ge=0)
    pass_rate: float | None = Field(default=None, ge=0, le=1)
    cost_availability: Literal["AVAILABLE", "PARTIAL", "NOT_AVAILABLE"]
    total_cost: float | None
    trace_availability: Literal["AVAILABLE", "PARTIAL", "NOT_AVAILABLE"]


class CustomEvaluationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    namespace: Literal[TaskNamespace.CUSTOM] = TaskNamespace.CUSTOM
    official_benchmark_eligible: Literal[False] = False
    universal_model_claim_allowed: Literal[False] = False
    evaluation_id: str
    plan_digest: Sha256Digest
    preset: CustomEvaluationPreset
    repeat_count: Literal[1, 3, 5]
    custom_tasks: tuple[CustomPlannedTask, ...]
    targets: tuple[CustomTargetReport, ...]
    deterministic_verifier_evidence: tuple[CustomRunEvidence, ...]
    missing_treatment: Literal["EXCLUDED_FROM_CAPABILITY_DENOMINATOR"] = (
        "EXCLUDED_FROM_CAPABILITY_DENOMINATOR"
    )
    infrastructure_treatment: Literal["EXCLUDED_AND_REPORTED_SEPARATELY"] = (
        "EXCLUDED_AND_REPORTED_SEPARATELY"
    )
    comparability_limits: tuple[str, ...]


def canonical_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def parse_task_reference(value: str) -> tuple[str, str]:
    task_id, separator, version = value.rpartition("@")
    if not separator or not task_id or not version:
        raise ValueError("custom task reference must use <task-id>@<version>")
    return task_id, version


def validate_relative_source(value: str) -> str:
    if "\x00" in value:
        raise ValueError("source path contains a null byte")
    return value
