from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.comparability.models import ComparabilityIntent, canonical_digest
from harnesslab.contracts.common import EvaluationLane
from harnesslab.experiment.dispatch import (
    BlockAwareDispatcher,
    BlockDispatchResult,
    DispatchProfile,
)
from harnesslab.experiment.executor import ExperimentLaneBinding, ExperimentRunExecutor
from harnesslab.experiment.methodology import (
    BudgetContract,
    BudgetDimension,
    BudgetDimensionStatus,
    BudgetScope,
    EvaluationMode,
    FunnelStage,
    ProviderAvailability,
    load_evaluation_methodology,
)
from harnesslab.experiment.plan import (
    MethodologyV2ExperimentPlan,
    PlannedCell,
    build_methodology_v2_plan,
)
from harnesslab.experiment.queue import enqueue_plan
from harnesslab.experiment.spec import (
    AblationSpec,
    ExperimentCellSpec,
    ExperimentSpec,
    PairedComparisonSpec,
)
from harnesslab.registry.models import HarnessDefinition, HarnessProfileDefinition
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.release.contracts import load_core_corpus
from harnesslab.tasks.package import TaskPackage

V6_EXPERIMENT_ID = "core-real-matrix-v6"
V6_EXECUTION_SEED = 20260824
V6_SCHEDULE_SEED = 20260831
V6_CORPUS_REFERENCE = "release/core-corpus-v4.json"
V6_METHODOLOGY_REFERENCE = "release/evaluation-methodology-v2.json"
V6_THROUGHPUT_R2_SELECTED_PROFILE_ID = "V6_PROFILE_C_C6_H3"


@dataclass(frozen=True)
class V6CellBinding:
    cell_id: str
    provider_profile_id: str
    harness_profile_id: str


V6_CELL_BINDINGS = (
    V6CellBinding(
        "model-gpt56-relay-responses",
        "gpt56-relay-gpt56-responses",
        "direct-gpt56-relay-gpt56-responses",
    ),
    V6CellBinding(
        "model-qwen38-alibaba-bailian-chat",
        "alibaba-bailian-qwen3.8-max-chat",
        "direct-alibaba-bailian-qwen3.8-max-chat",
    ),
    V6CellBinding(
        "model-deepseek-v4pro-chat",
        "deepseek-official-v4pro-chat",
        "direct-deepseek-official-v4pro-chat",
    ),
    V6CellBinding(
        "harness-codex-gpt56-medium",
        "gpt56-relay-gpt56-responses",
        "codex-gpt56-medium",
    ),
    V6CellBinding(
        "harness-codex-gpt56-high",
        "gpt56-relay-gpt56-responses",
        "codex-gpt56-high",
    ),
    V6CellBinding(
        "harness-claude-qwen38-alibaba-bailian",
        "alibaba-bailian-qwen3.8-max-messages",
        "claude-qwen38-alibaba-bailian",
    ),
    V6CellBinding(
        "model-deepseek-v4flash-chat",
        "deepseek-official-v4flash-chat",
        "direct-deepseek-official-v4flash-chat",
    ),
)


V6_JUDGE_CANDIDATES = (
    "alibaba-bailian-glm-5.2-chat",
    "alibaba-bailian-deepseek-v4-pro-chat",
)


def v6_dispatch_profiles() -> tuple[DispatchProfile, DispatchProfile]:
    provider_caps = {
        "gpt56-relay": 2,
        "alibaba-bailian": 2,
        "deepseek-official": 2,
    }
    return (
        DispatchProfile(
            profile_id="V6_PROFILE_A_C4",
            global_concurrency=4,
            max_harness_concurrency=2,
            max_direct_concurrency=4,
            provider_concurrency=provider_caps,
        ),
        DispatchProfile(
            profile_id="V6_PROFILE_B_C6",
            global_concurrency=6,
            max_harness_concurrency=2,
            max_direct_concurrency=4,
            provider_concurrency=provider_caps,
        ),
    )


def v6_throughput_r2_profiles() -> tuple[DispatchProfile, DispatchProfile, DispatchProfile]:
    """Bounded local-qualification candidates; no profile permits adaptive limits."""

    a, b = v6_dispatch_profiles()
    return (
        a,
        b,
        DispatchProfile(
            profile_id="V6_PROFILE_C_C6_H3",
            global_concurrency=6,
            max_harness_concurrency=3,
            max_direct_concurrency=4,
            provider_concurrency={
                "gpt56-relay": 2,
                "alibaba-bailian": 2,
                "deepseek-official": 2,
            },
        ),
    )


def selected_v6_dispatch_profile() -> DispatchProfile:
    """Return the fixed R2 profile selected by real local host telemetry."""

    return next(
        profile
        for profile in v6_throughput_r2_profiles()
        if profile.profile_id == V6_THROUGHPUT_R2_SELECTED_PROFILE_ID
    )


def v6_budget_contract() -> BudgetContract:
    """Preserve V5 ceilings without inventing one Harness-wide turn count."""

    unavailable = {
        "status": BudgetDimensionStatus.NOT_AVAILABLE,
        "value": None,
        "scopes": (BudgetScope.NOT_AVAILABLE,),
    }
    return BudgetContract(
        max_wall_time=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=300,
            unit="seconds",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_output_tokens=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=2000,
            unit="tokens",
            scopes=(BudgetScope.PER_PROVIDER_REQUEST,),
        ),
        max_model_turns=BudgetDimension(unit="turns", **unavailable),
        max_tool_calls=BudgetDimension(unit="calls", **unavailable),
        max_provider_requests=BudgetDimension(unit="requests", **unavailable),
        max_cost=BudgetDimension(unit="USD", **unavailable),
    )


def _harness_profiles(
    harnesses: tuple[HarnessDefinition, ...],
) -> dict[str, tuple[HarnessDefinition, HarnessProfileDefinition]]:
    return {
        profile.profile_id: (harness, profile)
        for harness in harnesses
        for profile in harness.profiles
    }


def build_v6_plan(
    repository_root: Path,
    environment: Mapping[str, str] | None = None,
) -> MethodologyV2ExperimentPlan:
    root = repository_root.resolve()
    selected_environment = environment or {}
    catalog = build_registry_catalog(root, selected_environment)
    profiles = {item.profile_id: item for item in catalog.provider_model_profiles}
    harness_profiles = _harness_profiles(catalog.harnesses)
    corpus = load_core_corpus(root / V6_CORPUS_REFERENCE)
    task_paths = tuple(task.package_path for task in corpus.tasks)
    packages = tuple(TaskPackage.load(root / path) for path in task_paths)
    budget_identities = {
        canonical_digest(package.definition.budget.model_dump(mode="json")) for package in packages
    }
    if len(budget_identities) != 1:
        raise ValueError("V6 Core tasks do not share one resource budget identity")
    network_policies = {package.definition.budget.network_policy for package in packages}
    if len(network_policies) != 1:
        raise ValueError("V6 Core tasks do not share one network policy")
    budget_identity = next(iter(budget_identities))
    network_policy = next(iter(network_policies))

    cells: list[ExperimentCellSpec] = []
    for binding in V6_CELL_BINDINGS:
        try:
            provider_profile = profiles[binding.provider_profile_id]
            harness, harness_profile = harness_profiles[binding.harness_profile_id]
        except KeyError as exc:
            raise ValueError("V6 references a missing registry profile") from exc
        if provider_profile.profile_id not in harness_profile.supported_provider_profile_ids:
            raise ValueError("V6 provider and Harness profiles are not explicitly compatible")
        cells.append(
            ExperimentCellSpec(
                id=binding.cell_id,
                lane=(
                    EvaluationLane.MODEL
                    if harness.harness_id == "direct-model"
                    else EvaluationLane.HARNESS
                ),
                requested_model=provider_profile.requested_model,
                provider_route=provider_profile.provider_route_identity,
                profile_reference=harness_profile.profile_reference,
                profile_identity=canonical_digest(
                    {
                        "provider_profile_identity": provider_profile.profile_identity,
                        "harness_id": harness.harness_id,
                        "harness_version": harness.version,
                        "profile_reference": harness_profile.profile_reference,
                    }
                ),
                harness=harness.harness_id,
                harness_version=harness.version,
                harness_config_identity=harness_profile.harness_config_identity,
                reasoning_effort=(
                    harness_profile.reasoning_effort
                    if harness_profile.reasoning_effort is not None
                    else provider_profile.reasoning_effort
                ),
                resource_budget_identity=budget_identity,
                network_policy=network_policy,
                runner_contract=harness.runner_contract,
                credential_reference=provider_profile.credential_reference,
                base_provider_profile_identity=provider_profile.base_provider_profile_identity,
                resource_envelope_identity=canonical_digest(
                    {
                        "task_budget_identity": budget_identity,
                        "request_timeout_seconds": provider_profile.request_timeout_seconds,
                        "max_output_tokens": provider_profile.max_output_tokens,
                    }
                ),
            )
        )

    spec = ExperimentSpec(
        experiment_id=V6_EXPERIMENT_ID,
        name="HarnessLab Core Real Matrix v6",
        task_packages=task_paths,
        cells=tuple(cells),
        repeat_count=5,
        execution_seed=V6_EXECUTION_SEED,
        comparison_intent=ComparabilityIntent.HARNESS_UPLIFT,
        paired_comparisons=(
            PairedComparisonSpec(
                id="gpt56-relay-direct-vs-codex",
                left_cell_id="model-gpt56-relay-responses",
                right_cell_id="harness-codex-gpt56-medium",
            ),
        ),
        ablations=(
            AblationSpec(
                id="codex-gpt56-reasoning-effort",
                base_cell_id="harness-codex-gpt56-medium",
                variant_cell_id="harness-codex-gpt56-high",
                changed_dimension="reasoning_effort",
                intent=ComparabilityIntent.CONTROLLED_ABLATION,
            ),
        ),
    )
    methodology = load_evaluation_methodology(root / V6_METHODOLOGY_REFERENCE)
    availability = {cell.provider_route: ProviderAvailability.AVAILABLE for cell in cells}
    plan = build_methodology_v2_plan(
        spec,
        root,
        methodology=methodology,
        evaluation_mode=EvaluationMode.FORMAL_EXHAUSTIVE,
        funnel_stage=FunnelStage.FORMAL,
        schedule_seed=V6_SCHEDULE_SEED,
        budget_contract=v6_budget_contract(),
        provider_availability=availability,
    )
    validate_v6_plan(plan)
    return plan


def validate_v6_plan(plan: MethodologyV2ExperimentPlan) -> None:
    expected_cells = {item.cell_id for item in V6_CELL_BINDINGS}
    if plan.experiment_id != V6_EXPERIMENT_ID or plan.schema_version != 2:
        raise ValueError("V6 plan identity or schema drifted")
    if plan.scheduling_policy != "BLOCKED_INTERLEAVED_SCHEDULING":
        raise ValueError("V6 plan lacks blocked-interleaved scheduling")
    if len(plan.tasks) != 18 or len(plan.cells) != 7 or len(plan.run_slots) != 630:
        raise ValueError("V6 plan is not exactly 18x7x5")
    if {cell.id for cell in plan.cells} != expected_cells:
        raise ValueError("V6 cell set drifted")
    if len(plan.schedule_blocks) != 90:
        raise ValueError("V6 plan must contain exactly 90 schedule blocks")
    if any(
        len(block.slot_ids) != 7 or len(set(block.cell_execution_order)) != 7
        for block in plan.schedule_blocks
    ):
        raise ValueError("every V6 block must contain seven unique cells")
    if any("opencode-go" in cell.provider_route for cell in plan.cells):
        raise ValueError("V6 subject plan retains an OpenCode route")


def v6_binding_identity(cell: PlannedCell) -> str:
    """Bind executable lane wiring without credentials or endpoint values."""

    return canonical_digest(
        {
            "cell_id": cell.id,
            "requested_model": cell.requested_model,
            "provider_route": cell.provider_route,
            "profile_identity": cell.profile_identity,
            "harness": cell.harness,
            "harness_version": cell.harness_version,
            "harness_config_identity": cell.harness_config_identity,
            "reasoning_effort": cell.reasoning_effort,
            "runner_contract": cell.runner_contract,
            "credential_reference": cell.credential_reference,
        }
    )


async def dispatch_v6_queue(
    repository_root: Path,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    bindings: Mapping[str, ExperimentLaneBinding],
    binding_identities: Mapping[str, str],
    owner: str,
    max_runs: int,
    profile: DispatchProfile | None = None,
) -> BlockDispatchResult:
    """Authoritative V6 production path; it never falls back to schema-v1 claiming."""

    plan = build_v6_plan(repository_root, {})
    expected_cells = {cell.id for cell in plan.cells}
    if set(bindings) != expected_cells:
        raise ValueError("V6 bindings must exactly match the frozen seven-cell set")
    expected_identities = {cell.id: v6_binding_identity(cell) for cell in plan.cells}
    if dict(binding_identities) != expected_identities:
        raise ValueError("V6 executable binding identity drifted from the frozen plan")
    selected = profile or selected_v6_dispatch_profile()
    async with session_factory() as session, session.begin():
        await enqueue_plan(session, plan)
    executor = ExperimentRunExecutor(
        repository_root=repository_root,
        session_factory=session_factory,
        bindings=bindings,
        owner=owner,
    )
    dispatcher = BlockAwareDispatcher(executor=executor, plan=plan, profile=selected)
    return await dispatcher.run(max_runs=max_runs)
