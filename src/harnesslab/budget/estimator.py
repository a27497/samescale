from __future__ import annotations

from decimal import Decimal

from harnesslab.budget.models import (
    BudgetCeilingStatus,
    BudgetEstimate,
    BudgetEstimateRequest,
    CallResourceCeiling,
    CostProjection,
    ExpectedCallUsage,
    MatrixBudgetComponent,
    MatrixBudgetEstimate,
    MatrixBudgetEstimateRequest,
    PricingAvailability,
    ProviderPricing,
    TokenCeilings,
)

_MILLION = Decimal(1_000_000)


def estimate_budget(request: BudgetEstimateRequest) -> BudgetEstimate:
    """Calculate a conservative budget estimate without performing external calls."""

    repeats = request.mode.repeat_count
    subject_calls = request.task_count * request.subject_cell_count * repeats
    judge_calls = subject_calls * request.judge_calls_per_subject

    tokens = TokenCeilings(
        subject_input=subject_calls * request.subject_ceiling.input_tokens,
        subject_output=subject_calls * request.subject_ceiling.output_tokens,
        judge_input=judge_calls * request.judge_ceiling.input_tokens,
        judge_output=judge_calls * request.judge_ceiling.output_tokens,
        total=(
            subject_calls
            * (request.subject_ceiling.input_tokens + request.subject_ceiling.output_tokens)
            + judge_calls
            * (request.judge_ceiling.input_tokens + request.judge_ceiling.output_tokens)
        ),
    )
    provider_requests = (
        subject_calls * request.subject_ceiling.provider_requests
        + judge_calls * request.judge_ceiling.provider_requests
    )
    harness_turns = (
        subject_calls * request.subject_ceiling.harness_turns
        + judge_calls * request.judge_ceiling.harness_turns
    )

    worst = _project_cost(
        subject_calls=subject_calls,
        judge_calls=judge_calls,
        subject_usage=request.subject_ceiling,
        judge_usage=request.judge_ceiling,
        subject_pricing=request.subject_pricing,
        judge_pricing=request.judge_pricing,
    )
    expected = None
    if request.expected_subject_usage is not None:
        expected = _project_cost(
            subject_calls=subject_calls,
            judge_calls=judge_calls,
            subject_usage=request.expected_subject_usage,
            judge_usage=request.expected_judge_usage or request.judge_ceiling,
            subject_pricing=request.subject_pricing,
            judge_pricing=request.judge_pricing,
        )

    return BudgetEstimate(
        mode=request.mode,
        repeat_count=repeats,
        expected_subject_calls=subject_calls,
        expected_judge_calls=judge_calls,
        token_ceiling=tokens,
        provider_request_ceiling=provider_requests,
        harness_turn_ceiling=harness_turns,
        estimated_cost_availability=worst.availability,
        projected_worst_case=worst,
        projected_expected_case=expected,
        expected_case_justification=request.expected_case_justification,
        budget_ceiling_usd=request.budget_ceiling_usd,
        budget_ceiling_status=_ceiling_status(request.budget_ceiling_usd, worst),
    )


def estimate_matrix_budget(request: MatrixBudgetEstimateRequest) -> MatrixBudgetEstimate:
    """Aggregate heterogeneous subject cells and the fixed Judge campaign keylessly."""

    components: list[MatrixBudgetComponent] = []
    subject_input = subject_output = judge_input = judge_output = 0
    provider_requests = harness_turns = 0
    known_amount = Decimal(0)
    unknown_routes: set[str] = set()

    for cell in request.subject_cells:
        calls = cell.planned_run_count
        projection = _project_single_component(calls, cell.resource_ceiling, cell.pricing)
        components.append(
            _matrix_component(
                component_id=cell.cell_id,
                kind="SUBJECT",
                calls=calls,
                ceiling=cell.resource_ceiling,
                route_identity=cell.route_identity,
                projection=projection,
            )
        )
        subject_input += calls * cell.resource_ceiling.input_tokens
        subject_output += calls * cell.resource_ceiling.output_tokens
        provider_requests += calls * cell.resource_ceiling.provider_requests
        harness_turns += calls * cell.resource_ceiling.harness_turns
        if projection.amount_usd is None:
            unknown_routes.update(projection.unknown_route_identities)
        else:
            known_amount += projection.amount_usd

    judge = request.judge_campaign
    judge_projection = _project_single_component(
        judge.planned_call_count,
        judge.resource_ceiling,
        judge.pricing,
    )
    components.append(
        _matrix_component(
            component_id=judge.profile_id,
            kind="JUDGE",
            calls=judge.planned_call_count,
            ceiling=judge.resource_ceiling,
            route_identity=judge.route_identity,
            projection=judge_projection,
        )
    )
    judge_input = judge.planned_call_count * judge.resource_ceiling.input_tokens
    judge_output = judge.planned_call_count * judge.resource_ceiling.output_tokens
    provider_requests += judge.planned_call_count * judge.resource_ceiling.provider_requests
    harness_turns += judge.planned_call_count * judge.resource_ceiling.harness_turns
    if judge_projection.amount_usd is None:
        unknown_routes.update(judge_projection.unknown_route_identities)
    else:
        known_amount += judge_projection.amount_usd

    worst = (
        CostProjection(
            availability=PricingAvailability.UNKNOWN,
            unknown_route_identities=tuple(sorted(unknown_routes)),
        )
        if unknown_routes
        else CostProjection(availability=PricingAvailability.KNOWN, amount_usd=known_amount)
    )
    tokens = TokenCeilings(
        subject_input=subject_input,
        subject_output=subject_output,
        judge_input=judge_input,
        judge_output=judge_output,
        total=subject_input + subject_output + judge_input + judge_output,
    )
    return MatrixBudgetEstimate(
        expected_subject_calls=sum(cell.planned_run_count for cell in request.subject_cells),
        expected_judge_calls=judge.planned_call_count,
        components=tuple(components),
        token_ceiling=tokens,
        provider_request_ceiling=provider_requests,
        harness_turn_ceiling=harness_turns,
        estimated_cost_availability=worst.availability,
        projected_worst_case=worst,
        budget_ceiling_usd=request.budget_ceiling_usd,
        budget_ceiling_status=_ceiling_status(request.budget_ceiling_usd, worst),
    )


def _project_single_component(
    calls: int,
    ceiling: CallResourceCeiling,
    pricing: ProviderPricing,
) -> CostProjection:
    if calls == 0:
        return CostProjection(availability=PricingAvailability.KNOWN, amount_usd=Decimal(0))
    if pricing.availability is PricingAvailability.UNKNOWN:
        return CostProjection(
            availability=PricingAvailability.UNKNOWN,
            unknown_route_identities=(pricing.route_identity,),
        )
    return CostProjection(
        availability=PricingAvailability.KNOWN,
        amount_usd=_call_cost(calls, ceiling, pricing),
    )


def _matrix_component(
    *,
    component_id: str,
    kind: str,
    calls: int,
    ceiling: CallResourceCeiling,
    route_identity: str,
    projection: CostProjection,
) -> MatrixBudgetComponent:
    return MatrixBudgetComponent(
        component_id=component_id,
        kind=kind,
        call_count=calls,
        route_identity=route_identity,
        input_token_ceiling=calls * ceiling.input_tokens,
        output_token_ceiling=calls * ceiling.output_tokens,
        provider_request_ceiling=calls * ceiling.provider_requests,
        harness_turn_ceiling=calls * ceiling.harness_turns,
        projected_worst_case=projection,
    )


def _project_cost(
    *,
    subject_calls: int,
    judge_calls: int,
    subject_usage: CallResourceCeiling | ExpectedCallUsage,
    judge_usage: CallResourceCeiling | ExpectedCallUsage,
    subject_pricing: ProviderPricing,
    judge_pricing: ProviderPricing,
) -> CostProjection:
    active: tuple[tuple[int, ProviderPricing], ...] = ((subject_calls, subject_pricing),)
    if judge_calls:
        active += ((judge_calls, judge_pricing),)
    unknown = tuple(
        sorted(
            {
                pricing.route_identity
                for calls, pricing in active
                if calls and pricing.availability is PricingAvailability.UNKNOWN
            }
        )
    )
    if unknown:
        return CostProjection(
            availability=PricingAvailability.UNKNOWN,
            unknown_route_identities=unknown,
        )

    amount = _call_cost(subject_calls, subject_usage, subject_pricing)
    if judge_calls:
        amount += _call_cost(judge_calls, judge_usage, judge_pricing)
    return CostProjection(availability=PricingAvailability.KNOWN, amount_usd=amount)


def _call_cost(
    calls: int,
    usage: CallResourceCeiling | ExpectedCallUsage,
    pricing: ProviderPricing,
) -> Decimal:
    if pricing.availability is not PricingAvailability.KNOWN:
        raise ValueError("cannot calculate cost from unknown pricing")
    if (
        pricing.input_usd_per_million_tokens is None
        or pricing.output_usd_per_million_tokens is None
        or pricing.request_usd is None
    ):
        raise ValueError("known pricing is incomplete")
    count = Decimal(calls)
    return count * (
        Decimal(usage.input_tokens) * pricing.input_usd_per_million_tokens / _MILLION
        + Decimal(usage.output_tokens) * pricing.output_usd_per_million_tokens / _MILLION
        + Decimal(usage.provider_requests) * pricing.request_usd
    )


def _ceiling_status(
    budget_ceiling_usd: Decimal | None,
    worst: CostProjection,
) -> BudgetCeilingStatus:
    if budget_ceiling_usd is None:
        return BudgetCeilingStatus.NOT_CONFIGURED
    if worst.availability is PricingAvailability.UNKNOWN:
        return BudgetCeilingStatus.INDETERMINATE
    if worst.amount_usd is None:
        raise ValueError("known worst-case projection is missing its amount")
    if worst.amount_usd > budget_ceiling_usd:
        return BudgetCeilingStatus.EXCEEDS_CEILING
    return BudgetCeilingStatus.WITHIN_CEILING
