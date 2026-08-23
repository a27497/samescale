from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.comparability.manifest import load_manifest_facts
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.model import ModelProfile
from harnesslab.contracts.run import RunStatus
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.experiment.outcomes import StatisticalOutcome, normalize_lane_evidence
from harnesslab.experiment.queue import (
    RunSnapshot,
    claim_next_run,
    finish_run,
    transition_run,
)
from harnesslab.harness_lane.adapter import CodexBackend
from harnesslab.harness_lane.models import (
    CodexHarnessProfile,
    HarnessLaneEvidence,
    HarnessLaneRunResult,
    TraceEventType,
)
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.model_lane.models import (
    DirectModelEvidence,
    DirectModelRunResult,
    GenerationSettings,
    ProviderAdapter,
)
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.multi_harness.adapter import MultiHarnessAdapter, MultiHarnessBackend
from harnesslab.multi_harness.models import (
    MultiHarnessEvidence,
    MultiHarnessProfile,
    MultiHarnessRunResult,
)
from harnesslab.multi_harness.runner import MultiHarnessRunner
from harnesslab.sandbox.artifacts import sha256_file

type LaneRunResult = DirectModelRunResult | HarnessLaneRunResult | MultiHarnessRunResult
type LaneEvidence = DirectModelEvidence | HarnessLaneEvidence | MultiHarnessEvidence
type LaneProfile = ModelProfile | CodexHarnessProfile | MultiHarnessProfile


def resolved_comparison_profile_identity(profile: LaneProfile) -> str:
    """Match Phase F manifest extraction without requiring a completed run."""

    if isinstance(profile, ModelProfile):
        generation = GenerationSettings(
            effort=profile.reasoning.effort,
            temperature=profile.reasoning.temperature,
            max_output_tokens=profile.reasoning.max_output_tokens,
            request_timeout_seconds=profile.request_timeout_seconds,
        )
        return canonical_digest(
            {
                "provider": profile.provider,
                "endpoint": f"{profile.base_url}{profile.route}",
                "protocol": profile.protocol.value,
                "generation_settings": generation.model_dump(mode="json"),
            }
        )
    controls = profile.model_dump(mode="json")
    controls.pop("requested_model", None)
    return canonical_digest(controls)


class ExperimentLaneBinding(Protocol):
    async def run(self, task_path: Path, run_id: str) -> LaneRunResult: ...


@dataclass(frozen=True)
class DirectModelBinding:
    runner: DirectModelRunner
    profile: ModelProfile
    provider: ProviderAdapter

    async def run(self, task_path: Path, run_id: str) -> DirectModelRunResult:
        return await self.runner.run(task_path, self.profile, adapter=self.provider, run_id=run_id)


@dataclass(frozen=True)
class CodexHarnessBinding:
    runner: CodexHarnessRunner
    profile: CodexHarnessProfile
    backend: CodexBackend

    async def run(self, task_path: Path, run_id: str) -> HarnessLaneRunResult:
        return await self.runner.run(task_path, self.profile, backend=self.backend, run_id=run_id)


@dataclass(frozen=True)
class MultiHarnessBinding:
    runner: MultiHarnessRunner
    profile: MultiHarnessProfile
    adapter: MultiHarnessAdapter
    backend: MultiHarnessBackend

    async def run(self, task_path: Path, run_id: str) -> MultiHarnessRunResult:
        return await self.runner.run(
            task_path,
            self.profile,
            adapter=self.adapter,
            backend=self.backend,
            run_id=run_id,
        )


@dataclass(frozen=True)
class ExecutionMetrics:
    duration_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    tool_calls: int | None
    steps: int | None


def _metrics(evidence: LaneEvidence) -> ExecutionMetrics:
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
        tool_calls=sum(
            event
            in {
                TraceEventType.COMMAND_EXECUTION,
                TraceEventType.FILE_CHANGE,
                TraceEventType.MCP_TOOL_CALL,
            }
            for event in evidence.trace_event_types
        ),
        steps=evidence.trace_event_count,
    )


def _now() -> datetime:
    return datetime.now(UTC)


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
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.session_factory = session_factory
        self.bindings = dict(bindings)
        self.owner = owner
        self.lease_ttl = lease_ttl
        self.clock = clock

    async def claim(self, experiment_id: str) -> RunSnapshot | None:
        async with self.session_factory() as session, session.begin():
            return await claim_next_run(
                session,
                experiment_id,
                self.owner,
                now=self.clock(),
                ttl=self.lease_ttl,
            )

    async def _transition(self, run_id: str, status: RunStatus) -> RunSnapshot:
        async with self.session_factory() as session, session.begin():
            return await transition_run(session, run_id, self.owner, status, now=self.clock())

    async def execute(self, claimed: RunSnapshot) -> RunSnapshot:
        if claimed.status is not RunStatus.CLAIMED or claimed.lease_owner != self.owner:
            raise ValueError("executor requires a run claimed by its own worker identity")
        binding = self.bindings.get(claimed.cell_id)
        await self._transition(claimed.run_id, RunStatus.PREPARING)
        await self._transition(claimed.run_id, RunStatus.RUNNING)
        result: LaneRunResult | None = None
        error: Exception | None = None
        try:
            if binding is None:
                raise RuntimeError(f"no runner binding for cell {claimed.cell_id}")
            task_path = (self.repository_root / claimed.slot.task.package_path).resolve()
            result = await binding.run(task_path, claimed.run_id)
        except Exception as exc:  # durable worker boundary normalizes unexpected infrastructure
            error = exc

        await self._transition(claimed.run_id, RunStatus.VERIFYING)
        await self._transition(claimed.run_id, RunStatus.SCORING)
        if result is None:
            return await self._finish_infra(claimed.run_id, error)

        evidence = result.evidence
        manifest = result.artifact_directory / "manifest.json"
        outcome = normalize_lane_evidence(evidence)
        failure_detail: str | None = None
        try:
            load_manifest_facts(manifest)
            digest = sha256_file(manifest)
        except Exception as exc:
            outcome = StatisticalOutcome.INFRA_FAILURE
            digest = None
            failure_detail = f"persisted manifest validation failed: {type(exc).__name__}"
        metrics = _metrics(evidence)
        async with self.session_factory() as session, session.begin():
            return await finish_run(
                session,
                claimed.run_id,
                self.owner,
                now=self.clock(),
                normalized_outcome=outcome,
                source_outcome=evidence.outcome.value,
                artifact_manifest_path=str(manifest),
                evidence_digest=digest,
                failure_detail=failure_detail,
                duration_ms=metrics.duration_ms,
                input_tokens=metrics.input_tokens,
                output_tokens=metrics.output_tokens,
                tool_calls=metrics.tool_calls,
                steps=metrics.steps,
            )

    async def _finish_infra(self, run_id: str, error: Exception | None) -> RunSnapshot:
        detail = type(error).__name__ if error is not None else "unknown worker failure"
        async with self.session_factory() as session, session.begin():
            return await finish_run(
                session,
                run_id,
                self.owner,
                now=self.clock(),
                normalized_outcome=StatisticalOutcome.INFRA_FAILURE,
                source_outcome="worker_infrastructure_error",
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

    async def _refresh_experiment_status(self, experiment_id: str) -> None:
        terminal = (
            RunStatus.COMPLETED.value,
            RunStatus.FAILED_INFRA.value,
            RunStatus.FAILED_SUBJECT.value,
            RunStatus.CANCELLED.value,
        )
        async with self.session_factory() as session, session.begin():
            experiment = await session.get(ExperimentRecord, experiment_id, with_for_update=True)
            if experiment is None:
                raise RuntimeError("experiment disappeared while worker was active")
            total, finished, started_at, finished_at = (
                await session.execute(
                    select(
                        func.count(),
                        func.count().filter(ExperimentRunRecord.status.in_(terminal)),
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
