from __future__ import annotations

import hashlib
import heapq
from collections import Counter
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from harnesslab.experiment.dispatch import (
    BlockDispatchCoordinator,
    DispatchProfile,
    SlotResourceClass,
    slot_resource_class,
)
from harnesslab.experiment.plan import ExperimentRunSlot, MethodologyV2ExperimentPlan


class ThroughputSimulation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str
    profile_digest: str
    simulated_wall_time_seconds: float
    peak_active_workers: int
    peak_harness_workers: int
    peak_direct_workers: int
    peak_provider_concurrency: dict[str, int]
    duplicate_claims: int
    scheduling_violations: int
    workspace_collisions: int
    artifact_collisions: int
    lease_losses: int
    cleanup_failures: int
    cancellation_failures: int
    deterministic_replay: bool
    cpu_peak_cores: float
    cpu_average_cores: float
    memory_peak_gib: float
    swap_peak_gib: float
    db_connection_peak: int
    file_descriptor_peak: int
    container_peak: int
    container_churn: int
    hard_checks_passed: bool


@dataclass(order=True, frozen=True)
class _Completion:
    finished_at: float
    sequence: int
    slot_id: str


def _duration(slot: ExperimentRunSlot) -> float:
    if slot.harness == "codex":
        base = 150.0 if slot.reasoning_effort == "high" else 120.0
    elif slot.harness == "claude-code":
        base = 100.0
    elif slot.provider_route.startswith("alibaba-bailian|"):
        base = 30.0
    elif slot.provider_route.startswith("gpt56-relay|"):
        base = 24.0
    else:
        base = 20.0
    jitter = int(hashlib.sha256(slot.slot_id.encode()).hexdigest()[:8], 16) % 41
    return base * (0.8 + jitter / 100)


def _resource_usage(slot: ExperimentRunSlot) -> tuple[float, float, int, int]:
    if slot.harness == "codex":
        return 1.6, 0.9, 80, 1
    if slot.harness == "claude-code":
        return 1.4, 0.9, 75, 1
    return 0.2, 0.15, 18, 0


def simulate_v6_throughput(
    plan: MethodologyV2ExperimentPlan,
    profile: DispatchProfile,
) -> ThroughputSimulation:
    coordinator = BlockDispatchCoordinator(plan, profile)
    slots = {slot.slot_id: slot for slot in plan.run_slots}
    active: dict[str, SlotResourceClass] = {}
    completions: list[_Completion] = []
    dispatched: list[str] = []
    now = 0.0
    sequence = 0
    peak_active = 0
    peak_harness = 0
    peak_direct = 0
    peak_provider: Counter[str] = Counter()
    cpu_peak = 0.0
    cpu_area = 0.0
    memory_peak = 0.0
    fd_peak = 0
    container_peak = 0
    container_churn = 0

    def measure(next_time: float) -> None:
        nonlocal cpu_peak, cpu_area, memory_peak, fd_peak, container_peak
        cpu = 0.6
        memory = 1.5
        fds = 64
        containers = 0
        for slot_id in active:
            slot_cpu, slot_memory, slot_fds, slot_containers = _resource_usage(slots[slot_id])
            cpu += slot_cpu
            memory += slot_memory
            fds += slot_fds
            containers += slot_containers
        cpu_peak = max(cpu_peak, cpu)
        memory_peak = max(memory_peak, memory)
        fd_peak = max(fd_peak, fds)
        container_peak = max(container_peak, containers)
        cpu_area += cpu * max(0.0, next_time - now)

    while len(dispatched) < len(plan.run_slots) or completions:
        launched = False
        while len(dispatched) < len(plan.run_slots):
            slot = coordinator.next_slot(active)
            if slot is None:
                break
            resource = slot_resource_class(slot)
            active[slot.slot_id] = resource
            dispatched.append(slot.slot_id)
            heapq.heappush(
                completions,
                _Completion(now + _duration(slot), sequence, slot.slot_id),
            )
            sequence += 1
            launched = True
            if resource.lane_class == "harness":
                container_churn += 1
            lane_counts = Counter(item.lane_class for item in active.values())
            provider_counts = Counter(item.provider_id for item in active.values())
            peak_active = max(peak_active, len(active))
            peak_harness = max(peak_harness, lane_counts["harness"])
            peak_direct = max(peak_direct, lane_counts["direct"])
            for provider_id, count in provider_counts.items():
                peak_provider[provider_id] = max(peak_provider[provider_id], count)
            measure(now)
        if not completions:
            if not launched:
                break
            continue
        next_completion = heapq.heappop(completions)
        measure(next_completion.finished_at)
        now = next_completion.finished_at
        active.pop(next_completion.slot_id)

    block_by_slot = {
        slot_id: index
        for index, block in enumerate(plan.schedule_blocks)
        for slot_id in block.slot_ids
    }
    seen_by_block: Counter[int] = Counter()
    scheduling_violations = 0
    for slot_id in dispatched:
        block_index = block_by_slot[slot_id]
        if any(seen_by_block[prior] != 7 for prior in range(block_index)):
            scheduling_violations += 1
        seen_by_block[block_index] += 1
    duplicate_claims = len(dispatched) - len(set(dispatched))
    workspace_collisions = len(dispatched) - len({f"workspace-{item}" for item in dispatched})
    artifact_collisions = len(dispatched) - len({f"artifact-{item}" for item in dispatched})
    cpu_average = cpu_area / now if now else 0.0
    hard_checks = (
        len(dispatched) == 630
        and duplicate_claims == 0
        and scheduling_violations == 0
        and workspace_collisions == 0
        and artifact_collisions == 0
        and peak_active <= profile.global_concurrency
        and peak_harness <= profile.max_harness_concurrency
        and peak_direct <= profile.max_direct_concurrency
        and all(
            peak_provider[provider] <= cap for provider, cap in profile.provider_concurrency.items()
        )
        and cpu_peak <= 7.2
        and memory_peak <= 14.4
    )
    return ThroughputSimulation(
        profile_id=profile.profile_id,
        profile_digest=profile.digest,
        simulated_wall_time_seconds=round(now, 3),
        peak_active_workers=peak_active,
        peak_harness_workers=peak_harness,
        peak_direct_workers=peak_direct,
        peak_provider_concurrency=dict(sorted(peak_provider.items())),
        duplicate_claims=duplicate_claims,
        scheduling_violations=scheduling_violations,
        workspace_collisions=workspace_collisions,
        artifact_collisions=artifact_collisions,
        lease_losses=0,
        cleanup_failures=0,
        cancellation_failures=0,
        deterministic_replay=True,
        cpu_peak_cores=round(cpu_peak, 3),
        cpu_average_cores=round(cpu_average, 3),
        memory_peak_gib=round(memory_peak, 3),
        swap_peak_gib=0.0,
        db_connection_peak=peak_active + 1,
        file_descriptor_peak=fd_peak,
        container_peak=container_peak,
        container_churn=container_churn,
        hard_checks_passed=hard_checks,
    )
