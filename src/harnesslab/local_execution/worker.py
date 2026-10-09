"""Separate local process. Only this process needs Docker execution privilege.

Single-slot ownership uses the existing execution_lease table and queue-style
SKIP LOCKED selection. An expired physical attempt is never requeued.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.api.local_configuration import configured_credentials, workspace_catalog
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.db.models.execution_lease import ExecutionLease
from harnesslab.db.models.local_execution import (
    LocalExecutionAttemptRecord,
    LocalExecutionAuthorizationRecord,
    LocalExecutionResultRecord,
)
from harnesslab.harness_lane.models import CodexHarnessProfile, HarnessLaneRunResult
from harnesslab.harness_lane.profile import SHELL_TOOL_ENVIRONMENT_POLICY, SUBJECT_TOOLCHAIN_PROFILE
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.local_execution.backend import IsolatedFakeCodexBackend
from harnesslab.local_execution.evidence import (
    persist_completion,
    read_bound_episode,
    result_document,
    validate_result,
)
from harnesslab.local_execution.models import ExecutionAuthorization
from harnesslab.local_execution.policy import load_execution_policy, operator_identity
from harnesslab.local_execution.sandbox import PinnedVerifierSandbox
from harnesslab.local_execution.service import (
    ACTIVE,
    saved_plan,
    validate_current,
    validated_authorization,
)
from harnesslab.local_plans.service import local_image_identity
from harnesslab.local_plans.tasks import fail, inspect_task, load_policy, no_links
from harnesslab.registry.models import canonical_digest
from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.preflight import _docker_runtime_preflight
from harnesslab.sandbox.subprocess_loop import run_on_subprocess_loop
from harnesslab.tasks.package import digest_tree


class LocalWorker:
    def __init__(
        self, factory: async_sessionmaker[AsyncSession], *, owner: str | None = None
    ) -> None:
        if os.environ.get("HARNESSLAB_PUBLIC_DEMO_MANIFEST"):
            raise fail("PUBLIC_DEMO_READ_ONLY", "Public Demo cannot host an execution Worker.", 403)
        self.factory = factory
        self.owner = owner or "worker-" + uuid4().hex
        self.policy = load_execution_policy()
        for root in (self.policy.runtime_root, self.policy.artifact_root):
            no_links(root)
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o022:
                raise ValueError("Worker roots must be owned and not shared writable")

    async def claim(self) -> str | None:
        async with self.factory() as session, session.begin():
            lease = await session.scalar(
                select(ExecutionLease)
                .join(
                    LocalExecutionAttemptRecord,
                    ExecutionLease.run_id == LocalExecutionAttemptRecord.run_id,
                )
                .where(
                    ExecutionLease.status == "QUEUED",
                    ExecutionLease.attempt == 0,
                    ExecutionLease.cancellation_requested.is_(False),
                )
                .order_by(ExecutionLease.run_id)
                .with_for_update(of=ExecutionLease, skip_locked=True)
                .limit(1)
            )
            if lease is None:
                return None
            now = datetime.now(UTC)
            lease.attempt = 1
            lease.status = "CLAIMED"
            lease.lease_owner = self.owner
            lease.heartbeat_at = now
            lease.lease_expires_at = now + timedelta(seconds=self.policy.lease_seconds)
            return lease.run_id

    async def _owned(self, session: AsyncSession, run_id: str) -> ExecutionLease:
        lease = await session.scalar(
            select(ExecutionLease).where(ExecutionLease.run_id == run_id).with_for_update()
        )
        if (
            lease is None
            or lease.lease_owner != self.owner
            or lease.attempt != 1
            or lease.status not in ACTIVE
            or lease.lease_expires_at is None
            or lease.lease_expires_at <= datetime.now(UTC)
        ):
            raise fail("WORKER_LEASE_LOST", "Attempt ownership expired; never redispatch.", 409)
        return lease

    async def _authorization(self, session: AsyncSession, run_id: str) -> ExecutionAuthorization:
        attempt = await session.get(LocalExecutionAttemptRecord, run_id)
        if attempt is None:
            raise ValueError("Attempt missing")
        row = await session.get(LocalExecutionAuthorizationRecord, attempt.authorization_id)
        if row is None:
            raise ValueError("Authorization missing")
        auth = validated_authorization(row)
        if auth.plan_id != attempt.plan_id:
            raise ValueError("Attempt binding changed")
        return auth

    async def _prepare(
        self, run_id: str
    ) -> tuple[ExecutionAuthorization, Path, CodexHarnessProfile]:
        async with self.factory() as session, session.begin():
            lease = await self._owned(session, run_id)
            auth = await self._authorization(session, run_id)
            plan = await saved_plan(session, auth.plan_id)
            material = plan.preflight.material
            assert material is not None and material.request.budget is not None
            if (
                auth.expires_at <= datetime.now(UTC)
                or auth.operator_identity != operator_identity()
                or auth.plan_digest != plan.plan_digest
                or auth.execution_policy_identity != load_execution_policy().identity
                or auth.execution_policy_identity != self.policy.identity
                or auth.run_slot_digest
                != canonical_digest(material.custom_plan.run_slots[0].model_dump(mode="json"))
            ):
                raise fail(
                    "EXECUTION_AUTHORIZATION_STALE",
                    "Authorization expired or frozen identity changed.",
                    409,
                )
            validate_current(
                plan, await workspace_catalog(session), await configured_credentials(session)
            )
            task, package = inspect_task(load_policy(), material.task.reference)
            frozen = material.configuration
            # Check exact local images; never call ensure_image/build/pull or use a mutable tag.
            if (
                local_image_identity(frozen.harness.image_reference) != frozen.image_identity
                or local_image_identity(self.policy.subject_image_identity)
                != self.policy.subject_image_identity
                or local_image_identity(self.policy.verifier_image_identity)
                != self.policy.verifier_image_identity
            ):
                raise fail(
                    "WORKER_IMAGE_DRIFT",
                    "Pinned local runtime images are unavailable or changed.",
                    409,
                )
            if (
                task.task_identity not in self.policy.fixture_task_identities
                or package.definition.id != "micro-python-clamp"
                or package.manifest.context_path is not None
            ):
                raise fail(
                    "FAKE_FIXTURE_NOT_APPROVED",
                    "Only a trusted isolated test fixture may run.",
                    403,
                )
            profile = CodexHarnessProfile(
                codex_cli_version=frozen.harness.version,
                requested_model=frozen.model.requested_model,
                reasoning_effort=frozen.harness_profile.reasoning_effort,
                provider_route="fake-isolated-no-provider",
                built_in_behavior_profile="fake-codex-jsonl-v1",
                execution_timeout_seconds=material.request.budget.wall_time_seconds,
                codex_image=ImageIdentity(
                    reference=frozen.harness.image_reference, image_id=frozen.image_identity
                ),
                subject_toolchain_profile=SUBJECT_TOOLCHAIN_PROFILE,
                shell_tool_environment_policy=SHELL_TOOL_ENVIRONMENT_POLICY,
            )
            if lease.cancellation_requested:
                raise fail(
                    "CANCELLED_BEFORE_START", "Cancellation requested before subject dispatch.", 409
                )
            lease.status = "RUNNING"
            # Preserve an immutable package copy for this attempt, re-check after copying.
            import shutil

            destination = (
                self.policy.runtime_root
                / (run_id + "-package")
                / package.definition.id
                / package.definition.version
            )
            shutil.copytree(package.root, destination)
            if digest_tree(destination) != package.definition.content_digest:
                raise fail("WORKER_TASK_DRIFT", "Task changed during snapshot copying.", 409)
            return auth, destination, profile

    async def _watch(self, run_id: str, task: asyncio.Task[HarnessLaneRunResult]) -> None:
        while not task.done():
            await asyncio.sleep(min(2, self.policy.lease_seconds / 3))
            if task.done():
                return
            try:
                async with self.factory() as session, session.begin():
                    lease = await self._owned(session, run_id)
                    if lease.cancellation_requested:
                        task.cancel()
                        return
                    lease.heartbeat_at = datetime.now(UTC)
                    lease.lease_expires_at = lease.heartbeat_at + timedelta(
                        seconds=self.policy.lease_seconds
                    )
            except Exception:
                task.cancel()
                return

    async def _store(self, run_id: str, result: dict[str, Any]) -> None:
        async with self.factory() as session, session.begin():
            lease = await self._owned(session, run_id)
            if lease.cancellation_requested and result["status"] not in {
                "FAILED_INFRA",
                "CANCELLED",
            }:
                from harnesslab.episodes.service import Episode

                result = result_document(
                    await self._authorization(session, run_id),
                    run_id,
                    "CANCELLED",
                    "OPERATOR_CANCELLED",
                    episode=Episode.model_validate(result["episode"])
                    if result["episode"]
                    else None,
                )
            row = LocalExecutionResultRecord(
                run_id=run_id, digest=result["digest"], document=result
            )
            validate_result(row, await self._authorization(session, run_id))
            session.add(row)
            lease.status = result["status"]
            lease.lease_owner = None
            lease.lease_expires_at = None

    async def execute(self, run_id: str) -> None:
        # flock complements the DB lease: an expired live process cannot race recovery.
        lock_path = self.policy.artifact_root / (run_id + ".lock")
        no_links(lock_path)
        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            async with self.factory() as session:
                auth = await self._authorization(session, run_id)
            result: dict[str, Any]
            entered_runner = False
            try:
                auth, package, profile = await self._prepare(run_id)
                backend = IsolatedFakeCodexBackend(self.policy)
                backend.run_id = run_id
                sandbox = PinnedVerifierSandbox(
                    image_id=self.policy.verifier_image_identity,
                    run_id=run_id,
                    runtime_root=self.policy.runtime_root / "verifier-runtime",
                    artifact_root=self.policy.artifact_root / "verifier-staging",
                    force_timeout=self.policy.scenario == "verifier_timeout",
                )
                runner = CodexHarnessRunner(
                    artifact_root=self.policy.artifact_root,
                    runtime_root=self.policy.runtime_root / "subjects",
                    sandbox=sandbox,
                    local_worker_evidence=True,
                    plan_profile_identity=auth.plan_digest,
                    plan_harness_config_identity=auth.digest,
                )
                entered_runner = True
                task = asyncio.create_task(
                    runner.run(package, profile, backend=backend, run_id=run_id)
                )
                watcher = asyncio.create_task(self._watch(run_id, task))
                try:
                    lane = await task
                finally:
                    watcher.cancel()
                    with suppress(asyncio.CancelledError):
                        await watcher
                episode = read_bound_episode(lane.artifact_directory, auth, run_id)
                status = {"RECORDED_PASS": "VERIFIED_PASS", "RECORDED_FAIL": "VERIFIED_FAIL"}.get(
                    episode.acceptance, "FAILED_INFRA"
                )
                failure_subtype = (
                    lane.evidence.verifier_lifecycle.failure_subtype
                    if lane.evidence.verifier_lifecycle
                    else None
                )
                if failure_subtype and failure_subtype.value == "VERIFIER_TIMEOUT":
                    status = "TIMEOUT"
                if lane.evidence.timed_out:
                    status = "TIMEOUT"
                if lane.evidence.summary == "isolated Hidden Verifier failed: CancelledError":
                    status = "CANCELLED"
                if lane.evidence.cancelled:
                    status = "CANCELLED"
                result = result_document(
                    auth,
                    run_id,
                    status,
                    lane.evidence.harness_failure.value
                    if lane.evidence.harness_failure
                    else failure_subtype.value
                    if failure_subtype
                    else lane.evidence.outcome.value,
                    episode=episode,
                )
            except asyncio.CancelledError:
                result = result_document(auth, run_id, "CANCELLED", "WORKER_STOPPED_NO_RETRY")
            except WorkbenchAPIError as exc:
                result = result_document(auth, run_id, "BLOCKED", exc.code)
            except Exception:
                # Never include raw exception text, credentials, native reasoning or host paths.
                result = result_document(auth, run_id, "FAILED_INFRA", "WORKER_EXECUTION_FAILED")
            if entered_runner:
                # A terminal receipt requires subject/verifier container absence. Cleanup
                # failure leaves the consumed attempt active for recovery, never requeued.
                await self._cleanup_abandoned(run_id)
                import shutil

                package_root = self.policy.runtime_root / (run_id + "-package")
                no_links(package_root)
                shutil.rmtree(package_root)
            persist_completion(self.policy.artifact_root, result)
            await self._store(run_id, result)

    async def recover(self) -> int:
        recovered = 0
        async with self.factory() as session:
            ids = list(
                await session.scalars(
                    select(ExecutionLease.run_id)
                    .join(
                        LocalExecutionAttemptRecord,
                        LocalExecutionAttemptRecord.run_id == ExecutionLease.run_id,
                    )
                    .where(
                        ExecutionLease.status.in_(ACTIVE),
                        ExecutionLease.lease_expires_at <= datetime.now(UTC),
                    )
                )
            )
        for run_id in ids:
            lock_path = self.policy.artifact_root / (run_id + ".lock")
            no_links(lock_path)
            with lock_path.open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                # Owned containers must be absent before marking a lost attempt terminal.
                await self._cleanup_abandoned(run_id)
                async with self.factory() as session, session.begin():
                    lease = await session.scalar(
                        select(ExecutionLease)
                        .where(ExecutionLease.run_id == run_id)
                        .with_for_update()
                    )
                    if (
                        lease is None
                        or lease.status not in ACTIVE
                        or lease.lease_expires_at is None
                        or lease.lease_expires_at > datetime.now(UTC)
                    ):
                        continue
                    auth = await self._authorization(session, run_id)
                    sealed = self.policy.artifact_root / (run_id + ".result.json")
                    result = result_document(
                        auth, run_id, "INTERRUPTED", "WORKER_LOST_NO_AUTOMATIC_RETRY"
                    )
                    if sealed.exists() and not lease.cancellation_requested:
                        no_links(sealed)
                        try:
                            if sealed.stat().st_size > 4_000_000:
                                raise ValueError("sealed result too large")
                            document = json.loads(sealed.read_bytes())
                            candidate = LocalExecutionResultRecord(
                                run_id=run_id, digest=document["digest"], document=document
                            )
                            result = validate_result(candidate, auth)
                        except (OSError, ValueError, KeyError, WorkbenchAPIError):
                            result = result_document(
                                auth, run_id, "FAILED_INFRA", "RECOVERY_EVIDENCE_INVALID"
                            )
                    session.add(
                        LocalExecutionResultRecord(
                            run_id=run_id, digest=result["digest"], document=result
                        )
                    )
                    lease.status = result["status"]
                    lease.lease_owner = None
                    lease.lease_expires_at = None
                    recovered += 1
        return recovered

    async def _cleanup_abandoned(self, run_id: str) -> None:
        async def cleanup() -> None:
            _, environment = await _docker_runtime_preflight()
            cli = _DockerCLI(environment=environment)
            names = ("harnesslab-local-" + run_id, "harnesslab-verifier-" + run_id + "-verifier")
            for name in names:
                raw = await cli.run("inspect", name, check=False)
                if raw.returncode != 0:
                    absent = await cli.run("ps", "--all", "--quiet", "--filter", f"name=^/{name}$")
                    if absent.stdout.strip():
                        raise ValueError("Owned container inspection failed")
                    continue
                labels = json.loads(raw.stdout)[0]["Config"]["Labels"]
                expected = (
                    (name, "E", None)
                    if name.startswith("harnesslab-local-")
                    else (run_id + "-verifier", "C", "verifier")
                )
                if (
                    labels.get("com.harnesslab.run_id") != expected[0]
                    or labels.get("com.harnesslab.phase") != expected[1]
                    or (
                        expected[2] is not None and labels.get("com.harnesslab.role") != expected[2]
                    )
                ):
                    raise ValueError("Refuse cleanup of unowned container")
                await cli.run("rm", "--force", name)
                absent = await cli.run("ps", "--all", "--quiet", "--filter", f"name=^/{name}$")
                if absent.stdout.strip():
                    raise ValueError("Abandoned cleanup not verified")

        await run_on_subprocess_loop(cleanup())

    async def once(self) -> str | None:
        await self.recover()
        run_id = await self.claim()
        if run_id:
            await self.execute(run_id)
        return run_id
