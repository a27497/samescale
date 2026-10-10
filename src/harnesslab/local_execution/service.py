from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.db.models.execution_lease import ExecutionLease
from harnesslab.db.models.local_execution import (
    LocalExecutionAttemptRecord,
    LocalExecutionAuthorizationRecord,
    LocalExecutionResultRecord,
)
from harnesslab.db.models.local_plan import LocalTaskPlanRecord
from harnesslab.local_execution.models import AuthorizationRequest, ExecutionAuthorization
from harnesslab.local_execution.policy import load_execution_policy, operator_identity
from harnesslab.local_execution.subscription import deny_real_execution, real_execution_readiness
from harnesslab.local_plans import service as planning
from harnesslab.local_plans.models import SavedPlan
from harnesslab.local_plans.tasks import fail
from harnesslab.registry.models import RegistryCatalog, canonical_digest

TERMINAL = frozenset(
    {
        "VERIFIED_PASS",
        "VERIFIED_FAIL",
        "TIMEOUT",
        "CANCELLED",
        "FAILED_INFRA",
        "INTERRUPTED",
        "BLOCKED",
    }
)
ACTIVE = frozenset({"CLAIMED", "RUNNING"})


async def saved_plan(session: AsyncSession, plan_id: str, *, lock: bool = False) -> SavedPlan:
    query = select(LocalTaskPlanRecord).where(LocalTaskPlanRecord.id == plan_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is None:
        raise fail("PLAN_NOT_FOUND", "Saved plan does not exist.", 404)
    return planning.validated_plan(row)


def validate_current(
    plan: SavedPlan, catalog: RegistryCatalog, credentials: frozenset[str]
) -> None:
    material = plan.preflight.material
    assert material is not None
    current, _ = planning.assess(material.request, catalog, credentials)
    if current is None or current.material_digest != material.material_digest:
        raise fail(
            "PLAN_STALE",
            "Task, configuration, admission, image or application identity drifted.",
            409,
        )


def validated_authorization(row: LocalExecutionAuthorizationRecord) -> ExecutionAuthorization:
    try:
        auth = ExecutionAuthorization.model_validate(row.document)
        if (
            auth.authorization_id != row.id
            or auth.digest != row.digest
            or auth.plan_id != row.plan_id
            or str(auth.request.idempotency_key) != row.idempotency_key
        ):
            raise ValueError("authorization row binding")
        return auth
    except ValueError:
        raise fail(
            "AUTHORIZATION_INTEGRITY_ERROR", "Execution authorization is corrupted.", 409
        ) from None


async def authorize(
    session: AsyncSession,
    plan_id: str,
    request: AuthorizationRequest,
    catalog: RegistryCatalog,
    credentials: frozenset[str],
) -> dict[str, Any]:
    if request.mode == "REAL_CODEX":
        deny_real_execution()
    policy = load_execution_policy()
    if request.max_model_cost_usd != 0:
        raise fail(
            "ZERO_MODEL_BUDGET_REQUIRED",
            "Fake execution permits zero model cost and zero model calls.",
        )
    if request.subscription_limits != policy.protocol_limits:
        raise fail(
            "PROTOCOL_LIMITS_CONFIRMATION_REQUIRED",
            "Confirm the exact offline request/turn limits.",
            409,
        )
    plan = await saved_plan(session, plan_id, lock=True)
    material = plan.preflight.material
    assert material is not None
    slot = canonical_digest(material.custom_plan.run_slots[0].model_dump(mode="json"))
    if (
        request.plan_digest != plan.plan_digest
        or request.run_slot_digest != slot
        or request.confirmed_budget != material.request.budget
    ):
        raise fail(
            "EXECUTION_BINDING_MISMATCH",
            "Confirm the exact plan, single run slot and frozen budget.",
            409,
        )
    old = await session.scalar(
        select(LocalExecutionAuthorizationRecord).where(
            or_(
                LocalExecutionAuthorizationRecord.plan_id == plan_id,
                LocalExecutionAuthorizationRecord.idempotency_key == str(request.idempotency_key),
            )
        )
    )
    if old is not None:
        auth = validated_authorization(old)
        if (
            auth.plan_id != plan_id
            or auth.request.model_dump(exclude={"idempotency_key"})
            != request.model_dump(exclude={"idempotency_key"})
            or auth.operator_identity != operator_identity()
        ):
            raise fail(
                "EXECUTION_IDEMPOTENCY_CONFLICT",
                "One authorization is already bound to another request.",
                409,
            )
        return await view(session, plan_id)
    validate_current(plan, catalog, credentials)
    if material.task.task_identity not in policy.fixture_task_identities:
        raise fail(
            "FAKE_FIXTURE_NOT_APPROVED",
            "Fake execution is restricted to operator-approved isolated fixtures.",
            403,
        )
    now = datetime.now(UTC)
    payload = {
        "authorization_id": "authorization-" + uuid4().hex,
        "plan_id": plan_id,
        "plan_digest": plan.plan_digest,
        "run_slot_digest": slot,
        "request": request.model_dump(mode="json"),
        "operator_identity": operator_identity(),
        "execution_policy_identity": policy.identity,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(seconds=policy.authorization_ttl_seconds))
        .isoformat()
        .replace("+00:00", "Z"),
        "model_calls_allowed": 0,
        "cost_enforcement": "ZERO_MODEL_CALLS_NETWORK_NONE_NO_CREDENTIALS",
        "token_enforcement": "REFERENCE_ONLY_NOT_A_HARD_LIMIT",
    }
    auth = ExecutionAuthorization.model_validate({**payload, "digest": canonical_digest(payload)})
    # Normalize datetime representation before computing the persisted canonical digest.
    normalized = auth.model_dump(mode="json", exclude={"digest"})
    auth = ExecutionAuthorization.model_validate(
        {**normalized, "digest": canonical_digest(normalized)}
    )
    run_id = "local-run-" + uuid4().hex
    session.add(
        LocalExecutionAuthorizationRecord(
            id=auth.authorization_id,
            plan_id=plan_id,
            idempotency_key=str(request.idempotency_key),
            digest=auth.digest,
            document=auth.model_dump(mode="json"),
        )
    )
    session.add(
        ExecutionLease(run_id=run_id, status="QUEUED", attempt=0, cancellation_requested=False)
    )
    try:
        await session.flush()
        session.add(
            LocalExecutionAttemptRecord(
                run_id=run_id, authorization_id=auth.authorization_id, plan_id=plan_id
            )
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise fail(
            "EXECUTION_IDEMPOTENCY_CONFLICT",
            "Authorization conflicts with an existing request.",
            409,
        ) from None
    return await view(session, plan_id)


async def view(session: AsyncSession, plan_id: str) -> dict[str, Any]:
    await saved_plan(session, plan_id)
    attempt = await session.scalar(
        select(LocalExecutionAttemptRecord).where(LocalExecutionAttemptRecord.plan_id == plan_id)
    )
    if attempt is None:
        return {
            "status": "NOT_AUTHORIZED",
            "attempt": None,
            "result": None,
            "mode": "FAKE_CODEX",
            "real_execution_enabled": False,
            "subscription_readiness": real_execution_readiness(),
        }
    row = await session.get(LocalExecutionAuthorizationRecord, attempt.authorization_id)
    lease = await session.get(ExecutionLease, attempt.run_id)
    if row is None or lease is None:
        raise fail("EXECUTION_INTEGRITY_ERROR", "Execution references are incomplete.", 409)
    auth = validated_authorization(row)
    result_row = await session.get(LocalExecutionResultRecord, attempt.run_id)
    result = None
    if result_row is not None:
        from harnesslab.local_execution.evidence import validate_result

        result = validate_result(result_row, auth)
        if result["status"] != lease.status:
            raise fail("EXECUTION_INTEGRITY_ERROR", "Result and lifecycle disagree.", 409)
    return {
        "status": lease.status,
        "attempt": {
            "run_id": attempt.run_id,
            "attempt_number": lease.attempt,
            "authorization": auth.model_dump(mode="json"),
            "cancellation_requested": lease.cancellation_requested,
            "lease_expires_at": lease.lease_expires_at,
        },
        "result": result,
        "mode": "FAKE_CODEX",
        "real_execution_enabled": False,
        "subscription_readiness": real_execution_readiness(),
    }


async def cancel(session: AsyncSession, plan_id: str) -> dict[str, Any]:
    await saved_plan(session, plan_id)
    lease = await session.scalar(
        select(ExecutionLease)
        .join(
            LocalExecutionAttemptRecord, LocalExecutionAttemptRecord.run_id == ExecutionLease.run_id
        )
        .where(LocalExecutionAttemptRecord.plan_id == plan_id)
        .with_for_update()
    )
    if lease is None:
        raise fail("EXECUTION_NOT_FOUND", "No authorized attempt exists.", 404)
    if lease.status not in TERMINAL:
        lease.cancellation_requested = True
        # Queued cancellation never creates a subject. Active cancellation is acknowledged
        # only after the worker has stopped the runner and verified cleanup.
        if lease.status == "QUEUED":
            lease.status = "CANCELLED"
        await session.commit()
    return await view(session, plan_id)
