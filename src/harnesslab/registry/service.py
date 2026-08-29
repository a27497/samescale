from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from harnesslab.comparability.models import ComparabilityIntent
from harnesslab.contracts.common import EvaluationLane
from harnesslab.contracts.model import ModelProfile
from harnesslab.experiment.methodology import (
    BudgetContract,
    BudgetDimensionStatus,
    ComparisonType,
    EvaluationMode,
    FunnelStage,
    MethodologyError,
    ProviderAvailability,
    load_evaluation_methodology,
    require_comparable_budgets,
    require_comparison_type,
)
from harnesslab.experiment.plan import MethodologyV2ExperimentPlan, build_methodology_v2_plan
from harnesslab.experiment.spec import (
    AblationSpec,
    ExperimentCellSpec,
    ExperimentSpec,
    ExperimentSpecError,
    PairedComparisonSpec,
)
from harnesslab.registry.models import (
    BillingMode,
    CapabilityAssessment,
    CheckStatus,
    CompatibilityStatus,
    CostEstimate,
    CostEstimateStatus,
    CredentialReferenceStatus,
    CredentialStatus,
    ExperimentBuilderRequest,
    ExperimentPreflight,
    ExperimentSnapshot,
    FrozenProviderSelection,
    HarnessDefinition,
    HarnessProfileDefinition,
    ObservedModelCapability,
    PreflightCheck,
    PreflightStatus,
    ProviderDefinition,
    ProviderHealthStatus,
    ProviderModelProfile,
    RegistryCatalog,
    RegistryError,
    RegistrySettings,
    ScheduleBlockPreview,
    TraceCoverage,
    canonical_digest,
    freeze_experiment_snapshot,
)
from harnesslab.registry.runtime import (
    DirectRuntimeContractError,
    DirectRuntimeProfileSource,
    direct_harness_control_identity,
    resolve_direct_runtime_profile,
)
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.tasks.package import TaskPackage

METHODOLOGY_PATH = Path("release/evaluation-methodology-v2.json")


@dataclass(frozen=True)
class _ResolvedHarnessProfile:
    harness: HarnessDefinition
    profile: HarnessProfileDefinition


@dataclass(frozen=True)
class _Candidate:
    plan: MethodologyV2ExperimentPlan
    selections: tuple[FrozenProviderSelection, ...]


def _direct_runtime_source(
    provider: ProviderDefinition,
    profile: ProviderModelProfile,
) -> DirectRuntimeProfileSource:
    endpoint = profile.provider_route_identity.rsplit("|", 1)[-1]
    if not endpoint.endswith(profile.route):
        raise RegistryError("provider route identity does not end in the registered route")
    base = endpoint[: -len(profile.route)]
    expected_reference = provider.protocol_base_url_references.get(
        profile.protocol, provider.base_url_reference
    )
    if base.startswith("env:"):
        reference = base.removeprefix("env:")
        if reference != expected_reference:
            raise RegistryError("provider route identity has the wrong base URL reference")
        return DirectRuntimeProfileSource(
            provider=provider.provider_id,
            requested_model=profile.requested_model,
            protocol=profile.protocol,
            route=profile.route,
            base_url_reference=reference,
            credential_reference=profile.credential_reference,
            reasoning_effort=profile.reasoning_effort,
            request_timeout_seconds=profile.request_timeout_seconds,
        )
    if expected_reference is not None:
        raise RegistryError("provider route identity bypasses its frozen URL reference")
    return DirectRuntimeProfileSource(
        provider=provider.provider_id,
        requested_model=profile.requested_model,
        protocol=profile.protocol,
        route=profile.route,
        base_url=base,
        credential_reference=profile.credential_reference,
        reasoning_effort=profile.reasoning_effort,
        request_timeout_seconds=profile.request_timeout_seconds,
    )


def resolve_frozen_direct_runtime(
    selection: FrozenProviderSelection,
    budget: BudgetContract,
) -> ModelProfile:
    """Re-derive and validate a frozen Direct selection at load/preflight/runtime time."""

    if selection.harness_id != "direct-model" or selection.runtime_profile_source is None:
        raise RegistryError("selection does not contain a frozen Direct runtime source")
    try:
        resolved = resolve_direct_runtime_profile(selection.runtime_profile_source, budget)
    except DirectRuntimeContractError as exc:
        raise RegistryError(str(exc)) from exc
    expected = {
        "runtime profile control": (
            selection.runtime_profile_control_identity,
            resolved.profile_control_identity,
        ),
        "effective runtime profile": (
            selection.effective_runtime_profile_identity,
            resolved.effective_profile_identity,
        ),
        "resource envelope": (
            selection.resource_envelope_identity,
            resolved.resource_envelope_identity,
        ),
        "Direct harness control": (
            selection.harness_config_identity,
            direct_harness_control_identity(),
        ),
        "requested model": (
            selection.requested_model,
            resolved.profile.requested_model,
        ),
        "provider": (selection.provider_id, resolved.profile.provider),
        "route": (selection.safe_route_identity, resolved.profile.provider_route_identity),
        "credential reference": (
            selection.credential_reference,
            resolved.profile.credential_reference,
        ),
    }
    mismatches = [name for name, (frozen, actual) in expected.items() if frozen != actual]
    if mismatches:
        raise RegistryError("frozen Direct runtime drift: " + ", ".join(mismatches))
    return resolved.profile


def validate_frozen_runtime_contract(
    plan: MethodologyV2ExperimentPlan,
    selections: tuple[FrozenProviderSelection, ...],
) -> dict[str, ModelProfile]:
    """Validate plan cells/slots against the canonical frozen runtime derivation."""

    cells = {cell.id: cell for cell in plan.cells}
    if len(cells) != len(plan.cells):
        raise RegistryError("frozen plan contains duplicate cell identities")
    resolved_profiles: dict[str, ModelProfile] = {}
    for selection in selections:
        if selection.harness_id != "direct-model":
            continue
        try:
            cell = cells[selection.cell_id]
        except KeyError as exc:
            raise RegistryError("frozen Direct selection has no plan cell") from exc
        profile = resolve_frozen_direct_runtime(selection, plan.budget_contract)
        cell_checks = {
            "requested model": (cell.requested_model, profile.requested_model),
            "provider route": (cell.provider_route, profile.provider_route_identity),
            "runtime profile control": (
                cell.profile_identity,
                selection.runtime_profile_control_identity,
            ),
            "effective runtime profile": (
                cell.effective_runtime_profile_identity,
                selection.effective_runtime_profile_identity,
            ),
            "base provider profile": (
                cell.base_provider_profile_identity,
                selection.base_provider_profile_identity,
            ),
            "resource envelope": (
                cell.resource_envelope_identity,
                selection.resource_envelope_identity,
            ),
            "Direct harness control": (
                cell.harness_config_identity,
                selection.harness_config_identity,
            ),
            "runner contract": (cell.runner_contract, "direct-model-v1"),
        }
        mismatches = [name for name, (frozen, actual) in cell_checks.items() if frozen != actual]
        if mismatches:
            raise RegistryError("frozen Direct cell drift: " + ", ".join(mismatches))
        resolved_profiles[selection.cell_id] = profile
    for slot in plan.run_slots:
        if slot.cell_id not in resolved_profiles:
            continue
        cell = cells[slot.cell_id]
        if any(
            (
                slot.requested_model != cell.requested_model,
                slot.provider_route != cell.provider_route,
                slot.profile_identity != cell.profile_identity,
                slot.harness_config_identity != cell.harness_config_identity,
                slot.runner_contract != cell.runner_contract,
                slot.base_provider_profile_identity != cell.base_provider_profile_identity,
                slot.effective_runtime_profile_identity != cell.effective_runtime_profile_identity,
                slot.resource_envelope_identity != cell.resource_envelope_identity,
            )
        ):
            raise RegistryError("frozen Direct slot controls drift from its plan cell")
    return resolved_profiles


def registry_catalog(
    repository_root: Path,
    environment: Mapping[str, str],
    *,
    task_corpus_path: Path | None = None,
) -> RegistryCatalog:
    if task_corpus_path is None:
        return build_registry_catalog(repository_root, environment)
    return build_registry_catalog(repository_root, environment, task_corpus_path=task_corpus_path)


def registry_settings(catalog: RegistryCatalog, environment: Mapping[str, str]) -> RegistrySettings:
    references = tuple(sorted({item.credential_reference for item in catalog.providers}))
    return RegistrySettings(
        defaults=catalog.defaults,
        credentials=tuple(
            CredentialReferenceStatus(
                credential_reference=reference,
                status=(
                    CredentialStatus.SET
                    if environment.get(reference, "").strip()
                    else CredentialStatus.MISSING
                ),
            )
            for reference in references
        ),
        provider_enabled={item.provider_id: item.enabled for item in catalog.providers},
    )


def _harness_profiles(catalog: RegistryCatalog) -> dict[str, _ResolvedHarnessProfile]:
    return {
        profile.profile_id: _ResolvedHarnessProfile(harness=harness, profile=profile)
        for harness in catalog.harnesses
        for profile in harness.profiles
    }


def assess_capability(
    catalog: RegistryCatalog,
    provider_profile_id: str,
    harness_profile_id: str,
) -> CapabilityAssessment:
    providers = {item.provider_id: item for item in catalog.providers}
    profiles = {item.profile_id: item for item in catalog.provider_model_profiles}
    harness_profiles = _harness_profiles(catalog)
    try:
        profile = profiles[provider_profile_id]
        resolved = harness_profiles[harness_profile_id]
        provider = providers[profile.provider_id]
    except KeyError as exc:
        raise RegistryError("capability selection references an unknown registry identity") from exc

    protocol_compatible = profile.protocol in resolved.harness.supported_protocols
    model_provider_compatible = (
        profile.profile_id in resolved.profile.supported_provider_profile_ids
    )
    reason_codes: list[str] = []
    if not protocol_compatible:
        reason_codes.append("PROTOCOL_UNSUPPORTED_BY_HARNESS")
    if not model_provider_compatible:
        reason_codes.append("PROVIDER_MODEL_PROFILE_UNSUPPORTED_BY_HARNESS")
    if not provider.enabled or not profile.enabled:
        reason_codes.append("PROVIDER_OR_PROFILE_DISABLED")
    if not provider.automation_allowed or not profile.automation_allowed:
        reason_codes.append("AUTOMATION_NOT_ALLOWED")

    compatible = (
        protocol_compatible
        and model_provider_compatible
        and provider.enabled
        and profile.enabled
        and provider.automation_allowed
        and profile.automation_allowed
    )
    partial = compatible and (
        resolved.harness.trace_coverage is not TraceCoverage.FULL_STREAM
        or resolved.harness.observed_model_exposure is ObservedModelCapability.NOT_AVAILABLE
    )
    if compatible and resolved.harness.trace_coverage is not TraceCoverage.FULL_STREAM:
        reason_codes.append("TRACE_COVERAGE_LIMITED")
    if (
        compatible
        and resolved.harness.observed_model_exposure is ObservedModelCapability.NOT_AVAILABLE
    ):
        reason_codes.append("OBSERVED_MODEL_NOT_EXPOSED")
    status = (
        CompatibilityStatus.UNSUPPORTED
        if not compatible
        else CompatibilityStatus.PARTIALLY_SUPPORTED
        if partial
        else CompatibilityStatus.SUPPORTED
    )
    return CapabilityAssessment(
        provider_profile_id=profile.profile_id,
        harness_profile_id=resolved.profile.profile_id,
        status=status,
        reason_codes=tuple(reason_codes),
        protocol_compatible=protocol_compatible,
        model_provider_compatible=model_provider_compatible,
        observed_model=resolved.harness.observed_model_exposure,
        trace_coverage=resolved.harness.trace_coverage,
        native_tools=resolved.harness.native_tools,
        workspace_mutation=resolved.harness.workspace_mutation,
        network_requirement=resolved.harness.network_capability,
        reasoning_control_supported=(
            resolved.profile.reasoning_effort is None
            or profile.reasoning_effort == resolved.profile.reasoning_effort
            or resolved.harness.harness_id == "codex"
        ),
        harness_uplift_eligible=(compatible and resolved.harness.harness_id != "direct-model"),
        judge_eligible=(
            compatible
            and resolved.harness.harness_id == "direct-model"
            and profile.model_id == "glm-5.2"
        ),
    )


def all_capabilities(catalog: RegistryCatalog) -> tuple[CapabilityAssessment, ...]:
    return tuple(
        assess_capability(catalog, provider.profile_id, harness_profile.profile_id)
        for provider in catalog.provider_model_profiles
        for harness in catalog.harnesses
        for harness_profile in harness.profiles
    )


def _comparison_intent(comparison_type: ComparisonType) -> ComparabilityIntent:
    if comparison_type is ComparisonType.HARNESS_UPLIFT:
        return ComparabilityIntent.HARNESS_UPLIFT
    if comparison_type is ComparisonType.MODEL_COMPARISON:
        return ComparabilityIntent.MODEL_COMPARISON
    return ComparabilityIntent.GENERAL


def _funnel_stage(mode: EvaluationMode) -> FunnelStage:
    return {
        EvaluationMode.QUICK: FunnelStage.BREADTH,
        EvaluationMode.INFORMAL: FunnelStage.INFORMAL,
        EvaluationMode.FORMAL_EXHAUSTIVE: FunnelStage.FORMAL,
    }[mode]


def _resolve_cells(
    request: ExperimentBuilderRequest,
    catalog: RegistryCatalog,
    repository_root: Path,
) -> tuple[tuple[ExperimentCellSpec, ...], tuple[FrozenProviderSelection, ...]]:
    provider_profiles = {item.profile_id: item for item in catalog.provider_model_profiles}
    providers = {item.provider_id: item for item in catalog.providers}
    harness_profiles = _harness_profiles(catalog)
    tasks = {item.task_id: item for item in catalog.tasks}
    try:
        selected_tasks = tuple(tasks[task_id] for task_id in request.task_ids)
    except KeyError as exc:
        raise RegistryError("experiment references an unregistered task identity") from exc
    packages = tuple(
        TaskPackage.load(repository_root / item.package_path) for item in selected_tasks
    )
    budget_identities = {
        canonical_digest(item.definition.budget.model_dump(mode="json")) for item in packages
    }
    network_policies = {item.definition.budget.network_policy for item in packages}
    if len(budget_identities) != 1 or len(network_policies) != 1:
        raise RegistryError("selected tasks do not share one enforceable execution budget")
    resource_budget_identity = next(iter(budget_identities))
    network_policy = next(iter(network_policies))

    cells: list[ExperimentCellSpec] = []
    frozen: list[FrozenProviderSelection] = []
    for selection in request.cells:
        try:
            provider_profile = provider_profiles[selection.provider_model_profile_id]
            provider = providers[provider_profile.provider_id]
            resolved_harness = harness_profiles[selection.harness_profile_id]
        except KeyError as exc:
            raise RegistryError("experiment references an unknown profile identity") from exc
        capability = assess_capability(
            catalog, provider_profile.profile_id, resolved_harness.profile.profile_id
        )
        if capability.status is CompatibilityStatus.UNSUPPORTED:
            raise RegistryError("provider model and harness profiles are not explicitly compatible")
        direct_runtime = None
        if resolved_harness.harness.harness_id == "direct-model":
            source = _direct_runtime_source(provider, provider_profile)
            direct_runtime = resolve_direct_runtime_profile(source, request.budget)
            if (
                resolved_harness.profile.harness_config_identity
                != direct_harness_control_identity()
            ):
                raise RegistryError("Direct harness profile does not match its canonical control")
            combined_profile_identity = direct_runtime.profile_control_identity
        else:
            source = None
            combined_profile_identity = canonical_digest(
                {
                    "provider_profile_identity": provider_profile.profile_identity,
                    "harness_config_identity": resolved_harness.profile.harness_config_identity,
                }
            )
        cells.append(
            ExperimentCellSpec(
                id=selection.cell_id,
                lane=(
                    EvaluationLane.MODEL
                    if resolved_harness.harness.harness_id == "direct-model"
                    else EvaluationLane.HARNESS
                ),
                requested_model=provider_profile.requested_model,
                provider_route=provider_profile.provider_route_identity,
                profile_reference=resolved_harness.profile.profile_reference,
                profile_identity=combined_profile_identity,
                harness=resolved_harness.harness.harness_id,
                harness_version=resolved_harness.harness.version,
                harness_config_identity=resolved_harness.profile.harness_config_identity,
                reasoning_effort=(
                    resolved_harness.profile.reasoning_effort
                    if resolved_harness.profile.reasoning_effort is not None
                    else provider_profile.reasoning_effort
                ),
                resource_budget_identity=resource_budget_identity,
                network_policy=network_policy,
                runner_contract=resolved_harness.harness.runner_contract,
                credential_reference=provider_profile.credential_reference,
                base_provider_profile_identity=(
                    provider_profile.base_provider_profile_identity
                    if direct_runtime is not None
                    else None
                ),
                effective_runtime_profile_identity=(
                    direct_runtime.effective_profile_identity
                    if direct_runtime is not None
                    else None
                ),
                resource_envelope_identity=(
                    direct_runtime.resource_envelope_identity
                    if direct_runtime is not None
                    else None
                ),
            )
        )
        billing_mode = request.billing_modes.get(provider.provider_id, provider.billing_mode)
        frozen.append(
            FrozenProviderSelection(
                cell_id=selection.cell_id,
                provider_id=provider.provider_id,
                provider_profile_id=provider_profile.profile_id,
                provider_profile_identity=provider_profile.profile_identity,
                model_id=provider_profile.model_id,
                requested_model=provider_profile.requested_model,
                harness_id=resolved_harness.harness.harness_id,
                harness_profile_id=resolved_harness.profile.profile_id,
                harness_config_identity=resolved_harness.profile.harness_config_identity,
                credential_reference=provider_profile.credential_reference,
                safe_route_identity=provider_profile.provider_route_identity,
                runtime_endpoint_fingerprint=provider_profile.runtime_endpoint_fingerprint,
                billing_mode=billing_mode,
                pricing_snapshot_reference=provider_profile.pricing_snapshot_reference,
                base_provider_profile_identity=(
                    provider_profile.base_provider_profile_identity
                    if direct_runtime is not None
                    else None
                ),
                runtime_profile_source=source,
                runtime_profile_control_identity=(
                    direct_runtime.profile_control_identity if direct_runtime is not None else None
                ),
                effective_runtime_profile_identity=(
                    direct_runtime.effective_profile_identity
                    if direct_runtime is not None
                    else None
                ),
                resource_envelope_identity=(
                    direct_runtime.resource_envelope_identity
                    if direct_runtime is not None
                    else None
                ),
            )
        )
    return tuple(cells), tuple(frozen)


def _comparison_definitions(
    request: ExperimentBuilderRequest, cells: tuple[ExperimentCellSpec, ...]
) -> tuple[tuple[PairedComparisonSpec, ...], tuple[AblationSpec, ...]]:
    left, right = cells
    if request.comparison_type is not ComparisonType.END_TO_END_SYSTEM_COMPARISON:
        declared = (
            "reasoning_effort"
            if request.comparison_type is ComparisonType.CONTROLLED_ABLATION
            else None
        )
        try:
            require_comparison_type(
                left,
                right,
                request.comparison_type,
                declared_ablation_dimension=declared,
            )
        except MethodologyError as exc:
            raise RegistryError(str(exc)) from exc
    if request.comparison_type is ComparisonType.HARNESS_UPLIFT:
        try:
            require_comparable_budgets(request.budget, request.budget)
        except MethodologyError as exc:
            raise RegistryError(
                "Harness uplift requires a resource-normalized budget contract"
            ) from exc
        direct = next((cell for cell in cells if cell.lane is EvaluationLane.MODEL), None)
        harness = next((cell for cell in cells if cell.lane is EvaluationLane.HARNESS), None)
        if direct is None or harness is None:
            raise RegistryError("Harness uplift requires one direct and one Harness cell")
        return (
            PairedComparisonSpec(
                id="registry-harness-uplift",
                left_cell_id=direct.id,
                right_cell_id=harness.id,
            ),
        ), ()
    if request.comparison_type is ComparisonType.CONTROLLED_ABLATION:
        return (), (
            AblationSpec(
                id="registry-controlled-ablation",
                base_cell_id=left.id,
                variant_cell_id=right.id,
                changed_dimension="reasoning_effort",
            ),
        )
    return (), ()


def _build_candidate(
    request: ExperimentBuilderRequest,
    catalog: RegistryCatalog,
    repository_root: Path,
) -> _Candidate:
    methodology = load_evaluation_methodology(repository_root / METHODOLOGY_PATH)
    if (
        request.methodology_id != methodology.methodology_id
        or request.methodology_digest != methodology.digest
    ):
        raise RegistryError("methodology identity does not match active methodology v2")
    cells, selections = _resolve_cells(request, catalog, repository_root)
    pairs, ablations = _comparison_definitions(request, cells)
    request_identity = canonical_digest(
        {
            "request": request.model_dump(mode="json"),
            "registry_id": catalog.registry_id,
            "registry_digest": catalog.digest,
            "selections": [item.model_dump(mode="json") for item in selections],
        }
    )
    experiment_id = request.experiment_id or (
        "registry-" + request_identity.removeprefix("sha256:")[:24]
    )
    tasks = {item.task_id: item for item in catalog.tasks}
    spec = ExperimentSpec(
        experiment_id=experiment_id,
        name=request.name,
        task_packages=tuple(tasks[item].package_path for item in request.task_ids),
        cells=cells,
        repeat_count=request.evaluation_mode.repeat_count,
        execution_seed=request.schedule_seed,
        comparison_intent=_comparison_intent(request.comparison_type),
        paired_comparisons=pairs,
        ablations=ablations,
    )
    unavailable_routes = {
        selection.safe_route_identity
        for selection in selections
        if next(
            provider
            for provider in catalog.providers
            if provider.provider_id == selection.provider_id
        ).health_status
        in {ProviderHealthStatus.UNAVAILABLE, ProviderHealthStatus.QUOTA_EXHAUSTED}
    }
    plan = build_methodology_v2_plan(
        spec,
        repository_root,
        methodology=methodology,
        evaluation_mode=request.evaluation_mode,
        funnel_stage=_funnel_stage(request.evaluation_mode),
        schedule_seed=request.schedule_seed,
        budget_contract=request.budget,
        provider_availability={
            route: ProviderAvailability.PROVIDER_UNAVAILABLE for route in unavailable_routes
        },
    )
    validate_frozen_runtime_contract(plan, selections)
    return _Candidate(plan=plan, selections=selections)


def _check(key: str, status: CheckStatus, reason_code: str, detail: str) -> PreflightCheck:
    return PreflightCheck(key=key, status=status, reason_code=reason_code, detail=detail)


def preflight_experiment(
    request: ExperimentBuilderRequest,
    repository_root: Path,
    environment: Mapping[str, str],
    *,
    task_corpus_path: Path | None = None,
) -> ExperimentPreflight:
    catalog = registry_catalog(repository_root, environment, task_corpus_path=task_corpus_path)
    checks: list[PreflightCheck] = []
    methodology = load_evaluation_methodology(repository_root / METHODOLOGY_PATH)
    if (
        request.methodology_id == methodology.methodology_id
        and request.methodology_digest == methodology.digest
    ):
        checks.append(
            _check(
                "methodology", CheckStatus.PASS, "METHODOLOGY_VALID", "Active v2 identity matches"
            )
        )
    else:
        checks.append(
            _check(
                "methodology",
                CheckStatus.BLOCKED,
                "METHODOLOGY_IDENTITY_MISMATCH",
                "The selected methodology is not the active immutable v2 artifact",
            )
        )

    candidate: _Candidate | None = None
    try:
        candidate = _build_candidate(request, catalog, repository_root)
    except (RegistryError, ExperimentSpecError, ValueError) as exc:
        checks.append(
            _check("builder", CheckStatus.BLOCKED, "INVALID_EXPERIMENT_SELECTION", str(exc))
        )
    else:
        checks.extend(
            (
                _check(
                    "task-health",
                    CheckStatus.PASS,
                    "TASK_HEALTH_ATTESTED",
                    (
                        f"{len(candidate.plan.task_health_attestations)} task identities "
                        "passed 5x health"
                    ),
                ),
                _check(
                    "schedule",
                    CheckStatus.PASS,
                    "BLOCKED_INTERLEAVED_SCHEDULE_VALID",
                    f"{len(candidate.plan.schedule_blocks)} deterministic blocks are frozen",
                ),
                _check(
                    "repeat-policy",
                    CheckStatus.PASS,
                    "MODE_REPEAT_POLICY_VALID",
                    (
                        f"{request.evaluation_mode.value} fixes "
                        f"n={request.evaluation_mode.repeat_count}"
                    ),
                ),
                _check(
                    "runtime-contract",
                    CheckStatus.PASS,
                    "FROZEN_RUNTIME_IDENTITIES_VALID",
                    "Direct selections re-resolve to their frozen runtime identities",
                ),
            )
        )

    providers = {item.provider_id: item for item in catalog.providers}
    profile_by_id = {item.profile_id: item for item in catalog.provider_model_profiles}
    for selection in request.cells:
        profile = profile_by_id.get(selection.provider_model_profile_id)
        if profile is None:
            continue
        provider = providers[profile.provider_id]
        if not environment.get(profile.credential_reference, "").strip():
            checks.append(
                _check(
                    f"credential:{profile.profile_id}",
                    CheckStatus.BLOCKED,
                    "CREDENTIAL_REFERENCE_MISSING",
                    f"{profile.credential_reference}=MISSING",
                )
            )
        else:
            checks.append(
                _check(
                    f"credential:{profile.profile_id}",
                    CheckStatus.PASS,
                    "CREDENTIAL_REFERENCE_SET",
                    f"{profile.credential_reference}=SET",
                )
            )
        if not provider.enabled or not profile.enabled:
            checks.append(
                _check(
                    f"provider:{provider.provider_id}",
                    CheckStatus.BLOCKED,
                    "PROVIDER_DISABLED",
                    "Provider or profile is disabled by operator configuration",
                )
            )
        elif provider.health_status in {
            ProviderHealthStatus.UNAVAILABLE,
            ProviderHealthStatus.QUOTA_EXHAUSTED,
        }:
            checks.append(
                _check(
                    f"provider:{provider.provider_id}",
                    CheckStatus.BLOCKED,
                    provider.health_status.value,
                    "Affected schedule blocks cannot be acquired",
                )
            )
        elif provider.health_status is ProviderHealthStatus.UNKNOWN:
            checks.append(
                _check(
                    f"provider:{provider.provider_id}",
                    CheckStatus.WARNING,
                    "PROVIDER_STATUS_UNKNOWN",
                    "No provider probe was performed; operator status is UNKNOWN",
                )
            )
        else:
            checks.append(
                _check(
                    f"provider:{provider.provider_id}",
                    CheckStatus.PASS,
                    "PROVIDER_AVAILABLE",
                    "Operator-supplied status is AVAILABLE",
                )
            )
        billing_mode = request.billing_modes.get(provider.provider_id, provider.billing_mode)
        if (
            provider.provider_id == "alibaba-bailian"
            and billing_mode is not BillingMode.PAY_AS_YOU_GO
        ):
            checks.append(
                _check(
                    "billing:alibaba-bailian",
                    CheckStatus.BLOCKED,
                    "AUTOMATION_NOT_ALLOWED_FOR_BILLING_PLAN",
                    "Alibaba automated evaluation requires PAY_AS_YOU_GO",
                )
            )
        else:
            checks.append(
                _check(
                    f"billing:{provider.provider_id}",
                    CheckStatus.PASS,
                    "BILLING_AUTOMATION_ALLOWED",
                    f"Billing mode {billing_mode.value} permits this planning contract",
                )
            )
        if provider.base_url_reference and provider.runtime_endpoint_fingerprint is None:
            checks.append(
                _check(
                    f"endpoint:{provider.provider_id}",
                    CheckStatus.BLOCKED,
                    provider.configuration_reason_codes[0]
                    if provider.configuration_reason_codes
                    else "RUNTIME_ENDPOINT_REFERENCE_MISSING",
                    "Protected runtime endpoint is missing or invalid",
                )
            )

    if request.budget.max_wall_time.status is BudgetDimensionStatus.NOT_AVAILABLE:
        checks.append(
            _check(
                "budget",
                CheckStatus.BLOCKED,
                "MAX_WALL_TIME_REQUIRED",
                "A finite wall-time bound is required for experiment planning",
            )
        )
    else:
        checks.append(
            _check(
                "budget",
                CheckStatus.PASS,
                "BUDGET_CONTRACT_VALID",
                "The strict methodology-v2 budget contract is persisted",
            )
        )
    if any(
        dimension.status is BudgetDimensionStatus.NOT_AVAILABLE
        for dimension in (
            request.budget.max_model_turns,
            request.budget.max_tool_calls,
            request.budget.max_provider_requests,
            request.budget.max_cost,
        )
    ):
        checks.append(
            _check(
                "budget-availability",
                CheckStatus.WARNING,
                "BUDGET_METRIC_NOT_AVAILABLE",
                "Unavailable dimensions remain explicitly NOT_AVAILABLE",
            )
        )
    checks.append(
        _check(
            "pricing",
            CheckStatus.WARNING,
            "PRICING_NOT_AVAILABLE",
            "No immutable price/input evidence is registered; cost estimate is unavailable",
        )
    )

    overall = (
        PreflightStatus.BLOCKED
        if any(item.status is CheckStatus.BLOCKED for item in checks)
        else PreflightStatus.READY_WITH_WARNINGS
        if any(item.status is CheckStatus.WARNING for item in checks)
        else PreflightStatus.READY
    )
    planned = len(candidate.plan.run_slots) if candidate is not None else 0
    wall_value = request.budget.max_wall_time.value
    max_wall = (
        math.ceil(planned / request.max_parallel_runs * float(wall_value))
        if candidate is not None and wall_value is not None
        else None
    )
    preview = (
        tuple(
            ScheduleBlockPreview(
                block_identity=block.block_identity,
                task_id=block.task_id,
                repeat_index=block.repeat_index,
                cell_execution_order=block.cell_execution_order,
                provider_status=block.provider_availability.value,
            )
            for block in candidate.plan.schedule_blocks
        )
        if candidate is not None
        else ()
    )
    return ExperimentPreflight(
        status=overall,
        checks=tuple(checks),
        estimated_logical_slots=planned,
        estimated_maximum_wall_time_seconds=max_wall,
        evaluation_mode=request.evaluation_mode,
        repeat_count=request.evaluation_mode.repeat_count,
        max_parallel_runs=request.max_parallel_runs,
        cost_estimate=CostEstimate(status=CostEstimateStatus.NOT_AVAILABLE),
        schedule_preview=preview,
        candidate_experiment_id=(candidate.plan.experiment_id if candidate else None),
        candidate_plan_digest=(candidate.plan.digest if candidate else None),
    )


def build_experiment_snapshot(
    request: ExperimentBuilderRequest,
    repository_root: Path,
    environment: Mapping[str, str],
    *,
    task_corpus_path: Path | None = None,
) -> ExperimentSnapshot:
    catalog = registry_catalog(repository_root, environment, task_corpus_path=task_corpus_path)
    candidate = _build_candidate(request, catalog, repository_root)
    preflight = preflight_experiment(
        request,
        repository_root,
        environment,
        task_corpus_path=task_corpus_path,
    )
    snapshot_id = "snapshot-" + candidate.plan.experiment_id.removeprefix("registry-")
    snapshot = freeze_experiment_snapshot(
        snapshot_id=snapshot_id,
        registry_id=catalog.registry_id,
        registry_digest=catalog.digest,
        methodology_id=candidate.plan.methodology_id,
        methodology_digest=candidate.plan.methodology_digest,
        comparison_type=request.comparison_type,
        plan=candidate.plan,
        provider_selections=candidate.selections,
        preflight=preflight,
    )
    validate_frozen_runtime_contract(snapshot.plan, snapshot.provider_selections)
    return snapshot
