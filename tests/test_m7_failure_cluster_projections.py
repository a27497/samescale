from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from harnesslab.comparability.models import canonical_digest
from harnesslab.db.models.experiment import (
    ExperimentRecord,
    ExperimentRunAttemptRecord,
    ExperimentRunRecord,
)
from harnesslab.diagnosis.models import CausalStrength, FailureClass, FailureScope
from harnesslab.diagnosis.projection_models import (
    FAILURE_NORMALIZATION_VERSION,
    AttemptReadPath,
    AttemptSelectionPolicy,
    ClusterProjectionRequest,
    CohortMember,
    ControlledEvidenceBinding,
    DiagnosticLayer,
    MissingValuePolicy,
    OperationalTerminalCounts,
    ProjectedClusterReadRequest,
    ProjectionDimension,
)
from harnesslab.diagnosis.projection_service import (
    _aggregate_snapshot_identity,
    _raw_failure_fact,
    build_cluster_projection,
    build_failure_cohort,
    build_projected_cluster_report,
    read_projected_failure_clusters,
)
from harnesslab.diagnosis.service import DiagnosisRequestError
from harnesslab.experiment.authoritative import (
    append_attempt_transition,
    create_recovery_attempt,
    recovery_attempt_identity,
)
from harnesslab.experiment.lifecycle import InfraRecoveryAuthorization, LifecycleState
from harnesslab.experiment.queue import enqueue_plan
from tests.phase_g_helpers import ROOT
from tests.test_m5_unified_preflight_budget_reservation import _fixture
from tests.test_m6_durable_lifecycle_controls import NOW, _setup_authoritative

DIGEST_A = "sha256:" + "1" * 64
DIGEST_B = "sha256:" + "2" * 64
ZERO_COUNTS = OperationalTerminalCounts(
    failed_capability=0,
    failed_infra=0,
    cancelled=0,
    budget_exhausted=0,
)


def _fact(
    run: str,
    *,
    experiment: str = "experiment-a",
    plan: str = DIGEST_A,
    model: str | None = "model-a",
    task: str | None = "task-a",
    trace: str | None = "trace-a",
    failure_class: FailureClass = FailureClass.TEST_FAILURE,
    failure_scope: FailureScope = FailureScope.CAPABILITY,
    effective: bool = True,
) -> Any:
    return _raw_failure_fact(
        normalization_version=FAILURE_NORMALIZATION_VERSION,
        experiment_id=experiment,
        plan_digest=plan,
        logical_run_id=run,
        cell_id="cell-a",
        slot_id=canonical_digest({"slot": run}),
        physical_attempt_id=None,
        attempt_number=None,
        attempt_role="LEGACY_COMPATIBILITY",
        is_primary_attempt=True,
        is_effective_attempt_at_snapshot=effective,
        read_path=AttemptReadPath.LEGACY_COMPATIBILITY,
        evidence_identity=canonical_digest({"evidence": run}),
        artifact_verified=True,
        model=model,
        harness="codex",
        task_id=task,
        task_version="1.0.0",
        language="python",
        task_family="bug-fix",
        failure_class=failure_class,
        failure_scope=failure_scope,
        trace_pattern=trace,
        tool_pattern="count=1;failed=0",
        workspace_diff_pattern="paths=1;statuses=modified:1;extensions=.py:1",
    )


def _context(
    *,
    dimensions: tuple[ProjectionDimension, ...] = tuple(ProjectionDimension),
    version: str = "1",
    missing: MissingValuePolicy = MissingValuePolicy.SEPARATE_UNKNOWN,
    namespace: str = "workbench",
    members: tuple[CohortMember, ...] | None = None,
) -> Any:
    exact_members = members or (
        CohortMember(
            experiment_id="experiment-a",
            plan_digest=DIGEST_A,
            evidence_snapshot_identity=DIGEST_A,
        ),
    )
    snapshot = _aggregate_snapshot_identity(exact_members, AttemptSelectionPolicy.PRIMARY_ONLY)
    projection = build_cluster_projection(
        ClusterProjectionRequest(
            projection_id="failure-clusters",
            projection_version=version,
            dimensions=dimensions,
            missing_value_policy=missing,
            namespace=namespace,
        ),
        evidence_snapshot_identity=snapshot,
    )
    return projection, build_failure_cohort(projection, exact_members)


def _report(
    facts: tuple[Any, ...],
    *,
    dimensions: tuple[ProjectionDimension, ...] = tuple(ProjectionDimension),
    version: str = "1",
    missing: MissingValuePolicy = MissingValuePolicy.SEPARATE_UNKNOWN,
) -> Any:
    projection, cohort = _context(dimensions=dimensions, version=version, missing=missing)
    return build_projected_cluster_report(
        projection=projection,
        cohort=cohort,
        attempt_selection=AttemptSelectionPolicy.PRIMARY_ONLY,
        facts=tuple(facts),
        operational_terminal_counts=ZERO_COUNTS,
    )


def test_raw_fact_digest_is_deterministic_and_projection_independent() -> None:
    first = _fact("run-a", effective=False)
    second = _fact("run-a", effective=False)
    later_snapshot_view = _fact("run-a", effective=True)

    assert first == second
    assert first.fact_digest == later_snapshot_view.fact_digest


def test_input_order_cannot_change_clusters_or_report_digest() -> None:
    facts = (_fact("run-b"), _fact("run-a"))
    assert _report(facts) == _report(tuple(reversed(facts)))


def test_full_tuple_projection_preserves_existing_grouping() -> None:
    same = (_fact("run-a"), _fact("run-b"))
    different = _fact("run-c", trace="trace-b")
    report = _report((*same, different))

    assert sorted(len(cluster.facts) for cluster in report.clusters) == [1, 2]
    assert tuple(report.projection.dimensions) == tuple(ProjectionDimension)


@pytest.mark.parametrize(
    ("omitted", "changed_value"),
    (
        (ProjectionDimension.TASK, "task-b"),
        (ProjectionDimension.MODEL, "model-b"),
    ),
)
def test_omitting_dimension_intentionally_broadens_cluster(
    omitted: ProjectionDimension, changed_value: str
) -> None:
    dimensions = tuple(item for item in ProjectionDimension if item is not omitted)
    first = _fact("run-a")
    second = (
        _fact("run-b", task=changed_value)
        if omitted is ProjectionDimension.TASK
        else _fact("run-b", model=changed_value)
    )

    assert len(_report((first, second)).clusters) == 2
    broadened = _report((first, second), dimensions=dimensions)
    assert len(broadened.clusters) == 1
    assert broadened.clusters[0].raw_fact_digests == tuple(
        sorted((first.fact_digest, second.fact_digest))
    )


def test_projection_version_changes_cluster_not_raw_fact_identity() -> None:
    fact = _fact("run-a")
    v1 = _report((fact,), version="1")
    v2 = _report((fact,), version="2")

    assert v1.clusters[0].facts[0].fact_digest == v2.clusters[0].facts[0].fact_digest
    assert v1.clusters[0].cluster_id != v2.clusters[0].cluster_id


def test_unknown_is_not_wildcard_and_is_explicitly_grouped() -> None:
    report = _report(
        (_fact("missing", trace=None), _fact("known", trace="trace-a")),
        dimensions=(ProjectionDimension.TRACE_PATTERN,),
    )

    assert len(report.clusters) == 2
    assert report.unknown_grouped_fact_count == 1
    assert any(
        "__UNKNOWN__:TRACE_PATTERN" in cluster.dimensions.values() for cluster in report.clusters
    )


def test_excluded_unknown_facts_remain_counted_and_auditable() -> None:
    missing = _fact("missing", trace=None)
    report = _report(
        (missing, _fact("known")),
        dimensions=(ProjectionDimension.TRACE_PATTERN,),
        missing=MissingValuePolicy.EXCLUDE_WITH_REASON,
    )

    assert report.raw_fact_count == 2
    assert report.clustered_fact_count == 1
    assert report.excluded_fact_count == 1
    assert report.excluded_facts[0].fact_digest == missing.fact_digest
    assert report.excluded_facts[0].missing_dimensions == (ProjectionDimension.TRACE_PATTERN,)


def test_malformed_and_duplicate_dimensions_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ClusterProjectionRequest(
            projection_id="bad",
            projection_version="1",
            namespace="workbench",
            dimensions=("ARBITRARY",),
        )
    with pytest.raises(ValidationError, match="must be unique"):
        ClusterProjectionRequest(
            projection_id="bad",
            projection_version="1",
            namespace="workbench",
            dimensions=(ProjectionDimension.MODEL, ProjectionDimension.MODEL),
        )


def test_namespace_normalization_and_exact_cohort_mismatches_fail_closed() -> None:
    fact = _fact("run-a")
    projection, cohort = _context()
    with pytest.raises(DiagnosisRequestError, match="namespaces"):
        build_projected_cluster_report(
            projection=projection,
            cohort=cohort.model_copy(update={"namespace": "other"}),
            attempt_selection=AttemptSelectionPolicy.PRIMARY_ONLY,
            facts=(fact,),
        )
    with pytest.raises(DiagnosisRequestError, match="normalization"):
        build_cluster_projection(
            ClusterProjectionRequest(
                projection_id="bad",
                projection_version="1",
                normalization_version="unknown-normalizer",
                namespace="workbench",
            ),
            evidence_snapshot_identity=DIGEST_A,
        )
    with pytest.raises(DiagnosisRequestError, match="exact cohort"):
        build_projected_cluster_report(
            projection=projection,
            cohort=cohort,
            attempt_selection=AttemptSelectionPolicy.PRIMARY_ONLY,
            facts=(_fact("foreign", experiment="experiment-b", plan=DIGEST_B),),
        )


def test_cluster_membership_preserves_taxonomy_and_never_raises_causality() -> None:
    capability = _fact("capability")
    infra = _fact(
        "infra",
        failure_class=FailureClass.ARTIFACT_FAILURE,
        failure_scope=FailureScope.INFRASTRUCTURE,
    )
    report = _report(
        (capability, infra),
        dimensions=(ProjectionDimension.HARNESS,),
    )

    assert len(report.clusters) == 1
    by_digest = {fact.fact_digest: fact for fact in report.clusters[0].facts}
    assert by_digest[capability.fact_digest].failure_class is FailureClass.TEST_FAILURE
    assert by_digest[infra.fact_digest].failure_scope is FailureScope.INFRASTRUCTURE
    assert report.clusters[0].causal_strength is CausalStrength.CORRELATION_ONLY
    assert report.clusters[0].layer is DiagnosticLayer.DIAGNOSTIC_CLUSTER


def test_controlled_ablation_binding_stays_separate_and_diagnostic_only() -> None:
    fact = _fact("run-a")
    projection, cohort = _context()
    controlled = ControlledEvidenceBinding(
        fact_digest=fact.fact_digest,
        evidence_reference="ablation:registered-a",
    )
    report = build_projected_cluster_report(
        projection=projection,
        cohort=cohort,
        attempt_selection=AttemptSelectionPolicy.PRIMARY_ONLY,
        facts=(fact,),
        controlled_evidence=(controlled,),
    )

    assert report.controlled_evidence == (controlled,)
    assert controlled.layer is DiagnosticLayer.CONTROLLED_EVIDENCE
    assert report.clusters[0].causal_strength is CausalStrength.CORRELATION_ONLY
    assert report.cohort.diagnostic_only and not report.cohort.comparability_claim
    assert "not a formal comparability" in report.cross_experiment_limitation


def test_explicit_cross_experiment_cohort_groups_diagnostically_not_comparatively() -> None:
    members = (
        CohortMember(
            experiment_id="experiment-a",
            plan_digest=DIGEST_A,
            evidence_snapshot_identity=DIGEST_A,
        ),
        CohortMember(
            experiment_id="experiment-b",
            plan_digest=DIGEST_B,
            evidence_snapshot_identity=DIGEST_B,
        ),
    )
    projection, cohort = _context(
        dimensions=(ProjectionDimension.FAILURE_CLASS,),
        members=members,
    )
    report = build_projected_cluster_report(
        projection=projection,
        cohort=cohort,
        attempt_selection=AttemptSelectionPolicy.PRIMARY_ONLY,
        facts=(
            _fact("run-a", experiment="experiment-a", plan=DIGEST_A),
            _fact("run-b", experiment="experiment-b", plan=DIGEST_B),
        ),
    )

    assert len(report.clusters) == 1
    assert tuple(member.experiment_id for member in report.cohort.members) == (
        "experiment-a",
        "experiment-b",
    )
    assert report.cohort.diagnostic_only is True
    assert report.cohort.comparability_claim is False


@pytest.mark.integration
async def test_authoritative_attempt_selection_and_operational_states_are_explicit(
    database_url: str,
) -> None:
    engine, factory, fixture, _, _ = await _setup_authoritative(database_url, label="m7-projection")
    experiment_id = fixture["plan"].experiment_id
    try:
        async with factory() as session:
            runs = tuple(
                (
                    await session.scalars(
                        select(ExperimentRunRecord)
                        .where(ExperimentRunRecord.experiment_id == experiment_id)
                        .order_by(ExperimentRunRecord.slot_order)
                    )
                ).all()
            )
            primary_attempts = tuple(
                (
                    await session.scalars(
                        select(ExperimentRunAttemptRecord)
                        .where(
                            ExperimentRunAttemptRecord.run_id.in_(run.run_id for run in runs[:2])
                        )
                        .order_by(ExperimentRunAttemptRecord.run_id)
                    )
                ).all()
            )
        by_run = {attempt.run_id: attempt for attempt in primary_attempts}
        async with factory() as session, session.begin():
            await append_attempt_transition(
                session,
                attempt_id=by_run[runs[0].run_id].attempt_id,
                target=LifecycleState.FAILED_INFRA,
                occurred_at=NOW + timedelta(seconds=1),
                reason_code="PRIMARY_INFRA",
            )
            await append_attempt_transition(
                session,
                attempt_id=by_run[runs[1].run_id].attempt_id,
                target=LifecycleState.CANCELLED,
                occurred_at=NOW + timedelta(seconds=1),
                reason_code="OPERATOR_CANCELLED",
            )
        authorization_identity = canonical_digest(
            {
                "authorized_by": "m7-test",
                "authorized_at": (NOW + timedelta(seconds=2)).isoformat(),
                "reason_code": "RETRY_INFRA",
                "repair_reference": "synthetic:m7",
            }
        )
        recovery_id = recovery_attempt_identity(
            plan_digest=fixture["plan"].digest,
            run_id=runs[0].run_id,
            slot_id=runs[0].slot_id,
            attempt_number=2,
            failed_attempt_identity=by_run[runs[0].run_id].attempt_id,
            authorization_identity=authorization_identity,
        )
        async with factory() as session, session.begin():
            recovery = await create_recovery_attempt(
                session,
                run_id=runs[0].run_id,
                authorization=InfraRecoveryAuthorization(
                    failed_attempt_identity=by_run[runs[0].run_id].attempt_id,
                    recovery_attempt_identity=recovery_id,
                    authorized_by="m7-test",
                    authorized_at=NOW + timedelta(seconds=2),
                    reason_code="RETRY_INFRA",
                    repair_reference="synthetic:m7",
                ),
                plan_digest=fixture["plan"].digest,
                now=NOW + timedelta(seconds=2),
            )
            for offset, state in enumerate(
                (
                    LifecycleState.PREPARING,
                    LifecycleState.RUNNING,
                    LifecycleState.VERIFYING,
                    LifecycleState.FAILED_CAPABILITY,
                ),
                start=3,
            ):
                await append_attempt_transition(
                    session,
                    attempt_id=recovery.attempt_id,
                    target=state,
                    occurred_at=NOW + timedelta(seconds=offset),
                    reason_code="RECOVERY_CAPABILITY"
                    if state is LifecycleState.FAILED_CAPABILITY
                    else None,
                )
        projection = ClusterProjectionRequest(
            projection_id="m7-attempts",
            projection_version="1",
            dimensions=(ProjectionDimension.FAILURE_SCOPE,),
            missing_value_policy=MissingValuePolicy.SEPARATE_UNKNOWN,
            namespace="workbench",
        )
        async with factory() as session, session.begin():
            recovery_record = await session.get(ExperimentRunAttemptRecord, recovery_id)
            assert recovery_record is not None
            recovery_record.artifact_manifest_path = "/outside/recovery/manifest.json"
            recovery_record.evidence_digest = DIGEST_B
        async with factory() as session:
            primary = await read_projected_failure_clusters(
                session,
                experiment_id,
                ProjectedClusterReadRequest(
                    attempt_selection=AttemptSelectionPolicy.PRIMARY_ONLY,
                    projection=projection,
                ),
                (),
                repository_root=ROOT,
            )
        async with factory() as session, session.begin():
            recovery_record = await session.get(ExperimentRunAttemptRecord, recovery_id)
            assert recovery_record is not None
            recovery_record.artifact_manifest_path = None
            recovery_record.evidence_digest = None
        async with factory() as session:
            effective = await read_projected_failure_clusters(
                session,
                experiment_id,
                ProjectedClusterReadRequest(
                    attempt_selection=AttemptSelectionPolicy.EFFECTIVE_EXPLICIT,
                    projection=projection,
                ),
                (),
                repository_root=ROOT,
            )
        assert primary.operational_terminal_counts.failed_infra == 1
        assert primary.operational_terminal_counts.failed_capability == 0
        assert effective.operational_terminal_counts.failed_infra == 0
        assert effective.operational_terminal_counts.failed_capability == 1
        assert effective.operational_terminal_counts.cancelled == 1
        assert effective.operational_terminal_counts.budget_exhausted == 0
        assert effective.raw_fact_count == 1
        assert all(
            fact.failure_scope is not FailureScope.CAPABILITY
            for cluster in primary.clusters
            for fact in cluster.facts
        )
        selected = next(
            item for item in effective.attempt_reads if item.logical_run_id == runs[0].run_id
        )
        assert selected.primary_outcome == LifecycleState.FAILED_INFRA.value
        assert selected.recovery_outcomes == (LifecycleState.FAILED_CAPABILITY.value,)
        assert selected.recovery_selected_as_effective
        assert selected.selected_attempt_id == recovery_id
        primary_fact = primary.clusters[0].facts[0]
        effective_fact = effective.clusters[0].facts[0]
        assert primary_fact.physical_attempt_id == by_run[runs[0].run_id].attempt_id
        assert primary_fact.attempt_role == "PRIMARY"
        assert effective_fact.physical_attempt_id == recovery_id
        assert effective_fact.attempt_role == "RECOVERY"
        assert effective.all_attempt_terminal_counts.failed_infra == 1
        assert effective.all_attempt_terminal_counts.failed_capability == 1
    finally:
        async with factory() as session, session.begin():
            record = await session.get(ExperimentRecord, experiment_id)
            if record is not None:
                await session.delete(record)
        await engine.dispose()


@pytest.mark.integration
async def test_historical_projection_uses_labeled_compatibility_without_fabricating_attempts(
    database_url: str,
) -> None:
    fixture = _fixture(experiment_id=f"m7-legacy-{uuid4().hex[:10]}")
    from harnesslab.core.config import Settings
    from harnesslab.db.session import create_engine, create_session_factory

    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, fixture["plan"])
            runs = tuple(
                (
                    await session.scalars(
                        select(ExperimentRunRecord)
                        .where(ExperimentRunRecord.experiment_id == fixture["plan"].experiment_id)
                        .order_by(ExperimentRunRecord.slot_order)
                        .limit(2)
                    )
                ).all()
            )
            assert len(runs) == 2
            runs[0].status = "failed_infra"
            runs[0].normalized_outcome = "infra_failure"
            runs[0].source_outcome = "legacy_infra"
            runs[1].status = "budget_exhausted"
            runs[1].normalized_outcome = None
            runs[1].source_outcome = "campaign_budget"
        async with factory() as session:
            report = await read_projected_failure_clusters(
                session,
                fixture["plan"].experiment_id,
                ProjectedClusterReadRequest(
                    attempt_selection=AttemptSelectionPolicy.EFFECTIVE_EXPLICIT,
                    projection=ClusterProjectionRequest(
                        projection_id="legacy",
                        projection_version="1",
                        namespace="workbench",
                    ),
                ),
                (),
                repository_root=ROOT,
            )
            attempt_count = await session.scalar(
                select(func.count())
                .select_from(ExperimentRunAttemptRecord)
                .where(
                    ExperimentRunAttemptRecord.run_id.in_(
                        select(ExperimentRunRecord.run_id).where(
                            ExperimentRunRecord.experiment_id == fixture["plan"].experiment_id
                        )
                    )
                )
            )
        selected = next(
            item for item in report.attempt_reads if item.logical_run_id == runs[0].run_id
        )
        assert selected.read_path is AttemptReadPath.LEGACY_COMPATIBILITY
        assert selected.primary_attempt_id is None and selected.selected_attempt_id is None
        assert report.raw_fact_count == 1
        assert report.operational_terminal_counts.failed_infra == 1
        assert report.operational_terminal_counts.budget_exhausted == 1
        assert report.all_attempt_terminal_counts == ZERO_COUNTS
        assert all(
            fact.read_path is AttemptReadPath.LEGACY_COMPATIBILITY
            for cluster in report.clusters
            for fact in cluster.facts
        )
        assert attempt_count == 0
    finally:
        async with factory() as session, session.begin():
            record = await session.get(ExperimentRecord, fixture["plan"].experiment_id)
            if record is not None:
                await session.delete(record)
        await engine.dispose()
