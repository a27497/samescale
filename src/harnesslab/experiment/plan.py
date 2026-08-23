from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane, NetworkPolicy, Sha256Digest
from harnesslab.experiment.spec import (
    AblationSpec,
    ExperimentCellSpec,
    ExperimentSpec,
    ExperimentSpecError,
    PairedComparisonSpec,
)
from harnesslab.tasks.package import TaskPackage, TaskPackageError


class PlannedTask(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    package_path: str
    task_id: str
    task_version: str
    task_digest: Sha256Digest
    workspace_input_digest: Sha256Digest
    context_identity: Sha256Digest | None
    verifier_identity: Sha256Digest
    budget_identity: Sha256Digest
    network_policy: NetworkPolicy


class PlannedCell(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    lane: Literal[EvaluationLane.MODEL, EvaluationLane.HARNESS]
    requested_model: str
    provider_route: str
    profile_reference: str
    profile_identity: Sha256Digest
    harness: str
    harness_version: str
    harness_config_identity: Sha256Digest
    reasoning_effort: str | None
    resource_budget_identity: Sha256Digest
    network_policy: NetworkPolicy
    runner_contract: str
    credential_reference: str | None

    @classmethod
    def from_spec(cls, cell: ExperimentCellSpec) -> PlannedCell:
        return cls.model_validate(cell.model_dump(mode="json"))


class ExperimentRunSlot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slot_id: Sha256Digest
    slot_order: int
    experiment_id: str
    cell_id: str
    lane: Literal[EvaluationLane.MODEL, EvaluationLane.HARNESS]
    task: PlannedTask
    repeat_index: int
    paired_slot_identity: Sha256Digest
    requested_model: str
    provider_route: str
    profile_identity: Sha256Digest
    harness: str
    harness_version: str
    harness_config_identity: Sha256Digest
    reasoning_effort: str | None
    runner_contract: str


class ExperimentPlan(BaseModel):
    """Canonical, timestamp-free expansion used as durable queue identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    experiment_id: str
    name: str
    execution_seed: int
    repeat_count: int
    comparison_intent: str
    tasks: tuple[PlannedTask, ...]
    cells: tuple[PlannedCell, ...]
    paired_comparisons: tuple[PairedComparisonSpec, ...]
    ablations: tuple[AblationSpec, ...]
    run_slots: tuple[ExperimentRunSlot, ...]

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


@dataclass(frozen=True)
class _ResolvedTask:
    task: PlannedTask
    lane_support: frozenset[EvaluationLane]


def _resolve_task(repository_root: Path, package_path: str) -> _ResolvedTask:
    candidate = (repository_root / package_path).resolve()
    tasks_root = (repository_root / "tasks").resolve()
    if tasks_root not in candidate.parents:
        raise ExperimentSpecError("task path escapes the repository task root")
    try:
        package = TaskPackage.load(candidate)
    except TaskPackageError as exc:
        raise ExperimentSpecError(f"cannot resolve task package {package_path}: {exc}") from exc
    definition = package.definition
    return _ResolvedTask(
        task=PlannedTask(
            package_path=package_path,
            task_id=definition.id,
            task_version=definition.version,
            task_digest=definition.content_digest,
            workspace_input_digest=definition.workspace.digest,
            context_identity=(
                definition.context_bundle.digest if definition.context_bundle else None
            ),
            verifier_identity=package.verifier_digest,
            budget_identity=canonical_digest(definition.budget.model_dump(mode="json")),
            network_policy=definition.budget.network_policy,
        ),
        lane_support=definition.lane_support,
    )


def build_experiment_plan(spec: ExperimentSpec, repository_root: Path) -> ExperimentPlan:
    resolved_tasks = tuple(
        sorted(
            (_resolve_task(repository_root, path) for path in spec.task_packages),
            key=lambda resolved: (
                resolved.task.task_id,
                resolved.task.task_version,
                resolved.task.task_digest,
            ),
        )
    )
    tasks = tuple(resolved.task for resolved in resolved_tasks)
    lane_support = {
        resolved.task.package_path: resolved.lane_support for resolved in resolved_tasks
    }
    cells = tuple(
        sorted((PlannedCell.from_spec(cell) for cell in spec.cells), key=lambda cell: cell.id)
    )
    slots: list[ExperimentRunSlot] = []
    for cell in cells:
        for task in tasks:
            if cell.lane not in lane_support[task.package_path]:
                raise ExperimentSpecError(
                    f"task {task.task_id} does not support cell {cell.id} lane {cell.lane.value}"
                )
            if cell.resource_budget_identity != task.budget_identity:
                raise ExperimentSpecError(
                    f"cell {cell.id} budget identity does not match task {task.task_id}"
                )
            if cell.network_policy is not task.network_policy:
                raise ExperimentSpecError(
                    f"cell {cell.id} network policy does not match task {task.task_id}"
                )
            for repeat_index in range(spec.repeat_count):
                pair_identity = canonical_digest(
                    {
                        "experiment_id": spec.experiment_id,
                        "task_id": task.task_id,
                        "task_version": task.task_version,
                        "task_digest": task.task_digest,
                        "repeat_index": repeat_index,
                    }
                )
                identity = {
                    "experiment_id": spec.experiment_id,
                    "cell_id": cell.id,
                    "lane": cell.lane.value,
                    "task": task.model_dump(mode="json"),
                    "repeat_index": repeat_index,
                    "requested_model": cell.requested_model,
                    "provider_route": cell.provider_route,
                    "profile_identity": cell.profile_identity,
                    "harness": cell.harness,
                    "harness_version": cell.harness_version,
                    "harness_config_identity": cell.harness_config_identity,
                    "reasoning_effort": cell.reasoning_effort,
                    "runner_contract": cell.runner_contract,
                }
                slots.append(
                    ExperimentRunSlot(
                        slot_id=canonical_digest(identity),
                        slot_order=len(slots),
                        experiment_id=spec.experiment_id,
                        cell_id=cell.id,
                        lane=cell.lane,
                        task=task,
                        repeat_index=repeat_index,
                        paired_slot_identity=pair_identity,
                        requested_model=cell.requested_model,
                        provider_route=cell.provider_route,
                        profile_identity=cell.profile_identity,
                        harness=cell.harness,
                        harness_version=cell.harness_version,
                        harness_config_identity=cell.harness_config_identity,
                        reasoning_effort=cell.reasoning_effort,
                        runner_contract=cell.runner_contract,
                    )
                )
    if len({slot.slot_id for slot in slots}) != len(slots):
        raise ExperimentSpecError("matrix expansion produced duplicate logical run slots")
    return ExperimentPlan(
        experiment_id=spec.experiment_id,
        name=spec.name,
        execution_seed=spec.execution_seed,
        repeat_count=spec.repeat_count,
        comparison_intent=spec.comparison_intent.value,
        tasks=tasks,
        cells=cells,
        paired_comparisons=tuple(sorted(spec.paired_comparisons, key=lambda pair: pair.id)),
        ablations=tuple(sorted(spec.ablations, key=lambda ablation: ablation.id)),
        run_slots=tuple(slots),
    )
