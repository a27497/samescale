from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from harnesslab.comparability.models import ComparabilityStatus, canonical_digest
from harnesslab.evaluation_suites import (
    AdmissionDecision,
    AdmissionEvidenceReference,
    AdmissionPolicy,
    AdmissionReasonCode,
    AdmissionStatus,
    DiscriminativeAcceptanceCriteria,
    EvidenceKind,
    GovernanceNamespace,
    ImmutableArtifactReference,
    PolicyProvenance,
    StressAcceptanceCriteria,
    StressDimension,
    SuitePurpose,
    TaskArtifactReference,
    build_admission_candidate,
    build_admission_decision,
    build_admission_policy,
    build_evaluation_suite_manifest,
    build_policy_provenance,
    build_task_characteristics,
)
from harnesslab.evaluation_suites.models import (
    EvaluationSuiteManifest,
    EvaluationSuiteMembership,
)
from harnesslab.experiment.funnel_plan import (
    FunnelSlotDisposition,
    ObservationReuseEvidence,
    build_funnel_v3_experiment_plan,
    build_stage_material_identity,
    logical_observation_identity,
)
from harnesslab.experiment.funnel_v3 import (
    DecisionActorAuthorization,
    EvidenceRoleV3,
    FunnelMethodologyV3,
    FunnelV3Error,
    FunnelV3Stage,
    PreflightBudgetFacts,
    StageComparabilityFacts,
    StageCoverageFacts,
    StageDecision,
    StageDecisionReasonCode,
    StageDecisionValue,
    StageEvidence,
    StageMaterialIdentity,
    build_funnel_v3_methodology,
    build_stage_chain_link,
    build_stage_decision,
    build_stage_evidence,
)
from harnesslab.experiment.methodology import (
    FunnelStage,
    load_evaluation_methodology,
    next_funnel_stage,
)
from harnesslab.experiment.methodology import StageDecision as HistoricalStageDecision
from harnesslab.experiment.plan import ExperimentPlan, ExperimentRunSlot, build_experiment_plan
from harnesslab.experiment.spec import ExperimentSpec
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.quality import (
    QualificationCheck,
    QualificationEvidence,
    TaskQualification,
    TaskQualityMetadata,
    qualify_task,
)
from tests.phase_g_helpers import ROOT, basic_spec, identity

METHODOLOGY_V2 = ROOT / "release" / "evaluation-methodology-v2.json"


def _digest(label: str) -> str:
    return canonical_digest({"m4-fixture": label})


def _artifact(label: str) -> ImmutableArtifactReference:
    return ImmutableArtifactReference(
        artifact_id=label,
        schema_version=1,
        artifact_digest=_digest(label),
    )


def _suite(
    purpose: SuitePurpose,
    *,
    memberships: tuple[EvaluationSuiteMembership, ...] = (),
) -> EvaluationSuiteManifest:
    return build_evaluation_suite_manifest(
        suite_id=f"m4-{purpose.value.lower()}",
        suite_version="1.0.0",
        purpose=purpose,
        memberships=memberships,
    )


def _base_for(stage: FunnelV3Stage) -> ExperimentPlan:
    repeat_count = stage.repeat_count or 1
    return build_experiment_plan(basic_spec(repeat_count=repeat_count), ROOT)


def _material(stage: FunnelV3Stage) -> StageMaterialIdentity:
    suite = None
    if stage.suite_purpose is not None:
        suite = _suite(stage.suite_purpose)
    return build_stage_material_identity(
        _base_for(stage),
        stage=stage,
        methodology=build_funnel_v3_methodology(),
        namespace=GovernanceNamespace.OFFICIAL,
        suite_manifest=suite,
    )


def _coverage(stage: FunnelV3Stage, *, complete: bool = True) -> StageCoverageFacts:
    if stage is FunnelV3Stage.PREFLIGHT:
        return StageCoverageFacts(
            planned_observations=0,
            terminal_observations=0,
            capability_observations=0,
            infrastructure_observations=0,
            missing_observations=0,
            eligible_primary_observations=0,
            primary_repeats_per_unit=0,
            all_scheduled_accounted=True,
        )
    repeats = stage.repeat_count or 1
    planned = repeats * 2
    missing = 0 if complete else 1
    return StageCoverageFacts(
        planned_observations=planned,
        terminal_observations=planned - missing,
        capability_observations=planned - missing,
        infrastructure_observations=0,
        missing_observations=missing,
        eligible_primary_observations=planned - missing,
        primary_repeats_per_unit=repeats,
        primary_repeat_indices=tuple(range(repeats)),
        all_scheduled_accounted=complete,
    )


def _comparability(
    status: ComparabilityStatus = ComparabilityStatus.COMPARABLE,
) -> StageComparabilityFacts:
    return StageComparabilityFacts(
        status=status,
        comparability_reference=_artifact(f"comparability-{status.value.lower()}"),
    )


def _preflight(*, passed: bool = True, provider_calls: int = 0) -> PreflightBudgetFacts:
    return PreflightBudgetFacts(
        preflight_reference=_artifact("preflight"),
        budget_reference=_artifact("budget"),
        preflight_passed=passed,
        provider_calls=provider_calls,
        harness_calls=0,
        judge_calls=0,
        matrix_calls=0,
    )


def _evidence(
    stage: FunnelV3Stage,
    *,
    complete: bool = True,
    comparable: ComparabilityStatus = ComparabilityStatus.COMPARABLE,
    preflight_passed: bool = True,
    provider_calls: int = 0,
) -> StageEvidence:
    return build_stage_evidence(
        evidence_id=f"evidence-stage-{stage.number}",
        stage=stage,
        source_plan=_artifact(f"plan-stage-{stage.number}"),
        source_report=_artifact(f"report-stage-{stage.number}"),
        material_identity=_material(stage),
        coverage=_coverage(stage, complete=complete),
        comparability=_comparability(comparable),
        budget_preflight=_preflight(
            passed=preflight_passed,
            provider_calls=provider_calls,
        ),
    )


def _actor() -> DecisionActorAuthorization:
    return DecisionActorAuthorization(
        actor_id="m4-reviewer",
        actor_identity=_digest("actor"),
        decision_authorization_identity=_digest("decision-authority"),
    )


def _go(
    source: FunnelV3Stage,
    target_material: StageMaterialIdentity | None = None,
) -> StageDecision:
    target = tuple(FunnelV3Stage)[source.number + 1]
    return build_stage_decision(
        decision_id=f"go-{source.number}-{target.number}",
        decision=StageDecisionValue.GO,
        source_evidence=_evidence(source),
        target_stage=target,
        target_material_identity=target_material or _material(target),
        methodology=build_funnel_v3_methodology(),
        actor_authorization=_actor(),
    )


def test_funnel_v3_vocabulary_order_and_fixed_repeats_are_exact() -> None:
    methodology = build_funnel_v3_methodology()

    assert tuple(FunnelV3Stage) == (
        FunnelV3Stage.PREFLIGHT,
        FunnelV3Stage.SMOKE,
        FunnelV3Stage.INFORMAL,
        FunnelV3Stage.FORMAL,
        FunnelV3Stage.DISCRIMINATIVE,
        FunnelV3Stage.STRESS,
    )
    assert "BREADTH" not in {stage.value for stage in FunnelV3Stage}
    assert len({FunnelV3Stage.DISCRIMINATIVE, FunnelV3Stage.STRESS}) == 2
    assert tuple(stage.repeat_count for stage in FunnelV3Stage) == (None, 1, 3, 5, None, None)
    assert tuple(item.stage_number for item in methodology.stages) == tuple(range(6))
    assert all(
        item.explicit_decision_required and not item.auto_promote for item in methodology.stages
    )


@pytest.mark.parametrize(
    ("source", "target"),
    tuple(zip(tuple(FunnelV3Stage)[:-1], tuple(FunnelV3Stage)[1:], strict=True)),
)
def test_every_adjacent_forward_go_is_evidence_bound(
    source: FunnelV3Stage, target: FunnelV3Stage
) -> None:
    decision = _go(source)

    assert decision.source_stage is source
    assert decision.target_stage is target
    assert decision.decision is StageDecisionValue.GO
    assert decision.source_evidence.artifact_digest == _evidence(source).evidence_digest
    assert decision.authorizes_plan_creation_only
    assert not decision.external_execution_authorized
    assert not decision.actor_authorization.external_execution_authorized


@pytest.mark.parametrize(
    ("source", "target"),
    (
        (FunnelV3Stage.PREFLIGHT, FunnelV3Stage.INFORMAL),
        (FunnelV3Stage.FORMAL, FunnelV3Stage.SMOKE),
        (FunnelV3Stage.SMOKE, FunnelV3Stage.SMOKE),
    ),
)
def test_skipped_backward_and_same_stage_transitions_fail(
    source: FunnelV3Stage, target: FunnelV3Stage
) -> None:
    with pytest.raises(FunnelV3Error, match="adjacent and forward"):
        build_stage_decision(
            decision_id="invalid-transition",
            decision=StageDecisionValue.GO,
            source_evidence=_evidence(source),
            target_stage=target,
            target_material_identity=_material(target),
            methodology=build_funnel_v3_methodology(),
            actor_authorization=_actor(),
        )


def test_stage_zero_go_requires_passing_keyless_zero_call_evidence() -> None:
    for evidence in (
        _evidence(FunnelV3Stage.PREFLIGHT, preflight_passed=False),
        _evidence(FunnelV3Stage.PREFLIGHT, provider_calls=1),
    ):
        with pytest.raises(FunnelV3Error, match="Stage 0"):
            build_stage_decision(
                decision_id="invalid-preflight-go",
                decision=StageDecisionValue.GO,
                source_evidence=evidence,
                target_stage=FunnelV3Stage.SMOKE,
                target_material_identity=_material(FunnelV3Stage.SMOKE),
                methodology=build_funnel_v3_methodology(),
                actor_authorization=_actor(),
            )


def test_incomplete_and_noncomparable_formal_evidence_fail_closed() -> None:
    with pytest.raises(FunnelV3Error, match="coverage"):
        build_stage_decision(
            decision_id="incomplete-smoke",
            decision=StageDecisionValue.GO,
            source_evidence=_evidence(FunnelV3Stage.SMOKE, complete=False),
            target_stage=FunnelV3Stage.INFORMAL,
            target_material_identity=_material(FunnelV3Stage.INFORMAL),
            methodology=build_funnel_v3_methodology(),
            actor_authorization=_actor(),
        )
    with pytest.raises(FunnelV3Error, match="COMPARABLE"):
        build_stage_decision(
            decision_id="noncomparable-formal",
            decision=StageDecisionValue.GO,
            source_evidence=_evidence(
                FunnelV3Stage.FORMAL,
                comparable=ComparabilityStatus.PARTIALLY_COMPARABLE,
            ),
            target_stage=FunnelV3Stage.DISCRIMINATIVE,
            target_material_identity=_material(FunnelV3Stage.DISCRIMINATIVE),
            methodology=build_funnel_v3_methodology(),
            actor_authorization=_actor(),
        )


def test_wrong_suite_purpose_and_missing_suite_identity_fail() -> None:
    base = _base_for(FunnelV3Stage.DISCRIMINATIVE)
    with pytest.raises(FunnelV3Error, match="exact stage purpose"):
        build_stage_material_identity(
            base,
            stage=FunnelV3Stage.DISCRIMINATIVE,
            methodology=build_funnel_v3_methodology(),
            namespace=GovernanceNamespace.OFFICIAL,
            suite_manifest=_suite(SuitePurpose.STRESS),
        )
    with pytest.raises(FunnelV3Error, match="requires a manifest"):
        build_stage_material_identity(
            base,
            stage=FunnelV3Stage.STRESS,
            methodology=build_funnel_v3_methodology(),
            namespace=GovernanceNamespace.OFFICIAL,
        )


def test_stop_is_immutable_terminal_and_cannot_create_a_chain_link() -> None:
    source = _evidence(FunnelV3Stage.SMOKE, complete=False)
    stop = build_stage_decision(
        decision_id="stop-after-smoke",
        decision=StageDecisionValue.STOP,
        source_evidence=source,
        target_stage=FunnelV3Stage.INFORMAL,
        target_material_identity=_material(FunnelV3Stage.INFORMAL),
        methodology=build_funnel_v3_methodology(),
        actor_authorization=_actor(),
        reason_codes=(StageDecisionReasonCode.INCOMPLETE_COVERAGE,),
    )

    with pytest.raises(FunnelV3Error, match="STOP terminates"):
        build_stage_chain_link(decision=stop, eligible_plan=_artifact("ineligible-plan"))
    with pytest.raises(ValidationError, match="frozen"):
        stop.decision = StageDecisionValue.GO  # type: ignore[misc]


def test_stale_source_plan_report_methodology_and_unknown_fields_fail() -> None:
    decision = _go(FunnelV3Stage.SMOKE)
    raw = json.loads(decision.canonical_json())
    raw["source_plan"]["artifact_digest"] = _digest("stale-plan")
    raw["decision_digest"] = canonical_digest(
        {key: value for key, value in raw.items() if key != "decision_digest"}
    )
    with pytest.raises(ValidationError, match="source plan"):
        StageDecision.model_validate(raw)

    raw = json.loads(decision.canonical_json())
    raw["unknown_auto_promote"] = True
    with pytest.raises(ValidationError, match="Extra inputs"):
        StageDecision.model_validate(raw)

    drifted = decision.model_dump(mode="json")
    drifted["methodology"]["methodology_digest"] = _digest("methodology-drift")
    drifted["decision_digest"] = canonical_digest(
        {key: value for key, value in drifted.items() if key != "decision_digest"}
    )
    with pytest.raises(ValidationError, match="methodology identity"):
        StageDecision.model_validate(drifted)


def _stage_one_inputs() -> tuple[
    FunnelMethodologyV3,
    ExperimentSpec,
    ExperimentPlan,
    StageDecision,
]:
    methodology = build_funnel_v3_methodology()
    spec = basic_spec(repeat_count=1)
    base = build_experiment_plan(spec, ROOT)
    target = build_stage_material_identity(
        base,
        stage=FunnelV3Stage.SMOKE,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
    )
    source_base = build_experiment_plan(spec, ROOT)
    source_material = build_stage_material_identity(
        source_base,
        stage=FunnelV3Stage.PREFLIGHT,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
    )
    source = build_stage_evidence(
        evidence_id="stage-zero-receipt",
        stage=FunnelV3Stage.PREFLIGHT,
        source_plan=_artifact("frozen-stage-one-plan"),
        source_report=_artifact("passing-preflight-receipt"),
        material_identity=source_material,
        coverage=_coverage(FunnelV3Stage.PREFLIGHT),
        comparability=_comparability(),
        budget_preflight=_preflight(),
    )
    decision = build_stage_decision(
        decision_id="stage-zero-to-one",
        decision=StageDecisionValue.GO,
        source_evidence=source,
        target_stage=FunnelV3Stage.SMOKE,
        target_material_identity=target,
        methodology=methodology,
        actor_authorization=_actor(),
    )
    return methodology, spec, base, decision


def test_bare_go_never_authorizes_planning_and_plan_is_inert() -> None:
    methodology, spec, _, decision = _stage_one_inputs()
    with pytest.raises(FunnelV3Error, match="bare GO"):
        build_funnel_v3_experiment_plan(
            spec,
            ROOT,
            stage=FunnelV3Stage.SMOKE,
            methodology=methodology,
            namespace=GovernanceNamespace.OFFICIAL,
            entry_decision=StageDecisionValue.GO,  # type: ignore[arg-type]
        )

    plan = build_funnel_v3_experiment_plan(
        spec,
        ROOT,
        stage=FunnelV3Stage.SMOKE,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
        entry_decision=decision,
    )
    assert plan.base_plan.repeat_count == 1
    assert not plan.automatic_promotion
    assert not plan.external_execution_authorized
    assert plan.reused_slot_ids == ()
    assert len(plan.newly_scheduled_slot_ids) == 2


@pytest.mark.parametrize(
    ("stage", "wrong_repeat"),
    (
        (FunnelV3Stage.SMOKE, 3),
        (FunnelV3Stage.INFORMAL, 1),
        (FunnelV3Stage.FORMAL, 3),
    ),
)
def test_fixed_repeat_stage_planning_fails_closed(stage: FunnelV3Stage, wrong_repeat: int) -> None:
    methodology = build_funnel_v3_methodology()
    spec = basic_spec(repeat_count=wrong_repeat)
    target = build_stage_material_identity(
        build_experiment_plan(spec, ROOT),
        stage=stage,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
    )
    source_stage = tuple(FunnelV3Stage)[stage.number - 1]
    decision = build_stage_decision(
        decision_id=f"wrong-repeat-{stage.value.lower()}",
        decision=StageDecisionValue.GO,
        source_evidence=_evidence(source_stage),
        target_stage=stage,
        target_material_identity=target,
        methodology=methodology,
        actor_authorization=_actor(),
    )
    with pytest.raises(FunnelV3Error, match=f"{stage.value} planning requires"):
        build_funnel_v3_experiment_plan(
            spec,
            ROOT,
            stage=stage,
            methodology=methodology,
            namespace=GovernanceNamespace.OFFICIAL,
            entry_decision=decision,
        )


def _reuse(
    source_slot: ExperimentRunSlot,
    methodology: FunnelMethodologyV3,
    *,
    role: EvidenceRoleV3 = EvidenceRoleV3.PRIMARY,
) -> ObservationReuseEvidence:
    logical_id = logical_observation_identity(
        source_slot,
        methodology=methodology.as_reference(),
    )
    return ObservationReuseEvidence(
        source_plan=_artifact("prior-plan"),
        source_slot=source_slot,
        methodology=methodology.as_reference(),
        logical_observation_identity=logical_id,
        evidence=_artifact(f"observation-{source_slot.cell_id}-{source_slot.repeat_index}"),
        evidence_role=role,
        evidence_eligible=True,
    )


def test_reused_and_new_slot_ids_are_explicit_deterministic_and_unique() -> None:
    methodology, spec, base, decision = _stage_one_inputs()
    reuse = _reuse(base.run_slots[0], methodology)
    first = build_funnel_v3_experiment_plan(
        spec,
        ROOT,
        stage=FunnelV3Stage.SMOKE,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
        entry_decision=decision,
        reusable_observations=(reuse,),
    )
    second = build_funnel_v3_experiment_plan(
        spec,
        ROOT,
        stage=FunnelV3Stage.SMOKE,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
        entry_decision=decision,
        reusable_observations=(reuse,),
    )

    assert first == second
    assert len(first.reused_slot_ids) == len(first.reused_source_slot_ids) == 1
    assert len(first.newly_scheduled_slot_ids) == 1
    assert {item.disposition for item in first.logical_slots} == {
        FunnelSlotDisposition.REUSED,
        FunnelSlotDisposition.NEWLY_SCHEDULED,
    }
    assert len({item.logical_observation_identity for item in first.logical_slots}) == 2


def test_control_envelope_drift_and_recovery_evidence_cannot_be_reused() -> None:
    methodology, spec, base, decision = _stage_one_inputs()
    drifted = base.run_slots[0].model_copy(
        update={"resource_envelope_identity": identity("changed-envelope")}
    )
    with pytest.raises(FunnelV3Error, match="does not match"):
        build_funnel_v3_experiment_plan(
            spec,
            ROOT,
            stage=FunnelV3Stage.SMOKE,
            methodology=methodology,
            namespace=GovernanceNamespace.OFFICIAL,
            entry_decision=decision,
            reusable_observations=(_reuse(drifted, methodology),),
        )
    with pytest.raises(FunnelV3Error, match="recovery evidence"):
        build_funnel_v3_experiment_plan(
            spec,
            ROOT,
            stage=FunnelV3Stage.SMOKE,
            methodology=methodology,
            namespace=GovernanceNamespace.OFFICIAL,
            entry_decision=decision,
            reusable_observations=(
                _reuse(base.run_slots[0], methodology, role=EvidenceRoleV3.RECOVERY),
            ),
        )


def test_n_one_reuse_does_not_inflate_n_three() -> None:
    methodology = build_funnel_v3_methodology()
    source_spec = basic_spec(repeat_count=1)
    target_spec = basic_spec(repeat_count=3)
    source_base = build_experiment_plan(source_spec, ROOT)
    target_base = build_experiment_plan(target_spec, ROOT)
    source_material = build_stage_material_identity(
        source_base,
        stage=FunnelV3Stage.SMOKE,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
    )
    target_material = build_stage_material_identity(
        target_base,
        stage=FunnelV3Stage.INFORMAL,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
    )
    source = build_stage_evidence(
        evidence_id="smoke-evidence",
        stage=FunnelV3Stage.SMOKE,
        source_plan=_artifact("smoke-plan"),
        source_report=_artifact("smoke-report"),
        material_identity=source_material,
        coverage=_coverage(FunnelV3Stage.SMOKE),
        comparability=_comparability(),
        budget_preflight=_preflight(),
    )
    decision = build_stage_decision(
        decision_id="smoke-to-informal",
        decision=StageDecisionValue.GO,
        source_evidence=source,
        target_stage=FunnelV3Stage.INFORMAL,
        target_material_identity=target_material,
        methodology=methodology,
        actor_authorization=_actor(),
    )
    plan = build_funnel_v3_experiment_plan(
        target_spec,
        ROOT,
        stage=FunnelV3Stage.INFORMAL,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
        entry_decision=decision,
        reusable_observations=tuple(_reuse(slot, methodology) for slot in source_base.run_slots),
    )

    assert plan.base_plan.repeat_count == 3
    assert len(plan.reused_slot_ids) == 2
    assert len(plan.newly_scheduled_slot_ids) == 4


def _admission_policy(purpose: SuitePurpose) -> AdmissionPolicy:
    provenance: PolicyProvenance = build_policy_provenance(
        authority_identity=_digest(f"{purpose.value}-authority"),
        source_revision_identity=_digest(f"{purpose.value}-source"),
    )
    if purpose is SuitePurpose.DISCRIMINATIVE:
        criteria: DiscriminativeAcceptanceCriteria | StressAcceptanceCriteria = (
            DiscriminativeAcceptanceCriteria(
                minimum_configurations=2,
                minimum_repetitions_per_configuration=2,
                minimum_pairwise_effect_absolute=0.1,
                maximum_rank_instability=0.2,
            )
        )
    else:
        criteria = StressAcceptanceCriteria(
            minimum_distinct_stress_dimensions=2,
            required_dimensions=(StressDimension.MULTI_FILE, StressDimension.REPAIR_LOOP),
        )
    return build_admission_policy(
        policy_id=f"m4-{purpose.value.lower()}-admission",
        policy_version="1.0.0",
        namespace=GovernanceNamespace.OFFICIAL,
        suite_purpose=purpose,  # type: ignore[arg-type]
        acceptance_criteria=criteria,
        provenance=provenance,
    )


def _qualified_task() -> tuple[TaskQualityMetadata, TaskQualification]:
    package = TaskPackage.load(ROOT / "tasks" / "micro-python-clamp" / "1.0.0")
    quality = TaskQualityMetadata.from_package(package)
    checks = (
        QualificationCheck.BASELINE_FAILS,
        QualificationCheck.DETERMINISTIC_HEALTH,
        QualificationCheck.ORACLE_PASSES,
        QualificationCheck.PACKAGE_VALID,
    )
    qualification = qualify_task(
        quality,
        qualification_id="m4-task-qualification",
        evidence=tuple(
            QualificationEvidence(check=check, evidence_identity=_digest(check.value))
            for check in checks
        ),
    )
    return quality, qualification


def _admitted_suite(
    purpose: SuitePurpose,
) -> tuple[EvaluationSuiteManifest, AdmissionPolicy, AdmissionDecision]:
    quality, qualification = _qualified_task()
    suite = _suite(purpose, memberships=(EvaluationSuiteMembership(task=quality.task),))
    policy = _admission_policy(purpose)
    candidate = build_admission_candidate(build_task_characteristics(quality), qualification)
    evidence = []
    for kind in policy.evidence_requirements:
        artifact_id = kind.value.lower()
        digest = _digest(artifact_id)
        if kind is EvidenceKind.TASK_QUALIFICATION:
            artifact_id = qualification.qualification_id or "missing"
            digest = qualification.qualification_identity
        evidence.append(
            AdmissionEvidenceReference(
                kind=kind,
                reference=TaskArtifactReference(
                    task=quality.task,
                    artifact=ImmutableArtifactReference(
                        artifact_id=artifact_id,
                        schema_version=1,
                        artifact_digest=digest,
                    ),
                ),
            )
        )
    decision = build_admission_decision(
        decision_id=f"admit-{purpose.value.lower()}-task",
        status=AdmissionStatus.ADMITTED,
        candidate=candidate,
        target_suite=suite.as_reference(),
        policy=policy,
        evidence=tuple(evidence),
        reason_codes=(AdmissionReasonCode.ACCEPTANCE_CRITERIA_SATISFIED,),
    )
    return suite, policy, decision


def test_discriminative_plan_consumes_exact_m2_manifest_and_m3_admission() -> None:
    methodology = build_funnel_v3_methodology()
    suite, policy, admission = _admitted_suite(SuitePurpose.DISCRIMINATIVE)
    target_spec = basic_spec(repeat_count=1)
    target_base = build_experiment_plan(target_spec, ROOT)
    target_material = build_stage_material_identity(
        target_base,
        stage=FunnelV3Stage.DISCRIMINATIVE,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
        suite_manifest=suite,
        relevant_policies=(policy.as_reference(),),
    )
    source = _evidence(FunnelV3Stage.FORMAL)
    decision = build_stage_decision(
        decision_id="formal-to-discriminative",
        decision=StageDecisionValue.GO,
        source_evidence=source,
        target_stage=FunnelV3Stage.DISCRIMINATIVE,
        target_material_identity=target_material,
        methodology=methodology,
        actor_authorization=_actor(),
    )
    plan = build_funnel_v3_experiment_plan(
        target_spec,
        ROOT,
        stage=FunnelV3Stage.DISCRIMINATIVE,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
        entry_decision=decision,
        suite_manifest=suite,
        admission_decisions=(admission,),
        admission_policies=(policy,),
    )

    assert plan.suite_manifest == suite.as_reference()
    assert plan.admission_decisions == (admission.as_empirical_reference().artifact,)


@pytest.mark.parametrize(
    ("purpose", "insufficient_kind"),
    (
        (SuitePurpose.DISCRIMINATIVE, EvidenceKind.HISTORICAL_MATRIX_PARTICIPATION),
        (SuitePurpose.STRESS, EvidenceKind.TIER_B_QUALIFICATION),
    ),
)
def test_historical_matrix_or_tier_b_alone_cannot_satisfy_suite_stage(
    purpose: SuitePurpose, insufficient_kind: EvidenceKind
) -> None:
    methodology = build_funnel_v3_methodology()
    suite, policy, admitted = _admitted_suite(purpose)
    weak_raw = admitted.model_dump(mode="json")
    weak_raw["evidence"] = [
        AdmissionEvidenceReference(
            kind=insufficient_kind,
            reference=TaskArtifactReference(
                task=admitted.candidate.characteristics.task,
                artifact=_artifact(insufficient_kind.value.lower()),
            ),
        ).model_dump(mode="json")
    ]
    weak_raw["decision_digest"] = canonical_digest(
        {key: value for key, value in weak_raw.items() if key != "decision_digest"}
    )
    weak = type(admitted).model_validate(weak_raw)
    stage = (
        FunnelV3Stage.DISCRIMINATIVE
        if purpose is SuitePurpose.DISCRIMINATIVE
        else FunnelV3Stage.STRESS
    )
    source_stage = tuple(FunnelV3Stage)[stage.number - 1]
    spec = basic_spec(repeat_count=1)
    material = build_stage_material_identity(
        build_experiment_plan(spec, ROOT),
        stage=stage,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
        suite_manifest=suite,
        relevant_policies=(policy.as_reference(),),
    )
    entry = build_stage_decision(
        decision_id=f"weak-entry-{purpose.value.lower()}",
        decision=StageDecisionValue.GO,
        source_evidence=_evidence(source_stage),
        target_stage=stage,
        target_material_identity=material,
        methodology=methodology,
        actor_authorization=_actor(),
    )
    with pytest.raises(FunnelV3Error, match="admission evidence is missing"):
        build_funnel_v3_experiment_plan(
            spec,
            ROOT,
            stage=stage,
            methodology=methodology,
            namespace=GovernanceNamespace.OFFICIAL,
            entry_decision=entry,
            suite_manifest=suite,
            admission_decisions=(weak,),
            admission_policies=(policy,),
        )


def test_official_admission_cannot_be_cross_used_in_custom_plan() -> None:
    methodology = build_funnel_v3_methodology()
    suite, policy, admission = _admitted_suite(SuitePurpose.DISCRIMINATIVE)
    spec = basic_spec(repeat_count=1)
    material = build_stage_material_identity(
        build_experiment_plan(spec, ROOT),
        stage=FunnelV3Stage.DISCRIMINATIVE,
        methodology=methodology,
        namespace=GovernanceNamespace.CUSTOM,
        suite_manifest=suite,
        relevant_policies=(policy.as_reference(),),
    )
    entry = build_stage_decision(
        decision_id="custom-cross-use",
        decision=StageDecisionValue.GO,
        source_evidence=_evidence(FunnelV3Stage.FORMAL),
        target_stage=FunnelV3Stage.DISCRIMINATIVE,
        target_material_identity=material,
        methodology=methodology,
        actor_authorization=_actor(),
    )
    with pytest.raises(FunnelV3Error, match="Official and Custom"):
        build_funnel_v3_experiment_plan(
            spec,
            ROOT,
            stage=FunnelV3Stage.DISCRIMINATIVE,
            methodology=methodology,
            namespace=GovernanceNamespace.CUSTOM,
            entry_decision=entry,
            suite_manifest=suite,
            admission_decisions=(admission,),
            admission_policies=(policy,),
        )


@pytest.mark.parametrize("status", (AdmissionStatus.CANDIDATE, AdmissionStatus.REJECTED))
def test_candidate_or_rejected_admission_cannot_masquerade_as_membership(
    status: AdmissionStatus,
) -> None:
    methodology = build_funnel_v3_methodology()
    suite, policy, admitted = _admitted_suite(SuitePurpose.DISCRIMINATIVE)
    reasons = (
        ()
        if status is AdmissionStatus.CANDIDATE
        else (AdmissionReasonCode.MISSING_REQUIRED_EVIDENCE,)
    )
    evidence = () if status is AdmissionStatus.CANDIDATE else admitted.evidence
    decision = build_admission_decision(
        decision_id=f"not-admitted-{status.value.lower()}",
        status=status,
        candidate=admitted.candidate,
        target_suite=suite.as_reference(),
        policy=policy,
        evidence=evidence,
        reason_codes=reasons,
    )
    spec = basic_spec(repeat_count=1)
    material = build_stage_material_identity(
        build_experiment_plan(spec, ROOT),
        stage=FunnelV3Stage.DISCRIMINATIVE,
        methodology=methodology,
        namespace=GovernanceNamespace.OFFICIAL,
        suite_manifest=suite,
        relevant_policies=(policy.as_reference(),),
    )
    entry = build_stage_decision(
        decision_id=f"entry-{status.value.lower()}",
        decision=StageDecisionValue.GO,
        source_evidence=_evidence(FunnelV3Stage.FORMAL),
        target_stage=FunnelV3Stage.DISCRIMINATIVE,
        target_material_identity=material,
        methodology=methodology,
        actor_authorization=_actor(),
    )
    with pytest.raises(FunnelV3Error, match="candidate or rejected"):
        build_funnel_v3_experiment_plan(
            spec,
            ROOT,
            stage=FunnelV3Stage.DISCRIMINATIVE,
            methodology=methodology,
            namespace=GovernanceNamespace.OFFICIAL,
            entry_decision=entry,
            suite_manifest=suite,
            admission_decisions=(decision,),
            admission_policies=(policy,),
        )


def test_material_drift_starts_new_chain_without_rewriting_predecessor() -> None:
    first_decision = _go(FunnelV3Stage.PREFLIGHT)
    first = build_stage_chain_link(
        decision=first_decision,
        eligible_plan=_evidence(FunnelV3Stage.SMOKE).source_plan,
    )
    second_decision = _go(FunnelV3Stage.SMOKE)
    second = build_stage_chain_link(
        decision=second_decision,
        eligible_plan=_artifact("stage-two-eligible-plan"),
        predecessor=first,
    )
    drifted_material = second_decision.target_material_identity.model_copy(
        update={"controls_identity": _digest("changed-controls")}
    )
    drifted_decision = build_stage_decision(
        decision_id="drifted-smoke-to-informal",
        decision=StageDecisionValue.GO,
        source_evidence=_evidence(FunnelV3Stage.SMOKE),
        target_stage=FunnelV3Stage.INFORMAL,
        target_material_identity=drifted_material,
        methodology=build_funnel_v3_methodology(),
        actor_authorization=_actor(),
    )
    drifted = build_stage_chain_link(
        decision=drifted_decision,
        eligible_plan=_artifact("drifted-stage-two-plan"),
        predecessor=first,
    )

    assert not second.started_new_chain
    assert second.chain_id == first.chain_id
    assert drifted.started_new_chain
    assert drifted.chain_id != first.chain_id
    assert drifted.predecessor_link_digest == first.link_digest

    with pytest.raises(FunnelV3Error, match="exact source stage plan"):
        build_stage_chain_link(
            decision=second_decision,
            eligible_plan=_artifact("unreachable-stage-two-plan"),
            predecessor=first.model_copy(update={"eligible_plan": _artifact("stale-source-plan")}),
        )


def test_v2_methodology_is_loadable_byte_identical_and_explicitly_historical() -> None:
    before = METHODOLOGY_V2.read_bytes()
    methodology = load_evaluation_methodology(METHODOLOGY_V2)
    after = METHODOLOGY_V2.read_bytes()

    assert before == after
    assert hashlib.sha256(after).hexdigest() == (
        "13f9f544c2d52c4b63da801c40a677a018b999fed33d914eb24b3563bc69de6a"
    )
    assert tuple(item.stage for item in methodology.funnel) == tuple(FunnelStage)
    assert FunnelStage.BREADTH in FunnelStage
    assert next_funnel_stage(FunnelStage.PREFLIGHT, HistoricalStageDecision.GO) is FunnelStage.SMOKE
