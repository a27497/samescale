from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from harnesslab.budget import (
    BudgetCeilingStatus,
    BudgetEstimateRequest,
    BudgetMode,
    CallResourceCeiling,
    ExpectedCallUsage,
    PricingAvailability,
    ProviderPricing,
    estimate_budget,
)


def _known_pricing(
    route: str,
    *,
    input_rate: str = "2",
    output_rate: str = "4",
    request_rate: str = "0.01",
) -> ProviderPricing:
    return ProviderPricing(
        route_identity=route,
        availability=PricingAvailability.KNOWN,
        input_usd_per_million_tokens=Decimal(input_rate),
        output_usd_per_million_tokens=Decimal(output_rate),
        request_usd=Decimal(request_rate),
        evidence_reference=f"pricing-snapshot:{route}",
    )


def _unknown_pricing(route: str) -> ProviderPricing:
    return ProviderPricing(route_identity=route, availability=PricingAvailability.UNKNOWN)


def _request(**updates: object) -> BudgetEstimateRequest:
    values: dict[str, object] = {
        "mode": BudgetMode.COMPARE,
        "task_count": 2,
        "subject_cell_count": 2,
        "judge_calls_per_subject": 2,
        "subject_ceiling": CallResourceCeiling(
            input_tokens=1_000,
            output_tokens=500,
            provider_requests=2,
            harness_turns=4,
        ),
        "judge_ceiling": CallResourceCeiling(
            input_tokens=200,
            output_tokens=100,
            provider_requests=1,
            harness_turns=0,
        ),
        "subject_pricing": _known_pricing("subject-route"),
        "judge_pricing": _known_pricing(
            "judge-route", input_rate="1", output_rate="2", request_rate="0.005"
        ),
    }
    values.update(updates)
    return BudgetEstimateRequest.model_validate(values)


@pytest.mark.parametrize(
    ("mode", "repeat_count"),
    [
        (BudgetMode.QUICK, 1),
        (BudgetMode.INFORMAL, 3),
        (BudgetMode.COMPARE, 3),
        (BudgetMode.FORMAL, 5),
    ],
)
def test_evaluation_modes_freeze_required_repeat_counts(
    mode: BudgetMode, repeat_count: int
) -> None:
    estimate = estimate_budget(
        _request(mode=mode, task_count=1, subject_cell_count=1, judge_calls_per_subject=1)
    )

    assert estimate.repeat_count == repeat_count
    assert estimate.expected_subject_calls == repeat_count
    assert estimate.expected_judge_calls == repeat_count


def test_estimator_aggregates_calls_and_resource_ceilings() -> None:
    estimate = estimate_budget(_request())

    assert estimate.expected_subject_calls == 12
    assert estimate.expected_judge_calls == 24
    assert estimate.token_ceiling.subject_input == 12_000
    assert estimate.token_ceiling.subject_output == 6_000
    assert estimate.token_ceiling.judge_input == 4_800
    assert estimate.token_ceiling.judge_output == 2_400
    assert estimate.token_ceiling.total == 25_200
    assert estimate.provider_request_ceiling == 48
    assert estimate.harness_turn_ceiling == 48
    assert estimate.estimated_cost_availability is PricingAvailability.KNOWN
    assert estimate.projected_worst_case.availability is PricingAvailability.KNOWN
    assert estimate.projected_worst_case.amount_usd == Decimal("0.4176")


def test_expected_cost_requires_bounded_usage_and_justification() -> None:
    request = _request(
        budget_ceiling_usd=Decimal("0.4"),
        expected_subject_usage=ExpectedCallUsage(
            input_tokens=Decimal(500),
            output_tokens=Decimal(100),
            provider_requests=Decimal(1),
            harness_turns=Decimal(2),
        ),
        expected_judge_usage=ExpectedCallUsage(
            input_tokens=Decimal(100),
            output_tokens=Decimal(50),
            provider_requests=Decimal(1),
            harness_turns=Decimal(0),
        ),
        expected_case_justification="Frozen medians from the preceding keyless fixture run.",
    )

    estimate = estimate_budget(request)

    assert estimate.projected_expected_case is not None
    assert estimate.projected_expected_case.amount_usd == Decimal("0.2616")
    # Expected cost does not weaken enforcement of the conservative worst-case ceiling.
    assert estimate.budget_ceiling_status is BudgetCeilingStatus.EXCEEDS_CEILING
    assert request.expected_subject_usage is not None
    assert request.expected_judge_usage is not None

    with pytest.raises(ValidationError, match="requires a justification"):
        _request(
            expected_subject_usage=request.expected_subject_usage,
            expected_judge_usage=request.expected_judge_usage,
        )
    with pytest.raises(ValidationError, match="exceeds its ceiling"):
        _request(
            expected_subject_usage=request.expected_subject_usage.model_copy(
                update={"output_tokens": Decimal(501)}
            ),
            expected_judge_usage=request.expected_judge_usage,
            expected_case_justification="Invalid oversized expectation",
        )


def test_unknown_active_pricing_is_never_treated_as_zero() -> None:
    estimate = estimate_budget(
        _request(
            subject_pricing=_unknown_pricing("unpriced-subject"),
            budget_ceiling_usd=Decimal("1000"),
        )
    )

    assert estimate.projected_worst_case.availability is PricingAvailability.UNKNOWN
    assert estimate.estimated_cost_availability is PricingAvailability.UNKNOWN
    assert estimate.projected_worst_case.amount_usd is None
    assert estimate.projected_worst_case.unknown_route_identities == ("unpriced-subject",)
    assert estimate.budget_ceiling_status is BudgetCeilingStatus.INDETERMINATE


def test_inactive_unknown_judge_route_does_not_hide_known_subject_cost() -> None:
    estimate = estimate_budget(
        _request(
            judge_calls_per_subject=0,
            judge_pricing=_unknown_pricing("unused-judge"),
            budget_ceiling_usd=Decimal("1"),
        )
    )

    assert estimate.expected_judge_calls == 0
    assert estimate.projected_worst_case.availability is PricingAvailability.KNOWN
    assert estimate.projected_worst_case.amount_usd == Decimal("0.288")
    assert estimate.budget_ceiling_status is BudgetCeilingStatus.WITHIN_CEILING


def test_pricing_and_expected_usage_validation_is_deterministic() -> None:
    with pytest.raises(ValidationError, match="UNKNOWN pricing cannot contain rates"):
        ProviderPricing(
            route_identity="unknown",
            availability=PricingAvailability.UNKNOWN,
            input_usd_per_million_tokens=Decimal(0),
        )
    with pytest.raises(ValidationError, match="KNOWN pricing requires"):
        ProviderPricing(
            route_identity="incomplete",
            availability=PricingAvailability.KNOWN,
            input_usd_per_million_tokens=Decimal(1),
        )
    with pytest.raises(ValidationError, match="cover every active call type"):
        _request(
            expected_subject_usage=ExpectedCallUsage(input_tokens=1, output_tokens=1),
            expected_case_justification="Only one active route was characterized",
        )


def test_estimate_serialization_and_digest_are_stable() -> None:
    first = estimate_budget(_request())
    second = estimate_budget(_request())

    assert first.canonical_json() == second.canonical_json()
    assert first.digest == second.digest
    assert "created_at" not in first.canonical_json()
