from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from harnesslab.contracts.run import RunStatus
from harnesslab.core.config import Settings
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.experiment.executor import ExperimentRunExecutor, attempt_execution_id
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.plan import ExperimentPlan, build_experiment_plan
from harnesslab.experiment.queue import (
    ACTIVE_STATUSES,
    ExperimentConflict,
    RunSnapshot,
    claim_next_run,
    enqueue_plan,
    inspect_run,
    request_run_cancellation,
)
from harnesslab.experiment.report import build_experiment_report
from tests.phase_g_helpers import ROOT, basic_spec


class BlockingBinding:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.run_ids: list[str] = []

    async def run(self, task_path: Path, run_id: str) -> Any:
        self.run_ids.append(run_id)
        self.entered.set()
        await self.release.wait()
        return object()


class RaisingBinding:
    def __init__(self) -> None:
        self.run_ids: list[str] = []

    async def run(self, task_path: Path, run_id: str) -> Any:
        self.run_ids.append(run_id)
        raise RuntimeError("controlled worker failure")


def _single_run_plan(experiment_id: str) -> ExperimentPlan:
    base = basic_spec(repeat_count=1)
    spec = base.model_copy(
        update={
            "experiment_id": experiment_id,
            "cells": (base.cells[0],),
            "paired_comparisons": (),
        }
    )
    return build_experiment_plan(spec, ROOT)


def _three_run_plan(experiment_id: str) -> ExperimentPlan:
    base = basic_spec(repeat_count=3)
    spec = base.model_copy(
        update={
            "experiment_id": experiment_id,
            "cells": (base.cells[0],),
            "paired_comparisons": (),
        }
    )
    return build_experiment_plan(spec, ROOT)


async def _wait_for_status(factory: Any, run_id: str, status: RunStatus) -> None:
    async def wait() -> None:
        while True:
            async with factory() as session:
                snapshot = await inspect_run(session, run_id)
            if snapshot.status is status:
                return
            await asyncio.sleep(0.005)

    await asyncio.wait_for(wait(), timeout=5)


@pytest.mark.integration
@pytest.mark.parametrize("new_owner", ["worker-b", "worker-a"])
async def test_executor_heartbeat_protects_active_run_and_lost_owner_cannot_write(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    new_owner: str,
) -> None:
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    experiment_id = f"phase-g-heartbeat-{uuid4().hex[:12]}"
    binding = BlockingBinding()
    ttl = timedelta(milliseconds=120)
    now = datetime.now(UTC)
    renewed = asyncio.Event()
    lost_owner = asyncio.Event()
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, _single_run_plan(experiment_id))
        executor = ExperimentRunExecutor(
            repository_root=ROOT,
            session_factory=factory,
            bindings={"model": binding},
            owner="worker-a",
            lease_ttl=ttl,
            heartbeat_cadence=timedelta(milliseconds=20),
            clock=lambda: now,
        )
        claimed = await executor.claim(experiment_id)
        assert claimed is not None
        initial_expiry = claimed.lease_expires_at
        assert initial_expiry is not None
        heartbeat = executor._heartbeat

        async def observe_heartbeat(claim: RunSnapshot) -> RunSnapshot:
            try:
                snapshot = await heartbeat(claim)
            except ExperimentConflict:
                lost_owner.set()
                raise
            if snapshot.lease_expires_at is not None and snapshot.lease_expires_at > initial_expiry:
                renewed.set()
            return snapshot

        monkeypatch.setattr(executor, "_heartbeat", observe_heartbeat)
        execution = asyncio.create_task(executor.execute(claimed))
        await asyncio.wait_for(binding.entered.wait(), timeout=5)

        # Observe a committed renewal before advancing past the original lease.
        # Host scheduling latency must not decide whether this lease is expired.
        now += ttl / 2
        await asyncio.wait_for(renewed.wait(), timeout=5)
        now = initial_expiry
        async with factory() as session, session.begin():
            cannot_reclaim = await claim_next_run(
                session,
                experiment_id,
                "worker-b",
                now=now,
                ttl=ttl,
            )
        assert cannot_reclaim is None

        async with factory() as session, session.begin():
            durable = await session.get(ExperimentRunRecord, claimed.run_id, with_for_update=True)
            assert durable is not None
            durable.lease_owner = new_owner
            durable.lease_expires_at = now + ttl
            durable.attempt += 1
            durable.status = RunStatus.CLAIMED.value
        await asyncio.wait_for(lost_owner.wait(), timeout=5)
        binding.release.set()
        stale_result = await asyncio.wait_for(execution, timeout=5)

        assert stale_result.status is RunStatus.CLAIMED
        assert stale_result.lease_owner == new_owner
        assert stale_result.normalized_outcome is None
        assert binding.run_ids == [attempt_execution_id(claimed)]
    finally:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()


@pytest.mark.integration
async def test_executor_cancellation_short_circuits_after_active_binding_returns(
    database_url: str,
) -> None:
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    experiment_id = f"phase-g-cancel-{uuid4().hex[:12]}"
    binding = BlockingBinding()
    now = datetime.now(UTC)  # Cancellation behavior is independent of host scheduling.
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, _single_run_plan(experiment_id))
        executor = ExperimentRunExecutor(
            repository_root=ROOT,
            session_factory=factory,
            bindings={"model": binding},
            owner="cancel-worker",
            clock=lambda: now,
            lease_ttl=timedelta(milliseconds=150),
            heartbeat_cadence=timedelta(milliseconds=20),
        )
        claimed = await executor.claim(experiment_id)
        assert claimed is not None
        execution = asyncio.create_task(executor.execute(claimed))
        await asyncio.wait_for(binding.entered.wait(), timeout=5)
        async with factory() as session, session.begin():
            await request_run_cancellation(session, claimed.run_id, now=now)
        await _wait_for_status(factory, claimed.run_id, RunStatus.CANCELLED)
        binding.release.set()
        cancelled = await asyncio.wait_for(execution, timeout=5)

        assert cancelled.status is RunStatus.CANCELLED
        assert cancelled.normalized_outcome is StatisticalOutcome.CANCELLED
        assert cancelled.artifact_manifest_path is None
        async with factory() as session:
            report = await build_experiment_report(session, experiment_id, bootstrap_resamples=99)
        assert report.cells[0].cancelled_runs == 1
        assert report.cells[0].completed_capability_runs == 0
    finally:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()


@pytest.mark.integration
async def test_reclaimed_attempt_passes_unique_attempt_artifact_identity(database_url: str) -> None:
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    experiment_id = f"phase-g-attempt-{uuid4().hex[:12]}"
    binding = RaisingBinding()
    ttl = timedelta(milliseconds=50)
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, _single_run_plan(experiment_id))
            first = await claim_next_run(
                session, experiment_id, "abandoned-worker", now=datetime.now(UTC), ttl=ttl
            )
        assert first is not None
        await asyncio.sleep(0.06)
        executor = ExperimentRunExecutor(
            repository_root=ROOT,
            session_factory=factory,
            bindings={"model": binding},
            owner="reclaim-worker",
            lease_ttl=timedelta(seconds=1),
            heartbeat_cadence=timedelta(milliseconds=50),
        )
        reclaimed = await executor.claim(experiment_id)
        assert reclaimed is not None
        assert reclaimed.run_id == first.run_id
        assert reclaimed.attempt == 2
        finished = await executor.execute(reclaimed)

        assert attempt_execution_id(first) != attempt_execution_id(reclaimed)
        assert binding.run_ids == [attempt_execution_id(reclaimed)]
        assert finished.status is RunStatus.FAILED_INFRA
    finally:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()


@pytest.mark.integration
async def test_bounded_executor_resumes_without_duplicate_logical_runs(database_url: str) -> None:
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    experiment_id = f"phase-k-bounded-resume-{uuid4().hex[:12]}"
    binding = RaisingBinding()
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, _three_run_plan(experiment_id))
        executor = ExperimentRunExecutor(
            repository_root=ROOT,
            session_factory=factory,
            bindings={"model": binding},
            owner="phase-k-bounded-worker",
        )

        first_slice = await executor.run_bounded(
            experiment_id,
            max_runs=2,
            concurrency=2,
        )
        resumed_slice = await executor.run_bounded(
            experiment_id,
            max_runs=3,
            concurrency=2,
        )
        exhausted_slice = await executor.run_bounded(
            experiment_id,
            max_runs=3,
            concurrency=2,
        )

        assert len(first_slice) == 2
        assert len(resumed_slice) == 1
        assert exhausted_slice == ()
        assert len(binding.run_ids) == 3
        assert len(set(binding.run_ids)) == 3
        async with factory() as session:
            snapshots = tuple(
                (
                    await session.scalars(
                        select(ExperimentRunRecord).where(
                            ExperimentRunRecord.experiment_id == experiment_id
                        )
                    )
                ).all()
            )
        assert len(snapshots) == 3
        assert {item.attempt for item in snapshots} == {1}
    finally:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.parametrize("cancel_after_expiry", [False, True])
@pytest.mark.parametrize("active_status", ACTIVE_STATUSES)
async def test_cancelled_abandoned_run_reaches_terminal_without_binding(
    database_url: str, cancel_after_expiry: bool, active_status: str
) -> None:
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    experiment_id = f"phase-l2-cancel-{uuid4().hex[:12]}"
    now = datetime(2026, 9, 6, tzinfo=UTC)
    ttl = timedelta(seconds=30)
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, _single_run_plan(experiment_id))
            claim = await claim_next_run(session, experiment_id, "dead-worker", now=now, ttl=ttl)
        assert claim is not None
        async with factory() as session, session.begin():
            row = await session.get(ExperimentRunRecord, claim.run_id)
            assert row is not None
            row.status = active_status
        requested_at = now + (ttl if cancel_after_expiry else timedelta(seconds=1))
        async with factory() as session, session.begin():
            requested = await request_run_cancellation(session, claim.run_id, now=requested_at)
        if cancel_after_expiry:
            assert requested.status is RunStatus.CANCELLED
        else:
            assert requested.status.value == active_status
            # Maintenance before expiry must leave the live cancelled claim alone.
            async with factory() as session, session.begin():
                assert (
                    await claim_next_run(
                        session, experiment_id, "restart-worker", now=requested_at, ttl=ttl
                    )
                    is None
                )
            async with factory() as session:
                assert await inspect_run(session, claim.run_id) == requested
        # A normal restarted worker must reconcile this even though no slot is claimable.
        executor = ExperimentRunExecutor(
            repository_root=ROOT,
            session_factory=factory,
            bindings={},
            owner="restart-worker",
            clock=lambda: now + ttl,
        )
        assert await executor.run_until_idle(experiment_id) == ()
        async with factory() as session:
            terminal = await inspect_run(session, claim.run_id)
            experiment = await session.get(ExperimentRecord, experiment_id)
            assert terminal.status is RunStatus.CANCELLED
            assert terminal.attempt == claim.attempt
            assert terminal.lease_owner is None and terminal.lease_expires_at is None
            assert terminal.normalized_outcome is StatisticalOutcome.CANCELLED
            assert terminal.artifact_manifest_path is None and terminal.evidence_digest is None
            assert experiment is not None and experiment.status == "completed"
        assert await executor.run_until_idle(experiment_id) == ()
        async with factory() as session:
            assert await inspect_run(session, claim.run_id) == terminal
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()


@pytest.mark.parametrize(
    "length, attempt, expected",
    [
        (8, 1, "rrrrrrrr-a1"),
        (97, 1, "r" * 97 + "-a1"),
        (100, 12, "r" * 79 + "-f572291ca751ad37-a12"),
    ],
)
def test_shared_attempt_identity_preserves_historical_manifest_ids(
    tmp_path: Path, length: int, attempt: int, expected: str
) -> None:
    import json

    from harnesslab.evidence.reader import load_verified_manifest
    from harnesslab.sandbox.artifacts import sha256_file

    # Expected IDs were captured from the pre-closeout reader, including the 100-char boundary.
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"run_id": expected}))
    run = ExperimentRunRecord(
        run_id="r" * length,
        attempt=attempt,
        artifact_manifest_path=str(manifest),
        evidence_digest=sha256_file(manifest),
    )
    assert attempt_execution_id(run) == expected
    assert len(expected) <= 100
    assert load_verified_manifest(run, (tmp_path,)).raw["run_id"] == expected
