from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import statistics
import tempfile
import time
from collections import Counter
from collections.abc import Collection, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.contracts.run import RunStatus
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.experiment.dispatch import (
    BlockAwareDispatcher,
    DispatchEvent,
    DispatchProfile,
    slot_resource_class,
)
from harnesslab.experiment.methodology import ProviderAvailability
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.plan import MethodologyV2ExperimentPlan
from harnesslab.experiment.queue import (
    RunSnapshot,
    claim_next_run,
    enqueue_plan,
    finish_run,
    heartbeat_run,
    inspect_run,
    request_run_cancellation,
    transition_run,
)

QUALIFIER_LABEL = "com.harnesslab.qualifier"
QUALIFIER_LABEL_VALUE = "kb3-v6-throughput-r2"
CODEX_IMAGE = "harnesslab-phase-e-codex:0.149.0"
CLAUDE_IMAGE = "harnesslab-phase-f-claude:2.1.241"
EXPECTED_LOGICAL_SLOTS = 630
EXPECTED_BLOCKS = 90
RESUME_CUT = 70


class HostTelemetrySample(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    elapsed_seconds: float = Field(ge=0)
    cpu_used_cores: float | None = Field(default=None, ge=0)
    memory_used_bytes: int = Field(ge=0)
    memory_available_bytes: int = Field(ge=0)
    swap_used_bytes: int = Field(ge=0)
    load_1m: float = Field(ge=0)
    load_5m: float = Field(ge=0)
    load_15m: float = Field(ge=0)
    qualifier_containers: int = Field(ge=0)
    host_active_containers: int = Field(ge=0)
    database_connections: int = Field(ge=0)
    process_file_descriptors: int = Field(ge=0)
    host_allocated_file_descriptors: int = Field(ge=0)


class HostTelemetrySummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sample_interval_seconds: float
    sample_count: int
    cpu_count: int
    cpu_peak_cores: float
    cpu_average_cores: float
    memory_baseline_bytes: int
    memory_peak_bytes: int
    memory_peak_delta_bytes: int
    swap_baseline_bytes: int
    swap_peak_bytes: int
    load_1m_peak: float
    load_5m_peak: float
    load_15m_peak: float
    qualifier_container_peak_sampled: int
    host_active_container_peak: int
    database_connection_baseline: int
    database_connection_peak: int
    process_file_descriptor_baseline: int
    process_file_descriptor_peak: int
    host_allocated_file_descriptor_baseline: int
    host_allocated_file_descriptor_peak: int
    collection_errors: tuple[str, ...]
    samples: tuple[HostTelemetrySample, ...]


class TrialSafetyMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    peak_active_workers: int
    peak_harness_workers: int
    peak_direct_workers: int
    peak_provider_concurrency: dict[str, int]
    container_peak_exact: int
    container_churn: int
    heartbeat_count: int
    duplicate_claims: int
    scheduling_violations: int
    provider_cap_violations: int
    lane_cap_violations: int
    workspace_collisions: int
    artifact_collisions: int
    container_identity_collisions: int
    lease_losses: int
    cleanup_failures: int
    security_failures: int
    pipelined_block_transitions: int
    resume_preserved_terminal_slots: int
    terminal_slots: int
    attempts_above_one: int
    resource_pressure_violations: tuple[str, ...]


class QualificationTrial(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    trial_id: str
    profile_id: str
    profile_digest: str
    wall_time_seconds: float
    dispatch_sequence_digest: str
    dispatch_sequence: tuple[str, ...]
    completion_count: int
    safety: TrialSafetyMetrics
    host_telemetry: HostTelemetrySummary
    hard_checks_passed: bool


class ProfileQualification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: dict[str, Any]
    profile_digest: str
    trials: tuple[QualificationTrial, ...]
    median_wall_time_seconds: float
    logical_dispatch_reproduced: bool
    hard_checks_passed: bool


class CancellationProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    cancellation_observed: bool
    heartbeat_count: int
    lease_losses: int
    cleanup_failures: int
    remaining_containers: int
    workspace_cleaned: bool
    passed: bool


class QualificationSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selected_profile_id: str
    selected_profile_digest: str
    selection_rule: str
    b_improvement_over_a_percent: float
    c_improvement_over_b_percent: float
    c_improvement_over_a_percent: float
    minimum_higher_profile_improvement_percent: float
    reason: str


class ThroughputR2Qualification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    evidence_class: str = "REAL_LOCAL_HOST_TELEMETRY_KEYLESS_WORKLOAD"
    profiles: tuple[ProfileQualification, ...]
    cancellation_probe: CancellationProbe
    selection: QualificationSelection
    docker_images: dict[str, str]
    database_identity_digest: str
    external_call_counts: dict[str, int]


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: str
    stderr: str


async def _command(*argv: str, timeout_seconds: float = 30.0) -> _CommandResult:
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError(f"bounded local command timed out: {argv[0]}") from None
    decoded_stdout = stdout.decode(errors="replace")
    decoded_stderr = stderr.decode(errors="replace")
    if process.returncode != 0:
        bounded = decoded_stderr.strip()[:500]
        raise RuntimeError(f"local command failed ({argv[0]}): {bounded}")
    return _CommandResult(process.returncode or 0, decoded_stdout, decoded_stderr)


def _canonical_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_memory() -> tuple[int, int, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, raw = line.split(":", 1)
        if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
            values[key] = int(raw.strip().split()[0]) * 1024
    used = values["MemTotal"] - values["MemAvailable"]
    swap_used = values["SwapTotal"] - values["SwapFree"]
    return used, values["MemAvailable"], swap_used


def _read_cpu() -> tuple[int, int]:
    fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
    values = [int(value) for value in fields]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def _read_host_allocated_fds() -> int:
    return int(Path("/proc/sys/fs/file-nr").read_text(encoding="utf-8").split()[0])


class HostTelemetryMonitor:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        sample_interval_seconds: float = 0.25,
    ) -> None:
        self.session_factory = session_factory
        self.sample_interval_seconds = sample_interval_seconds
        self.samples: list[HostTelemetrySample] = []
        self.errors: list[str] = []
        self._started = time.monotonic()
        self._previous_cpu: tuple[int, int] | None = None

    async def _container_counts(self) -> tuple[int, int]:
        qualifier = await _command(
            "docker",
            "ps",
            "--quiet",
            "--filter",
            f"label={QUALIFIER_LABEL}={QUALIFIER_LABEL_VALUE}",
        )
        total = await _command("docker", "ps", "--quiet")
        return (
            len([line for line in qualifier.stdout.splitlines() if line]),
            len([line for line in total.stdout.splitlines() if line]),
        )

    async def sample(self) -> None:
        try:
            cpu_total, cpu_idle = _read_cpu()
            cpu_used: float | None = None
            if self._previous_cpu is not None:
                total_delta = cpu_total - self._previous_cpu[0]
                idle_delta = cpu_idle - self._previous_cpu[1]
                if total_delta > 0:
                    cpu_used = os.cpu_count() or 1
                    cpu_used *= max(0.0, min(1.0, 1.0 - idle_delta / total_delta))
            self._previous_cpu = (cpu_total, cpu_idle)
            memory_used, memory_available, swap_used = _read_memory()
            load_1m, load_5m, load_15m = os.getloadavg()
            qualifier_containers, active_containers = await self._container_counts()
            async with self.session_factory() as session:
                connections = int(
                    await session.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()"
                        )
                    )
                    or 0
                )
            self.samples.append(
                HostTelemetrySample(
                    elapsed_seconds=round(time.monotonic() - self._started, 6),
                    cpu_used_cores=None if cpu_used is None else round(cpu_used, 6),
                    memory_used_bytes=memory_used,
                    memory_available_bytes=memory_available,
                    swap_used_bytes=swap_used,
                    load_1m=load_1m,
                    load_5m=load_5m,
                    load_15m=load_15m,
                    qualifier_containers=qualifier_containers,
                    host_active_containers=active_containers,
                    database_connections=connections,
                    process_file_descriptors=len(tuple(Path("/proc/self/fd").iterdir())),
                    host_allocated_file_descriptors=_read_host_allocated_fds(),
                )
            )
        except Exception as exc:
            self.errors.append(type(exc).__name__)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.sample()
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.sample_interval_seconds)
        await self.sample()

    def summary(self) -> HostTelemetrySummary:
        if not self.samples:
            raise RuntimeError("host telemetry produced zero samples")
        cpu_values = [
            item.cpu_used_cores for item in self.samples if item.cpu_used_cores is not None
        ]
        first = self.samples[0]
        memory_peak = max(item.memory_used_bytes for item in self.samples)
        return HostTelemetrySummary(
            sample_interval_seconds=self.sample_interval_seconds,
            sample_count=len(self.samples),
            cpu_count=os.cpu_count() or 1,
            cpu_peak_cores=round(max(cpu_values, default=0.0), 6),
            cpu_average_cores=round(statistics.fmean(cpu_values) if cpu_values else 0.0, 6),
            memory_baseline_bytes=first.memory_used_bytes,
            memory_peak_bytes=memory_peak,
            memory_peak_delta_bytes=max(0, memory_peak - first.memory_used_bytes),
            swap_baseline_bytes=first.swap_used_bytes,
            swap_peak_bytes=max(item.swap_used_bytes for item in self.samples),
            load_1m_peak=max(item.load_1m for item in self.samples),
            load_5m_peak=max(item.load_5m for item in self.samples),
            load_15m_peak=max(item.load_15m for item in self.samples),
            qualifier_container_peak_sampled=max(
                item.qualifier_containers for item in self.samples
            ),
            host_active_container_peak=max(item.host_active_containers for item in self.samples),
            database_connection_baseline=first.database_connections,
            database_connection_peak=max(item.database_connections for item in self.samples),
            process_file_descriptor_baseline=first.process_file_descriptors,
            process_file_descriptor_peak=max(
                item.process_file_descriptors for item in self.samples
            ),
            host_allocated_file_descriptor_baseline=first.host_allocated_file_descriptors,
            host_allocated_file_descriptor_peak=max(
                item.host_allocated_file_descriptors for item in self.samples
            ),
            collection_errors=tuple(self.errors),
            samples=tuple(self.samples),
        )


@dataclass(frozen=True)
class _WorkEvidence:
    artifact_path: str
    evidence_digest: str


class LocalKeylessWorkload:
    """Filesystem and network-none Docker work with collision and cleanup accounting."""

    def __init__(self, root: Path, trial_id: str) -> None:
        self.root = root.resolve()
        self.trial_id = trial_id
        self.workspace_root = self.root / "workspaces"
        self.artifact_root = self.root / "artifacts"
        self.workspace_root.mkdir(parents=True)
        self.artifact_root.mkdir(parents=True)
        self.workspace_collisions = 0
        self.artifact_collisions = 0
        self.container_identity_collisions = 0
        self.cleanup_failures = 0
        self.security_failures = 0
        self.container_churn = 0
        self.container_peak = 0
        self._active_containers = 0
        self._seen_workspaces: set[str] = set()
        self._seen_artifacts: set[str] = set()
        self._seen_containers: set[str] = set()
        self._lock = asyncio.Lock()
        self.started: dict[str, asyncio.Event] = {}

    async def _register_path(self, slot_id: str, *, artifact: bool) -> Path:
        token = slot_id.removeprefix("sha256:")
        base = self.artifact_root if artifact else self.workspace_root
        seen = self._seen_artifacts if artifact else self._seen_workspaces
        async with self._lock:
            if token in seen:
                if artifact:
                    self.artifact_collisions += 1
                else:
                    self.workspace_collisions += 1
                raise RuntimeError("qualification path identity collided")
            seen.add(token)
        path = base / token
        try:
            path.mkdir()
        except FileExistsError:
            if artifact:
                self.artifact_collisions += 1
            else:
                self.workspace_collisions += 1
            raise RuntimeError("qualification path already exists") from None
        return path

    async def _register_container(self, name: str) -> None:
        async with self._lock:
            if name in self._seen_containers:
                self.container_identity_collisions += 1
                raise RuntimeError("qualification container identity collided")
            self._seen_containers.add(name)

    async def _container_started(self) -> None:
        async with self._lock:
            self._active_containers += 1
            self.container_churn += 1
            self.container_peak = max(self.container_peak, self._active_containers)

    async def _container_stopped(self) -> None:
        async with self._lock:
            self._active_containers -= 1

    @staticmethod
    def _payload(slot_id: str) -> bytes:
        seed = hashlib.sha256(slot_id.encode()).digest()
        return (seed * (65536 // len(seed) + 1))[:65536]

    @staticmethod
    def _container_name(trial_id: str, slot_id: str) -> str:
        trial = hashlib.sha256(trial_id.encode()).hexdigest()[:8]
        slot = hashlib.sha256(slot_id.encode()).hexdigest()[:16]
        return f"hl-v6r2-{trial}-{slot}"

    async def _run_container(self, slot: RunSnapshot) -> None:
        image = CODEX_IMAGE if slot.slot.harness == "codex" else CLAUDE_IMAGE
        name = self._container_name(self.trial_id, slot.slot_id)
        await self._register_container(name)
        exists = await asyncio.create_subprocess_exec(
            "docker",
            "container",
            "inspect",
            name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await exists.wait()
        if exists.returncode == 0:
            self.container_identity_collisions += 1
            raise RuntimeError("qualification container already exists")
        sleep_seconds = {
            "harness-codex-gpt56-medium": "0.09",
            "harness-codex-gpt56-high": "0.13",
            "harness-claude-qwen38-alibaba-bailian": "0.07",
        }[slot.cell_id]
        created = False
        counted_active = False
        try:
            await _command(
                "docker",
                "create",
                "--name",
                name,
                "--label",
                f"{QUALIFIER_LABEL}={QUALIFIER_LABEL_VALUE}",
                "--label",
                f"com.harnesslab.qualifier.trial={self.trial_id}",
                "--network",
                "none",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=32m",
                "--cpus",
                "2",
                "--memory",
                "1g",
                "--pids-limit",
                "64",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges=true",
                "--restart",
                "no",
                "--entrypoint",
                "/bin/sh",
                image,
                "-c",
                (
                    "dd if=/dev/zero of=/tmp/payload bs=1M count=8 >/dev/null 2>&1; "
                    "sha256sum /tmp/payload >/dev/null; "
                    f"sleep {sleep_seconds}"
                ),
            )
            created = True
            inspection = await _command(
                "docker",
                "inspect",
                name,
                "--format",
                (
                    "{{.HostConfig.NetworkMode}}|{{.HostConfig.ReadonlyRootfs}}|"
                    "{{.HostConfig.Privileged}}|{{json .HostConfig.CapDrop}}|"
                    "{{json .HostConfig.SecurityOpt}}|{{.HostConfig.Memory}}|"
                    "{{.HostConfig.NanoCpus}}"
                ),
            )
            fields = inspection.stdout.strip().split("|")
            expected = (
                len(fields) == 7
                and fields[0] == "none"
                and fields[1].lower() == "true"
                and fields[2].lower() == "false"
                and "ALL" in fields[3]
                and "no-new-privileges" in fields[4]
                and int(fields[5]) == 1_073_741_824
                and int(fields[6]) == 2_000_000_000
            )
            if not expected:
                self.security_failures += 1
                raise RuntimeError("qualification container security attestation failed")
            await _command("docker", "start", name)
            await self._container_started()
            counted_active = True
            completed = await _command("docker", "wait", name, timeout_seconds=20)
            if completed.stdout.strip() != "0":
                raise RuntimeError("qualification container returned a non-zero exit code")
        finally:
            if created:
                try:
                    await _command("docker", "rm", "--force", name)
                    check = await asyncio.create_subprocess_exec(
                        "docker",
                        "container",
                        "inspect",
                        name,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await check.wait()
                    if check.returncode == 0:
                        self.cleanup_failures += 1
                except Exception:
                    self.cleanup_failures += 1
                    with suppress(Exception):
                        await _command("docker", "rm", "--force", name)
            if counted_active:
                await self._container_stopped()

    async def run(self, claimed: RunSnapshot) -> _WorkEvidence:
        workspace = await self._register_path(claimed.slot_id, artifact=False)
        artifact = await self._register_path(claimed.slot_id, artifact=True)
        self.started.setdefault(claimed.slot_id, asyncio.Event()).set()
        try:
            payload = self._payload(claimed.slot_id)
            await asyncio.to_thread((workspace / "input.bin").write_bytes, payload)
            observed = await asyncio.to_thread((workspace / "input.bin").read_bytes)
            if observed != payload:
                raise RuntimeError("qualification filesystem round trip drifted")
            if claimed.slot.harness != "direct-model":
                await self._run_container(claimed)
            else:
                delay = 0.012 + (int(claimed.slot_id[-2:], 16) % 7) * 0.002
                await asyncio.sleep(delay)
            response = {
                "schema_version": 1,
                "slot_id": claimed.slot_id,
                "cell_id": claimed.cell_id,
                "provider_route": claimed.slot.provider_route,
                "result": "KEYLESS_LOCAL_PASS",
                "payload_sha256": "sha256:" + hashlib.sha256(observed).hexdigest(),
            }
            encoded = json.dumps(response, sort_keys=True, separators=(",", ":")).encode()
            output = artifact / "evidence.json"
            await asyncio.to_thread(output.write_bytes, encoded)
            reread = await asyncio.to_thread(output.read_bytes)
            digest = "sha256:" + hashlib.sha256(reread).hexdigest()
            if reread != encoded:
                raise RuntimeError("qualification artifact round trip drifted")
            return _WorkEvidence(
                artifact_path=output.relative_to(self.root).as_posix(),
                evidence_digest=digest,
            )
        finally:
            try:
                await asyncio.to_thread(shutil.rmtree, workspace)
            except Exception:
                self.cleanup_failures += 1
            if workspace.exists():
                self.cleanup_failures += 1

    async def remaining_containers(self) -> int:
        result = await _command(
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--filter",
            f"label={QUALIFIER_LABEL}={QUALIFIER_LABEL_VALUE}",
            "--filter",
            f"label=com.harnesslab.qualifier.trial={self.trial_id}",
        )
        return len([line for line in result.stdout.splitlines() if line])


class QualificationExecutor:
    """Durable local executor with the same queue lifecycle and heartbeat primitives."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        workload: LocalKeylessWorkload,
        profile: DispatchProfile,
        owner: str,
        lease_ttl: timedelta = timedelta(seconds=5),
        heartbeat_cadence: timedelta = timedelta(milliseconds=100),
    ) -> None:
        self.session_factory = session_factory
        self.workload = workload
        self.profile = profile
        self.owner = owner
        self.lease_ttl = lease_ttl
        self.heartbeat_cadence = heartbeat_cadence
        self.heartbeat_count = 0
        self.lease_losses = 0
        self.provider_cap_violations = 0
        self.lane_cap_violations = 0
        self.peak_active_workers = 0
        self.peak_harness_workers = 0
        self.peak_direct_workers = 0
        self.peak_provider_concurrency: Counter[str] = Counter()
        self._active: dict[str, tuple[str, str]] = {}
        self._lock = asyncio.Lock()

    async def claim(
        self,
        experiment_id: str,
        *,
        slot_ids: Collection[str] | None = None,
    ) -> RunSnapshot | None:
        async with self.session_factory() as session, session.begin():
            return await claim_next_run(
                session,
                experiment_id,
                self.owner,
                now=datetime.now(UTC),
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
                now=datetime.now(UTC),
            )

    async def _inspect(self, run_id: str) -> RunSnapshot:
        async with self.session_factory() as session:
            return await inspect_run(session, run_id)

    async def _heartbeat(
        self,
        claimed: RunSnapshot,
        stop: asyncio.Event,
        lease_lost: asyncio.Event,
        cancelled: asyncio.Event,
    ) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=self.heartbeat_cadence.total_seconds(),
                )
                return
            except TimeoutError:
                pass
            try:
                async with self.session_factory() as session, session.begin():
                    snapshot = await heartbeat_run(
                        session,
                        claimed.run_id,
                        self.owner,
                        attempt=claimed.attempt,
                        now=datetime.now(UTC),
                        ttl=self.lease_ttl,
                    )
                self.heartbeat_count += 1
            except Exception:
                self.lease_losses += 1
                lease_lost.set()
                return
            if snapshot.status is RunStatus.CANCELLED:
                cancelled.set()
                return

    async def _activate(self, claimed: RunSnapshot) -> None:
        resource = slot_resource_class(claimed.slot)
        async with self._lock:
            self._active[claimed.slot_id] = (resource.lane_class, resource.provider_id)
            lane_counts = Counter(lane for lane, _ in self._active.values())
            provider_counts = Counter(provider for _, provider in self._active.values())
            self.peak_active_workers = max(self.peak_active_workers, len(self._active))
            self.peak_harness_workers = max(
                self.peak_harness_workers,
                lane_counts["harness"],
            )
            self.peak_direct_workers = max(self.peak_direct_workers, lane_counts["direct"])
            for provider, count in provider_counts.items():
                self.peak_provider_concurrency[provider] = max(
                    self.peak_provider_concurrency[provider],
                    count,
                )
                if count > self.profile.provider_concurrency[provider]:
                    self.provider_cap_violations += 1
            if lane_counts["harness"] > self.profile.max_harness_concurrency:
                self.lane_cap_violations += 1
            if lane_counts["direct"] > self.profile.max_direct_concurrency:
                self.lane_cap_violations += 1
            if len(self._active) > self.profile.global_concurrency:
                self.lane_cap_violations += 1

    async def _deactivate(self, slot_id: str) -> None:
        async with self._lock:
            self._active.pop(slot_id, None)

    async def execute(self, claimed: RunSnapshot) -> RunSnapshot:
        if claimed.status is not RunStatus.CLAIMED or claimed.lease_owner != self.owner:
            raise ValueError("qualification executor requires its own live claim")
        await self._activate(claimed)
        heartbeat_stop = asyncio.Event()
        lease_lost = asyncio.Event()
        cancelled = asyncio.Event()
        heartbeat_task: asyncio.Task[None] | None = None
        started = time.monotonic()
        try:
            preparing = await self._transition(claimed, RunStatus.PREPARING)
            if preparing.status is RunStatus.CANCELLED:
                return preparing
            running = await self._transition(claimed, RunStatus.RUNNING)
            if running.status is RunStatus.CANCELLED:
                return running
            heartbeat_task = asyncio.create_task(
                self._heartbeat(
                    claimed,
                    heartbeat_stop,
                    lease_lost,
                    cancelled,
                )
            )
            evidence = await self.workload.run(claimed)
            heartbeat_stop.set()
            await heartbeat_task
            if lease_lost.is_set() or cancelled.is_set():
                return await self._inspect(claimed.run_id)
            verifying = await self._transition(claimed, RunStatus.VERIFYING)
            if verifying.status is RunStatus.CANCELLED:
                return verifying
            scoring = await self._transition(claimed, RunStatus.SCORING)
            if scoring.status is RunStatus.CANCELLED:
                return scoring
            async with self.session_factory() as session, session.begin():
                return await finish_run(
                    session,
                    claimed.run_id,
                    self.owner,
                    attempt=claimed.attempt,
                    now=datetime.now(UTC),
                    normalized_outcome=StatisticalOutcome.CAPABILITY_PASS,
                    source_outcome="keyless_local_throughput_qualification",
                    artifact_manifest_path=evidence.artifact_path,
                    evidence_digest=evidence.evidence_digest,
                    duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                    input_tokens=0,
                    output_tokens=0,
                    tool_calls=0,
                    steps=1,
                )
        finally:
            heartbeat_stop.set()
            if heartbeat_task is not None and not heartbeat_task.done():
                await heartbeat_task
            await self._deactivate(claimed.slot_id)


def _derived_plan(
    plan: MethodologyV2ExperimentPlan,
    experiment_id: str,
) -> MethodologyV2ExperimentPlan:
    if (
        len(plan.run_slots) != EXPECTED_LOGICAL_SLOTS
        or len(plan.schedule_blocks) != EXPECTED_BLOCKS
    ):
        raise ValueError("qualification requires the exact frozen V6 topology")
    if any(
        block.provider_availability is not ProviderAvailability.AVAILABLE
        for block in plan.schedule_blocks
    ):
        raise ValueError("qualification plan contains an unavailable block")
    return plan.model_copy(
        update={
            "experiment_id": experiment_id,
            "name": f"HarnessLab V6 local throughput qualification {experiment_id}",
        }
    )


async def _delete_experiment(
    factory: async_sessionmaker[AsyncSession],
    experiment_id: str,
) -> None:
    async with factory() as session, session.begin():
        await session.execute(delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id))


def _scheduling_violations(
    plan: MethodologyV2ExperimentPlan,
    events: Sequence[DispatchEvent],
) -> int:
    block_by_slot = {
        slot_id: index
        for index, block in enumerate(plan.schedule_blocks)
        for slot_id in block.slot_ids
    }
    seen: Counter[int] = Counter()
    violations = 0
    for event in events:
        index = block_by_slot[event.slot_id]
        if any(seen[prior] != 7 for prior in range(index)):
            violations += 1
        seen[index] += 1
    return violations


def _pipelined_transitions(
    plan: MethodologyV2ExperimentPlan,
    events: Sequence[DispatchEvent],
    completed: Sequence[RunSnapshot],
) -> int:
    claims = {event.slot_id: event.claimed_at for event in events}
    finishes = {
        snapshot.slot_id: snapshot.heartbeat_at
        for snapshot in completed
        if snapshot.heartbeat_at is not None
    }
    pipelined = 0
    for prior, following in zip(plan.schedule_blocks, plan.schedule_blocks[1:], strict=False):
        prior_finishes = [finishes[item] for item in prior.slot_ids if item in finishes]
        following_claims = [claims[item] for item in following.slot_ids if item in claims]
        if prior_finishes and following_claims and min(following_claims) < max(prior_finishes):
            pipelined += 1
    return pipelined


async def run_qualification_trial(
    plan: MethodologyV2ExperimentPlan,
    profile: DispatchProfile,
    factory: async_sessionmaker[AsyncSession],
    *,
    trial_id: str,
    root: Path,
) -> QualificationTrial:
    experiment_id = f"kb3-v6-throughput-r2-{profile.profile_id.lower()}-{trial_id}"
    qualified_plan = _derived_plan(plan, experiment_id)
    await _delete_experiment(factory, experiment_id)
    workload = LocalKeylessWorkload(root, trial_id)
    executor = QualificationExecutor(
        session_factory=factory,
        workload=workload,
        profile=profile,
        owner=f"v6-r2-{profile.profile_id.lower()}-{trial_id}",
    )
    async with factory() as session, session.begin():
        await enqueue_plan(session, qualified_plan)
    telemetry = HostTelemetryMonitor(factory)
    telemetry_stop = asyncio.Event()
    telemetry_task = asyncio.create_task(telemetry.run(telemetry_stop))
    events: list[DispatchEvent] = []
    completed: list[RunSnapshot] = []
    started = time.monotonic()
    try:
        first_dispatcher = BlockAwareDispatcher(
            executor=executor,
            plan=qualified_plan,
            profile=profile,
        )
        first = await first_dispatcher.run(max_runs=RESUME_CUT)
        events.extend(first.events)
        completed.extend(first.completed)
        if len(first.completed) != RESUME_CUT:
            raise RuntimeError("qualification resume cut did not become terminal")
        first_terminal = {item.slot_id for item in first.completed}
        resumed_executor = QualificationExecutor(
            session_factory=factory,
            workload=workload,
            profile=profile,
            owner=f"v6-r2-{profile.profile_id.lower()}-{trial_id}-resume",
        )
        resumed_dispatcher = BlockAwareDispatcher(
            executor=resumed_executor,
            plan=qualified_plan,
            profile=profile,
        )
        resumed = await resumed_dispatcher.run(max_runs=EXPECTED_LOGICAL_SLOTS - RESUME_CUT)
        events.extend(resumed.events)
        completed.extend(resumed.completed)
        overlap = first_terminal & {event.slot_id for event in resumed.events}
        resume_preserved = len(first_terminal) - len(overlap)
        executor.heartbeat_count += resumed_executor.heartbeat_count
        executor.lease_losses += resumed_executor.lease_losses
        executor.provider_cap_violations += resumed_executor.provider_cap_violations
        executor.lane_cap_violations += resumed_executor.lane_cap_violations
        executor.peak_active_workers = max(
            executor.peak_active_workers,
            resumed_executor.peak_active_workers,
        )
        executor.peak_harness_workers = max(
            executor.peak_harness_workers,
            resumed_executor.peak_harness_workers,
        )
        executor.peak_direct_workers = max(
            executor.peak_direct_workers,
            resumed_executor.peak_direct_workers,
        )
        for provider, count in resumed_executor.peak_provider_concurrency.items():
            executor.peak_provider_concurrency[provider] = max(
                executor.peak_provider_concurrency[provider],
                count,
            )
        async with factory() as session:
            rows = (
                await session.execute(
                    select(
                        ExperimentRunRecord.slot_id,
                        ExperimentRunRecord.status,
                        ExperimentRunRecord.attempt,
                    ).where(ExperimentRunRecord.experiment_id == experiment_id)
                )
            ).all()
        wall_time = time.monotonic() - started
    except BaseException:
        await _delete_experiment(factory, experiment_id)
        raise
    finally:
        telemetry_stop.set()
        await telemetry_task
    sequence = tuple(event.slot_id for event in events)
    terminal_slots = sum(
        status in {RunStatus.COMPLETED.value, RunStatus.FAILED_SUBJECT.value}
        for _, status, _ in rows
    )
    attempts_above_one = sum(attempt > 1 for _, _, attempt in rows)
    duplicate_claims = len(sequence) - len(set(sequence))
    scheduling_violations = _scheduling_violations(qualified_plan, events)
    remaining_containers = await workload.remaining_containers()
    if remaining_containers:
        workload.cleanup_failures += remaining_containers
    safety = TrialSafetyMetrics(
        peak_active_workers=executor.peak_active_workers,
        peak_harness_workers=executor.peak_harness_workers,
        peak_direct_workers=executor.peak_direct_workers,
        peak_provider_concurrency=dict(sorted(executor.peak_provider_concurrency.items())),
        container_peak_exact=workload.container_peak,
        container_churn=workload.container_churn,
        heartbeat_count=executor.heartbeat_count,
        duplicate_claims=duplicate_claims,
        scheduling_violations=scheduling_violations,
        provider_cap_violations=executor.provider_cap_violations,
        lane_cap_violations=executor.lane_cap_violations,
        workspace_collisions=workload.workspace_collisions,
        artifact_collisions=workload.artifact_collisions,
        container_identity_collisions=workload.container_identity_collisions,
        lease_losses=executor.lease_losses,
        cleanup_failures=workload.cleanup_failures,
        security_failures=workload.security_failures,
        pipelined_block_transitions=_pipelined_transitions(
            qualified_plan,
            events,
            completed,
        ),
        resume_preserved_terminal_slots=resume_preserved,
        terminal_slots=terminal_slots,
        attempts_above_one=attempts_above_one,
        resource_pressure_violations=(),
    )
    summary = telemetry.summary()
    first_sample = summary.samples[0]
    memory_total = first_sample.memory_used_bytes + first_sample.memory_available_bytes
    resource_violations: list[str] = []
    if summary.cpu_average_cores > summary.cpu_count * 0.8:
        resource_violations.append("sustained_cpu_above_80_percent")
    if summary.memory_peak_bytes > memory_total * 0.9:
        resource_violations.append("memory_used_above_90_percent")
    if summary.swap_peak_bytes > summary.swap_baseline_bytes + 64 * 1024 * 1024:
        resource_violations.append("swap_growth_above_64_mib")
    if summary.load_1m_peak > summary.cpu_count * 1.25:
        resource_violations.append("load_1m_above_125_percent_cpu_count")
    if summary.database_connection_peak > (
        summary.database_connection_baseline + profile.global_concurrency + 3
    ):
        resource_violations.append("database_connection_growth_exceeded_bound")
    if summary.process_file_descriptor_peak > (
        summary.process_file_descriptor_baseline + profile.global_concurrency * 8 + 32
    ):
        resource_violations.append("qualifier_file_descriptor_growth_exceeded_bound")
    if summary.host_allocated_file_descriptor_peak > (
        summary.host_allocated_file_descriptor_baseline + 4096
    ):
        resource_violations.append("host_file_descriptor_growth_above_4096")
    if workload.container_peak > profile.max_harness_concurrency:
        resource_violations.append("container_peak_exceeded_harness_cap")
    safety = safety.model_copy(update={"resource_pressure_violations": tuple(resource_violations)})
    hard_checks = (
        len(sequence) == EXPECTED_LOGICAL_SLOTS
        and len(completed) == EXPECTED_LOGICAL_SLOTS
        and terminal_slots == EXPECTED_LOGICAL_SLOTS
        and safety.duplicate_claims == 0
        and safety.scheduling_violations == 0
        and safety.provider_cap_violations == 0
        and safety.lane_cap_violations == 0
        and safety.workspace_collisions == 0
        and safety.artifact_collisions == 0
        and safety.container_identity_collisions == 0
        and safety.lease_losses == 0
        and safety.cleanup_failures == 0
        and safety.security_failures == 0
        and safety.resume_preserved_terminal_slots == RESUME_CUT
        and safety.attempts_above_one == 0
        and safety.heartbeat_count > 0
        and not summary.collection_errors
        and not safety.resource_pressure_violations
    )
    result = QualificationTrial(
        trial_id=trial_id,
        profile_id=profile.profile_id,
        profile_digest=profile.digest,
        wall_time_seconds=round(wall_time, 6),
        dispatch_sequence_digest=_canonical_digest(sequence),
        dispatch_sequence=sequence,
        completion_count=len(completed),
        safety=safety,
        host_telemetry=summary,
        hard_checks_passed=hard_checks,
    )
    await _delete_experiment(factory, experiment_id)
    return result


async def qualify_profile(
    plan: MethodologyV2ExperimentPlan,
    profile: DispatchProfile,
    factory: async_sessionmaker[AsyncSession],
    *,
    root: Path,
    repetitions: int = 2,
) -> ProfileQualification:
    if repetitions < 2:
        raise ValueError("profile qualification requires at least two reproducibility trials")
    trials: list[QualificationTrial] = []
    for index in range(repetitions):
        trial_id = f"{profile.profile_id.lower()}-r{index + 1}"
        trial_root = root / trial_id
        trial_root.mkdir()
        trials.append(
            await run_qualification_trial(
                plan,
                profile,
                factory,
                trial_id=trial_id,
                root=trial_root,
            )
        )
    dispatch_reproduced = len({item.dispatch_sequence_digest for item in trials}) == 1
    return ProfileQualification(
        profile=profile.model_dump(mode="json"),
        profile_digest=profile.digest,
        trials=tuple(trials),
        median_wall_time_seconds=round(
            statistics.median(item.wall_time_seconds for item in trials),
            6,
        ),
        logical_dispatch_reproduced=dispatch_reproduced,
        hard_checks_passed=dispatch_reproduced and all(item.hard_checks_passed for item in trials),
    )


async def run_cancellation_probe(
    plan: MethodologyV2ExperimentPlan,
    profile: DispatchProfile,
    factory: async_sessionmaker[AsyncSession],
    *,
    root: Path,
) -> CancellationProbe:
    experiment_id = "kb3-v6-throughput-r2-cancellation-probe"
    qualified_plan = _derived_plan(plan, experiment_id)
    await _delete_experiment(factory, experiment_id)
    workload = LocalKeylessWorkload(root, "cancellation-probe")
    executor = QualificationExecutor(
        session_factory=factory,
        workload=workload,
        profile=profile,
        owner="v6-r2-cancellation-probe",
        heartbeat_cadence=timedelta(milliseconds=50),
    )
    async with factory() as session, session.begin():
        await enqueue_plan(session, qualified_plan)
    harness_slot = next(slot for slot in qualified_plan.run_slots if slot.harness != "direct-model")
    claimed = await executor.claim(experiment_id, slot_ids=(harness_slot.slot_id,))
    if claimed is None:
        raise RuntimeError("cancellation probe could not claim its exact Harness slot")
    execution = asyncio.create_task(executor.execute(claimed))
    started = workload.started.setdefault(claimed.slot_id, asyncio.Event())
    await asyncio.wait_for(started.wait(), timeout=5)
    async with factory() as session, session.begin():
        await request_run_cancellation(session, claimed.run_id, now=datetime.now(UTC))
    result = await asyncio.wait_for(execution, timeout=30)
    remaining = await workload.remaining_containers()
    workspace = workload.workspace_root / claimed.slot_id.removeprefix("sha256:")
    passed = (
        result.status is RunStatus.CANCELLED
        and result.normalized_outcome is StatisticalOutcome.CANCELLED
        and executor.heartbeat_count > 0
        and executor.lease_losses == 0
        and workload.cleanup_failures == 0
        and remaining == 0
        and not workspace.exists()
    )
    probe = CancellationProbe(
        status=result.status.value,
        cancellation_observed=result.status is RunStatus.CANCELLED,
        heartbeat_count=executor.heartbeat_count,
        lease_losses=executor.lease_losses,
        cleanup_failures=workload.cleanup_failures,
        remaining_containers=remaining,
        workspace_cleaned=not workspace.exists(),
        passed=passed,
    )
    await _delete_experiment(factory, experiment_id)
    return probe


def _improvement(lower: ProfileQualification, higher: ProfileQualification) -> float:
    if lower.median_wall_time_seconds <= 0:
        raise ValueError("lower profile has a non-positive wall time")
    return (
        100
        * (lower.median_wall_time_seconds - higher.median_wall_time_seconds)
        / lower.median_wall_time_seconds
    )


def select_qualified_profile(
    profiles: Sequence[ProfileQualification],
    *,
    minimum_improvement_percent: float = 10.0,
) -> QualificationSelection:
    by_id = {str(item.profile["profile_id"]): item for item in profiles}
    a = by_id["V6_PROFILE_A_C4"]
    b = by_id["V6_PROFILE_B_C6"]
    c = by_id["V6_PROFILE_C_C6_H3"]
    b_over_a = _improvement(a, b)
    c_over_b = _improvement(b, c)
    c_over_a = _improvement(a, c)
    selected = a
    reason = "Profile A is the simplest qualified profile; higher profiles missed the 10% gate."
    if b.hard_checks_passed and a.hard_checks_passed and b_over_a >= minimum_improvement_percent:
        selected = b
        reason = "Profile B passed every hard check and improved at least 10% over Profile A."
    if (
        c.hard_checks_passed
        and b.hard_checks_passed
        and a.hard_checks_passed
        and c_over_b >= minimum_improvement_percent
        and c_over_a >= minimum_improvement_percent
    ):
        selected = c
        reason = (
            "Profile C passed every hard check and improved at least 10% over both "
            "the same-global H=2 profile and Profile A."
        )
    if not a.hard_checks_passed:
        details = [
            {
                "trial_id": trial.trial_id,
                "hard_checks_passed": trial.hard_checks_passed,
                "sequence": trial.dispatch_sequence_digest,
                "safety": trial.safety.model_dump(mode="json"),
                "telemetry_errors": trial.host_telemetry.collection_errors,
            }
            for trial in a.trials
        ]
        raise RuntimeError(
            "the lowest-risk Profile A failed qualification: "
            + json.dumps(details, sort_keys=True, separators=(",", ":"))
        )
    return QualificationSelection(
        selected_profile_id=str(selected.profile["profile_id"]),
        selected_profile_digest=selected.profile_digest,
        selection_rule="LOWEST_CONCURRENCY_UNLESS_HIGHER_IS_AT_LEAST_10_PERCENT_FASTER_AND_SAFE",
        b_improvement_over_a_percent=round(b_over_a, 6),
        c_improvement_over_b_percent=round(c_over_b, 6),
        c_improvement_over_a_percent=round(c_over_a, 6),
        minimum_higher_profile_improvement_percent=minimum_improvement_percent,
        reason=reason,
    )


async def _docker_image_identities() -> dict[str, str]:
    identities: dict[str, str] = {}
    for image in (CODEX_IMAGE, CLAUDE_IMAGE):
        inspected = await _command(
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            "{{.Id}}",
        )
        identity = inspected.stdout.strip()
        if not identity.startswith("sha256:") or len(identity) != 71:
            raise RuntimeError("local Harness image identity was not immutable")
        identities[image] = identity
    return identities


async def _database_identity(factory: async_sessionmaker[AsyncSession]) -> str:
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT current_database(), current_user, current_setting('server_version'), "
                    "system_identifier::text FROM pg_control_system()"
                )
            )
        ).one()
    return _canonical_digest(tuple(str(value) for value in row))


async def qualify_v6_throughput_r2(
    plan: MethodologyV2ExperimentPlan,
    profiles: Sequence[DispatchProfile],
    factory: async_sessionmaker[AsyncSession],
    *,
    repetitions: int = 2,
) -> ThroughputR2Qualification:
    required = {
        "V6_PROFILE_A_C4",
        "V6_PROFILE_B_C6",
        "V6_PROFILE_C_C6_H3",
    }
    if {profile.profile_id for profile in profiles} != required:
        raise ValueError("R2 requires exactly Profiles A, B, and C")
    images = await _docker_image_identities()
    database_identity = await _database_identity(factory)
    with tempfile.TemporaryDirectory(prefix="harnesslab-v6-throughput-r2-") as raw_root:
        root = Path(raw_root)
        qualifications: list[ProfileQualification] = []
        for profile in profiles:
            profile_root = root / profile.profile_id.lower()
            profile_root.mkdir()
            qualifications.append(
                await qualify_profile(
                    plan,
                    profile,
                    factory,
                    root=profile_root,
                    repetitions=repetitions,
                )
            )
        selection = select_qualified_profile(qualifications)
        selected = next(
            profile for profile in profiles if profile.profile_id == selection.selected_profile_id
        )
        probe_root = root / "cancellation-probe"
        probe_root.mkdir()
        cancellation = await run_cancellation_probe(
            plan,
            selected,
            factory,
            root=probe_root,
        )
        if not cancellation.passed:
            raise RuntimeError("local cancellation/cleanup probe failed")
        result = ThroughputR2Qualification(
            profiles=tuple(qualifications),
            cancellation_probe=cancellation,
            selection=selection,
            docker_images=images,
            database_identity_digest=database_identity,
            external_call_counts={
                "real_provider_calls": 0,
                "real_harness_provider_calls": 0,
                "real_judge_calls": 0,
            },
        )
    leftovers = await _command(
        "docker",
        "ps",
        "--all",
        "--quiet",
        "--filter",
        f"label={QUALIFIER_LABEL}={QUALIFIER_LABEL_VALUE}",
    )
    if leftovers.stdout.strip():
        raise RuntimeError("qualification left Docker containers behind")
    return result
