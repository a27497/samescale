from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.comparability.manifest import load_manifest_facts
from harnesslab.contracts.run import RunStatus
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.evaluation_suites.models import ImmutableArtifactReference
from harnesslab.experiment.authoritative import (
    ObservedResourceDimension,
    ObservedResourceUsage,
    ReconciliationReceipt,
    ReconciliationStatus,
    ResourceAvailability,
    current_attempt_record,
    durable_reservation_for_attempt,
    reconcile_attempt_resources,
)
from harnesslab.experiment.evidence import (
    ManifestControlMismatch,
    validate_manifest_against_slot,
)
from harnesslab.experiment.execution import (
    CodexHarnessBinding as CodexHarnessBinding,
)
from harnesslab.experiment.execution import (
    DirectModelBinding as DirectModelBinding,
)
from harnesslab.experiment.execution import (
    ExecutionControlMismatch,
    ExecutionDispatcher,
    ExecutionRequest,
)
from harnesslab.experiment.execution import (
    ExperimentLaneBinding as ExperimentLaneBinding,
)
from harnesslab.experiment.execution import (
    LaneEvidence as LaneEvidence,
)
from harnesslab.experiment.execution import (
    LaneProfile as LaneProfile,
)
from harnesslab.experiment.execution import (
    LaneRunResult as LaneRunResult,
)
from harnesslab.experiment.execution import (
    MultiHarnessBinding as MultiHarnessBinding,
)
from harnesslab.experiment.execution import (
    resolved_comparison_profile_identity as resolved_comparison_profile_identity,
)
from harnesslab.experiment.outcomes import (
    StatisticalOutcome,
    normalize_lane_evidence,
    source_taxonomy_from_lane_evidence,
)
from harnesslab.experiment.queue import (
    TERMINAL_STATUSES,
    AuthoritativeClaimGate,
    ExperimentConflict,
    RunSnapshot,
    claim_next_run,
    finish_run,
    heartbeat_run,
    inspect_run,
    transition_run,
)
from harnesslab.experiment.queue import (
    attempt_execution_id as attempt_execution_id,
)
from harnesslab.experiment.tool_metrics import manifest_tool_calls
from harnesslab.model_lane.models import (
    DirectModelEvidence,
)
from harnesslab.sandbox.artifacts import sha256_file


@dataclass(frozen=True)
class ExecutionMetrics:
    duration_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    tool_calls: int | None
    steps: int | None


def _metrics(evidence: LaneEvidence, manifest_path: Path | None = None) -> ExecutionMetrics:
    if isinstance(evidence, DirectModelEvidence):
        result = evidence.provider_result
        return ExecutionMetrics(
            duration_ms=result.latency_ms if result else None,
            input_tokens=result.usage.input_tokens if result else None,
            output_tokens=result.usage.output_tokens if result else None,
            tool_calls=0,
            steps=1 if result else 0,
        )
    usage = evidence.usage
    return ExecutionMetrics(
        duration_ms=evidence.duration_ms,
        input_tokens=usage.input_tokens if usage else None,
        output_tokens=usage.output_tokens if usage else None,
        tool_calls=manifest_tool_calls(evidence.model_dump(mode="json"), manifest_path),
        steps=evidence.trace_event_count,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _observed(value: int | Decimal | None, unit: str) -> ObservedResourceDimension:
    if value is None:
        return ObservedResourceDimension(
            availability=ResourceAvailability.NOT_AVAILABLE,
            unit=unit,
        )
    return ObservedResourceDimension(
        availability=ResourceAvailability.AVAILABLE,
        value=Decimal(value),
        unit=unit,
    )


def _observed_usage(metrics: ExecutionMetrics | None) -> ObservedResourceUsage:
    return ObservedResourceUsage(
        wall_time=_observed(
            (
                None
                if metrics is None or metrics.duration_ms is None
                else Decimal(metrics.duration_ms) / 1000
            ),
            "seconds",
        ),
        output_tokens=_observed(None if metrics is None else metrics.output_tokens, "tokens"),
        model_turns=_observed(None, "turns"),
        tool_calls=_observed(None if metrics is None else metrics.tool_calls, "calls"),
        provider_requests=_observed(None, "requests"),
        monetary_cost=_observed(None, "USD"),
    )


class ExperimentRunExecutor:
    """Dispatch durable slots through existing lane runners; never reimplements a runner."""

    def __init__(
        self,
        *,
        repository_root: Path,
        session_factory: async_sessionmaker[AsyncSession],
        bindings: Mapping[str, ExperimentLaneBinding],
        owner: str,
        lease_ttl: timedelta = timedelta(minutes=15),
        heartbeat_cadence: timedelta | None = None,
        clock: Callable[[], datetime] = _now,
        authoritative_claim_gate: AuthoritativeClaimGate | None = None,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.session_factory = session_factory
        self.bindings = dict(bindings)
        self.dispatcher = ExecutionDispatcher(self.repository_root, self.bindings)
        self.owner = owner
        self.lease_ttl = lease_ttl
        self.heartbeat_cadence = heartbeat_cadence or lease_ttl / 3
        if self.heartbeat_cadence <= timedelta(0):
            raise ValueError("heartbeat cadence must be positive")
        if self.heartbeat_cadence > lease_ttl / 3:
            raise ValueError("heartbeat cadence must not exceed one third of the lease ttl")
        self.clock = clock
        self.authoritative_claim_gate = authoritative_claim_gate

    async def claim(
        self, experiment_id: str, *, slot_ids: Collection[str] | None = None
    ) -> RunSnapshot | None:
        async with self.session_factory() as session, session.begin():
            if self.authoritative_claim_gate is not None:
                return await self.authoritative_claim_gate.claim(
                    session,
                    experiment_id,
                    self.owner,
                    now=self.clock(),
                    ttl=self.lease_ttl,
                    slot_ids=slot_ids,
                )
            return await claim_next_run(
                session,
                experiment_id,
                self.owner,
                now=self.clock(),
                ttl=self.lease_ttl,
                slot_ids=slot_ids,
            )

    async def _transition(self, claimed: RunSnapshot, status: RunStatus) -> RunSnapshot:
        async with self.session_factory() as session, session.begin():
            return await transition_run(
                session,
                claimed.run_id,
                self.owner,
                status,
                attempt=claimed.attempt,
                now=self.clock(),
            )

    async def _heartbeat(self, claimed: RunSnapshot) -> RunSnapshot:
        async with self.session_factory() as session, session.begin():
            return await heartbeat_run(
                session,
                claimed.run_id,
                self.owner,
                attempt=claimed.attempt,
                now=self.clock(),
                ttl=self.lease_ttl,
            )

    async def _inspect(self, run_id: str) -> RunSnapshot:
        async with self.session_factory() as session:
            return await inspect_run(session, run_id)

    async def _reconcile_terminal(
        self,
        claimed: RunSnapshot,
        *,
        metrics: ExecutionMetrics | None,
        evidence_digest: str | None,
    ) -> ReconciliationReceipt | None:
        if self.authoritative_claim_gate is None:
            return None
        async with self.session_factory() as session, session.begin():
            run = await session.get(ExperimentRunRecord, claimed.run_id, with_for_update=True)
            attempt = await current_attempt_record(session, claimed.run_id, lock=True)
            if attempt is None:
                raise RuntimeError("authoritative execution lost its physical attempt")
            if (
                run is None
                or run.attempt != claimed.attempt
                or attempt.attempt_number != claimed.attempt
            ):
                raise ExperimentConflict("stale claim cannot reconcile another physical attempt")
            reservation = await durable_reservation_for_attempt(session, attempt.attempt_id)
            if reservation is None:
                raise RuntimeError("authoritative execution terminated without a reservation")
            reference = (
                None
                if evidence_digest is None
                else ImmutableArtifactReference(
                    artifact_id=f"attempt-evidence-{attempt.attempt_id.removeprefix('sha256:')[:32]}",
                    schema_version=1,
                    artifact_digest=evidence_digest,
                )
            )
            return await reconcile_attempt_resources(
                session,
                attempt_id=attempt.attempt_id,
                reservation=reservation,
                usage=_observed_usage(metrics),
                evidence_reference=reference,
                now=self.clock(),
            )

    async def _maintain_heartbeat(
        self,
        claimed: RunSnapshot,
        stop: asyncio.Event,
        lost: asyncio.Event,
        cancelled: asyncio.Event,
    ) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.heartbeat_cadence.total_seconds())
                return
            except TimeoutError:
                pass
            try:
                snapshot = await self._heartbeat(claimed)
            except Exception:
                lost.set()
                return
            if snapshot.status is RunStatus.CANCELLED:
                cancelled.set()
                return
            if snapshot.lease_owner != self.owner:
                lost.set()
                return

    async def execute(self, claimed: RunSnapshot) -> RunSnapshot:
        if claimed.status is not RunStatus.CLAIMED or claimed.lease_owner != self.owner:
            raise ValueError("executor requires a run claimed by its own worker identity")
        preparing = await self._transition(claimed, RunStatus.PREPARING)
        if preparing.status is RunStatus.CANCELLED:
            await self._reconcile_terminal(claimed, metrics=None, evidence_digest=None)
            return preparing
        running = await self._transition(claimed, RunStatus.RUNNING)
        if running.status is RunStatus.CANCELLED:
            await self._reconcile_terminal(claimed, metrics=None, evidence_digest=None)
            return running
        result: LaneRunResult | None = None
        error: Exception | None = None
        heartbeat_stop = asyncio.Event()
        heartbeat_lost = asyncio.Event()
        heartbeat_cancelled = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            self._maintain_heartbeat(
                claimed,
                heartbeat_stop,
                heartbeat_lost,
                heartbeat_cancelled,
            )
        )
        try:
            result = await self.dispatcher.execute(
                ExecutionRequest(execution_id=attempt_execution_id(claimed), slot=claimed.slot)
            )
        except Exception as exc:  # durable worker boundary normalizes unexpected infrastructure
            error = exc
        finally:
            heartbeat_stop.set()
            await heartbeat_task

        if heartbeat_lost.is_set() or heartbeat_cancelled.is_set():
            interrupted = await self._inspect(claimed.run_id)
            if self.authoritative_claim_gate is not None and interrupted.status in {
                RunStatus.FAILED_INFRA,
                RunStatus.CANCELLED,
            }:
                await self._reconcile_terminal(
                    claimed,
                    metrics=None if result is None else _metrics(result.evidence),
                    evidence_digest=None,
                )
            return interrupted

        verifying = await self._transition(claimed, RunStatus.VERIFYING)
        if verifying.status is RunStatus.CANCELLED:
            await self._reconcile_terminal(claimed, metrics=None, evidence_digest=None)
            return verifying
        scoring = await self._transition(claimed, RunStatus.SCORING)
        if scoring.status is RunStatus.CANCELLED:
            await self._reconcile_terminal(claimed, metrics=None, evidence_digest=None)
            return scoring
        if result is None:
            return await self._finish_infra(claimed, error)

        evidence = result.evidence
        manifest = result.artifact_directory / "manifest.json"
        outcome = normalize_lane_evidence(evidence)
        source_outcome = source_taxonomy_from_lane_evidence(evidence)
        failure_detail: str | None = None
        authoritative_manifest: str | None = str(manifest)
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("persisted manifest must contain an object")
            facts = load_manifest_facts(
                manifest,
                verifier_control_identity=claimed.slot.task.verifier_identity,
            )
            validate_manifest_against_slot(raw, facts, claimed.slot)
            digest = sha256_file(manifest)
        except ManifestControlMismatch as exc:
            outcome = StatisticalOutcome.INFRA_FAILURE
            source_outcome = "control_identity_mismatch"
            authoritative_manifest = None
            digest = None
            failure_detail = f"CONTROL_IDENTITY_MISMATCH: {','.join(exc.mismatches)}"
        except Exception as exc:
            outcome = StatisticalOutcome.INFRA_FAILURE
            source_outcome = "artifact_validation_error"
            authoritative_manifest = None
            digest = None
            failure_detail = f"persisted manifest validation failed: {type(exc).__name__}"
        metrics = _metrics(evidence, manifest if digest is not None else None)
        reconciliation = await self._reconcile_terminal(
            claimed,
            metrics=metrics,
            evidence_digest=digest,
        )
        if (
            reconciliation is not None
            and reconciliation.status is ReconciliationStatus.ENVELOPE_EXCEEDED
        ):
            return await self._inspect(claimed.run_id)
        async with self.session_factory() as session, session.begin():
            return await finish_run(
                session,
                claimed.run_id,
                self.owner,
                attempt=claimed.attempt,
                now=self.clock(),
                normalized_outcome=outcome,
                source_outcome=source_outcome,
                artifact_manifest_path=authoritative_manifest,
                evidence_digest=digest,
                failure_detail=failure_detail,
                duration_ms=metrics.duration_ms,
                input_tokens=metrics.input_tokens,
                output_tokens=metrics.output_tokens,
                tool_calls=metrics.tool_calls,
                steps=metrics.steps,
            )

    async def _finish_infra(self, claimed: RunSnapshot, error: Exception | None) -> RunSnapshot:
        detail = type(error).__name__ if error is not None else "unknown worker failure"
        await self._reconcile_terminal(claimed, metrics=None, evidence_digest=None)
        async with self.session_factory() as session, session.begin():
            return await finish_run(
                session,
                claimed.run_id,
                self.owner,
                attempt=claimed.attempt,
                now=self.clock(),
                normalized_outcome=StatisticalOutcome.INFRA_FAILURE,
                source_outcome=(
                    "control_identity_mismatch"
                    if isinstance(error, ExecutionControlMismatch)
                    else "worker_infrastructure_error"
                ),
                artifact_manifest_path=None,
                evidence_digest=None,
                failure_detail=detail,
            )

    async def run_until_idle(self, experiment_id: str) -> tuple[RunSnapshot, ...]:
        completed: list[RunSnapshot] = []
        while claimed := await self.claim(experiment_id):
            completed.append(await self.execute(claimed))
        await self._refresh_experiment_status(experiment_id)
        return tuple(completed)

    async def run_bounded(
        self,
        experiment_id: str,
        *,
        max_runs: int,
        concurrency: int = 1,
        slot_ids: Collection[str] | None = None,
    ) -> tuple[RunSnapshot, ...]:
        """Execute at most ``max_runs`` claimable slots with bounded concurrent workers."""

        if max_runs < 1:
            raise ValueError("max_runs must be positive")
        if not 1 <= concurrency <= 8:
            raise ValueError("concurrency must be between 1 and 8")
        reservation_lock = asyncio.Lock()
        reserved = 0
        completed: list[RunSnapshot] = []

        async def worker() -> None:
            nonlocal reserved
            while True:
                async with reservation_lock:
                    if reserved >= max_runs:
                        return
                    claimed = await self.claim(experiment_id, slot_ids=slot_ids)
                    if claimed is None:
                        return
                    reserved += 1
                result = await self.execute(claimed)
                async with reservation_lock:
                    completed.append(result)

        await asyncio.gather(*(worker() for _ in range(min(concurrency, max_runs))))
        await self._refresh_experiment_status(experiment_id)
        return tuple(completed)

    async def _refresh_experiment_status(self, experiment_id: str) -> None:
        async with self.session_factory() as session, session.begin():
            experiment = await session.get(ExperimentRecord, experiment_id, with_for_update=True)
            if experiment is None:
                raise RuntimeError("experiment disappeared while worker was active")
            total, finished, started_at, finished_at = (
                await session.execute(
                    select(
                        func.count(),
                        func.count().filter(ExperimentRunRecord.status.in_(TERMINAL_STATUSES)),
                        func.min(ExperimentRunRecord.started_at),
                        func.max(ExperimentRunRecord.finished_at),
                    ).where(ExperimentRunRecord.experiment_id == experiment_id)
                )
            ).one()
            experiment.started_at = started_at
            if total and total == finished:
                experiment.status = "completed"
                experiment.finished_at = finished_at
            elif started_at is not None:
                experiment.status = "running"
