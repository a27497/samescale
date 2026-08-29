from __future__ import annotations

from harnesslab.experiment.methodology import (
    BudgetContract,
    BudgetDimension,
    BudgetDimensionStatus,
    BudgetScope,
    ComparisonType,
    EvaluationMethodologyV2,
    EvaluationMode,
)
from harnesslab.registry.models import (
    BillingMode,
    ExperimentBuilderRequest,
    ExperimentCellSelection,
    RegistryCatalog,
)

TIER_B_SMOKE_EXPERIMENT_ID = "tier-b-keyless-smoke-v1"
TIER_B_SMOKE_SCHEDULE_SEED = 20260831
TIER_B_SMOKE_PLAN_DIGEST = "sha256:7c05ba81e67fba6df388c4511bf0ba7df5a84b07aaf5e27baa2a1b61e886186e"


def tier_b_smoke_budget() -> BudgetContract:
    """Symmetric Direct M-Lane envelope retained after Tier-B prompt-size analysis."""

    return BudgetContract(
        max_wall_time=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=240,
            unit="seconds",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_output_tokens=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=4000,
            unit="tokens",
            scopes=(BudgetScope.PER_PROVIDER_REQUEST, BudgetScope.PER_LOGICAL_RUN),
        ),
        max_model_turns=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=1,
            unit="turns",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_tool_calls=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=0,
            unit="calls",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_provider_requests=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=1,
            unit="requests",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_cost=BudgetDimension(
            status=BudgetDimensionStatus.NOT_AVAILABLE,
            value=None,
            unit="USD",
            scopes=(BudgetScope.NOT_AVAILABLE,),
        ),
    )


def tier_b_smoke_builder_request(
    catalog: RegistryCatalog,
    methodology: EvaluationMethodologyV2,
) -> ExperimentBuilderRequest:
    return ExperimentBuilderRequest(
        experiment_id=TIER_B_SMOKE_EXPERIMENT_ID,
        name="Tier-B Qwen3.8 Max vs DeepSeek V4 Pro keyless smoke n=1",
        methodology_id=methodology.methodology_id,
        methodology_digest=methodology.digest,
        evaluation_mode=EvaluationMode.QUICK,
        comparison_type=ComparisonType.MODEL_COMPARISON,
        task_ids=tuple(item.task_id for item in catalog.tasks),
        cells=(
            ExperimentCellSelection(
                cell_id="Q",
                provider_model_profile_id="alibaba-bailian-qwen3.8-max-chat",
                harness_profile_id="direct-alibaba-bailian-qwen3.8-max-chat",
            ),
            ExperimentCellSelection(
                cell_id="D",
                provider_model_profile_id="alibaba-bailian-deepseek-v4-pro-chat",
                harness_profile_id="direct-alibaba-bailian-deepseek-v4-pro-chat",
            ),
        ),
        budget=tier_b_smoke_budget(),
        schedule_seed=TIER_B_SMOKE_SCHEDULE_SEED,
        max_parallel_runs=1,
        billing_modes={"alibaba-bailian": BillingMode.PAY_AS_YOU_GO},
    )
