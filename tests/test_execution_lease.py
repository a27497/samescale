from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete

from harnesslab.core.config import Settings
from harnesslab.db.models.execution_lease import ExecutionLease
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.leases import (
    LeaseConflict,
    claim_execution,
    create_execution_run,
    heartbeat_execution,
    release_execution,
    request_cancellation,
)


@pytest.mark.integration
async def test_execution_lease_heartbeat_and_expiry_recovery(database_url: str) -> None:
    settings = Settings.without_dotenv(database_url=database_url)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    run_id = f"phase-c-{uuid4().hex}"
    started = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    ttl = timedelta(seconds=30)
    try:
        async with factory() as session:
            created = await create_execution_run(session, run_id)
            assert created.attempt == 0
            claimed = await claim_execution(session, run_id, "worker-a", now=started, ttl=ttl)
            assert claimed.lease_owner == "worker-a"
            assert claimed.attempt == 1

            with pytest.raises(LeaseConflict, match="cannot be stolen"):
                await claim_execution(
                    session,
                    run_id,
                    "worker-b",
                    now=started + timedelta(seconds=1),
                    ttl=ttl,
                )
            with pytest.raises(LeaseConflict, match="only the lease owner"):
                await heartbeat_execution(
                    session,
                    run_id,
                    "worker-b",
                    now=started + timedelta(seconds=1),
                    ttl=ttl,
                )
            with pytest.raises(LeaseConflict, match="only the lease owner"):
                await release_execution(
                    session, run_id, "worker-b", now=started + timedelta(seconds=1)
                )

            heartbeat = await heartbeat_execution(
                session,
                run_id,
                "worker-a",
                now=started + timedelta(seconds=10),
                ttl=ttl,
            )
            assert heartbeat.lease_expires_at == started + timedelta(seconds=40)
            cancellation = await request_cancellation(session, run_id)
            assert cancellation.cancellation_requested

            reclaimed = await claim_execution(
                session,
                run_id,
                "worker-b",
                now=started + timedelta(seconds=41),
                ttl=ttl,
            )
            assert reclaimed.lease_owner == "worker-b"
            assert reclaimed.attempt == 2
            assert reclaimed.lease_expires_at == started + timedelta(seconds=71)

            released = await release_execution(
                session, run_id, "worker-b", now=started + timedelta(seconds=42)
            )
            assert released.lease_owner is None
            assert released.status == "released"
            await session.rollback()
    finally:
        async with factory() as cleanup_session:
            await cleanup_session.execute(
                delete(ExecutionLease).where(ExecutionLease.run_id == run_id)
            )
            await cleanup_session.commit()
        await engine.dispose()
