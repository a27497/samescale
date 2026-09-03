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
async def test_executor_heartbeat_protects_active_run_and_lost_owner_cannot_write(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
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

        async def observe_heartbeat(run_id: str) -> RunSnapshot:
            try:
                snapshot = await heartbeat(run_id)
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
            durable.lease_owner = "worker-b"
            durable.lease_expires_at = now + ttl
            durable.attempt += 1
            durable.status = RunStatus.CLAIMED.value
        await asyncio.wait_for(lost_owner.wait(), timeout=5)
        binding.release.set()
        stale_result = await asyncio.wait_for(execution, timeout=5)

        assert stale_result.status is RunStatus.CLAIMED
        assert stale_result.lease_owner == "worker-b"
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
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, _single_run_plan(experiment_id))
        executor = ExperimentRunExecutor(
            repository_root=ROOT,
            session_factory=factory,
            bindings={"model": binding},
            owner="cancel-worker",
            lease_ttl=timedelta(milliseconds=150),
            heartbeat_cadence=timedelta(milliseconds=20),
        )
        claimed = await executor.claim(experiment_id)
        assert claimed is not None
        execution = asyncio.create_task(executor.execute(claimed))
        await asyncio.wait_for(binding.entered.wait(), timeout=5)
        async with factory() as session, session.begin():
            await request_run_cancellation(session, claimed.run_id, now=datetime.now(UTC))
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
