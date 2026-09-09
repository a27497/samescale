from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from harnesslab.contracts.run import RunStatus
from harnesslab.core.config import Settings, get_settings
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.plan import build_experiment_plan
from harnesslab.experiment.queue import (
    ExperimentConflict,
    claim_next_run,
    enqueue_plan,
    finish_run,
    heartbeat_run,
    inspect_run,
    release_run,
    request_run_cancellation,
    requeue_failed_infra_after_repair,
    transition_run,
)
from harnesslab.experiment.report import build_experiment_report
from tests.phase_g_helpers import ROOT, basic_spec


@pytest.mark.integration
async def test_postgresql_durable_queue_skip_locked_lease_and_idempotency(
    database_url: str,
) -> None:
    settings = Settings.without_dotenv(database_url=database_url)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    experiment_id = f"phase-g-{uuid4().hex[:12]}"
    spec = basic_spec().model_copy(update={"experiment_id": experiment_id})
    plan = build_experiment_plan(spec, ROOT)
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    ttl = timedelta(seconds=30)
    try:
        async with factory() as session, session.begin():
            first = await enqueue_plan(session, plan)
        async with factory() as session, session.begin():
            second = await enqueue_plan(session, plan)
        assert first.created
        assert not second.created
        assert first.logical_run_count == second.logical_run_count == len(plan.run_slots)

        changed = plan.model_copy(update={"execution_seed": plan.execution_seed + 1})
        async with factory() as session:
            with pytest.raises(ExperimentConflict, match="different immutable plan"):
                async with session.begin():
                    await enqueue_plan(session, changed)

        session_a = factory()
        session_b = factory()
        try:
            async with session_a.begin():
                claimed_a = await claim_next_run(
                    session_a, experiment_id, "worker-a", now=now, ttl=ttl
                )
                assert claimed_a is not None
                async with session_b.begin():
                    claimed_b = await claim_next_run(
                        session_b, experiment_id, "worker-b", now=now, ttl=ttl
                    )
                    assert claimed_b is not None
                    assert claimed_b.run_id != claimed_a.run_id
                    assert claimed_b.slot_order != claimed_a.slot_order
        finally:
            await session_a.close()
            await session_b.close()

        async with factory() as session, session.begin():
            heartbeat = await heartbeat_run(
                session,
                claimed_a.run_id,
                "worker-a",
                attempt=claimed_a.attempt,
                now=now + timedelta(seconds=5),
                ttl=ttl,
            )
        assert heartbeat.lease_expires_at == now + timedelta(seconds=35)

        async with factory() as session:
            with pytest.raises(ExperimentConflict, match="only the active lease owner"):
                async with session.begin():
                    await heartbeat_run(
                        session,
                        claimed_a.run_id,
                        "worker-x",
                        attempt=claimed_a.attempt,
                        now=now + timedelta(seconds=6),
                        ttl=ttl,
                    )
        async with factory() as session:
            with pytest.raises(ExperimentConflict, match="only the active lease owner"):
                async with session.begin():
                    await release_run(
                        session,
                        claimed_a.run_id,
                        "worker-x",
                        attempt=claimed_a.attempt,
                        now=now + timedelta(seconds=6),
                    )

        async with factory() as session, session.begin():
            active_cancellation = await request_run_cancellation(
                session, claimed_b.run_id, now=now + timedelta(seconds=6)
            )
        assert active_cancellation.cancellation_requested
        assert active_cancellation.status is RunStatus.CLAIMED
        async with factory() as session, session.begin():
            active_cancellation = await transition_run(
                session,
                claimed_b.run_id,
                "worker-b",
                RunStatus.PREPARING,
                attempt=claimed_b.attempt,
                now=now + timedelta(seconds=7),
            )
        assert active_cancellation.status is RunStatus.CANCELLED
        assert active_cancellation.lease_owner is None

        async with factory() as session, session.begin():
            reclaimed = await claim_next_run(
                session,
                experiment_id,
                "worker-c",
                now=now + timedelta(seconds=36),
                ttl=ttl,
            )
        assert reclaimed is not None
        assert reclaimed.run_id == claimed_a.run_id
        assert reclaimed.attempt == 2

        async with factory() as session, session.begin():
            queued_run_id = await session.scalar(
                select(ExperimentRunRecord.run_id)
                .where(
                    ExperimentRunRecord.experiment_id == experiment_id,
                    ExperimentRunRecord.status == RunStatus.QUEUED.value,
                )
                .order_by(ExperimentRunRecord.slot_order)
                .limit(1)
            )
            assert queued_run_id is not None
            cancelled = await request_run_cancellation(
                session, queued_run_id, now=now + timedelta(seconds=37)
            )
        assert cancelled.cancellation_requested
        assert cancelled.status is RunStatus.CANCELLED

        async with factory() as session, session.begin():
            released = await release_run(
                session,
                reclaimed.run_id,
                "worker-c",
                attempt=reclaimed.attempt,
                now=now + timedelta(seconds=37),
            )
        assert released.status is RunStatus.QUEUED
        assert released.lease_owner is None

        async with factory() as session, session.begin():
            lifecycle = await claim_next_run(
                session,
                experiment_id,
                "worker-d",
                now=now + timedelta(seconds=38),
                ttl=ttl,
            )
        assert lifecycle is not None
        assert lifecycle.run_id == claimed_a.run_id
        async with factory() as session:
            with pytest.raises(ExperimentConflict, match="invalid run lifecycle transition"):
                async with session.begin():
                    await transition_run(
                        session,
                        lifecycle.run_id,
                        "worker-d",
                        RunStatus.RUNNING,
                        attempt=lifecycle.attempt,
                        now=now + timedelta(seconds=39),
                    )
        for status in (
            RunStatus.PREPARING,
            RunStatus.RUNNING,
            RunStatus.VERIFYING,
            RunStatus.SCORING,
        ):
            async with factory() as session, session.begin():
                lifecycle = await transition_run(
                    session,
                    lifecycle.run_id,
                    "worker-d",
                    status,
                    attempt=lifecycle.attempt,
                    now=now + timedelta(seconds=39),
                )
        async with factory() as session, session.begin():
            lifecycle = await finish_run(
                session,
                lifecycle.run_id,
                "worker-d",
                attempt=lifecycle.attempt,
                now=now + timedelta(seconds=40),
                normalized_outcome=StatisticalOutcome.INFRA_FAILURE,
                source_outcome="queue_test_infra",
                artifact_manifest_path=None,
                evidence_digest=None,
                failure_detail="controlled repair fixture",
            )
        assert lifecycle.status is RunStatus.FAILED_INFRA
        assert lifecycle.normalized_outcome is StatisticalOutcome.INFRA_FAILURE
        async with factory() as session:
            report = await build_experiment_report(session, experiment_id, bootstrap_resamples=99)
        assert sum(cell.infra_failures for cell in report.cells) == 1
        assert sum(cell.completed_capability_runs for cell in report.cells) == 0
        assert sum(cell.cancelled_runs for cell in report.cells) == 2
        async with factory() as session, session.begin():
            repaired = await requeue_failed_infra_after_repair(
                session,
                lifecycle.run_id,
                expected_source_outcome="queue_test_infra",
                expected_failure_detail="controlled repair fixture",
            )
        assert repaired.status is RunStatus.QUEUED
        assert repaired.attempt == lifecycle.attempt
        async with factory() as session, session.begin():
            repaired_attempt = await claim_next_run(
                session,
                experiment_id,
                "worker-repair",
                now=now + timedelta(seconds=41),
                ttl=ttl,
                slot_ids=(repaired.slot_id,),
            )
        assert repaired_attempt is not None
        assert repaired_attempt.run_id == lifecycle.run_id
        assert repaired_attempt.attempt == lifecycle.attempt + 1
    finally:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()


@pytest.mark.integration
async def test_stale_attempt_cannot_heartbeat_after_same_owner_reclaim(database_url: str) -> None:
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    experiment_id = f"phase-l2-f1-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    spec = basic_spec(repeat_count=1).model_copy(update={"experiment_id": experiment_id})
    plan = build_experiment_plan(spec, ROOT)
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    ttl = timedelta(seconds=30)
    owner = "reused-worker"
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, plan)
        async with factory() as first_session, first_session.begin():
            first = await claim_next_run(first_session, experiment_id, owner, now=now, ttl=ttl)
        assert first is not None
        assert first.attempt == 1
        assert first.lease_expires_at == now + ttl

        # Reclaim through the real queue after expiry, in an independent session.
        # The old worker keeps its original immutable claim snapshot.
        reclaimed_at = now + ttl + timedelta(seconds=1)
        async with factory() as second_session, second_session.begin():
            second = await claim_next_run(
                second_session,
                experiment_id,
                owner,
                now=reclaimed_at,
                ttl=ttl,
                slot_ids=(first.slot_id,),
            )
        assert second is not None
        assert second.run_id == first.run_id
        assert first.attempt == 1 and second.attempt == 2
        assert first.lease_owner == second.lease_owner == owner

        # Positive control: the current attempt can still renew its own lease.
        async with factory() as current_session, current_session.begin():
            current = await heartbeat_run(
                current_session,
                second.run_id,
                owner,
                attempt=second.attempt,
                now=reclaimed_at + timedelta(seconds=1),
                ttl=ttl,
            )
        assert current.attempt == second.attempt
        assert current.lease_expires_at == reclaimed_at + timedelta(seconds=1) + ttl

        # F1: carry the original first.attempt. Reusing the owner must
        # not authorize this stale worker against the second attempt's live lease.
        # Keep raises outside the transaction so an erroneous success is committed.
        with pytest.raises(ExperimentConflict):
            async with factory() as stale_session, stale_session.begin():
                await heartbeat_run(
                    stale_session,
                    first.run_id,
                    owner,
                    attempt=first.attempt,
                    now=reclaimed_at + timedelta(seconds=2),
                    ttl=ttl,
                )
        async with factory() as observer:
            assert await inspect_run(observer, first.run_id) == current
    finally:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()


@pytest.mark.integration
def test_phase_f_to_phase_g_migration_preserves_execution_lease(database_url: str) -> None:
    source_url = make_url(database_url)
    database_name = f"harnesslab_g_upgrade_{uuid4().hex[:12]}"
    psycopg_url = source_url.set(drivername="postgresql")
    admin_url = psycopg_url.set(database="postgres").render_as_string(hide_password=False)
    temporary_url = source_url.set(database=database_name).render_as_string(hide_password=False)
    temporary_psycopg_url = psycopg_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        os.environ["DATABASE_URL"] = temporary_url
        get_settings.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "20260822_0002")
        with psycopg.connect(temporary_psycopg_url) as connection:
            connection.execute(
                "INSERT INTO execution_lease (run_id, status, attempt) "
                "VALUES ('preserved-phase-c-run', 'claimed', 2)"
            )
            connection.commit()
        command.upgrade(config, "20260823_0003")
        with psycopg.connect(temporary_psycopg_url) as connection:
            row = connection.execute(
                "SELECT run_id, status, attempt, "
                "to_regclass('public.experiment_run'), "
                "(SELECT version_num FROM alembic_version) "
                "FROM execution_lease WHERE run_id = 'preserved-phase-c-run'"
            ).fetchone()
        assert row == (
            "preserved-phase-c-run",
            "claimed",
            2,
            "experiment_run",
            "20260823_0003",
        )
    finally:
        get_settings.cache_clear()
        os.environ["DATABASE_URL"] = database_url
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )


@pytest.mark.integration
@pytest.mark.parametrize("operation", ["transition", "release", "finish"])
async def test_same_owner_stale_attempt_cannot_mutate_new_attempt(
    database_url: str, operation: str
) -> None:
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    experiment_id = f"phase-l2-fence-{uuid4().hex[:12]}"
    plan = build_experiment_plan(
        basic_spec(repeat_count=1).model_copy(update={"experiment_id": experiment_id}), ROOT
    )
    now = datetime(2026, 9, 6, tzinfo=UTC)
    ttl = timedelta(seconds=30)
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, plan)
            first = await claim_next_run(session, experiment_id, "owner", now=now, ttl=ttl)
        assert first is not None
        now += ttl
        async with factory() as session, session.begin():
            second = await claim_next_run(
                session, experiment_id, "owner", now=now, ttl=ttl, slot_ids=(first.slot_id,)
            )
            assert second is not None and second.attempt == first.attempt + 1
            if operation == "finish":
                for status in (
                    RunStatus.PREPARING,
                    RunStatus.RUNNING,
                    RunStatus.VERIFYING,
                    RunStatus.SCORING,
                ):
                    second = await transition_run(
                        session, second.run_id, "owner", status, attempt=second.attempt, now=now
                    )

        async def mutate(attempt: int) -> None:
            async with factory() as session, session.begin():
                if operation == "transition":
                    await transition_run(
                        session,
                        first.run_id,
                        "owner",
                        RunStatus.PREPARING,
                        attempt=attempt,
                        now=now,
                    )
                elif operation == "release":
                    await release_run(session, first.run_id, "owner", attempt=attempt, now=now)
                else:
                    await finish_run(
                        session,
                        first.run_id,
                        "owner",
                        attempt=attempt,
                        now=now,
                        normalized_outcome=StatisticalOutcome.INFRA_FAILURE,
                        source_outcome="controlled_failure",
                        artifact_manifest_path="stale.json",
                        evidence_digest="sha256:" + "a" * 64,
                        tool_calls=123,
                    )

        with pytest.raises(ExperimentConflict, match="active attempt"):
            await mutate(first.attempt)
        async with factory() as session:
            assert await inspect_run(session, first.run_id) == second
            row = await session.get(ExperimentRunRecord, first.run_id)
            assert row is not None and row.tool_calls is None
        await mutate(second.attempt)  # The same mutation remains legal for the current claim.
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()


@pytest.mark.integration
async def test_release_after_cancellation_cannot_strand_a_queued_run(database_url: str) -> None:
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    experiment_id = f"phase-l2-release-{uuid4().hex[:12]}"
    plan = build_experiment_plan(
        basic_spec(repeat_count=1).model_copy(update={"experiment_id": experiment_id}), ROOT
    )
    now = datetime(2026, 9, 6, tzinfo=UTC)
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, plan)
            claim = await claim_next_run(
                session, experiment_id, "owner", now=now, ttl=timedelta(seconds=30)
            )
        assert claim is not None
        async with factory() as session, session.begin():
            await request_run_cancellation(session, claim.run_id, now=now)
        async with factory() as session, session.begin():
            cancelled = await release_run(
                session, claim.run_id, "owner", attempt=claim.attempt, now=now
            )
        assert cancelled.status is RunStatus.CANCELLED
        assert cancelled.lease_owner is None and cancelled.lease_expires_at is None
        async with factory() as session, session.begin():
            assert await request_run_cancellation(session, claim.run_id, now=now) == cancelled
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()
