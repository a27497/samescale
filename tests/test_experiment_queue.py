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
    release_run,
    request_run_cancellation,
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
                    now=now + timedelta(seconds=39),
                )
        async with factory() as session, session.begin():
            lifecycle = await finish_run(
                session,
                lifecycle.run_id,
                "worker-d",
                now=now + timedelta(seconds=40),
                normalized_outcome=StatisticalOutcome.INFRA_FAILURE,
                source_outcome="queue_test_infra",
                artifact_manifest_path=None,
                evidence_digest=None,
            )
        assert lifecycle.status is RunStatus.FAILED_INFRA
        assert lifecycle.normalized_outcome is StatisticalOutcome.INFRA_FAILURE
        async with factory() as session:
            report = await build_experiment_report(session, experiment_id, bootstrap_resamples=99)
        assert sum(cell.infra_failures for cell in report.cells) == 1
        assert sum(cell.completed_capability_runs for cell in report.cells) == 0
        assert sum(cell.cancelled_runs for cell in report.cells) == 2
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
