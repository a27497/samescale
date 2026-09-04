from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.budget.plan import (
    PlanBudgetEstimate,
    PlanBudgetEstimateRequest,
    PlanBudgetStatus,
    PlanCellBudget,
    build_plan_budget_request,
    estimate_plan_budget,
)
from harnesslab.budget.reservation import (
    BudgetReservationReceipt,
    ReservationDecision,
)
from harnesslab.comparability.models import ComparabilityStatus, canonical_digest
from harnesslab.contracts.common import EvaluationLane, Identifier, NetworkPolicy, Sha256Digest
from harnesslab.evaluation_suites.admission import GovernanceNamespace
from harnesslab.evaluation_suites.models import ImmutableArtifactReference
from harnesslab.experiment.funnel_plan import build_stage_material_identity
from harnesslab.experiment.funnel_v3 import (
    FunnelMethodologyReference,
    FunnelMethodologyV3,
    FunnelV3Stage,
    PreflightBudgetFacts,
    StageComparabilityFacts,
    StageCoverageFacts,
    StageEvidence,
    StageMaterialIdentity,
    build_stage_evidence,
)
from harnesslab.experiment.methodology import BudgetContract
from harnesslab.experiment.plan import ExperimentPlan, build_experiment_plan
from harnesslab.experiment.spec import ExperimentSpec
from harnesslab.preflight.models import (
    CheckStatus,
    ConfigurationKind,
    ConfigurationRequirement,
    FrozenResourceEnvelope,
    HarnessRequirement,
    PreflightFinding,
    PreflightObservations,
    PreflightSpecification,
    ProviderRouteRequirement,
    TaskRequirement,
    TraceSupport,
)
from harnesslab.preflight.service import assess_preflight


class UnifiedPreflightError(ValueError):
    """A plan-derived preflight artifact is incomplete, stale, or unsafe."""


class UnifiedPreflightStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class NormalizedCheckId(StrEnum):
    DOCKER_RUNTIME = "DOCKER_RUNTIME"
    DATABASE_SCHEMA = "DATABASE_SCHEMA"
    DISK_CAPACITY = "DISK_CAPACITY"
    LOCAL_IMAGES = "LOCAL_IMAGES"
    CREDENTIALS = "CREDENTIALS"
    PROVIDER_ROUTES = "PROVIDER_ROUTES"
    HARNESS_RUNTIME_CAPABILITIES = "HARNESS_RUNTIME_CAPABILITIES"
    TASK_VALIDITY = "TASK_VALIDITY"
    LANE_SUPPORT = "LANE_SUPPORT"
    MODEL_HARNESS_COMPATIBILITY = "MODEL_HARNESS_COMPATIBILITY"
    NETWORK_POLICY = "NETWORK_POLICY"
    COMPARABILITY_RISK = "COMPARABILITY_RISK"
    PLAN_BUDGET = "PLAN_BUDGET"


class CheckDecision(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"


class LocalImageIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: str = Field(min_length=1, max_length=500)
    image_digest: Sha256Digest
    platform: str = Field(min_length=1, max_length=100)


class UnifiedRuntimeSelection(BaseModel):
    """Exact plan-cell route and harness selection, containing references but no secrets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cell_id: Identifier
    provider_route: str = Field(min_length=1, max_length=500)
    provider_profile_identity: Sha256Digest
    route_configuration_identity: Sha256Digest
    credential_references: tuple[str, ...] = ()
    requires_network: bool
    harness_id: str = Field(min_length=1, max_length=100)
    harness_version: str = Field(min_length=1, max_length=100)
    harness_config_identity: Sha256Digest
    requested_model: str = Field(min_length=1, max_length=300)
    supported_lanes: tuple[EvaluationLane, ...] = Field(min_length=1)
    compatible_models: tuple[str, ...] = Field(min_length=1)
    required_capabilities: tuple[str, ...] = ()
    image: LocalImageIdentity | None = None
    resource_envelope_identity: Sha256Digest
    selection_digest: Sha256Digest

    @model_validator(mode="after")
    def selection_is_canonical_and_self_identifying(self) -> UnifiedRuntimeSelection:
        if tuple(sorted(set(self.credential_references))) != self.credential_references:
            raise ValueError("credential references must be unique and canonical")
        if tuple(sorted(set(self.supported_lanes), key=lambda item: item.value)) != (
            self.supported_lanes
        ):
            raise ValueError("supported lanes must be unique and canonical")
        if tuple(sorted(set(self.compatible_models))) != self.compatible_models:
            raise ValueError("compatible models must be unique and canonical")
        if tuple(sorted(set(self.required_capabilities))) != self.required_capabilities:
            raise ValueError("required capabilities must be unique and canonical")
        if self.selection_digest != canonical_digest(self.payload()):
            raise ValueError("runtime selection digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"selection_digest"})


def build_runtime_selection(**values: Any) -> UnifiedRuntimeSelection:
    payload = dict(values)
    payload["credential_references"] = sorted(payload.get("credential_references", ()))
    payload["supported_lanes"] = sorted(
        item.value if isinstance(item, EvaluationLane) else item
        for item in payload["supported_lanes"]
    )
    payload["compatible_models"] = sorted(payload["compatible_models"])
    payload["required_capabilities"] = sorted(payload.get("required_capabilities", ()))
    image = payload.get("image")
    if isinstance(image, LocalImageIdentity):
        payload["image"] = image.model_dump(mode="json")
    else:
        payload["image"] = None
    payload["selection_digest"] = canonical_digest(payload)
    return UnifiedRuntimeSelection.model_validate(payload)


class UnifiedPreflightSpecification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    specification_id: Identifier
    base_plan: ExperimentPlan
    candidate_plan: ImmutableArtifactReference
    target_stage: Literal[FunnelV3Stage.SMOKE] = FunnelV3Stage.SMOKE
    target_material: StageMaterialIdentity
    methodology: FunnelMethodologyReference
    namespace: GovernanceNamespace
    runtime_selections: tuple[UnifiedRuntimeSelection, ...]
    prerequisites: PreflightSpecification
    budget_request: PlanBudgetEstimateRequest
    fixed_disk_bytes: int = Field(ge=0)
    disk_bytes_per_slot: int = Field(ge=0)
    formal_comparability_required: bool
    specification_digest: Sha256Digest

    @model_validator(mode="after")
    def bindings_are_exact_and_self_identifying(self) -> UnifiedPreflightSpecification:
        expected_plan = ImmutableArtifactReference(
            artifact_id=self.base_plan.experiment_id,
            schema_version=self.base_plan.schema_version,
            artifact_digest=self.base_plan.digest,
        )
        if self.candidate_plan != expected_plan:
            raise ValueError("candidate plan reference is stale or mismatched")
        if self.target_material.methodology != self.methodology:
            raise ValueError("target material methodology is stale or mismatched")
        if self.target_material.namespace is not self.namespace:
            raise ValueError("target material namespace is stale or mismatched")
        selections = tuple(sorted(self.runtime_selections, key=lambda item: item.cell_id))
        if selections != self.runtime_selections:
            raise ValueError("runtime selections must be canonical")
        cells = {cell.id: cell for cell in self.base_plan.cells}
        if set(cells) != {item.cell_id for item in selections}:
            raise ValueError("every exact plan cell requires one runtime selection")
        for selection in selections:
            cell = cells[selection.cell_id]
            if (
                selection.provider_route != cell.provider_route
                or selection.provider_profile_identity != cell.profile_identity
                or selection.harness_id != cell.harness
                or selection.harness_version != cell.harness_version
                or selection.harness_config_identity != cell.harness_config_identity
                or selection.requested_model != cell.requested_model
                or selection.resource_envelope_identity != cell.resource_envelope_identity
            ):
                raise ValueError("runtime selection does not match the exact planned cell")
        if (
            self.budget_request.candidate_plan != self.candidate_plan
            or self.budget_request.target_stage is not self.target_stage
            or self.budget_request.material_identity != self.target_material
        ):
            raise ValueError("budget request is not bound to the exact candidate material")
        required_disk = self.fixed_disk_bytes + self.disk_bytes_per_slot * len(
            self.base_plan.run_slots
        )
        if self.prerequisites.minimum_free_bytes != required_disk:
            raise ValueError("disk requirement is not derived from the exact logical slot count")
        if self.specification_digest != canonical_digest(self.payload()):
            raise ValueError("unified preflight specification digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", exclude={"specification_digest"})
        payload["prerequisites"] = _prerequisites_payload(self.prerequisites)
        return payload


class UnifiedPreflightObservations(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    local: PreflightObservations
    database_schema_ready: bool
    local_images: tuple[LocalImageIdentity, ...] = ()
    route_configuration_identities: dict[str, Sha256Digest] = Field(default_factory=dict)
    harness_runtime_selection_identities: dict[str, Sha256Digest] = Field(default_factory=dict)
    harness_capabilities: dict[str, frozenset[str]] = Field(default_factory=dict)
    task_validation_identities: dict[str, Sha256Digest] = Field(default_factory=dict)
    comparability_controls_match: bool


def _prerequisites_payload(prerequisites: PreflightSpecification) -> dict[str, Any]:
    payload = prerequisites.model_dump(mode="json")
    for harness in payload["harnesses"]:
        harness["compatible_models"] = sorted(harness["compatible_models"])
        harness["supported_lanes"] = sorted(harness["supported_lanes"])
    for task in payload["tasks"]:
        if "supported_lanes" in task:
            task["supported_lanes"] = sorted(task["supported_lanes"])
    return payload


class NormalizedPreflightCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    check_id: NormalizedCheckId
    decision: CheckDecision
    reason_codes: tuple[str, ...] = Field(min_length=1)
    source_finding_ids: tuple[str, ...] = ()


class UnifiedPreflightReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    receipt_id: Identifier
    specification: ImmutableArtifactReference
    candidate_plan: ImmutableArtifactReference
    target_stage: Literal[FunnelV3Stage.SMOKE] = FunnelV3Stage.SMOKE
    target_material: StageMaterialIdentity
    methodology: FunnelMethodologyReference
    namespace: GovernanceNamespace
    runtime_selection_identities: tuple[Sha256Digest, ...]
    network_policies: tuple[NetworkPolicy, ...]
    checks: tuple[NormalizedPreflightCheck, ...]
    budget_estimate: PlanBudgetEstimate
    status: UnifiedPreflightStatus
    provider_live_availability: Literal["NOT_PROBED"] = "NOT_PROBED"
    provider_calls: Literal[0] = 0
    harness_calls: Literal[0] = 0
    judge_calls: Literal[0] = 0
    matrix_calls: Literal[0] = 0
    automatic_stage_decision: Literal[False] = False
    external_execution_authorized: Literal[False] = False
    secret_values_included: Literal[False] = False
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def receipt_is_complete_and_self_identifying(self) -> UnifiedPreflightReceipt:
        if tuple(item.check_id for item in self.checks) != tuple(NormalizedCheckId):
            raise ValueError("receipt checks must be complete and canonical")
        blocked = any(item.decision is CheckDecision.BLOCKED for item in self.checks)
        if (self.status is UnifiedPreflightStatus.BLOCKED) != blocked:
            raise ValueError("receipt status does not match normalized checks")
        if self.receipt_digest != canonical_digest(self.payload()):
            raise ValueError("unified preflight receipt digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"receipt_digest"})

    def as_reference(self) -> ImmutableArtifactReference:
        return ImmutableArtifactReference(
            artifact_id=self.receipt_id,
            schema_version=self.schema_version,
            artifact_digest=self.receipt_digest,
        )


def build_unified_preflight_specification(
    *,
    specification_id: str,
    experiment_spec: ExperimentSpec,
    existing_plan: ExperimentPlan,
    repository_root: Path,
    methodology: FunnelMethodologyV3,
    namespace: GovernanceNamespace,
    runtime_selections: tuple[UnifiedRuntimeSelection, ...],
    stage_budget: BudgetContract,
    cell_budgets: tuple[PlanCellBudget, ...],
    fixed_disk_bytes: int,
    disk_bytes_per_slot: int,
    docker_required: bool = True,
    database_required: bool = True,
    formal_comparability_required: bool = False,
) -> UnifiedPreflightSpecification:
    """Derive one Stage-0 authority directly from ExperimentSpec and ExperimentPlan."""

    if build_experiment_plan(experiment_spec, repository_root) != existing_plan:
        raise UnifiedPreflightError("existing plan is not the exact expansion of ExperimentSpec")
    target_material = build_stage_material_identity(
        existing_plan,
        stage=FunnelV3Stage.SMOKE,
        methodology=methodology,
        namespace=namespace,
    )
    ordered = tuple(sorted(runtime_selections, key=lambda item: item.cell_id))
    credentials = tuple(
        sorted({reference for item in ordered for reference in item.credential_references})
    )
    images = tuple(sorted({item.image.reference for item in ordered if item.image is not None}))
    policies = tuple(sorted({cell.network_policy for cell in existing_plan.cells}, key=str))
    if len(policies) != 1:
        raise UnifiedPreflightError("one unified preflight requires one exact network policy")
    prerequisites = PreflightSpecification(
        docker_required=docker_required,
        database_required=database_required,
        minimum_free_bytes=fixed_disk_bytes + disk_bytes_per_slot * len(existing_plan.run_slots),
        required_images=images,
        configurations=tuple(
            ConfigurationRequirement(reference=reference, kind=ConfigurationKind.CREDENTIAL)
            for reference in credentials
        ),
        provider_routes=tuple(
            ProviderRouteRequirement(
                route_identity=item.provider_route,
                expected_identity=item.provider_route,
                requires_network=item.requires_network,
            )
            for item in ordered
        ),
        harnesses=tuple(
            HarnessRequirement(
                harness_id=item.cell_id,
                requested_model=item.requested_model,
                compatible_models=item.compatible_models,
                supported_lanes=item.supported_lanes,
                selected_lane=next(
                    cell.lane for cell in existing_plan.cells if cell.id == item.cell_id
                ),
                trace_support=TraceSupport.FULL_STREAM,
                required_trace_support=TraceSupport.FINAL_OUTPUT_ONLY,
            )
            for item in ordered
        ),
        tasks=tuple(
            TaskRequirement(
                package_path=task.package_path,
                selected_lane=existing_plan.cells[0].lane,
            )
            for task in existing_plan.tasks
        ),
        network_policy=policies[0],
        resource_envelope=FrozenResourceEnvelope(
            expected_identity=target_material.resource_envelope_identity,
            actual_identity=target_material.resource_envelope_identity,
        ),
        budget=None,
    )
    budget_request = build_plan_budget_request(
        request_id=f"{specification_id}-budget",
        plan=existing_plan,
        target_stage=FunnelV3Stage.SMOKE,
        material_identity=target_material,
        stage_budget=stage_budget,
        cell_budgets=cell_budgets,
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "specification_id": specification_id,
        "base_plan": existing_plan.model_dump(mode="json"),
        "candidate_plan": {
            "artifact_id": existing_plan.experiment_id,
            "schema_version": existing_plan.schema_version,
            "artifact_digest": existing_plan.digest,
        },
        "target_stage": FunnelV3Stage.SMOKE.value,
        "target_material": target_material.model_dump(mode="json"),
        "methodology": methodology.as_reference().model_dump(mode="json"),
        "namespace": namespace.value,
        "runtime_selections": [item.model_dump(mode="json") for item in ordered],
        "prerequisites": _prerequisites_payload(prerequisites),
        "budget_request": budget_request.model_dump(mode="json"),
        "fixed_disk_bytes": fixed_disk_bytes,
        "disk_bytes_per_slot": disk_bytes_per_slot,
        "formal_comparability_required": formal_comparability_required,
    }
    payload["specification_digest"] = canonical_digest(payload)
    return UnifiedPreflightSpecification.model_validate(payload)


_PREFIX_CATEGORIES: tuple[tuple[str, NormalizedCheckId], ...] = (
    ("docker", NormalizedCheckId.DOCKER_RUNTIME),
    ("database", NormalizedCheckId.DATABASE_SCHEMA),
    ("disk", NormalizedCheckId.DISK_CAPACITY),
    ("image:", NormalizedCheckId.LOCAL_IMAGES),
    ("configuration:", NormalizedCheckId.CREDENTIALS),
    ("provider-route:", NormalizedCheckId.PROVIDER_ROUTES),
    ("harness-runtime:", NormalizedCheckId.HARNESS_RUNTIME_CAPABILITIES),
    ("trace:", NormalizedCheckId.HARNESS_RUNTIME_CAPABILITIES),
    ("task:", NormalizedCheckId.TASK_VALIDITY),
    ("task-lane:", NormalizedCheckId.LANE_SUPPORT),
    ("harness-lane:", NormalizedCheckId.LANE_SUPPORT),
    ("harness-model:", NormalizedCheckId.MODEL_HARNESS_COMPATIBILITY),
    ("network:", NormalizedCheckId.NETWORK_POLICY),
    ("comparability:", NormalizedCheckId.COMPARABILITY_RISK),
    ("resource-envelope", NormalizedCheckId.COMPARABILITY_RISK),
)


def _category(finding: PreflightFinding) -> NormalizedCheckId | None:
    return next(
        (
            category
            for prefix, category in _PREFIX_CATEGORIES
            if finding.check_id.startswith(prefix)
        ),
        None,
    )


def assess_unified_preflight(
    specification: UnifiedPreflightSpecification,
    observations: UnifiedPreflightObservations,
) -> UnifiedPreflightReceipt:
    """Assess local facts and estimates only; never probes a provider or executes a harness."""

    legacy = assess_preflight(specification.prerequisites, observations.local)
    grouped: dict[NormalizedCheckId, list[PreflightFinding]] = {
        check_id: [] for check_id in NormalizedCheckId
    }
    for finding in legacy.findings:
        category = _category(finding)
        if category is not None:
            grouped[category].append(finding)

    extra: dict[NormalizedCheckId, list[str]] = {item: [] for item in NormalizedCheckId}
    if not observations.database_schema_ready:
        extra[NormalizedCheckId.DATABASE_SCHEMA].append("DATABASE_SCHEMA_NOT_READY")
    expected_images = {
        item.image.reference: item.image
        for item in specification.runtime_selections
        if item.image is not None
    }
    actual_images = {item.reference: item for item in observations.local_images}
    if expected_images != actual_images:
        extra[NormalizedCheckId.LOCAL_IMAGES].append("LOCAL_IMAGE_IDENTITY_MISMATCH")
    for selection in specification.runtime_selections:
        if (
            observations.route_configuration_identities.get(selection.cell_id)
            != selection.route_configuration_identity
        ):
            extra[NormalizedCheckId.PROVIDER_ROUTES].append(
                "PROVIDER_ROUTE_CONFIGURATION_IDENTITY_MISMATCH"
            )
        if (
            observations.harness_runtime_selection_identities.get(selection.cell_id)
            != selection.selection_digest
        ):
            extra[NormalizedCheckId.HARNESS_RUNTIME_CAPABILITIES].append(
                "HARNESS_RUNTIME_IDENTITY_MISMATCH"
            )
        available = observations.harness_capabilities.get(selection.cell_id, frozenset())
        if not set(selection.required_capabilities) <= available:
            extra[NormalizedCheckId.HARNESS_RUNTIME_CAPABILITIES].append(
                "HARNESS_CAPABILITY_MISSING"
            )
    planned_lanes = {cell.lane for cell in specification.base_plan.cells}
    for task in specification.base_plan.tasks:
        observed = observations.local.tasks.get(task.package_path)
        if observations.task_validation_identities.get(task.package_path) != canonical_digest(
            task.model_dump(mode="json")
        ):
            extra[NormalizedCheckId.TASK_VALIDITY].append("TASK_VALIDATION_IDENTITY_MISMATCH")
        if observed is None or not planned_lanes <= observed.supported_lanes:
            extra[NormalizedCheckId.LANE_SUPPORT].append("TASK_PLANNED_LANE_UNSUPPORTED")
    if not observations.comparability_controls_match:
        extra[NormalizedCheckId.COMPARABILITY_RISK].append("COMPARABILITY_CONTROL_DRIFT")
    budget = estimate_plan_budget(specification.budget_request, specification.base_plan)
    if budget.status is PlanBudgetStatus.BLOCKED:
        extra[NormalizedCheckId.PLAN_BUDGET].extend(item.value for item in budget.reason_codes)

    checks: list[NormalizedPreflightCheck] = []
    for check_id in NormalizedCheckId:
        findings = grouped[check_id]
        failures = [
            item.reason_code for item in findings if item.status is not CheckStatus.PASS
        ] + extra[check_id]
        reasons: tuple[str, ...]
        if not findings and not failures and check_id is not NormalizedCheckId.PLAN_BUDGET:
            reasons = ("NOT_APPLICABLE",)
        elif failures:
            reasons = tuple(sorted(set(failures)))
        else:
            reasons = ("CHECKS_PASSED",)
        checks.append(
            NormalizedPreflightCheck(
                check_id=check_id,
                decision=CheckDecision.BLOCKED if failures else CheckDecision.PASS,
                reason_codes=reasons,
                source_finding_ids=tuple(sorted(item.check_id for item in findings)),
            )
        )
    status = (
        UnifiedPreflightStatus.BLOCKED
        if any(item.decision is CheckDecision.BLOCKED for item in checks)
        else UnifiedPreflightStatus.READY
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "receipt_id": f"preflight-{specification.specification_digest[7:31]}",
        "specification": {
            "artifact_id": specification.specification_id,
            "schema_version": specification.schema_version,
            "artifact_digest": specification.specification_digest,
        },
        "candidate_plan": specification.candidate_plan.model_dump(mode="json"),
        "target_stage": specification.target_stage.value,
        "target_material": specification.target_material.model_dump(mode="json"),
        "methodology": specification.methodology.model_dump(mode="json"),
        "namespace": specification.namespace.value,
        "runtime_selection_identities": [
            item.selection_digest for item in specification.runtime_selections
        ],
        "network_policies": sorted(
            {cell.network_policy.value for cell in specification.base_plan.cells}
        ),
        "checks": [item.model_dump(mode="json") for item in checks],
        "budget_estimate": budget.model_dump(mode="json"),
        "status": status.value,
        "provider_live_availability": "NOT_PROBED",
        "provider_calls": 0,
        "harness_calls": 0,
        "judge_calls": 0,
        "matrix_calls": 0,
        "automatic_stage_decision": False,
        "external_execution_authorized": False,
        "secret_values_included": False,
    }
    payload["receipt_digest"] = canonical_digest(payload)
    return UnifiedPreflightReceipt.model_validate(payload)


def stage_zero_evidence_from_receipt(
    receipt: UnifiedPreflightReceipt,
    *,
    evidence_id: str,
) -> StageEvidence:
    """Adapt a READY receipt to authentic M.4 evidence without creating a GO decision."""

    if receipt.status is not UnifiedPreflightStatus.READY:
        raise UnifiedPreflightError("only a READY receipt can become Stage-0 evidence")
    coverage = StageCoverageFacts(
        planned_observations=0,
        terminal_observations=0,
        capability_observations=0,
        infrastructure_observations=0,
        missing_observations=0,
        eligible_primary_observations=0,
        primary_repeats_per_unit=0,
        all_scheduled_accounted=True,
    )
    comparability_reference = ImmutableArtifactReference(
        artifact_id=f"{receipt.receipt_id}-comparability",
        schema_version=1,
        artifact_digest=canonical_digest(
            {
                "receipt": receipt.receipt_digest,
                "check": NormalizedCheckId.COMPARABILITY_RISK.value,
            }
        ),
    )
    return build_stage_evidence(
        evidence_id=evidence_id,
        stage=FunnelV3Stage.PREFLIGHT,
        source_plan=receipt.candidate_plan,
        source_report=receipt.as_reference(),
        material_identity=receipt.target_material,
        coverage=coverage,
        comparability=StageComparabilityFacts(
            status=ComparabilityStatus.NOT_COMPARABLE,
            comparability_reference=comparability_reference,
        ),
        budget_preflight=PreflightBudgetFacts(
            preflight_reference=receipt.as_reference(),
            budget_reference=receipt.budget_estimate.as_reference(),
            preflight_passed=True,
            provider_calls=0,
            harness_calls=0,
            judge_calls=0,
            matrix_calls=0,
        ),
    )


class ExecutionGuardResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    eligible: Literal[True] = True
    execution_started: Literal[False] = False
    receipt_digest: Sha256Digest
    reservation_digest: Sha256Digest
    logical_unit_id: Sha256Digest
    guard_digest: Sha256Digest


def guard_pre_execution(
    *,
    receipt: UnifiedPreflightReceipt,
    specification: UnifiedPreflightSpecification,
    budget_estimate: PlanBudgetEstimate,
    reservation: BudgetReservationReceipt,
    logical_unit_id: str,
) -> ExecutionGuardResult:
    """Validate exact eligibility immediately before execution; this does not execute or claim."""

    if receipt.status is not UnifiedPreflightStatus.READY:
        raise UnifiedPreflightError("pre-execution guard requires a READY receipt")
    expected_spec = ImmutableArtifactReference(
        artifact_id=specification.specification_id,
        schema_version=specification.schema_version,
        artifact_digest=specification.specification_digest,
    )
    if (
        receipt.specification != expected_spec
        or receipt.candidate_plan != specification.candidate_plan
        or receipt.target_material != specification.target_material
        or receipt.methodology != specification.methodology
        or receipt.budget_estimate != budget_estimate
    ):
        raise UnifiedPreflightError("preflight receipt drifted from exact execution material")
    if (
        reservation.decision is not ReservationDecision.ACCEPTED
        or reservation.request.plan != receipt.candidate_plan
        or reservation.request.stage is not receipt.target_stage
        or reservation.request.budget_estimate != budget_estimate.as_reference()
        or reservation.request.logical_unit_id != logical_unit_id
    ):
        raise UnifiedPreflightError("an accepted exact-plan reservation is required")
    payload = {
        "eligible": True,
        "execution_started": False,
        "receipt_digest": receipt.receipt_digest,
        "reservation_digest": reservation.receipt_digest,
        "logical_unit_id": logical_unit_id,
    }
    return ExecutionGuardResult(**payload, guard_digest=canonical_digest(payload))


__all__ = [
    "CheckDecision",
    "ExecutionGuardResult",
    "LocalImageIdentity",
    "NormalizedCheckId",
    "NormalizedPreflightCheck",
    "UnifiedPreflightError",
    "UnifiedPreflightObservations",
    "UnifiedPreflightReceipt",
    "UnifiedPreflightSpecification",
    "UnifiedPreflightStatus",
    "UnifiedRuntimeSelection",
    "assess_unified_preflight",
    "build_runtime_selection",
    "build_unified_preflight_specification",
    "guard_pre_execution",
    "stage_zero_evidence_from_receipt",
]
