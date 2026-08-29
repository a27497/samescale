from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from harnesslab.comparability.models import canonical_digest
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.spec import ExperimentCellSpec


class MethodologyError(ValueError):
    """A methodology artifact or policy decision is invalid."""


class EvaluationMode(StrEnum):
    QUICK = "QUICK"
    INFORMAL = "INFORMAL"
    FORMAL_EXHAUSTIVE = "FORMAL_EXHAUSTIVE"

    @property
    def repeat_count(self) -> int:
        return {
            EvaluationMode.QUICK: 1,
            EvaluationMode.INFORMAL: 3,
            EvaluationMode.FORMAL_EXHAUSTIVE: 5,
        }[self]


class ComparisonType(StrEnum):
    END_TO_END_SYSTEM_COMPARISON = "END_TO_END_SYSTEM_COMPARISON"
    MODEL_COMPARISON = "MODEL_COMPARISON"
    HARNESS_UPLIFT = "HARNESS_UPLIFT"
    CONTROLLED_ABLATION = "CONTROLLED_ABLATION"


class TaskTier(StrEnum):
    TIER_A_MICRO_CONTRACT = "TIER_A_MICRO_CONTRACT"
    TIER_B_REPO_ENGINEERING = "TIER_B_REPO_ENGINEERING"
    TIER_C_LONG_HORIZON_AGENTIC = "TIER_C_LONG_HORIZON_AGENTIC"


class FunnelStage(StrEnum):
    PREFLIGHT = "PREFLIGHT"
    SMOKE = "SMOKE"
    BREADTH = "BREADTH"
    INFORMAL = "INFORMAL"
    FORMAL = "FORMAL"
    DISCRIMINATIVE_STRESS = "DISCRIMINATIVE_STRESS"


class StageDecision(StrEnum):
    GO = "GO"
    STOP = "STOP"


class ProviderAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class BudgetDimensionStatus(StrEnum):
    ENFORCED = "ENFORCED"
    OBSERVED_ONLY = "OBSERVED_ONLY"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class BudgetScope(StrEnum):
    """The resource boundary to which a budget dimension applies."""

    PER_PROVIDER_REQUEST = "PER_PROVIDER_REQUEST"
    PER_LOGICAL_RUN = "PER_LOGICAL_RUN"
    PER_MODEL_TURN = "PER_MODEL_TURN"
    OBSERVED_ONLY = "OBSERVED_ONLY"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class BudgetFairnessClass(StrEnum):
    RESOURCE_NORMALIZED_COMPARISON = "RESOURCE_NORMALIZED_COMPARISON"
    NATIVE_HARNESS_SYSTEM_COMPARISON = "NATIVE_HARNESS_SYSTEM_COMPARISON"


class MetricAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class RecoveryEligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    CAPABILITY_TERMINAL_NO_RETRY = "CAPABILITY_TERMINAL_NO_RETRY"
    INFRA_RECOVERY_EXHAUSTED = "INFRA_RECOVERY_EXHAUSTED"
    NOT_INFRASTRUCTURE_FAILURE = "NOT_INFRASTRUCTURE_FAILURE"


class NamedPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)


class EvaluationModePolicy(NamedPolicy):
    mode: EvaluationMode
    repeat_count: Literal[1, 3, 5]
    selection_scope: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def repeats_match_mode(self) -> EvaluationModePolicy:
        if self.repeat_count != self.mode.repeat_count:
            raise ValueError("evaluation mode repeat count does not match frozen semantics")
        return self


class ComparisonTypePolicy(NamedPolicy):
    comparison_type: ComparisonType
    required_controls: tuple[str, ...]
    declared_treatment: str
    claim_boundary: str = Field(min_length=1, max_length=1000)


class TaskTierPolicy(NamedPolicy):
    tier: TaskTier
    current_task_ids: tuple[str, ...] = ()
    universal_agent_benchmark: Literal[False] = False


class FunnelStagePolicy(NamedPolicy):
    stage: FunnelStage
    repeat_count: int | None = Field(default=None, ge=1, le=5)
    selection_scope: str = Field(min_length=1, max_length=500)
    explicit_decision_required: Literal[True] = True
    auto_promote: Literal[False] = False


class TaskHealthPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_expected: Literal["FAIL"] = "FAIL"
    oracle_expected: Literal["PASS"] = "PASS"
    oracle_health_repeats: Literal[5] = 5
    verifier_health_repeats: Literal[5] = 5
    identical_terminal_result_required: Literal[True] = True
    task_version_change_required_for_semantic_change: Literal[True] = True


class SchedulingPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Literal["BLOCKED_INTERLEAVED_SCHEDULING"] = "BLOCKED_INTERLEAVED_SCHEDULING"
    block_key: tuple[Literal["task_id"], Literal["repeat_index"]] = (
        "task_id",
        "repeat_index",
    )
    deterministic_seed_required: Literal[True] = True
    persist_block_identity: Literal[True] = True
    persist_cell_execution_order: Literal[True] = True
    provider_check_before_block: Literal[True] = True
    unavailable_provider_state: Literal["PROVIDER_UNAVAILABLE"] = "PROVIDER_UNAVAILABLE"
    provider_substitution_allowed: Literal[False] = False
    pause_entire_affected_block: Literal[True] = True


class InfraRecoveryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    maximum_recovery_attempts: Literal[1] = 1
    capability_retry_allowed: Literal[False] = False
    semantic_retry_allowed: Literal[False] = False
    fallback_allowed: Literal[False] = False
    original_attempt_immutable: Literal[True] = True
    recovery_attempt_new_identity: Literal[True] = True
    exhausted_state: Literal["INFRA_RECOVERY_EXHAUSTED"] = "INFRA_RECOVERY_EXHAUSTED"


class BudgetPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dimensions: tuple[
        Literal[
            "max_wall_time",
            "max_output_tokens",
            "max_model_turns",
            "max_tool_calls",
            "max_provider_requests",
            "max_cost",
        ],
        ...,
    ]
    missing_metric_state: Literal["NOT_AVAILABLE"] = "NOT_AVAILABLE"
    formal_comparability_required: Literal[True] = True


class MetricPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    primary_portfolio_metric: Literal["PASS_AT_1"] = "PASS_AT_1"
    repeated_trial_metric: Literal["TRIAL_SUCCESS_RATE"] = "TRIAL_SUCCESS_RATE"
    supported_metrics: tuple[str, ...]
    capability_denominator: Literal["capability_pass+capability_fail"] = (
        "capability_pass+capability_fail"
    )
    required_operational_counts: tuple[
        Literal[
            "planned",
            "capability_n",
            "infra_count",
            "missing_count",
            "recovery_attempt_count",
        ],
        ...,
    ]
    immutable_price_evidence_required_for_cost_claims: Literal[True] = True
    pricing_snapshot_is_retroactive_truth: Literal[False] = False
    unrelated_task_pooling_allowed: Literal[False] = False


class JudgeFunnelPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pilot_id: Literal["JUDGE_PILOT"] = "JUDGE_PILOT"
    pilot_slots: Literal[21] = 21
    formal_id: Literal["JUDGE_FORMAL"] = "JUDGE_FORMAL"
    formal_slots: Literal[63] = 63
    auto_promote: Literal[False] = False
    formal_entry_requirements: tuple[str, ...]
    post_output_schema_relaxation_allowed: Literal[False] = False


class CriticalComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    comparison_type: ComparisonType
    left_cell_id: str
    right_cell_id: str


class DefaultPortfolioPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    breadth_task_count: Literal[18] = 18
    breadth_cell_ids: tuple[str, ...]
    breadth_repeats: Literal[1] = 1
    critical_task_ids: tuple[str, ...]
    critical_comparisons: tuple[CriticalComparison, ...]
    critical_repeats: Literal[3] = 3
    reuse_existing_logical_slots: Literal[True] = True
    breadth_subject_runs: Literal[126] = 126
    critical_comparison_memberships: Literal[162] = 162
    critical_unique_subject_runs: Literal[135] = 135
    breadth_overlap_subject_runs: Literal[45] = 45
    incremental_critical_subject_runs: Literal[90] = 90
    projected_unique_subject_runs: Literal[216] = 216
    reduction_subject_runs: Literal[414] = 414
    formal_exhaustive_subject_runs: Literal[630] = 630


class BackwardCompatibilityPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    historical_experiment_id: Literal["core-real-matrix-v3"] = "core-real-matrix-v3"
    historical_plan_digest: str
    historical_methodology: Literal["FORMAL_EXHAUSTIVE_MODE"] = "FORMAL_EXHAUSTIVE_MODE"
    rewrite_historical_plans: Literal[False] = False
    preserve_existing_evidence: Literal[True] = True


class EvaluationMethodologyV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[2] = 2
    methodology_id: Literal["harnesslab-evaluation-methodology-v2"] = (
        "harnesslab-evaluation-methodology-v2"
    )
    active: Literal[True] = True
    task_tiers: tuple[TaskTierPolicy, ...]
    evaluation_modes: tuple[EvaluationModePolicy, ...]
    comparison_types: tuple[ComparisonTypePolicy, ...]
    task_health: TaskHealthPolicy
    funnel: tuple[FunnelStagePolicy, ...]
    scheduling: SchedulingPolicy
    infra_recovery: InfraRecoveryPolicy
    budget: BudgetPolicy
    metrics: MetricPolicy
    judge_funnel: JudgeFunnelPolicy
    default_portfolio: DefaultPortfolioPolicy
    backward_compatibility: BackwardCompatibilityPolicy

    @model_validator(mode="after")
    def policy_is_complete(self) -> EvaluationMethodologyV2:
        if {item.mode for item in self.evaluation_modes} != set(EvaluationMode):
            raise ValueError("methodology must define exactly all evaluation modes")
        if {item.comparison_type for item in self.comparison_types} != set(ComparisonType):
            raise ValueError("methodology must define exactly all comparison types")
        if {item.tier for item in self.task_tiers} != set(TaskTier):
            raise ValueError("methodology must define exactly all task tiers")
        if tuple(item.stage for item in self.funnel) != tuple(FunnelStage):
            raise ValueError("methodology funnel order is not canonical")
        if len(set(self.default_portfolio.breadth_cell_ids)) != len(
            self.default_portfolio.breadth_cell_ids
        ):
            raise ValueError("portfolio contains duplicate breadth cells")
        if len(set(self.default_portfolio.critical_task_ids)) != len(
            self.default_portfolio.critical_task_ids
        ):
            raise ValueError("portfolio contains duplicate critical tasks")
        project_default_portfolio(self.default_portfolio)
        return self

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


class BudgetDimension(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: BudgetDimensionStatus
    value: int | float | None = Field(default=None, ge=0)
    unit: str = Field(min_length=1, max_length=40)
    # Omitted only for backward-compatible reads of methodology-v2 artifacts.
    # exclude_if preserves their historical canonical JSON and digest.
    scopes: tuple[BudgetScope, ...] | None = Field(
        default=None,
        min_length=1,
        exclude_if=lambda value: value is None,
    )

    @model_validator(mode="after")
    def availability_matches_value(self) -> BudgetDimension:
        if self.status is BudgetDimensionStatus.NOT_AVAILABLE and self.value is not None:
            raise ValueError("NOT_AVAILABLE budget dimension cannot contain a value")
        if self.status is not BudgetDimensionStatus.NOT_AVAILABLE and self.value is None:
            raise ValueError("available budget dimension requires a value")
        if self.scopes is None:
            return self
        if len(set(self.scopes)) != len(self.scopes):
            raise ValueError("budget dimension scopes must be unique")
        if self.status is BudgetDimensionStatus.NOT_AVAILABLE:
            if self.scopes != (BudgetScope.NOT_AVAILABLE,):
                raise ValueError("NOT_AVAILABLE budget dimension requires NOT_AVAILABLE scope")
        elif self.status is BudgetDimensionStatus.OBSERVED_ONLY:
            if self.scopes != (BudgetScope.OBSERVED_ONLY,):
                raise ValueError("OBSERVED_ONLY budget dimension requires OBSERVED_ONLY scope")
        elif any(
            scope in {BudgetScope.NOT_AVAILABLE, BudgetScope.OBSERVED_ONLY} for scope in self.scopes
        ):
            raise ValueError("ENFORCED budget dimension requires an enforcement scope")
        return self


class BudgetContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_wall_time: BudgetDimension
    max_output_tokens: BudgetDimension
    max_model_turns: BudgetDimension
    max_tool_calls: BudgetDimension
    max_provider_requests: BudgetDimension
    max_cost: BudgetDimension

    @model_validator(mode="after")
    def positive_non_count_limits(self) -> BudgetContract:
        for name in ("max_wall_time", "max_output_tokens", "max_cost"):
            dimension = getattr(self, name)
            if dimension.value == 0:
                raise ValueError(f"{name} must be positive when available")
        return self

    @property
    def identity(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class MetricValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: MetricAvailability
    value: int | float | None = None

    @model_validator(mode="after")
    def availability_matches_value(self) -> MetricValue:
        if self.status is MetricAvailability.NOT_AVAILABLE and self.value is not None:
            raise ValueError("NOT_AVAILABLE metric cannot contain a value")
        if self.status is MetricAvailability.AVAILABLE and self.value is None:
            raise ValueError("AVAILABLE metric requires a value")
        return self


class OperationalCounts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    planned: int = Field(ge=0)
    capability_n: int = Field(ge=0)
    infra_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    recovery_attempt_count: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_reconcile(self) -> OperationalCounts:
        if self.capability_n + self.infra_count + self.missing_count != self.planned:
            raise ValueError("operational counts do not reconcile to planned")
        return self


class PortfolioProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    breadth_subject_runs: int = Field(ge=0)
    critical_comparison_memberships: int = Field(ge=0)
    critical_unique_subject_runs: int = Field(ge=0)
    breadth_overlap_subject_runs: int = Field(ge=0)
    incremental_critical_subject_runs: int = Field(ge=0)
    projected_unique_subject_runs: int = Field(ge=0)
    formal_exhaustive_subject_runs: int = Field(ge=1)
    reduction_subject_runs: int = Field(ge=0)
    reduction_fraction: float = Field(ge=0, le=1)


class RecoveryAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    eligibility: RecoveryEligibility
    original_slot_id: str
    original_attempt_identity: str
    recovery_attempt_count: int = Field(ge=0)
    recovery_attempt_identity: str | None = None


def load_evaluation_methodology(path: Path) -> EvaluationMethodologyV2:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        return EvaluationMethodologyV2.model_validate(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise MethodologyError(f"invalid evaluation methodology: {type(exc).__name__}") from exc


def classify_comparison(
    left: ExperimentCellSpec,
    right: ExperimentCellSpec,
    *,
    declared_ablation_dimension: str | None = None,
) -> ComparisonType:
    """Classify the strongest claim supported by declared cell controls."""

    tracked = {
        "requested_model": left.requested_model != right.requested_model,
        "provider_route": left.provider_route != right.provider_route,
        "harness": left.harness != right.harness,
        "harness_version": left.harness_version != right.harness_version,
        "reasoning_effort": left.reasoning_effort != right.reasoning_effort,
        "resource_budget_identity": (
            left.resource_budget_identity != right.resource_budget_identity
        ),
        "network_policy": left.network_policy != right.network_policy,
        "runner_contract": left.runner_contract != right.runner_contract,
    }
    changed = {field for field, differs in tracked.items() if differs}
    if declared_ablation_dimension is not None:
        if changed == {declared_ablation_dimension}:
            return ComparisonType.CONTROLLED_ABLATION
        return ComparisonType.END_TO_END_SYSTEM_COMPARISON
    harness_treatment = changed <= {
        "harness",
        "harness_version",
        "runner_contract",
    } and bool(changed)
    if harness_treatment:
        return ComparisonType.HARNESS_UPLIFT
    model_treatment = changed == {"requested_model"}
    if model_treatment:
        return ComparisonType.MODEL_COMPARISON
    return ComparisonType.END_TO_END_SYSTEM_COMPARISON


def require_comparison_type(
    left: ExperimentCellSpec,
    right: ExperimentCellSpec,
    claimed: ComparisonType,
    *,
    declared_ablation_dimension: str | None = None,
) -> None:
    classified = classify_comparison(
        left, right, declared_ablation_dimension=declared_ablation_dimension
    )
    if classified is not claimed:
        raise MethodologyError(
            f"comparison supports {classified.value}, not claimed {claimed.value}"
        )


def require_provider_identity(expected: ExperimentCellSpec, candidate: ExperimentCellSpec) -> None:
    if (
        candidate.requested_model != expected.requested_model
        or candidate.provider_route != expected.provider_route
        or candidate.profile_identity != expected.profile_identity
    ):
        raise MethodologyError("provider substitution changes immutable treatment identity")


def require_comparable_budgets(left: BudgetContract, right: BudgetContract) -> None:
    if (
        classify_budget_fairness(left, right)
        is not BudgetFairnessClass.RESOURCE_NORMALIZED_COMPARISON
    ):
        raise MethodologyError(
            "formal comparison budget contracts are not resource-normalized comparable"
        )


def classify_budget_fairness(left: BudgetContract, right: BudgetContract) -> BudgetFairnessClass:
    """Classify resource fairness without inferring scope from a numeric value.

    A strong resource-normalized comparison requires identical scoped contracts,
    a common enforced logical-run wall, and either a common aggregate compute
    envelope or a common trusted logical-run cost ceiling.
    """

    if left.identity != right.identity:
        return BudgetFairnessClass.NATIVE_HARNESS_SYSTEM_COMPARISON
    dimensions = (
        left.max_wall_time,
        left.max_output_tokens,
        left.max_model_turns,
        left.max_tool_calls,
        left.max_provider_requests,
        left.max_cost,
    )
    if any(dimension.scopes is None for dimension in dimensions):
        return BudgetFairnessClass.NATIVE_HARNESS_SYSTEM_COMPARISON

    def enforced_per_run(dimension: BudgetDimension) -> bool:
        return (
            dimension.status is BudgetDimensionStatus.ENFORCED
            and dimension.scopes is not None
            and BudgetScope.PER_LOGICAL_RUN in dimension.scopes
        )

    common_wall = enforced_per_run(left.max_wall_time)
    aggregate_compute = all(
        enforced_per_run(dimension)
        for dimension in (
            left.max_output_tokens,
            left.max_model_turns,
            left.max_provider_requests,
        )
    )
    trusted_cost = enforced_per_run(left.max_cost)
    if common_wall and (aggregate_compute or trusted_cost):
        return BudgetFairnessClass.RESOURCE_NORMALIZED_COMPARISON
    return BudgetFairnessClass.NATIVE_HARNESS_SYSTEM_COMPARISON


def recovery_authorization(
    *,
    slot_id: str,
    original_attempt_identity: str,
    outcome: StatisticalOutcome,
    recovery_attempt_count: int,
) -> RecoveryAuthorization:
    if recovery_attempt_count < 0:
        raise ValueError("recovery attempt count must be non-negative")
    if outcome in {
        StatisticalOutcome.CAPABILITY_PASS,
        StatisticalOutcome.CAPABILITY_FAIL,
    }:
        eligibility = RecoveryEligibility.CAPABILITY_TERMINAL_NO_RETRY
    elif outcome is not StatisticalOutcome.INFRA_FAILURE:
        eligibility = RecoveryEligibility.NOT_INFRASTRUCTURE_FAILURE
    elif recovery_attempt_count >= 1:
        eligibility = RecoveryEligibility.INFRA_RECOVERY_EXHAUSTED
    else:
        eligibility = RecoveryEligibility.ELIGIBLE
    recovery_identity = (
        canonical_digest(
            {
                "slot_id": slot_id,
                "original_attempt_identity": original_attempt_identity,
                "recovery_attempt_index": 1,
            }
        )
        if eligibility is RecoveryEligibility.ELIGIBLE
        else None
    )
    return RecoveryAuthorization(
        eligibility=eligibility,
        original_slot_id=slot_id,
        original_attempt_identity=original_attempt_identity,
        recovery_attempt_count=recovery_attempt_count,
        recovery_attempt_identity=recovery_identity,
    )


def project_default_portfolio(policy: DefaultPortfolioPolicy) -> PortfolioProjection:
    breadth_cells = set(policy.breadth_cell_ids)
    breadth_runs = policy.breadth_task_count * len(breadth_cells) * policy.breadth_repeats
    comparison_memberships = (
        len(policy.critical_comparisons)
        * 2
        * len(policy.critical_task_ids)
        * policy.critical_repeats
    )
    critical_cells = {
        cell_id
        for comparison in policy.critical_comparisons
        for cell_id in (comparison.left_cell_id, comparison.right_cell_id)
    }
    if not critical_cells <= breadth_cells:
        raise MethodologyError("critical comparison cell is absent from breadth selection")
    critical_unique = len(critical_cells) * len(policy.critical_task_ids) * policy.critical_repeats
    overlap = len(critical_cells) * len(policy.critical_task_ids) * policy.breadth_repeats
    incremental = critical_unique - overlap
    projected = breadth_runs + incremental
    formal = policy.formal_exhaustive_subject_runs
    if projected >= formal:
        raise MethodologyError("default portfolio must cost less than formal exhaustive mode")
    reduction = formal - projected
    declared = (
        policy.breadth_subject_runs,
        policy.critical_comparison_memberships,
        policy.critical_unique_subject_runs,
        policy.breadth_overlap_subject_runs,
        policy.incremental_critical_subject_runs,
        policy.projected_unique_subject_runs,
        policy.reduction_subject_runs,
    )
    calculated = (
        breadth_runs,
        comparison_memberships,
        critical_unique,
        overlap,
        incremental,
        projected,
        reduction,
    )
    if declared != calculated:
        raise MethodologyError("declared portfolio projection does not match policy inputs")
    return PortfolioProjection(
        breadth_subject_runs=breadth_runs,
        critical_comparison_memberships=comparison_memberships,
        critical_unique_subject_runs=critical_unique,
        breadth_overlap_subject_runs=overlap,
        incremental_critical_subject_runs=incremental,
        projected_unique_subject_runs=projected,
        formal_exhaustive_subject_runs=formal,
        reduction_subject_runs=reduction,
        reduction_fraction=reduction / formal,
    )


def next_funnel_stage(current: FunnelStage, decision: StageDecision) -> FunnelStage | None:
    if decision is StageDecision.STOP:
        return None
    stages = tuple(FunnelStage)
    index = stages.index(current)
    return stages[index + 1] if index + 1 < len(stages) else None
