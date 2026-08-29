from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane, NetworkPolicy, Sha256Digest
from harnesslab.experiment.methodology import (
    BudgetContract,
    EvaluationMethodologyV2,
    EvaluationMode,
    FunnelStage,
    ProviderAvailability,
    TaskTier,
)
from harnesslab.experiment.spec import (
    AblationSpec,
    ExperimentCellSpec,
    ExperimentSpec,
    ExperimentSpecError,
    PairedComparisonSpec,
)
from harnesslab.tasks.health import TaskHealthAttestation, validate_task_health
from harnesslab.tasks.package import TaskPackage, TaskPackageError
from harnesslab.tasks.tier_b import (
    load_tier_b_qualification,
    validate_tier_b_qualification,
)


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
    base_provider_profile_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    effective_runtime_profile_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    resource_envelope_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

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
    base_provider_profile_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    effective_runtime_profile_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    resource_envelope_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


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


class ScheduleBlock(BaseModel):
    """One reproducible task/repeat block with interleaved cell execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    block_identity: Sha256Digest
    task_id: str
    task_version: str
    task_digest: Sha256Digest
    repeat_index: int
    provider_availability: ProviderAvailability
    unavailable_provider_routes: tuple[str, ...] = ()
    cell_execution_order: tuple[str, ...]
    slot_ids: tuple[Sha256Digest, ...]


class MethodologyV2ExperimentPlan(BaseModel):
    """Schema-v2 plan with frozen methodology, budget, health, and schedule identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[2] = 2
    experiment_id: str
    name: str
    methodology_id: str
    methodology_digest: Sha256Digest
    evaluation_mode: EvaluationMode
    funnel_stage: FunnelStage
    execution_seed: int
    schedule_seed: int
    scheduling_policy: Literal["BLOCKED_INTERLEAVED_SCHEDULING"] = "BLOCKED_INTERLEAVED_SCHEDULING"
    repeat_count: Literal[1, 3, 5]
    comparison_intent: str
    budget_contract: BudgetContract
    budget_contract_identity: Sha256Digest
    benchmark_tier: TaskTier | None = Field(default=None, exclude_if=lambda value: value is None)
    tier_b_qualification_id: str | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    tier_b_qualification_digest: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    task_health_attestations: tuple[TaskHealthAttestation, ...]
    tasks: tuple[PlannedTask, ...]
    cells: tuple[PlannedCell, ...]
    paired_comparisons: tuple[PairedComparisonSpec, ...]
    ablations: tuple[AblationSpec, ...]
    schedule_blocks: tuple[ScheduleBlock, ...]
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


type AnyExperimentPlan = ExperimentPlan | MethodologyV2ExperimentPlan


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
                if cell.base_provider_profile_identity is not None:
                    identity["base_provider_profile_identity"] = cell.base_provider_profile_identity
                if cell.effective_runtime_profile_identity is not None:
                    identity["effective_runtime_profile_identity"] = (
                        cell.effective_runtime_profile_identity
                    )
                if cell.resource_envelope_identity is not None:
                    identity["resource_envelope_identity"] = cell.resource_envelope_identity
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
                        base_provider_profile_identity=cell.base_provider_profile_identity,
                        effective_runtime_profile_identity=(
                            cell.effective_runtime_profile_identity
                        ),
                        resource_envelope_identity=cell.resource_envelope_identity,
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


def build_blocked_interleaved_schedule(
    plan: ExperimentPlan,
    *,
    schedule_seed: int,
    provider_availability: dict[str, ProviderAvailability] | None = None,
) -> tuple[tuple[ScheduleBlock, ...], tuple[ExperimentRunSlot, ...]]:
    """Order immutable slots by task/repeat blocks and seeded cell permutations."""

    availability = provider_availability or {}
    slots_by_key = {
        (
            slot.task.task_id,
            slot.task.task_version,
            slot.task.task_digest,
            slot.repeat_index,
            slot.cell_id,
        ): slot
        for slot in plan.run_slots
    }
    blocks: list[ScheduleBlock] = []
    ordered_slots: list[ExperimentRunSlot] = []
    for repeat_index in range(plan.repeat_count):
        for task in plan.tasks:
            block_identity = canonical_digest(
                {
                    "methodology": "harnesslab-evaluation-methodology-v2",
                    "experiment_id": plan.experiment_id,
                    "task_id": task.task_id,
                    "task_version": task.task_version,
                    "task_digest": task.task_digest,
                    "repeat_index": repeat_index,
                }
            )
            cell_ids = sorted(
                (cell.id for cell in plan.cells),
                key=lambda cell_id: hashlib.sha256(
                    f"{schedule_seed}:{block_identity}:{cell_id}".encode()
                ).hexdigest(),
            )
            routes = {cell.id: cell.provider_route for cell in plan.cells}
            unavailable = tuple(
                sorted(
                    {
                        routes[cell_id]
                        for cell_id in cell_ids
                        if availability.get(routes[cell_id], ProviderAvailability.AVAILABLE)
                        is ProviderAvailability.PROVIDER_UNAVAILABLE
                    }
                )
            )
            block_slots = tuple(
                slots_by_key[
                    (
                        task.task_id,
                        task.task_version,
                        task.task_digest,
                        repeat_index,
                        cell_id,
                    )
                ]
                for cell_id in cell_ids
            )
            blocks.append(
                ScheduleBlock(
                    block_identity=block_identity,
                    task_id=task.task_id,
                    task_version=task.task_version,
                    task_digest=task.task_digest,
                    repeat_index=repeat_index,
                    provider_availability=(
                        ProviderAvailability.PROVIDER_UNAVAILABLE
                        if unavailable
                        else ProviderAvailability.AVAILABLE
                    ),
                    unavailable_provider_routes=unavailable,
                    cell_execution_order=tuple(cell_ids),
                    slot_ids=tuple(slot.slot_id for slot in block_slots),
                )
            )
            ordered_slots.extend(block_slots)
    scheduled_slots = tuple(
        slot.model_copy(update={"slot_order": slot_order})
        for slot_order, slot in enumerate(ordered_slots)
    )
    if {slot.slot_id for slot in scheduled_slots} != {slot.slot_id for slot in plan.run_slots}:
        raise ExperimentSpecError("blocked scheduling changed logical slot identity")
    return tuple(blocks), scheduled_slots


def build_methodology_v2_plan(
    spec: ExperimentSpec,
    repository_root: Path,
    *,
    methodology: EvaluationMethodologyV2,
    evaluation_mode: EvaluationMode,
    funnel_stage: FunnelStage,
    schedule_seed: int,
    budget_contract: BudgetContract,
    provider_availability: dict[str, ProviderAvailability] | None = None,
    tier_b_qualification_path: Path | None = None,
) -> MethodologyV2ExperimentPlan:
    """Build a health-gated schema-v2 plan without altering schema-v1 semantics."""

    if spec.repeat_count != evaluation_mode.repeat_count:
        raise ExperimentSpecError("repeat count does not match explicit evaluation mode")
    allowed_stage = {
        EvaluationMode.QUICK: {FunnelStage.SMOKE, FunnelStage.BREADTH},
        EvaluationMode.INFORMAL: {FunnelStage.INFORMAL},
        EvaluationMode.FORMAL_EXHAUSTIVE: {FunnelStage.FORMAL},
    }
    if funnel_stage not in allowed_stage[evaluation_mode]:
        raise ExperimentSpecError("funnel stage does not match explicit evaluation mode")

    base = build_experiment_plan(spec, repository_root)
    tier_a = next(
        policy for policy in methodology.task_tiers if policy.tier.value == "TIER_A_MICRO_CONTRACT"
    )
    planned_task_ids = {task.task_id for task in base.tasks}
    planned_packages = tuple(
        TaskPackage.load(repository_root / task.package_path) for task in base.tasks
    )
    repo_engineering = tuple(
        package.manifest.repo_engineering is not None for package in planned_packages
    )
    benchmark_tier: TaskTier | None = None
    qualification_id: str | None = None
    qualification_digest: str | None = None
    if any(repo_engineering):
        if not all(repo_engineering):
            raise ExperimentSpecError("one plan cannot aggregate Tier-A and Tier-B task outcomes")
        if tier_b_qualification_path is None:
            raise ExperimentSpecError("Tier-B plans require a frozen qualification artifact")
        try:
            qualification = load_tier_b_qualification(tier_b_qualification_path)
            validate_tier_b_qualification(repository_root, qualification)
        except ValueError as exc:
            raise ExperimentSpecError(f"invalid Tier-B qualification: {exc}") from exc
        qualified_ids = {task.task_id for task in qualification.tasks}
        if not planned_task_ids <= qualified_ids:
            raise ExperimentSpecError("Tier-B task is absent from the qualification inventory")
        benchmark_tier = TaskTier.TIER_B_REPO_ENGINEERING
        qualification_id = qualification.qualification_id
        qualification_digest = qualification.qualification_digest
    elif not planned_task_ids <= set(tier_a.current_task_ids):
        raise ExperimentSpecError("task tier assignment is missing from methodology v2")
    repeats = methodology.task_health.verifier_health_repeats
    attestations = tuple(
        sorted(
            (
                validate_task_health(repository_root / task.package_path, repeats=repeats)
                for task in base.tasks
            ),
            key=lambda item: (item.task_id, item.task_version, item.task_digest),
        )
    )
    blocks, scheduled_slots = build_blocked_interleaved_schedule(
        base,
        schedule_seed=schedule_seed,
        provider_availability=provider_availability,
    )
    return MethodologyV2ExperimentPlan(
        experiment_id=base.experiment_id,
        name=base.name,
        methodology_id=methodology.methodology_id,
        methodology_digest=methodology.digest,
        evaluation_mode=evaluation_mode,
        funnel_stage=funnel_stage,
        execution_seed=base.execution_seed,
        schedule_seed=schedule_seed,
        repeat_count=evaluation_mode.repeat_count,
        comparison_intent=base.comparison_intent,
        budget_contract=budget_contract,
        budget_contract_identity=budget_contract.identity,
        benchmark_tier=benchmark_tier,
        tier_b_qualification_id=qualification_id,
        tier_b_qualification_digest=qualification_digest,
        task_health_attestations=attestations,
        tasks=base.tasks,
        cells=base.cells,
        paired_comparisons=base.paired_comparisons,
        ablations=base.ablations,
        schedule_blocks=blocks,
        run_slots=scheduled_slots,
    )


def executable_block_slot_ids(block: ScheduleBlock) -> tuple[str, ...]:
    """Fail closed before acquisition when any provider in a block is unavailable."""

    if block.provider_availability is ProviderAvailability.PROVIDER_UNAVAILABLE:
        return ()
    return block.slot_ids


def load_experiment_plan_payload(raw: Any) -> AnyExperimentPlan:
    if not isinstance(raw, dict):
        raise ExperimentSpecError("experiment plan must contain a mapping")
    schema_version = raw.get("schema_version")
    try:
        if schema_version == 1:
            return ExperimentPlan.model_validate(raw)
        if schema_version == 2:
            return MethodologyV2ExperimentPlan.model_validate(raw)
    except ValidationError as exc:
        raise ExperimentSpecError(f"invalid experiment plan: {exc}") from exc
    raise ExperimentSpecError("unsupported experiment plan schema version")
