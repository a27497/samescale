from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.tasks.quality import QualificationStatus, TaskQualification


class TaskSplitError(ValueError):
    """A development/held-out split is leaky, unqualified, or not reproducible."""


class SplitRole(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    HELD_OUT = "HELD_OUT"


class DevelopmentExposure(StrEnum):
    NOT_USED = "NOT_USED"
    USED = "USED"
    UNKNOWN = "UNKNOWN"


class SplitCheckStatus(StrEnum):
    CLEAR = "CLEAR"
    BLOCKED = "BLOCKED"


class SplitFindingCode(StrEnum):
    MISSING_DEVELOPMENT_TASKS = "MISSING_DEVELOPMENT_TASKS"
    MISSING_HELD_OUT_TASKS = "MISSING_HELD_OUT_TASKS"
    DUPLICATE_ASSIGNMENT = "DUPLICATE_ASSIGNMENT"
    TASK_IDENTITY_CROSS_SPLIT = "TASK_IDENTITY_CROSS_SPLIT"
    TASK_ID_CROSS_SPLIT = "TASK_ID_CROSS_SPLIT"
    PROVENANCE_CROSS_SPLIT = "PROVENANCE_CROSS_SPLIT"
    HELD_OUT_DEVELOPMENT_EXPOSURE = "HELD_OUT_DEVELOPMENT_EXPOSURE"
    HELD_OUT_EXPOSURE_UNKNOWN = "HELD_OUT_EXPOSURE_UNKNOWN"
    HELD_OUT_TASK_UNQUALIFIED = "HELD_OUT_TASK_UNQUALIFIED"


class TaskSplitAssignment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: SplitRole
    qualification: TaskQualification
    development_exposure: DevelopmentExposure

    @model_validator(mode="after")
    def development_tasks_are_exposed(self) -> TaskSplitAssignment:
        if (
            self.role is SplitRole.DEVELOPMENT
            and self.development_exposure is not DevelopmentExposure.USED
        ):
            raise ValueError("development tasks must be marked as used for development")
        return self

    @property
    def task_key(self) -> tuple[str, str, str]:
        task = self.qualification.quality.task
        return task.task_id, task.task_version, task.task_digest


class SplitFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: SplitFindingCode
    task_ids: tuple[str, ...]
    detail: str = Field(min_length=1, max_length=500)


class SplitLeakageReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    status: SplitCheckStatus
    findings: tuple[SplitFinding, ...]

    @property
    def report_identity(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


def _finding(code: SplitFindingCode, task_ids: tuple[str, ...], detail: str) -> SplitFinding:
    return SplitFinding(code=code, task_ids=tuple(sorted(set(task_ids))), detail=detail)


def evaluate_split(assignments: tuple[TaskSplitAssignment, ...]) -> SplitLeakageReport:
    """Check exact identity, task-id, provenance lineage, exposure, and qualification leakage."""

    findings: list[SplitFinding] = []
    development = tuple(item for item in assignments if item.role is SplitRole.DEVELOPMENT)
    held_out = tuple(item for item in assignments if item.role is SplitRole.HELD_OUT)
    if not development:
        findings.append(
            _finding(
                SplitFindingCode.MISSING_DEVELOPMENT_TASKS,
                (),
                "a frozen split requires at least one development task",
            )
        )
    if not held_out:
        findings.append(
            _finding(
                SplitFindingCode.MISSING_HELD_OUT_TASKS,
                (),
                "a frozen split requires at least one held-out task",
            )
        )

    seen: dict[tuple[SplitRole, tuple[str, str, str]], list[str]] = {}
    for item in assignments:
        seen.setdefault((item.role, item.task_key), []).append(item.task_key[0])
    for (_role, _key), task_ids in seen.items():
        if len(task_ids) > 1:
            findings.append(
                _finding(
                    SplitFindingCode.DUPLICATE_ASSIGNMENT,
                    tuple(task_ids),
                    "the same task identity is assigned more than once",
                )
            )

    development_keys = {item.task_key for item in development}
    held_out_keys = {item.task_key for item in held_out}
    for task_id, _version, _digest in sorted(development_keys & held_out_keys):
        findings.append(
            _finding(
                SplitFindingCode.TASK_IDENTITY_CROSS_SPLIT,
                (task_id,),
                "the exact task identity appears in development and held-out sets",
            )
        )

    development_ids = {item.task_key[0] for item in development}
    held_out_ids = {item.task_key[0] for item in held_out}
    exact_overlap_ids = {key[0] for key in development_keys & held_out_keys}
    for task_id in sorted((development_ids & held_out_ids) - exact_overlap_ids):
        findings.append(
            _finding(
                SplitFindingCode.TASK_ID_CROSS_SPLIT,
                (task_id,),
                "versions of the same task id cannot straddle development and held-out sets",
            )
        )

    for held_out_item in held_out:
        task_id = held_out_item.task_key[0]
        if held_out_item.development_exposure is DevelopmentExposure.USED:
            findings.append(
                _finding(
                    SplitFindingCode.HELD_OUT_DEVELOPMENT_EXPOSURE,
                    (task_id,),
                    "a held-out task is known to have been used during development",
                )
            )
        elif held_out_item.development_exposure is DevelopmentExposure.UNKNOWN:
            findings.append(
                _finding(
                    SplitFindingCode.HELD_OUT_EXPOSURE_UNKNOWN,
                    (task_id,),
                    "held-out development exposure must be explicitly known absent",
                )
            )
        if held_out_item.qualification.status is not QualificationStatus.QUALIFIED:
            findings.append(
                _finding(
                    SplitFindingCode.HELD_OUT_TASK_UNQUALIFIED,
                    (task_id,),
                    "held-out claims require a qualified task with evidence",
                )
            )

        held_out_lineage = held_out_item.qualification.quality.provenance.lineage_identities
        for development_item in development:
            development_lineage = (
                development_item.qualification.quality.provenance.lineage_identities
            )
            if held_out_lineage & development_lineage:
                findings.append(
                    _finding(
                        SplitFindingCode.PROVENANCE_CROSS_SPLIT,
                        (development_item.task_key[0], task_id),
                        "development and held-out tasks share a source or parent identity",
                    )
                )

    ordered = tuple(
        sorted(
            findings,
            key=lambda item: (item.code.value, item.task_ids, item.detail),
        )
    )
    return SplitLeakageReport(
        status=SplitCheckStatus.BLOCKED if ordered else SplitCheckStatus.CLEAR,
        findings=ordered,
    )


def _assignment_key(item: TaskSplitAssignment) -> tuple[str, str, str, str]:
    task_id, task_version, task_digest = item.task_key
    return item.role.value, task_id, task_version, task_digest


class TaskSplitFreeze(BaseModel):
    """Timestamp-free, deterministic development/held-out assignment artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    split_id: Identifier
    methodology_id: Literal["harnesslab-dev-holdout-v1"] = "harnesslab-dev-holdout-v1"
    assignments: tuple[TaskSplitAssignment, ...] = Field(min_length=2)
    leakage_report: SplitLeakageReport
    split_identity: Sha256Digest

    @model_validator(mode="after")
    def freeze_is_canonical_and_valid(self) -> TaskSplitFreeze:
        if tuple(sorted(self.assignments, key=_assignment_key)) != self.assignments:
            raise ValueError("split assignments must use canonical order")
        current_report = evaluate_split(self.assignments)
        if current_report != self.leakage_report:
            raise ValueError("split leakage report does not match assignments")
        if current_report.status is not SplitCheckStatus.CLEAR:
            raise ValueError("a blocked split cannot be frozen")
        if self.split_identity != canonical_digest(self.payload()):
            raise ValueError("split identity does not match the frozen payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"split_identity"})

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


def freeze_split(split_id: str, assignments: tuple[TaskSplitAssignment, ...]) -> TaskSplitFreeze:
    ordered = tuple(sorted(assignments, key=_assignment_key))
    report = evaluate_split(ordered)
    if report.status is SplitCheckStatus.BLOCKED:
        codes = ", ".join(finding.code.value for finding in report.findings)
        raise TaskSplitError(f"development/held-out split is blocked: {codes}")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "split_id": split_id,
        "methodology_id": "harnesslab-dev-holdout-v1",
        "assignments": [item.model_dump(mode="json") for item in ordered],
        "leakage_report": report.model_dump(mode="json"),
    }
    payload["split_identity"] = canonical_digest(payload)
    return TaskSplitFreeze.model_validate(payload)


def load_split_freeze(path: Path) -> TaskSplitFreeze:
    try:
        return TaskSplitFreeze.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise TaskSplitError(f"invalid task split freeze: {type(exc).__name__}") from exc
