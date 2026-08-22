from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harnesslab.contracts.common import EvaluationLane, Identifier, Sha256Digest
from harnesslab.contracts.task import ExpectedToolContract, ResourceBudget


def validate_relative_path(value: str) -> str:
    """Validate a repository-relative POSIX path without resolving the filesystem."""

    from pathlib import PurePosixPath

    if not value or "\\" in value:
        raise ValueError("path must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError("path must not be absolute or contain '.' or '..'")
    if any(not part for part in path.parts):
        raise ValueError("path contains an empty component")
    return path.as_posix()


class VerifierPackageDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["python"] = "python"
    version: str = Field(min_length=1, max_length=100)
    entrypoint: str
    timeout_seconds: int = Field(default=15, gt=0, le=300)

    _entrypoint_is_safe = field_validator("entrypoint")(validate_relative_path)


class OraclePackageDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = "oracle"

    _path_is_safe = field_validator("path")(validate_relative_path)


class TaskPackageManifest(BaseModel):
    """Strict on-disk task.yaml schema that resolves into the TaskDefinition contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    id: Identifier
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    domain: str = Field(min_length=1, max_length=100)
    lane_support: frozenset[EvaluationLane] = Field(min_length=1)
    instruction_path: str = "instruction.md"
    workspace_path: str = "workspace"
    context_path: str | None = None
    verifier: VerifierPackageDefinition
    oracle: OraclePackageDefinition
    budget: ResourceBudget
    expected_tools: tuple[ExpectedToolContract, ...] = ()
    protected_paths: tuple[str, ...] = ()
    metadata: dict[str, str] = Field(default_factory=dict)

    _paths_are_safe = field_validator("instruction_path", "workspace_path", "context_path")(
        lambda value: None if value is None else validate_relative_path(value)
    )
    _protected_paths_are_safe = field_validator("protected_paths")(
        lambda values: tuple(validate_relative_path(value) for value in values)
    )


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    detail: str | None = Field(default=None, max_length=500)


class VerifierReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    checks: tuple[CheckResult, ...] = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=1000)


class OutcomeCategory(StrEnum):
    SUBJECT_RESULT = "subject_result"
    VERIFIER_ERROR = "verifier_error"
    TIMEOUT = "timeout"
    MALFORMED_OUTPUT = "malformed_output"
    PROTECTED_FILE_VIOLATION = "protected_file_violation"


class VerifierExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    checks: tuple[CheckResult, ...] = ()
    summary: str = Field(min_length=1, max_length=1000)
    category: OutcomeCategory
    exit_code: int | None
    duration_ms: int = Field(ge=0)
    stdout_digest: Sha256Digest
    stderr_digest: Sha256Digest
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    @model_validator(mode="after")
    def errors_fail_closed(self) -> VerifierExecutionResult:
        if self.category is not OutcomeCategory.SUBJECT_RESULT and (self.passed or self.score != 0):
            raise ValueError("verifier errors must fail closed with score 0")
        return self


class EvidenceAsset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1, max_length=500)
    digest: Sha256Digest


class EvidenceManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    task_id: Identifier
    task_version: str
    task_digest: Sha256Digest
    workspace_digest: Sha256Digest
    verifier: EvidenceAsset
    result: VerifierExecutionResult
    run_kind: Literal["baseline", "oracle", "fake_subject"]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )


class TaskValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    valid: bool
    task_id: Identifier
    task_version: str
    task_digest: Sha256Digest
    baseline: EvidenceManifest
    oracle: EvidenceManifest
    errors: tuple[str, ...] = ()
