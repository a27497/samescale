from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Sha256Digest
from harnesslab.evaluation_suites.admission import (
    AdmissionDecision,
    AdmissionPolicy,
    AdmissionStatus,
    GovernanceNamespace,
    validate_admission_decision,
)
from harnesslab.evaluation_suites.models import (
    EvaluationSuiteManifest,
    EvaluationSuiteMembership,
    ImmutableArtifactReference,
    SuiteManifestReference,
    VersionedPolicyReference,
)
from harnesslab.experiment.funnel_v3 import (
    EvidenceRoleV3,
    FunnelMethodologyReference,
    FunnelMethodologyV3,
    FunnelV3Error,
    FunnelV3Stage,
    StageDecisionValue,
    StageMaterialIdentity,
)
from harnesslab.experiment.funnel_v3 import StageDecision as FunnelV3StageDecision
from harnesslab.experiment.plan import (
    ExperimentPlan,
    ExperimentRunSlot,
    PlannedTask,
    build_experiment_plan,
)
from harnesslab.experiment.spec import ExperimentSpec

if TYPE_CHECKING:
    from harnesslab.evaluation_suites.holdout import HoldoutEligibilityResult


class FunnelSlotDisposition(StrEnum):
    REUSED = "REUSED"
    NEWLY_SCHEDULED = "NEWLY_SCHEDULED"


def logical_observation_identity(
    slot: ExperimentRunSlot,
    *,
    methodology: FunnelMethodologyReference,
) -> str:
    """Identity of one scientific observation, deliberately excluding experiment id/order."""

    payload = {
        "task": slot.task.model_dump(mode="json"),
        "cell_id": slot.cell_id,
        "lane": slot.lane.value,
        "repeat_index": slot.repeat_index,
        "requested_model": slot.requested_model,
        "provider_route": slot.provider_route,
        "profile_identity": slot.profile_identity,
        "harness": slot.harness,
        "harness_version": slot.harness_version,
        "harness_config_identity": slot.harness_config_identity,
        "reasoning_effort": slot.reasoning_effort,
        "runner_contract": slot.runner_contract,
        "base_provider_profile_identity": slot.base_provider_profile_identity,
        "effective_runtime_profile_identity": slot.effective_runtime_profile_identity,
        "resource_envelope_identity": slot.resource_envelope_identity,
        "methodology": methodology.model_dump(mode="json"),
    }
    return canonical_digest(payload)


def _plan_material_components(base_plan: ExperimentPlan) -> tuple[str, str, str, str]:
    task_selection = canonical_digest([task.model_dump(mode="json") for task in base_plan.tasks])
    cell_configuration = canonical_digest(
        [cell.model_dump(mode="json") for cell in base_plan.cells]
    )
    controls = canonical_digest(
        {
            "comparison_intent": base_plan.comparison_intent,
            "execution_seed": base_plan.execution_seed,
            "paired_comparisons": [
                item.model_dump(mode="json") for item in base_plan.paired_comparisons
            ],
            "ablations": [item.model_dump(mode="json") for item in base_plan.ablations],
            "task_controls": [
                {
                    "task_digest": task.task_digest,
                    "workspace_input_digest": task.workspace_input_digest,
                    "verifier_identity": task.verifier_identity,
                    "budget_identity": task.budget_identity,
                    "network_policy": task.network_policy.value,
                }
                for task in base_plan.tasks
            ],
        }
    )
    resource_envelope = canonical_digest(
        {
            "cells": [
                {
                    "cell_id": cell.id,
                    "resource_budget_identity": cell.resource_budget_identity,
                    "resource_envelope_identity": cell.resource_envelope_identity,
                }
                for cell in base_plan.cells
            ]
        }
    )
    return task_selection, cell_configuration, controls, resource_envelope


class ObservationReuseEvidence(BaseModel):
    """One immutable primary observation offered for exact logical-slot reuse."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_plan: ImmutableArtifactReference
    source_slot: ExperimentRunSlot
    methodology: FunnelMethodologyReference
    logical_observation_identity: Sha256Digest
    evidence: ImmutableArtifactReference
    evidence_role: EvidenceRoleV3
    evidence_eligible: bool

    @model_validator(mode="after")
    def identity_matches_source_slot(self) -> ObservationReuseEvidence:
        expected = logical_observation_identity(self.source_slot, methodology=self.methodology)
        if self.logical_observation_identity != expected:
            raise ValueError("reuse evidence logical observation identity is stale or mismatched")
        return self


class FunnelV3PlanSlot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    logical_observation_identity: Sha256Digest
    planned_slot_id: Sha256Digest
    disposition: FunnelSlotDisposition
    source_slot_id: Sha256Digest | None = None
    source_plan: ImmutableArtifactReference | None = None
    source_evidence: ImmutableArtifactReference | None = None

    @model_validator(mode="after")
    def reuse_fields_match_disposition(self) -> FunnelV3PlanSlot:
        reuse_fields = (self.source_slot_id, self.source_plan, self.source_evidence)
        if self.disposition is FunnelSlotDisposition.REUSED and any(
            item is None for item in reuse_fields
        ):
            raise ValueError("REUSED logical slot requires exact source identities")
        if self.disposition is FunnelSlotDisposition.NEWLY_SCHEDULED and any(
            item is not None for item in reuse_fields
        ):
            raise ValueError("NEWLY_SCHEDULED logical slot cannot claim source evidence")
        return self


class FunnelV3ExperimentPlan(BaseModel):
    """Planning-only v3 wrapper over the existing experiment-plan expansion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[3] = 3
    stage: FunnelV3Stage
    methodology: FunnelMethodologyReference
    namespace: GovernanceNamespace
    material_identity: StageMaterialIdentity
    entry_decision: ImmutableArtifactReference
    suite_manifest: SuiteManifestReference | None = None
    admission_decisions: tuple[ImmutableArtifactReference, ...] = ()
    holdout_eligibility: tuple[ImmutableArtifactReference, ...] = ()
    base_plan: ExperimentPlan
    logical_slots: tuple[FunnelV3PlanSlot, ...]
    reused_slot_ids: tuple[Sha256Digest, ...]
    reused_source_slot_ids: tuple[Sha256Digest, ...]
    newly_scheduled_slot_ids: tuple[Sha256Digest, ...]
    automatic_promotion: Literal[False] = False
    external_execution_authorized: Literal[False] = False
    plan_digest: Sha256Digest

    @model_validator(mode="after")
    def plan_is_consistent_and_self_identifying(self) -> FunnelV3ExperimentPlan:
        if self.stage is FunnelV3Stage.PREFLIGHT:
            raise ValueError("Stage 0 is evidence-only until the unified M.5 Preflight service")
        if self.methodology != self.material_identity.methodology:
            raise ValueError("plan methodology does not match its material identity")
        if self.namespace is not self.material_identity.namespace:
            raise ValueError("plan namespace does not match its material identity")
        if self.suite_manifest != self.material_identity.suite_manifest:
            raise ValueError("plan suite does not match its material identity")
        material_components = _plan_material_components(self.base_plan)
        declared_components = (
            self.material_identity.task_selection_identity,
            self.material_identity.cell_configuration_identity,
            self.material_identity.controls_identity,
            self.material_identity.resource_envelope_identity,
        )
        if material_components != declared_components:
            raise ValueError("base plan controls or identities do not match material identity")
        required_repeat = self.stage.repeat_count
        if required_repeat is not None and self.base_plan.repeat_count != required_repeat:
            raise ValueError(f"{self.stage.value} plan requires n={required_repeat}")
        if self.stage.suite_purpose is not None and (
            self.suite_manifest is None
            or self.suite_manifest.purpose is not self.stage.suite_purpose
        ):
            raise ValueError("suite stage plan requires the correct suite purpose")
        if self.stage.suite_purpose is None and self.suite_manifest is not None:
            raise ValueError("non-suite plan cannot claim a suite manifest")
        logical_ids = tuple(item.logical_observation_identity for item in self.logical_slots)
        if len(set(logical_ids)) != len(logical_ids):
            raise ValueError("Funnel v3 plan contains duplicate logical observations")
        expected_slots = {
            slot.slot_id: logical_observation_identity(slot, methodology=self.methodology)
            for slot in self.base_plan.run_slots
        }
        declared_slots = {
            item.planned_slot_id: item.logical_observation_identity for item in self.logical_slots
        }
        if expected_slots != declared_slots:
            raise ValueError("logical observations do not match the exact base plan slots")
        if tuple(sorted(self.logical_slots, key=lambda item: item.planned_slot_id)) != (
            self.logical_slots
        ):
            raise ValueError("Funnel v3 logical slots must use canonical planned-slot order")
        reused = tuple(
            item.planned_slot_id
            for item in self.logical_slots
            if item.disposition is FunnelSlotDisposition.REUSED
        )
        sources = tuple(
            item.source_slot_id
            for item in self.logical_slots
            if item.disposition is FunnelSlotDisposition.REUSED and item.source_slot_id is not None
        )
        new = tuple(
            item.planned_slot_id
            for item in self.logical_slots
            if item.disposition is FunnelSlotDisposition.NEWLY_SCHEDULED
        )
        if self.reused_slot_ids != reused or self.reused_source_slot_ids != sources:
            raise ValueError("explicit reused slot identities do not match slot dispositions")
        if self.newly_scheduled_slot_ids != new:
            raise ValueError("explicit newly scheduled slot identities do not match dispositions")
        if self.plan_digest != canonical_digest(self.payload()):
            raise ValueError("Funnel v3 plan digest does not match its payload")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"plan_digest"})

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def as_reference(self) -> ImmutableArtifactReference:
        return ImmutableArtifactReference(
            artifact_id=self.base_plan.experiment_id,
            schema_version=self.schema_version,
            artifact_digest=self.plan_digest,
        )


def build_stage_material_identity(
    base_plan: ExperimentPlan,
    *,
    stage: FunnelV3Stage,
    methodology: FunnelMethodologyV3,
    namespace: GovernanceNamespace,
    suite_manifest: EvaluationSuiteManifest | None = None,
    relevant_policies: tuple[VersionedPolicyReference, ...] = (),
) -> StageMaterialIdentity:
    expected_purpose = stage.suite_purpose
    if expected_purpose is None and suite_manifest is not None:
        raise FunnelV3Error("non-suite stage cannot use a suite manifest")
    if expected_purpose is not None and (
        suite_manifest is None or suite_manifest.purpose is not expected_purpose
    ):
        raise FunnelV3Error("suite stage requires a manifest with the exact stage purpose")
    policies = tuple(
        sorted(
            set(relevant_policies),
            key=lambda item: (item.policy_id, item.policy_version, item.policy_digest),
        )
    )
    task_selection, cell_configuration, controls, resource_envelope = _plan_material_components(
        base_plan
    )
    return StageMaterialIdentity(
        namespace=namespace,
        methodology=methodology.as_reference(),
        task_selection_identity=task_selection,
        cell_configuration_identity=cell_configuration,
        controls_identity=controls,
        resource_envelope_identity=resource_envelope,
        relevant_policies=policies,
        suite_manifest=None if suite_manifest is None else suite_manifest.as_reference(),
    )


def _planned_task_identity(task: PlannedTask) -> tuple[str, str, str, str, str]:
    return (
        task.task_id,
        task.task_version,
        task.task_digest,
        task.workspace_input_digest,
        task.verifier_identity,
    )


def _suite_task_identity(
    membership: EvaluationSuiteMembership,
) -> tuple[str, str, str, str, str]:
    task = membership.task
    return (
        task.task_id,
        task.task_version,
        task.task_digest,
        task.workspace_digest,
        task.verifier_digest,
    )


def _validate_suite_governance(
    *,
    base_plan: ExperimentPlan,
    suite_manifest: EvaluationSuiteManifest,
    namespace: GovernanceNamespace,
    admission_decisions: tuple[AdmissionDecision, ...],
    admission_policies: tuple[AdmissionPolicy, ...],
) -> tuple[ImmutableArtifactReference, ...]:
    planned = {_planned_task_identity(task) for task in base_plan.tasks}
    manifested = {_suite_task_identity(item) for item in suite_manifest.memberships}
    if planned != manifested:
        raise FunnelV3Error("suite-stage task selection must equal exact manifest membership")
    policy_by_reference = {policy.as_reference(): policy for policy in admission_policies}
    admitted_by_task: dict[tuple[str, str, str, str, str], AdmissionDecision] = {}
    for decision in admission_decisions:
        policy = policy_by_reference.get(decision.admission_policy)
        if policy is None:
            raise FunnelV3Error("suite admission decision is missing its exact policy")
        try:
            validate_admission_decision(
                decision,
                policy=policy,
                target_suite=suite_manifest.as_reference(),
            )
        except ValueError as exc:
            raise FunnelV3Error(str(exc)) from exc
        if decision.status is not AdmissionStatus.ADMITTED:
            raise FunnelV3Error("candidate or rejected admission cannot satisfy suite planning")
        if decision.namespace is not namespace or policy.namespace is not namespace:
            raise FunnelV3Error("Official and Custom suite governance cannot be cross-used")
        task = decision.candidate.characteristics.task
        key = (
            task.task_id,
            task.task_version,
            task.task_digest,
            task.workspace_digest,
            task.verifier_digest,
        )
        if key in admitted_by_task:
            raise FunnelV3Error("suite task has multiple admission decisions")
        admitted_by_task[key] = decision
    if set(admitted_by_task) != planned:
        raise FunnelV3Error("every selected suite member requires one admitted decision")
    return tuple(
        decision.as_empirical_reference().artifact
        for _, decision in sorted(admitted_by_task.items())
    )


def _holdout_references(
    results: tuple[HoldoutEligibilityResult, ...],
    *,
    base_plan: ExperimentPlan,
    namespace: GovernanceNamespace,
) -> tuple[ImmutableArtifactReference, ...]:
    from harnesslab.evaluation_suites.holdout import HoldoutEligibilityStatus

    planned_task_ids = {_planned_task_identity(task) for task in base_plan.tasks}
    references: list[ImmutableArtifactReference] = []
    seen: set[str] = set()
    for result in results:
        task = result.task
        task_identity = (
            task.task_id,
            task.task_version,
            task.task_digest,
            task.workspace_digest,
            task.verifier_digest,
        )
        if task_identity not in planned_task_ids:
            raise FunnelV3Error("holdout eligibility does not bind a selected task")
        if result.namespace is not namespace:
            raise FunnelV3Error("Official and Custom holdout evidence cannot be cross-used")
        if result.status is not HoldoutEligibilityStatus.ELIGIBLE:
            raise FunnelV3Error("ineligible or unknown holdout evidence cannot support planning")
        if result.eligibility_digest in seen:
            raise FunnelV3Error("duplicate holdout eligibility identity")
        seen.add(result.eligibility_digest)
        references.append(
            ImmutableArtifactReference(
                artifact_id=result.evaluation_id,
                schema_version=result.schema_version,
                artifact_digest=result.eligibility_digest,
            )
        )
    return tuple(sorted(references, key=lambda item: (item.artifact_id, item.artifact_digest)))


def build_funnel_v3_experiment_plan(
    spec: ExperimentSpec,
    repository_root: Path,
    *,
    stage: FunnelV3Stage,
    methodology: FunnelMethodologyV3,
    namespace: GovernanceNamespace,
    entry_decision: FunnelV3StageDecision,
    suite_manifest: EvaluationSuiteManifest | None = None,
    admission_decisions: tuple[AdmissionDecision, ...] = (),
    admission_policies: tuple[AdmissionPolicy, ...] = (),
    holdout_eligibility: tuple[HoldoutEligibilityResult, ...] = (),
    reusable_observations: tuple[ObservationReuseEvidence, ...] = (),
) -> FunnelV3ExperimentPlan:
    """Build an inert v3 plan through the existing deterministic plan expansion."""

    if not isinstance(entry_decision, FunnelV3StageDecision):
        raise FunnelV3Error("bare GO cannot authorize Funnel v3 planning")
    if stage is FunnelV3Stage.PREFLIGHT:
        raise FunnelV3Error("M.4 does not implement the unified Stage 0 Preflight planner")
    base_plan = build_experiment_plan(spec, repository_root)
    if stage.repeat_count is not None and base_plan.repeat_count != stage.repeat_count:
        raise FunnelV3Error(f"{stage.value} planning requires n={stage.repeat_count}")
    policy_refs = tuple(policy.as_reference() for policy in admission_policies)
    material = build_stage_material_identity(
        base_plan,
        stage=stage,
        methodology=methodology,
        namespace=namespace,
        suite_manifest=suite_manifest,
        relevant_policies=policy_refs,
    )
    if entry_decision.decision is not StageDecisionValue.GO:
        raise FunnelV3Error("only an evidence-bound GO can permit next-stage planning")
    if entry_decision.target_stage is not stage:
        raise FunnelV3Error("entry decision targets a different stage")
    if entry_decision.target_material_identity != material:
        raise FunnelV3Error("entry decision target controls or identity changed")
    # This revalidates exact source evidence only at issuance time. The immutable decision
    # reference is sufficient here; no external executor accepts this planning-only wrapper.
    if entry_decision.methodology != methodology.as_reference():
        raise FunnelV3Error("entry decision uses a stale methodology")
    required_gate_policies = {
        methodology.policy_for(entry_decision.source_stage).exit_policy,
        methodology.policy_for(stage).entry_policy,
    }
    if not required_gate_policies <= set(entry_decision.relevant_policies):
        raise FunnelV3Error("entry decision is missing exact stage gate policy identities")

    admission_references: tuple[ImmutableArtifactReference, ...] = ()
    if suite_manifest is not None:
        admission_references = _validate_suite_governance(
            base_plan=base_plan,
            suite_manifest=suite_manifest,
            namespace=namespace,
            admission_decisions=admission_decisions,
            admission_policies=admission_policies,
        )
    elif admission_decisions or admission_policies:
        raise FunnelV3Error("non-suite stages cannot consume suite admission governance")
    holdout_references = _holdout_references(
        holdout_eligibility,
        base_plan=base_plan,
        namespace=namespace,
    )

    reuse_by_logical: dict[str, ObservationReuseEvidence] = {}
    for evidence in reusable_observations:
        if evidence.methodology != methodology.as_reference():
            raise FunnelV3Error("reuse evidence methodology identity changed")
        if evidence.evidence_role is not EvidenceRoleV3.PRIMARY:
            raise FunnelV3Error("recovery evidence cannot silently replace primary evidence")
        if not evidence.evidence_eligible:
            raise FunnelV3Error("ineligible evidence cannot be reused")
        if evidence.logical_observation_identity in reuse_by_logical:
            raise FunnelV3Error("one logical observation cannot be reused more than once")
        reuse_by_logical[evidence.logical_observation_identity] = evidence

    slots: list[FunnelV3PlanSlot] = []
    for slot in base_plan.run_slots:
        logical_id = logical_observation_identity(slot, methodology=methodology.as_reference())
        reusable = reuse_by_logical.get(logical_id)
        if reusable is None:
            planned = FunnelV3PlanSlot(
                logical_observation_identity=logical_id,
                planned_slot_id=slot.slot_id,
                disposition=FunnelSlotDisposition.NEWLY_SCHEDULED,
            )
        else:
            planned = FunnelV3PlanSlot(
                logical_observation_identity=logical_id,
                planned_slot_id=slot.slot_id,
                disposition=FunnelSlotDisposition.REUSED,
                source_slot_id=reusable.source_slot.slot_id,
                source_plan=reusable.source_plan,
                source_evidence=reusable.evidence,
            )
        slots.append(planned)
    unused_reuse = set(reuse_by_logical) - {item.logical_observation_identity for item in slots}
    if unused_reuse:
        raise FunnelV3Error("reuse evidence does not match any exact target logical observation")
    ordered_slots = tuple(sorted(slots, key=lambda item: item.planned_slot_id))
    payload: dict[str, Any] = {
        "schema_version": 3,
        "stage": stage.value,
        "methodology": methodology.as_reference().model_dump(mode="json"),
        "namespace": namespace.value,
        "material_identity": material.model_dump(mode="json"),
        "entry_decision": entry_decision.as_reference().model_dump(mode="json"),
        "suite_manifest": (
            None
            if suite_manifest is None
            else suite_manifest.as_reference().model_dump(mode="json")
        ),
        "admission_decisions": [item.model_dump(mode="json") for item in admission_references],
        "holdout_eligibility": [item.model_dump(mode="json") for item in holdout_references],
        "base_plan": base_plan.model_dump(mode="json"),
        "logical_slots": [item.model_dump(mode="json") for item in ordered_slots],
        "reused_slot_ids": [
            item.planned_slot_id
            for item in ordered_slots
            if item.disposition is FunnelSlotDisposition.REUSED
        ],
        "reused_source_slot_ids": [
            item.source_slot_id
            for item in ordered_slots
            if item.disposition is FunnelSlotDisposition.REUSED
        ],
        "newly_scheduled_slot_ids": [
            item.planned_slot_id
            for item in ordered_slots
            if item.disposition is FunnelSlotDisposition.NEWLY_SCHEDULED
        ],
        "automatic_promotion": False,
        "external_execution_authorized": False,
    }
    payload["plan_digest"] = canonical_digest(payload)
    try:
        return FunnelV3ExperimentPlan.model_validate(payload)
    except ValueError as exc:
        if isinstance(exc, FunnelV3Error):
            raise
        raise FunnelV3Error(str(exc)) from exc
