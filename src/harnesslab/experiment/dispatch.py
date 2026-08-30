from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.contracts.common import EvaluationLane
from harnesslab.db.models.experiment import ExperimentRunRecord
from harnesslab.experiment.methodology import ProviderAvailability
from harnesslab.experiment.plan import ExperimentRunSlot, MethodologyV2ExperimentPlan
from harnesslab.experiment.queue import ACTIVE_STATUSES, TERMINAL_STATUSES, RunSnapshot


class DispatchProfile(BaseModel):
    """Frozen, non-adaptive campaign capacity limits."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str = Field(min_length=1, max_length=100)
    global_concurrency: int = Field(ge=1, le=8)
    max_harness_concurrency: int = Field(ge=1, le=8)
    max_direct_concurrency: int = Field(ge=1, le=8)
    provider_concurrency: dict[str, int]
    max_judge_concurrency: int = Field(default=1, ge=1, le=1)

    @model_validator(mode="after")
    def bounded_subcaps(self) -> DispatchProfile:
        if self.max_harness_concurrency > self.global_concurrency:
            raise ValueError("Harness cap cannot exceed global concurrency")
        if self.max_direct_concurrency > self.global_concurrency:
            raise ValueError("Direct cap cannot exceed global concurrency")
        if not self.provider_concurrency:
            raise ValueError("at least one provider cap is required")
        if any(
            value < 1 or value > self.global_concurrency
            for value in self.provider_concurrency.values()
        ):
            raise ValueError("provider caps must be positive and no larger than global concurrency")
        return self

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return "sha256:" + hashlib.sha256(raw).hexdigest()


class DispatchExecutor(Protocol):
    """Minimal durable executor contract used by the production dispatcher."""

    session_factory: async_sessionmaker[AsyncSession]

    async def claim(
        self,
        experiment_id: str,
        *,
        slot_ids: Collection[str] | None = None,
    ) -> RunSnapshot | None: ...

    async def execute(self, claimed: RunSnapshot) -> RunSnapshot: ...


@dataclass(frozen=True)
class SlotResourceClass:
    lane_class: str
    provider_id: str


def slot_resource_class(slot: ExperimentRunSlot) -> SlotResourceClass:
    provider_id, separator, _ = slot.provider_route.partition("|")
    if not separator or not provider_id:
        raise ValueError("slot provider route lacks a provider-family identity")
    lane_class = "direct" if slot.lane is EvaluationLane.MODEL else "harness"
    return SlotResourceClass(lane_class=lane_class, provider_id=provider_id)


class BlockDispatchCoordinator:
    """Pure block-frontier scheduler shared by production dispatch and simulation."""

    def __init__(
        self,
        plan: MethodologyV2ExperimentPlan,
        profile: DispatchProfile,
        *,
        represented_slot_ids: Collection[str] = (),
    ) -> None:
        self.plan = plan
        self.profile = profile
        self._slots = {slot.slot_id: slot for slot in plan.run_slots}
        self._represented = set(represented_slot_ids)
        unknown = self._represented - self._slots.keys()
        if unknown:
            raise ValueError("represented set contains a slot outside the frozen plan")
        self._dispatch_sequence: list[str] = []

    @property
    def dispatch_sequence(self) -> tuple[str, ...]:
        return tuple(self._dispatch_sequence)

    @property
    def represented_slot_ids(self) -> frozenset[str]:
        return frozenset(self._represented)

    def _first_incomplete_block_index(self) -> int | None:
        for index, block in enumerate(self.plan.schedule_blocks):
            if any(slot_id not in self._represented for slot_id in block.slot_ids):
                return index
        return None

    def next_slot(
        self,
        active: Mapping[str, SlotResourceClass],
        *,
        allowed_slot_ids: Collection[str] | None = None,
    ) -> ExperimentRunSlot | None:
        if len(active) >= self.profile.global_concurrency:
            return None
        block_index = self._first_incomplete_block_index()
        if block_index is None:
            return None
        block = self.plan.schedule_blocks[block_index]
        if block.provider_availability is ProviderAvailability.PROVIDER_UNAVAILABLE:
            return None
        allowed = set(allowed_slot_ids) if allowed_slot_ids is not None else None
        counts = Counter(resource.lane_class for resource in active.values())
        provider_counts = Counter(resource.provider_id for resource in active.values())
        for slot_id in block.slot_ids:
            if slot_id in self._represented or (allowed is not None and slot_id not in allowed):
                continue
            slot = self._slots[slot_id]
            resource = slot_resource_class(slot)
            lane_cap = (
                self.profile.max_direct_concurrency
                if resource.lane_class == "direct"
                else self.profile.max_harness_concurrency
            )
            provider_cap = self.profile.provider_concurrency.get(resource.provider_id)
            if provider_cap is None:
                raise ValueError(f"dispatch profile lacks provider cap: {resource.provider_id}")
            if counts[resource.lane_class] >= lane_cap:
                return None
            if provider_counts[resource.provider_id] >= provider_cap:
                return None
            self._represented.add(slot_id)
            self._dispatch_sequence.append(slot_id)
            return slot
        return None

    def restore_unclaimed(self, slot_id: str) -> None:
        """Undo a speculative representation when the durable exact-slot claim loses."""

        if self._dispatch_sequence and self._dispatch_sequence[-1] == slot_id:
            self._dispatch_sequence.pop()
        self._represented.discard(slot_id)


@dataclass(frozen=True)
class DispatchEvent:
    dispatch_order: int
    block_identity: str
    slot_id: str
    cell_id: str
    claimed_at: datetime


@dataclass(frozen=True)
class BlockDispatchResult:
    completed: tuple[RunSnapshot, ...]
    events: tuple[DispatchEvent, ...]


class BlockAwareDispatcher:
    """Dispatch methodology-v2 blocks with fixed lane and provider capacity limits."""

    def __init__(
        self,
        *,
        executor: DispatchExecutor,
        plan: MethodologyV2ExperimentPlan,
        profile: DispatchProfile,
    ) -> None:
        self.executor = executor
        self.plan = plan
        self.profile = profile

    async def _resume_state(self) -> tuple[set[str], set[str]]:
        now = datetime.now(UTC)
        async with self.executor.session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        ExperimentRunRecord.slot_id,
                        ExperimentRunRecord.status,
                        ExperimentRunRecord.lease_expires_at,
                    ).where(ExperimentRunRecord.experiment_id == self.plan.experiment_id)
                )
            ).all()
        if len(rows) != len(self.plan.run_slots):
            raise RuntimeError("persisted methodology-v2 queue is incomplete")
        represented = {slot_id for slot_id, status, _ in rows if status in TERMINAL_STATUSES}
        live = {
            slot_id
            for slot_id, status, expiry in rows
            if status in ACTIVE_STATUSES and expiry is not None and expiry > now
        }
        return represented, live

    async def run(
        self,
        *,
        max_runs: int,
        slot_ids: Collection[str] | None = None,
    ) -> BlockDispatchResult:
        if max_runs < 1:
            raise ValueError("max_runs must be positive")
        represented, live = await self._resume_state()
        if live:
            raise RuntimeError("another coordinator owns live methodology-v2 leases")
        allowed = set(slot_ids) if slot_ids is not None else None
        coordinator = BlockDispatchCoordinator(
            self.plan,
            self.profile,
            represented_slot_ids=represented,
        )
        active: dict[str, SlotResourceClass] = {}
        tasks: dict[asyncio.Task[RunSnapshot], str] = {}
        results: list[RunSnapshot] = []
        events: list[DispatchEvent] = []
        launched = 0

        async def finish_one() -> None:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                slot_id = tasks.pop(task)
                active.pop(slot_id, None)
                results.append(task.result())

        try:
            while launched < max_runs:
                launched_this_round = False
                while launched < max_runs:
                    slot = coordinator.next_slot(active, allowed_slot_ids=allowed)
                    if slot is None:
                        break
                    claimed = await self.executor.claim(
                        self.plan.experiment_id,
                        slot_ids=(slot.slot_id,),
                    )
                    if claimed is None:
                        coordinator.restore_unclaimed(slot.slot_id)
                        raise RuntimeError("exact methodology-v2 slot could not be durably claimed")
                    resource = slot_resource_class(slot)
                    active[slot.slot_id] = resource
                    task = asyncio.create_task(self.executor.execute(claimed))
                    tasks[task] = slot.slot_id
                    block = next(
                        item for item in self.plan.schedule_blocks if slot.slot_id in item.slot_ids
                    )
                    events.append(
                        DispatchEvent(
                            dispatch_order=len(events),
                            block_identity=block.block_identity,
                            slot_id=slot.slot_id,
                            cell_id=slot.cell_id,
                            claimed_at=claimed.heartbeat_at or datetime.now(UTC),
                        )
                    )
                    launched += 1
                    launched_this_round = True
                if tasks:
                    await finish_one()
                elif not launched_this_round:
                    break
            while tasks:
                await finish_one()
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return BlockDispatchResult(completed=tuple(results), events=tuple(events))
