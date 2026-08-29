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

MODEL_CHAT_V2_EXPERIMENT_ID = "portfolio-alibaba-model-chat-v2"
MODEL_CHAT_V2_PLAN_DIGEST = (
    "sha256:bd4e47e2e7cbcc406338d0fcb9f6fd029f0c43b89b02ae5bc41b805df4eb8eda"
)
MODEL_CHAT_V3_EXPERIMENT_ID = "portfolio-alibaba-model-chat-v3"
MODEL_CHAT_V3_SCHEDULE_SEED = 20260830
MODEL_CHAT_V3_PLAN_DIGEST = (
    "sha256:100ab920df1eee16f9a9cd754cf8b3454de446445518dbb5c86d326aa20b2042"
)


def model_chat_v2_budget() -> BudgetContract:
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


def model_chat_v2_builder_request(
    catalog: RegistryCatalog,
    methodology: EvaluationMethodologyV2,
) -> ExperimentBuilderRequest:
    return ExperimentBuilderRequest(
        experiment_id=MODEL_CHAT_V2_EXPERIMENT_ID,
        name="Alibaba Qwen3.8 Max vs DeepSeek V4 Pro Chat n=1",
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
        budget=model_chat_v2_budget(),
        schedule_seed=20260829,
        max_parallel_runs=1,
        billing_modes={"alibaba-bailian": BillingMode.PAY_AS_YOU_GO},
    )


def model_chat_v3_builder_request(
    catalog: RegistryCatalog,
    methodology: EvaluationMethodologyV2,
) -> ExperimentBuilderRequest:
    return ExperimentBuilderRequest(
        experiment_id=MODEL_CHAT_V3_EXPERIMENT_ID,
        name="Alibaba Qwen3.8 Max vs DeepSeek V4 Pro Chat v3 n=1",
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
        budget=model_chat_v2_budget(),
        schedule_seed=MODEL_CHAT_V3_SCHEDULE_SEED,
        max_parallel_runs=1,
        billing_modes={"alibaba-bailian": BillingMode.PAY_AS_YOU_GO},
    )
