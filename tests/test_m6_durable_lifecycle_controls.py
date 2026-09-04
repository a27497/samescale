from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Never
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from harnesslab.budget.durable import (
    DurableBudgetReservationReceipt,
    initialize_budget_scope,
    reserve_budget,
)
from harnesslab.budget.reservation import (
    ReservationDecision,
    ReservationScope,
    ReservationUnit,
    ResourceAmounts,
    build_reservation_request,
    reservation_units_for_plan,
)
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.run import RunStatus
from harnesslab.core.config import Settings, get_settings
from harnesslab.db.models.experiment import (
    BudgetScopeLedgerRecord,
    ExperimentAttemptEventRecord,
    ExperimentAttemptReconciliationRecord,
    ExperimentControlEventRecord,
    ExperimentRecord,
    ExperimentResourceEventRecord,
    ExperimentRunAttemptRecord,
)
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.evaluation_suites.models import ImmutableArtifactReference
from harnesslab.experiment.authoritative import (
    AttemptRole,
    AuthoritativeLifecycleError,
    BudgetExhaustionSource,
    ControlState,
    ControlType,
    ObservedResourceDimension,
    ObservedResourceUsage,
    ReconciliationStatus,
    ResourceAvailability,
    append_attempt_transition,
    capability_outcome_for_attempt,
    checkpoint_resume_supported,
    control_state,
    durable_reservation_for_attempt,
    initialize_authoritative_lifecycle,
    issue_control,
    never_started_slot_ids,
    read_authoritative_projection,
    reconcile_attempt_resources,
)
from harnesslab.experiment.executor import ExperimentRunExecutor
from harnesslab.experiment.funnel_v3 import FunnelV3Stage
from harnesslab.experiment.lifecycle import (
    LifecycleRecoveryError,
    LifecycleState,
    LifecycleTransitionError,
)
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.queue import (
    AuthoritativeClaimGate,
    claim_authoritative_run,
    claim_next_run,
    enqueue_plan,
    expire_authoritative_leases,
    finish_run,
    heartbeat_run,
    transition_run,
)
from harnesslab.preflight.unified import UnifiedPreflightReceipt, assess_unified_preflight
from tests.test_m5_unified_preflight_budget_reservation import M5Fixture, _fixture

NOW = datetime(2026, 9, 4, 10, 0, tzinfo=UTC)


class _RaisingBinding:
    async def run(self, task_path: Path, run_id: str) -> Never:
        raise RuntimeError("deterministic fake infrastructure failure")


def _available(value: int | str, unit: str) -> ObservedResourceDimension:
    return ObservedResourceDimension(
        availability=ResourceAvailability.AVAILABLE,
        value=Decimal(str(value)),
        unit=unit,
    )


def _unavailable(unit: str) -> ObservedResourceDimension:
    return ObservedResourceDimension(
        availability=ResourceAvailability.NOT_AVAILABLE,
        unit=unit,
    )


def _usage(*, wall: int = 5, unknown_cost: bool = False) -> ObservedResourceUsage:
    return ObservedResourceUsage(
        wall_time=_available(wall, "seconds"),
        output_tokens=_available(50, "tokens"),
        model_turns=_available(1, "turns"),
        tool_calls=_available(1, "calls"),
        provider_requests=_available(1, "requests"),
        monetary_cost=(_unavailable("USD") if unknown_cost else _available("0.005", "USD")),
    )


def _reference(label: str) -> ImmutableArtifactReference:
    return ImmutableArtifactReference(
        artifact_id=label,
        schema_version=1,
        artifact_digest=canonical_digest({"m6": label}),
    )


def test_budget_exhaustion_and_non_capability_states_stay_outside_denominator() -> None:
    assert (
        capability_outcome_for_attempt(
            LifecycleState.BUDGET_EXHAUSTED,
            budget_source=BudgetExhaustionSource.CAMPAIGN_OPERATOR_STAGE,
        )
        is None
    )
    assert (
        capability_outcome_for_attempt(LifecycleState.FAILED_INFRA)
        is StatisticalOutcome.INFRA_FAILURE
    )
    assert capability_outcome_for_attempt(LifecycleState.CANCELLED) is StatisticalOutcome.CANCELLED
    assert (
        capability_outcome_for_attempt(LifecycleState.FAILED_CAPABILITY)
        is StatisticalOutcome.CAPABILITY_FAIL
    )
    with pytest.raises(AuthoritativeLifecycleError, match="bound capability outcome"):
        capability_outcome_for_attempt(
            LifecycleState.BUDGET_EXHAUSTED,
            budget_source=BudgetExhaustionSource.TASK_COMPARABLE_ENVELOPE,
        )


def test_unknown_actual_dimension_is_not_zero_and_checkpoint_is_rejected() -> None:
    usage = _usage(unknown_cost=True)
    assert usage.monetary_cost.value is None
    assert usage.amounts().monetary_cost_usd is None
    assert checkpoint_resume_supported() is False


@pytest.mark.integration
def test_m6_migration_upgrades_fresh_database_without_fabricating_attempts(
    database_url: str,
) -> None:
    source_url = make_url(database_url)
    database_name = f"harnesslab_m6_upgrade_{uuid4().hex[:12]}"
    psycopg_url = source_url.set(drivername="postgresql")
    admin_url = psycopg_url.set(database="postgres").render_as_string(hide_password=False)
    temporary_url = source_url.set(database=database_name).render_as_string(hide_password=False)
    temporary_psycopg = psycopg_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        os.environ["DATABASE_URL"] = temporary_url
        get_settings.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "20260828_0005")
        command.upgrade(config, "head")
        with psycopg.connect(temporary_psycopg) as connection:
            row = connection.execute(
                "SELECT (SELECT version_num FROM alembic_version), "
                "to_regclass('public.experiment_run_attempt'), "
                "to_regclass('public.experiment_attempt_event'), "
                "to_regclass('public.experiment_resource_event'), "
                "to_regclass('public.experiment_control_event'), "
                "to_regclass('public.budget_reservation'), "
                "(SELECT count(*) FROM experiment_run_attempt)"
            ).fetchone()
        assert row == (
            "20260904_0006",
            "experiment_run_attempt",
            "experiment_attempt_event",
            "experiment_resource_event",
            "experiment_control_event",
            "budget_reservation",
            0,
        )
        command.downgrade(config, "20260828_0005")
        with psycopg.connect(temporary_psycopg) as connection:
            downgraded = connection.execute(
                "SELECT (SELECT version_num FROM alembic_version), "
                "to_regclass('public.experiment_run_attempt'), "
                "to_regclass('public.budget_scope_ledger')"
            ).fetchone()
        assert downgraded == ("20260828_0005", None, None)
    finally:
        get_settings.cache_clear()
        os.environ["DATABASE_URL"] = database_url
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )


async def _setup_authoritative(
    database_url: str, *, label: str
) -> tuple[
    AsyncEngine,
    async_sessionmaker[AsyncSession],
    M5Fixture,
    UnifiedPreflightReceipt,
    tuple[ReservationUnit, ...],
]:
    settings = Settings.without_dotenv(database_url=database_url)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    fixture = _fixture(experiment_id=f"m6-{label}-{uuid4().hex[:10]}")
    receipt = assess_unified_preflight(fixture["unified"], fixture["observations"])
    units = reservation_units_for_plan(fixture["plan"], fixture["cell_budgets"])
    async with factory() as session, session.begin():
        await enqueue_plan(session, fixture["plan"])
        await initialize_authoritative_lifecycle(
            session,
            experiment_id=fixture["plan"].experiment_id,
            plan_digest=fixture["plan"].digest,
            now=NOW,
        )
        await initialize_budget_scope(
            session,
            scope_id=f"scope-{fixture['plan'].experiment_id}",
            estimate=receipt.budget_estimate,
            scope=ReservationScope.STAGE,
            preflight_digest=receipt.receipt_digest,
            now=NOW,
        )
    return engine, factory, fixture, receipt, units


@pytest.mark.integration
async def test_authoritative_lifecycle_controls_recovery_and_reconciliation(
    database_url: str,
) -> None:
    engine, factory, fixture, receipt, units = await _setup_authoritative(
        database_url, label="lifecycle"
    )
    experiment_id = fixture["plan"].experiment_id
    scope_id = f"scope-{experiment_id}"
    actor = canonical_digest({"actor": "m6-operator"})
    authorization = canonical_digest({"authorization": "m6-controls"})
    first_slot = fixture["plan"].run_slots[0].slot_id
    try:
        async with factory() as session, session.begin():
            first = await initialize_authoritative_lifecycle(
                session,
                experiment_id=experiment_id,
                plan_digest=fixture["plan"].digest,
                now=NOW,
            )
            second = await initialize_authoritative_lifecycle(
                session,
                experiment_id=experiment_id,
                plan_digest=fixture["plan"].digest,
                now=NOW,
            )
        assert tuple(item.attempt_id for item in first) == tuple(item.attempt_id for item in second)

        async with factory() as session, session.begin():
            pause = await issue_control(
                session,
                experiment_id=experiment_id,
                plan_digest=fixture["plan"].digest,
                stage=FunnelV3Stage.SMOKE,
                control_type=ControlType.PAUSE,
                actor_identity=actor,
                authorization_identity=authorization,
                reason="operator review",
                now=NOW + timedelta(seconds=1),
                preflight_digest=receipt.receipt_digest,
                budget_estimate_digest=receipt.budget_estimate.estimate_digest,
            )
        assert pause.control_type is ControlType.PAUSE
        async with factory() as session, session.begin():
            blocked, reservation = await claim_authoritative_run(
                session,
                experiment_id,
                "worker",
                now=NOW + timedelta(seconds=2),
                ttl=timedelta(minutes=1),
                preflight=receipt,
                specification=fixture["unified"],
                estimate=receipt.budget_estimate,
                reservation_scope=ReservationScope.STAGE,
                reservation_scope_id=scope_id,
                reservation_units=units,
            )
        assert blocked is None and reservation is None
        async with factory() as session:
            assert await control_state(session, experiment_id) is ControlState.PAUSED
        async with factory() as session:
            with pytest.raises(AuthoritativeLifecycleError, match="differs"):
                async with session.begin():
                    await issue_control(
                        session,
                        experiment_id=experiment_id,
                        plan_digest=fixture["plan"].digest,
                        stage=FunnelV3Stage.SMOKE,
                        control_type=ControlType.RESUME,
                        actor_identity=actor,
                        authorization_identity=authorization,
                        reason="bad resume",
                        now=NOW + timedelta(seconds=3),
                        preflight_digest=canonical_digest({"stale": True}),
                        budget_estimate_digest=receipt.budget_estimate.estimate_digest,
                    )
        async with factory() as session, session.begin():
            await issue_control(
                session,
                experiment_id=experiment_id,
                plan_digest=fixture["plan"].digest,
                stage=FunnelV3Stage.SMOKE,
                control_type=ControlType.RESUME,
                actor_identity=actor,
                authorization_identity=authorization,
                reason="review complete",
                now=NOW + timedelta(seconds=4),
                preflight_digest=receipt.receipt_digest,
                budget_estimate_digest=receipt.budget_estimate.estimate_digest,
            )
        async with factory() as session, session.begin():
            claimed, durable = await claim_authoritative_run(
                session,
                experiment_id,
                "worker",
                now=NOW + timedelta(seconds=5),
                ttl=timedelta(minutes=1),
                preflight=receipt,
                specification=fixture["unified"],
                estimate=receipt.budget_estimate,
                reservation_scope=ReservationScope.STAGE,
                reservation_scope_id=scope_id,
                reservation_units=units,
                slot_ids=(first_slot,),
            )
        assert claimed is not None and durable is not None and durable.durable
        assert durable.decision is ReservationDecision.ACCEPTED
        for offset, status in enumerate(
            (RunStatus.PREPARING, RunStatus.RUNNING, RunStatus.VERIFYING, RunStatus.SCORING),
            start=6,
        ):
            async with factory() as session, session.begin():
                claimed = await transition_run(
                    session,
                    claimed.run_id,
                    "worker",
                    status,
                    now=NOW + timedelta(seconds=offset),
                )
        async with factory() as session, session.begin():
            reconciled = await reconcile_attempt_resources(
                session,
                attempt_id=first[0].attempt_id,
                reservation=durable,
                usage=_usage(unknown_cost=True),
                evidence_reference=_reference("primary-evidence"),
                now=NOW + timedelta(seconds=10),
            )
            finished = await finish_run(
                session,
                claimed.run_id,
                "worker",
                now=NOW + timedelta(seconds=11),
                normalized_outcome=StatisticalOutcome.CAPABILITY_FAIL,
                source_outcome="verified_fail",
                artifact_manifest_path="artifacts/primary/manifest.json",
                evidence_digest=canonical_digest({"evidence": "primary"}),
            )
            duplicate = await reconcile_attempt_resources(
                session,
                attempt_id=first[0].attempt_id,
                reservation=durable,
                usage=_usage(unknown_cost=True),
                evidence_reference=_reference("primary-evidence"),
                now=NOW + timedelta(seconds=12),
            )
        assert finished.status is RunStatus.FAILED_SUBJECT
        assert reconciled == duplicate
        assert reconciled.status is ReconciliationStatus.RECONCILED_WITH_UNAVAILABLE
        assert reconciled.actual.monetary_cost.value is None
        async with factory() as session:
            with pytest.raises(AuthoritativeLifecycleError, match="immutable original"):
                async with session.begin():
                    await reconcile_attempt_resources(
                        session,
                        attempt_id=first[0].attempt_id,
                        reservation=durable,
                        usage=_usage(wall=9),
                        evidence_reference=_reference("primary-evidence"),
                        now=NOW + timedelta(seconds=12),
                    )
        async with factory() as session:
            projection = await read_authoritative_projection(session, claimed.run_id)
            assert projection is not None
            assert projection.primary_attempt.state is LifecycleState.FAILED_CAPABILITY
            assert projection.primary_attempt.evidence_digest == canonical_digest(
                {"evidence": "primary"}
            )
            events = tuple(
                (
                    await session.scalars(
                        select(ExperimentAttemptEventRecord)
                        .where(
                            ExperimentAttemptEventRecord.attempt_id
                            == projection.primary_attempt.attempt_id
                        )
                        .order_by(ExperimentAttemptEventRecord.sequence)
                    )
                ).all()
            )
            assert tuple(item.sequence for item in events) == tuple(range(len(events)))
            assert events[0].previous_event_digest is None
            assert all(
                events[index].previous_event_digest == events[index - 1].event_digest
                for index in range(1, len(events))
            )
            resource_event_count = await session.scalar(
                select(func.coalesce(func.count(), 0)).select_from(ExperimentResourceEventRecord)
            )
            assert resource_event_count is not None and resource_event_count >= 1
            remaining = await never_started_slot_ids(session, experiment_id)
        assert first_slot not in remaining and remaining
        async with factory() as session:
            with pytest.raises(LifecycleTransitionError, match="FAILED_CAPABILITY"):
                async with session.begin():
                    await append_attempt_transition(
                        session,
                        attempt_id=first[0].attempt_id,
                        target=LifecycleState.FAILED_INFRA,
                        occurred_at=NOW + timedelta(seconds=12),
                        reason_code="ILLEGAL_RECLASSIFICATION",
                    )
        async with factory() as session:
            with pytest.raises(LifecycleRecoveryError, match="only a failed infrastructure"):
                async with session.begin():
                    await issue_control(
                        session,
                        experiment_id=experiment_id,
                        plan_digest=fixture["plan"].digest,
                        stage=FunnelV3Stage.SMOKE,
                        control_type=ControlType.RETRY_INFRA_SELECTED,
                        actor_identity=actor,
                        authorization_identity=authorization,
                        reason="capability is not infrastructure",
                        now=NOW + timedelta(seconds=12),
                        selected_slot_ids=(first_slot,),
                        preflight_digest=receipt.receipt_digest,
                        budget_estimate_digest=receipt.budget_estimate.estimate_digest,
                    )
        async with factory() as session, session.begin():
            await issue_control(
                session,
                experiment_id=experiment_id,
                plan_digest=fixture["plan"].digest,
                stage=FunnelV3Stage.SMOKE,
                control_type=ControlType.PAUSE,
                actor_identity=actor,
                authorization_identity=authorization,
                reason="pause after terminal primary",
                now=NOW + timedelta(seconds=12),
                preflight_digest=receipt.receipt_digest,
                budget_estimate_digest=receipt.budget_estimate.estimate_digest,
            )
            immutable_primary = await read_authoritative_projection(session, claimed.run_id)
            assert immutable_primary is not None
            assert immutable_primary.primary_attempt.evidence_digest == canonical_digest(
                {"evidence": "primary"}
            )
        async with factory() as session, session.begin():
            await issue_control(
                session,
                experiment_id=experiment_id,
                plan_digest=fixture["plan"].digest,
                stage=FunnelV3Stage.SMOKE,
                control_type=ControlType.RESUME,
                actor_identity=actor,
                authorization_identity=authorization,
                reason="resume remaining work",
                now=NOW + timedelta(seconds=12),
                preflight_digest=receipt.receipt_digest,
                budget_estimate_digest=receipt.budget_estimate.estimate_digest,
            )
        async with factory() as session, session.begin():
            run_remaining = await issue_control(
                session,
                experiment_id=experiment_id,
                plan_digest=fixture["plan"].digest,
                stage=FunnelV3Stage.SMOKE,
                control_type=ControlType.RUN_REMAINING,
                actor_identity=actor,
                authorization_identity=authorization,
                reason="finish untouched work",
                now=NOW + timedelta(seconds=13),
            )
        assert run_remaining.selected_slot_ids == remaining

        second_slot = remaining[0]
        async with factory() as session, session.begin():
            lost, lost_reservation = await claim_authoritative_run(
                session,
                experiment_id,
                "lost-worker",
                now=NOW + timedelta(seconds=14),
                ttl=timedelta(seconds=5),
                preflight=receipt,
                specification=fixture["unified"],
                estimate=receipt.budget_estimate,
                reservation_scope=ReservationScope.STAGE,
                reservation_scope_id=scope_id,
                reservation_units=units,
                slot_ids=(second_slot,),
            )
            assert lost is not None
            await transition_run(
                session,
                lost.run_id,
                "lost-worker",
                RunStatus.PREPARING,
                now=NOW + timedelta(seconds=15),
            )
        async with factory() as session, session.begin():
            expired = await expire_authoritative_leases(
                session, experiment_id, now=NOW + timedelta(seconds=20)
            )
        assert len(expired) == 1
        async with factory() as session:
            lost_projection = await read_authoritative_projection(session, lost.run_id)
            assert lost_projection is not None
            assert lost_projection.effective_attempt.state is LifecycleState.FAILED_INFRA
            assert len(lost_projection.recovery_attempts) == 0
        assert lost_reservation is not None
        async with factory() as session, session.begin():
            await reconcile_attempt_resources(
                session,
                attempt_id=expired[0],
                reservation=lost_reservation,
                usage=ObservedResourceUsage(
                    wall_time=_unavailable("seconds"),
                    output_tokens=_unavailable("tokens"),
                    model_turns=_unavailable("turns"),
                    tool_calls=_unavailable("calls"),
                    provider_requests=_unavailable("requests"),
                    monetary_cost=_unavailable("USD"),
                ),
                evidence_reference=None,
                now=NOW + timedelta(seconds=21),
            )
            retry = await issue_control(
                session,
                experiment_id=experiment_id,
                plan_digest=fixture["plan"].digest,
                stage=FunnelV3Stage.SMOKE,
                control_type=ControlType.RETRY_INFRA_SELECTED,
                actor_identity=actor,
                authorization_identity=authorization,
                reason="lease incident reviewed",
                now=NOW + timedelta(seconds=22),
                selected_slot_ids=(second_slot,),
                preflight_digest=receipt.receipt_digest,
                budget_estimate_digest=receipt.budget_estimate.estimate_digest,
            )
        assert retry.selected_slot_ids == (second_slot,)
        async with factory() as session:
            recovered = await read_authoritative_projection(session, lost.run_id)
        assert recovered is not None
        assert len(recovered.recovery_attempts) == 1
        assert recovered.recovery_attempts[0].role is AttemptRole.RECOVERY
        assert recovered.primary_attempt.terminal_reason == "LEASE_EXPIRED"
        assert recovered.primary_attempt.evidence_digest is None
        async with factory() as session:
            with pytest.raises(LifecycleRecoveryError, match="only a failed infrastructure"):
                async with session.begin():
                    await issue_control(
                        session,
                        experiment_id=experiment_id,
                        plan_digest=fixture["plan"].digest,
                        stage=FunnelV3Stage.SMOKE,
                        control_type=ControlType.RETRY_INFRA_SELECTED,
                        actor_identity=actor,
                        authorization_identity=authorization,
                        reason="duplicate retry",
                        now=NOW + timedelta(seconds=23),
                        selected_slot_ids=(second_slot,),
                        preflight_digest=receipt.receipt_digest,
                        budget_estimate_digest=receipt.budget_estimate.estimate_digest,
                    )
        async with factory() as session, session.begin():
            recovery_claim, recovery_reservation = await claim_authoritative_run(
                session,
                experiment_id,
                "recovery-worker",
                now=NOW + timedelta(seconds=24),
                ttl=timedelta(minutes=1),
                preflight=receipt,
                specification=fixture["unified"],
                estimate=receipt.budget_estimate,
                reservation_scope=ReservationScope.STAGE,
                reservation_scope_id=scope_id,
                reservation_units=units,
                slot_ids=(second_slot,),
            )
            assert recovery_claim is not None and recovery_reservation is not None
            await transition_run(
                session,
                recovery_claim.run_id,
                "recovery-worker",
                RunStatus.PREPARING,
                now=NOW + timedelta(seconds=25),
            )
        async with factory() as session, session.begin():
            await issue_control(
                session,
                experiment_id=experiment_id,
                plan_digest=fixture["plan"].digest,
                stage=FunnelV3Stage.SMOKE,
                control_type=ControlType.CANCEL,
                actor_identity=actor,
                authorization_identity=authorization,
                reason="stop selected recovery",
                now=NOW + timedelta(seconds=26),
                selected_slot_ids=(second_slot,),
            )
        async with factory() as session:
            selected_cancel_projection = await read_authoritative_projection(
                session, recovery_claim.run_id
            )
            assert selected_cancel_projection is not None
            assert selected_cancel_projection.effective_attempt.state is LifecycleState.PREPARING
        async with factory() as session, session.begin():
            cancelled = await heartbeat_run(
                session,
                recovery_claim.run_id,
                "recovery-worker",
                now=NOW + timedelta(seconds=27),
                ttl=timedelta(minutes=1),
            )
            assert cancelled.status is RunStatus.CANCELLED
            final_reconciliation = await reconcile_attempt_resources(
                session,
                attempt_id=recovered.recovery_attempts[0].attempt_id,
                reservation=recovery_reservation,
                usage=_usage(wall=1),
                evidence_reference=None,
                now=NOW + timedelta(seconds=28),
            )
            assert final_reconciliation.status is ReconciliationStatus.RECONCILED
            await issue_control(
                session,
                experiment_id=experiment_id,
                plan_digest=fixture["plan"].digest,
                stage=FunnelV3Stage.SMOKE,
                control_type=ControlType.CANCEL,
                actor_identity=actor,
                authorization_identity=authorization,
                reason="close campaign",
                now=NOW + timedelta(seconds=29),
            )
        async with factory() as session, session.begin():
            no_claim, no_reservation = await claim_authoritative_run(
                session,
                experiment_id,
                "blocked-worker",
                now=NOW + timedelta(seconds=30),
                ttl=timedelta(minutes=1),
                preflight=receipt,
                specification=fixture["unified"],
                estimate=receipt.budget_estimate,
                reservation_scope=ReservationScope.STAGE,
                reservation_scope_id=scope_id,
                reservation_units=units,
            )
        assert no_claim is None and no_reservation is None
        async with factory() as session:
            final_projection = await read_authoritative_projection(session, recovery_claim.run_id)
            assert final_projection is not None
            assert final_projection.primary_attempt.terminal_reason == "LEASE_EXPIRED"
            assert final_projection.primary_attempt.evidence_digest is None
            assert final_projection.recovery_attempts[0].state is LifecycleState.CANCELLED
            assert await control_state(session, experiment_id) is ControlState.CANCELLED
            control_sequences = tuple(
                (
                    await session.scalars(
                        select(ExperimentControlEventRecord.sequence)
                        .where(ExperimentControlEventRecord.experiment_id == experiment_id)
                        .order_by(ExperimentControlEventRecord.sequence)
                    )
                ).all()
            )
            assert control_sequences == tuple(range(len(control_sequences)))
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ExperimentRunAttemptRecord)
                    .where(ExperimentRunAttemptRecord.run_id == recovery_claim.run_id)
                )
                == 2
            )
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
            await session.execute(
                delete(BudgetScopeLedgerRecord).where(BudgetScopeLedgerRecord.scope_id == scope_id)
            )
        await engine.dispose()


@pytest.mark.integration
async def test_durable_reservation_concurrency_idempotency_and_budget_terminal(
    database_url: str,
) -> None:
    engine, factory, fixture, receipt, units = await _setup_authoritative(
        database_url, label="budget"
    )
    experiment_id = fixture["plan"].experiment_id
    scope_id = f"scope-{experiment_id}"
    try:
        async with factory() as session, session.begin():
            ledger = await session.get(BudgetScopeLedgerRecord, scope_id, with_for_update=True)
            assert ledger is not None
            ledger.consumed_totals_json = ResourceAmounts(
                wall_time_seconds=85,
                output_tokens=0,
                model_turns=0,
                tool_calls=0,
                provider_requests=0,
                monetary_cost_usd=0,
            ).model_dump(mode="json")
        requests = tuple(
            build_reservation_request(
                request_id=f"race-{index}",
                plan=receipt.candidate_plan,
                stage=FunnelV3Stage.SMOKE,
                scope=ReservationScope.STAGE,
                scope_id=scope_id,
                unit=unit,
                budget_estimate=receipt.budget_estimate,
            )
            for index, unit in enumerate(units)
        )

        async def reserve(index: int) -> DurableBudgetReservationReceipt:
            async with factory() as session, session.begin():
                return await reserve_budget(
                    session,
                    request=requests[index],
                    estimate=receipt.budget_estimate,
                    unit=units[index],
                    now=NOW + timedelta(seconds=index),
                )

        decisions = await asyncio.gather(reserve(0), reserve(1))
        assert sum(item.decision is ReservationDecision.ACCEPTED for item in decisions) == 1
        assert sum(item.decision is ReservationDecision.DENIED for item in decisions) == 1
        accepted_index = next(
            index
            for index, item in enumerate(decisions)
            if item.decision is ReservationDecision.ACCEPTED
        )
        assert await reserve(accepted_index) == decisions[accepted_index]
        denied_index = 1 - accepted_index
        denied_slot = units[denied_index].logical_unit_id
        async with factory() as session, session.begin():
            # The exact denied claim is persisted as a terminal budget fact and never executes.
            claimed, denied = await claim_authoritative_run(
                session,
                experiment_id,
                "budget-worker",
                now=NOW + timedelta(seconds=5),
                ttl=timedelta(minutes=1),
                preflight=receipt,
                specification=fixture["unified"],
                estimate=receipt.budget_estimate,
                reservation_scope=ReservationScope.STAGE,
                reservation_scope_id=scope_id,
                reservation_units=units,
                slot_ids=(denied_slot,),
            )
        assert claimed is None and denied is not None
        assert denied.decision is ReservationDecision.DENIED
        run = next(item for item in fixture["plan"].run_slots if item.slot_id == denied_slot)
        run_id = f"run-{run.slot_id.removeprefix('sha256:')}"
        async with factory() as session:
            projection = await read_authoritative_projection(session, run_id)
        assert projection is not None
        assert projection.effective_attempt.state is LifecycleState.BUDGET_EXHAUSTED
        assert capability_outcome_for_attempt(projection.effective_attempt.state) is None
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
            await session.execute(
                delete(BudgetScopeLedgerRecord).where(BudgetScopeLedgerRecord.scope_id == scope_id)
            )
        await engine.dispose()


@pytest.mark.integration
async def test_actual_over_reservation_fails_closed_and_legacy_queue_remains_readable(
    database_url: str,
) -> None:
    engine, factory, fixture, receipt, units = await _setup_authoritative(
        database_url, label="envelope"
    )
    experiment_id = fixture["plan"].experiment_id
    scope_id = f"scope-{experiment_id}"
    try:
        gate = AuthoritativeClaimGate(
            preflight=receipt,
            specification=fixture["unified"],
            estimate=receipt.budget_estimate,
            reservation_scope=ReservationScope.STAGE,
            reservation_scope_id=scope_id,
            reservation_units=units,
        )
        async with factory() as session, session.begin():
            claimed = await gate.claim(
                session,
                experiment_id,
                "worker",
                now=NOW,
                ttl=timedelta(minutes=1),
            )
            assert claimed is not None
            await transition_run(session, claimed.run_id, "worker", RunStatus.PREPARING, now=NOW)
        async with factory() as session, session.begin():
            projection = await read_authoritative_projection(session, claimed.run_id)
            assert projection is not None
            bound_reservation = await durable_reservation_for_attempt(
                session, projection.effective_attempt.attempt_id
            )
            assert bound_reservation is not None
            result = await reconcile_attempt_resources(
                session,
                attempt_id=projection.effective_attempt.attempt_id,
                reservation=bound_reservation,
                usage=_usage(wall=11),
                evidence_reference=None,
                now=NOW + timedelta(seconds=1),
            )
        assert result.status is ReconciliationStatus.ENVELOPE_EXCEEDED
        async with factory() as session:
            projection = await read_authoritative_projection(session, claimed.run_id)
        assert projection is not None
        assert projection.effective_attempt.state is LifecycleState.FAILED_INFRA

        legacy = _fixture(experiment_id=f"legacy-{uuid4().hex[:10]}")
        async with factory() as session, session.begin():
            await enqueue_plan(session, legacy["plan"])
            legacy_claim = await claim_next_run(
                session,
                legacy["plan"].experiment_id,
                "legacy-worker",
                now=NOW,
                ttl=timedelta(minutes=1),
            )
        assert legacy_claim is not None and legacy_claim.attempt == 1
        async with factory() as session:
            assert await read_authoritative_projection(session, legacy_claim.run_id) is None
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id.like("legacy-%"))
            )
            await session.execute(
                delete(BudgetScopeLedgerRecord).where(BudgetScopeLedgerRecord.scope_id == scope_id)
            )
        await engine.dispose()


@pytest.mark.integration
async def test_existing_executor_uses_durable_gate_and_reconciles_terminal_attempt(
    database_url: str,
) -> None:
    engine, factory, fixture, receipt, units = await _setup_authoritative(
        database_url, label="executor"
    )
    experiment_id = fixture["plan"].experiment_id
    scope_id = f"scope-{experiment_id}"
    gate = AuthoritativeClaimGate(
        preflight=receipt,
        specification=fixture["unified"],
        estimate=receipt.budget_estimate,
        reservation_scope=ReservationScope.STAGE,
        reservation_scope_id=scope_id,
        reservation_units=units,
    )
    binding = _RaisingBinding()
    executor = ExperimentRunExecutor(
        repository_root=Path(__file__).resolve().parents[1],
        session_factory=factory,
        bindings={cell.id: binding for cell in fixture["plan"].cells},
        owner="authoritative-executor",
        authoritative_claim_gate=gate,
        clock=lambda: NOW + timedelta(seconds=1),
    )
    try:
        claimed = await executor.claim(experiment_id)
        assert claimed is not None
        finished = await executor.execute(claimed)
        assert finished.status is RunStatus.FAILED_INFRA
        async with factory() as session:
            projection = await read_authoritative_projection(session, claimed.run_id)
            assert projection is not None
            assert projection.effective_attempt.state is LifecycleState.FAILED_INFRA
            reconciliation = await session.scalar(
                select(ExperimentAttemptReconciliationRecord).where(
                    ExperimentAttemptReconciliationRecord.attempt_id
                    == projection.effective_attempt.attempt_id
                )
            )
            assert reconciliation is not None
            persisted = ReconciliationStatus(reconciliation.status)
            assert persisted is ReconciliationStatus.RECONCILED_WITH_UNAVAILABLE
            assert projection.effective_attempt.reservation_digest is not None
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
            await session.execute(
                delete(BudgetScopeLedgerRecord).where(BudgetScopeLedgerRecord.scope_id == scope_id)
            )
        await engine.dispose()
