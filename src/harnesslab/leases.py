from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.db.models.execution_lease import ExecutionLease


class LeaseConflict(RuntimeError):
    """Lease ownership or expiry prevents the requested transition."""


@dataclass(frozen=True)
class LeaseSnapshot:
    run_id: str
    lease_owner: str | None
    lease_expires_at: datetime | None
    heartbeat_at: datetime | None
    attempt: int
    cancellation_requested: bool
    status: str


def _snapshot(lease: ExecutionLease) -> LeaseSnapshot:
    return LeaseSnapshot(
        run_id=lease.run_id,
        lease_owner=lease.lease_owner,
        lease_expires_at=lease.lease_expires_at,
        heartbeat_at=lease.heartbeat_at,
        attempt=lease.attempt,
        cancellation_requested=lease.cancellation_requested,
        status=lease.status,
    )


async def create_execution_run(session: AsyncSession, run_id: str) -> LeaseSnapshot:
    lease = ExecutionLease(run_id=run_id, status="available")
    session.add(lease)
    await session.flush()
    return _snapshot(lease)


async def _locked_lease(session: AsyncSession, run_id: str) -> ExecutionLease:
    lease = await session.scalar(
        select(ExecutionLease).where(ExecutionLease.run_id == run_id).with_for_update()
    )
    if lease is None:
        raise LeaseConflict("execution run does not exist")
    return lease


async def claim_execution(
    session: AsyncSession,
    run_id: str,
    owner: str,
    *,
    now: datetime,
    ttl: timedelta,
) -> LeaseSnapshot:
    if ttl <= timedelta(0):
        raise ValueError("lease ttl must be positive")
    lease = await _locked_lease(session, run_id)
    active = (
        lease.lease_owner is not None
        and lease.lease_expires_at is not None
        and lease.lease_expires_at > now
    )
    if active:
        raise LeaseConflict("active lease cannot be stolen")
    lease.lease_owner = owner
    lease.heartbeat_at = now
    lease.lease_expires_at = now + ttl
    lease.attempt += 1
    lease.status = "claimed"
    await session.flush()
    return _snapshot(lease)


async def heartbeat_execution(
    session: AsyncSession,
    run_id: str,
    owner: str,
    *,
    now: datetime,
    ttl: timedelta,
) -> LeaseSnapshot:
    if ttl <= timedelta(0):
        raise ValueError("lease ttl must be positive")
    lease = await _locked_lease(session, run_id)
    if lease.lease_owner != owner:
        raise LeaseConflict("only the lease owner may heartbeat")
    if lease.lease_expires_at is None or lease.lease_expires_at <= now:
        raise LeaseConflict("expired lease cannot heartbeat")
    lease.heartbeat_at = now
    lease.lease_expires_at = now + ttl
    await session.flush()
    return _snapshot(lease)


async def release_execution(
    session: AsyncSession, run_id: str, owner: str, *, now: datetime
) -> LeaseSnapshot:
    lease = await _locked_lease(session, run_id)
    if lease.lease_owner != owner:
        raise LeaseConflict("only the lease owner may release")
    lease.lease_owner = None
    lease.lease_expires_at = None
    lease.heartbeat_at = now
    lease.status = "released"
    await session.flush()
    return _snapshot(lease)


async def request_cancellation(session: AsyncSession, run_id: str) -> LeaseSnapshot:
    lease = await _locked_lease(session, run_id)
    lease.cancellation_requested = True
    await session.flush()
    return _snapshot(lease)
