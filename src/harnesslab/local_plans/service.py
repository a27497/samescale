from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab import __version__
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.custom_eval.evaluation import build_custom_plan
from harnesslab.custom_eval.models import CustomEvaluationPreset, CustomPlanRequest, CustomTarget
from harnesslab.db.models.local_plan import LocalPlanPreflightRecord, LocalTaskPlanRecord
from harnesslab.local_plans.models import (
    FrozenConfiguration,
    FrozenModelProfile,
    FrozenProvider,
    PlanConfirmation,
    PlanMaterial,
    PlanningCheck,
    PlanRequest,
    PreflightReceipt,
    SavedPlan,
)
from harnesslab.local_plans.tasks import fail, inspect_task, load_policy, task_store
from harnesslab.productization.assets import distribution_root
from harnesslab.registry.models import CompatibilityStatus, RegistryCatalog, canonical_digest
from harnesslab.registry.service import assess_capability


def local_image_identity(reference: str) -> str | None:
    """Read local Docker metadata only. Never pulls an image or invokes its CLI."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", reference, "--format", "{{.Id}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        value = result.stdout.strip()
        if (
            len(value) == 71
            and value.startswith("sha256:")
            and all(c in "0123456789abcdef" for c in value[7:])
        ):
            return value
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def application_code_identity() -> str:
    # Stable across caches/builds; binds all installed Python behavior, not .pyc files.
    root = distribution_root() / "src" / "harnesslab"
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big") + relative)
        digest.update(len(content).to_bytes(8, "big") + content)
    return "sha256:" + digest.hexdigest()


def assess(
    request: PlanRequest, catalog: RegistryCatalog, credentials: frozenset[str]
) -> tuple[PlanMaterial | None, tuple[PlanningCheck, ...]]:
    checks: list[PlanningCheck] = []

    def check(code: str, passed: bool) -> None:
        checks.append(PlanningCheck(code=code, passed=passed))

    try:
        policy = load_policy()
        task, package = inspect_task(policy, request.task_reference)
        check("TASK_INTEGRITY_AND_SOURCE", True)
        check("TRUSTED_PRIOR_QUALIFICATION", task.eligible_for_planning)
    except (OSError, ValueError, WorkbenchAPIError) as exc:
        code = exc.code if isinstance(exc, WorkbenchAPIError) else "TASK_INVALID"
        return None, (PlanningCheck(code=code, passed=False),)
    model = next(
        (p for p in catalog.provider_model_profiles if p.profile_id == request.provider_profile_id),
        None,
    )
    pair = next(
        (
            (h, p)
            for h in catalog.harnesses
            for p in h.profiles
            if p.profile_id == request.harness_profile_id and h.harness_id == "codex"
        ),
        None,
    )
    check(
        "ONE_CODEX_SUBJECT_CONFIGURATION",
        model is not None and pair is not None and model.purpose == "SUBJECT",
    )
    if model is None or pair is None:
        return None, tuple(checks)
    harness, profile = pair
    provider = next(p for p in catalog.providers if p.provider_id == model.provider_id)
    compatible = assess_capability(catalog, model.profile_id, profile.profile_id)
    check("MODEL_HARNESS_COMPATIBLE", compatible.status is CompatibilityStatus.SUPPORTED)
    check("CREDENTIAL_REFERENCE_PRESENT", model.credential_reference in credentials)
    check(
        "PROVIDER_ROUTE_VALID",
        model.runtime_endpoint_fingerprint is not None and not provider.configuration_reason_codes,
    )
    check(
        "PROVIDER_NOT_KNOWN_BLOCKED",
        provider.health_status.value not in {"UNAVAILABLE", "QUOTA_EXHAUSTED"},
    )
    worker_recheck = bool(os.environ.get("HARNESSLAB_LOCAL_EXECUTION_POLICY"))
    # Execution-enabled API processes require no Docker socket or CLI privilege.
    image = (
        policy.runtime_images.get(harness.image_reference)
        if worker_recheck
        else local_image_identity(harness.image_reference)
    )
    check(
        "OPERATOR_RUNTIME_IMAGE_ID_PRESENT" if worker_recheck else "PINNED_LOCAL_IMAGE_PRESENT",
        image is not None,
    )
    check(
        "LOCAL_RUNTIME_IMAGE_APPROVED",
        image is not None and policy.runtime_images.get(harness.image_reference) == image,
    )
    check("EXPLICIT_BUDGET_REQUIRED", request.budget is not None)
    if request.budget is not None:
        check(
            "TASK_WALL_TIME_LIMIT",
            request.budget.wall_time_seconds <= package.definition.budget.timeout_seconds,
        )
        check(
            "OUTPUT_ESTIMATE_WITHIN_PROFILE",
            request.budget.output_tokens_estimate <= model.max_output_tokens,
        )
    if not all(c.passed for c in checks) or image is None:
        return None, tuple(checks)
    configuration = FrozenConfiguration(
        runtime_probe=(
            "OPERATOR_IMAGE_ID_WORKER_RECHECK_REQUIRED"
            if worker_recheck
            else "LOCAL_IMAGE_METADATA_ONLY"
        ),
        provider=FrozenProvider.model_validate(provider.model_dump(mode="json")),
        model=FrozenModelProfile.model_validate(model.model_dump(mode="json")),
        harness=harness,
        harness_profile=profile,
        configuration_identity=canonical_digest(
            {
                "provider": provider.model_dump(mode="json"),
                "model": model.model_dump(mode="json"),
                "harness": harness.model_dump(mode="json"),
                "profile": profile.model_dump(mode="json"),
            }
        ),
        image_identity=image,
        application_version=__version__,
        application_code_identity=application_code_identity(),
    )
    seed = canonical_digest(
        {
            "request": request.model_dump(mode="json"),
            "task": task.model_dump(mode="json"),
            "configuration": configuration.model_dump(mode="json"),
            "policy": policy.identity,
        }
    )
    custom = build_custom_plan(
        CustomPlanRequest(
            evaluation_id="local-plan-" + seed[7:31],
            name=request.name,
            preset=CustomEvaluationPreset.QUICK,
            task_references=(request.task_reference,),
            targets=(
                CustomTarget(
                    id="codex",
                    requested_model=model.requested_model,
                    harness="codex",
                    harness_version=harness.version,
                ),
            ),
        ),
        task_store(policy),
    )
    payload = {
        "request": request.model_dump(mode="json"),
        "task": task.model_dump(mode="json"),
        "configuration": configuration.model_dump(mode="json"),
        "policy_identity": policy.identity,
        "custom_plan": custom.model_dump(mode="json"),
        "budget_semantics": {
            "attempts": "EXACTLY_ONE_PLANNED_ATTEMPT_NO_RUN_CREATED",
            "wall_time_seconds": "EXISTING_CODEX_RUNNER_TIMEOUT_SUPPORTED_WORKER_MUST_APPLY",
            "output_tokens_estimate": "ESTIMATE_ONLY_NOT_ENFORCED_BY_CODEX",
            "cost_budget_usd": "REFERENCE_ONLY_NO_HARD_COST_CAP_OR_RESERVATION",
            "active_enforcement": (
                "NONE_PLAN_ONLY_SEPARATE_EXECUTION_AUTHORIZATION_REQUIRED"
                if worker_recheck
                else "NONE_PHASE1_EXECUTION_DISABLED"
            ),
        },
        "workspace_policy": "ISOLATED_COPY_REQUIRED_HIDDEN_ASSETS_EXCLUDED",
    }
    return PlanMaterial.model_validate(
        {**payload, "material_digest": canonical_digest(payload)}
    ), tuple(checks)


async def preflight(
    session: AsyncSession,
    request: PlanRequest,
    catalog: RegistryCatalog,
    credentials: frozenset[str],
) -> PreflightReceipt:
    material, checks = assess(request, catalog, credentials)
    now = datetime.now(UTC)
    payload = {
        "schema_version": 1,
        "receipt_id": "preflight-" + uuid4().hex,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
        "status": "READY_TO_SAVE" if material else "BLOCKED",
        "checks": [c.model_dump(mode="json") for c in checks],
        "material": material.model_dump(mode="json") if material else None,
        "execution_authorized": False,
        "provider_calls": 0,
        "verifier_calls": 0,
    }
    receipt = PreflightReceipt.model_validate(
        {**payload, "receipt_digest": canonical_digest(payload)}
    )
    if material:
        session.add(
            LocalPlanPreflightRecord(
                id=receipt.receipt_id,
                digest=receipt.receipt_digest,
                document=receipt.model_dump(mode="json"),
            )
        )
        await session.commit()
    return receipt


def validated_plan(row: LocalTaskPlanRecord) -> SavedPlan:
    try:
        plan = SavedPlan.model_validate(row.document)
        if (
            plan.plan_id != row.id
            or plan.plan_digest != row.digest
            or plan.preflight.receipt_id != row.preflight_id
        ):
            raise ValueError("record mismatch")
        return plan
    except ValueError:
        raise fail(
            "PLAN_INTEGRITY_ERROR", "Stored plan integrity failed; no replacement was created.", 409
        ) from None


async def duplicate(session: AsyncSession, request: PlanConfirmation) -> SavedPlan | None:
    row = await session.scalar(
        select(LocalTaskPlanRecord).where(
            LocalTaskPlanRecord.idempotency_key == str(request.idempotency_key)
        )
    )
    if row is None:
        row = await session.scalar(
            select(LocalTaskPlanRecord).where(
                LocalTaskPlanRecord.preflight_id == request.receipt_id
            )
        )
    if row is None:
        return None
    plan = validated_plan(row)
    if (
        plan.preflight.receipt_id != request.receipt_id
        or plan.preflight.receipt_digest != request.receipt_digest
    ):
        raise fail(
            "IDEMPOTENCY_CONFLICT", "This request key is already bound to a different plan.", 409
        )
    return plan


async def confirm(
    session: AsyncSession,
    request: PlanConfirmation,
    catalog: RegistryCatalog,
    credentials: frozenset[str],
) -> SavedPlan:
    existing = await duplicate(session, request)
    if existing is not None:
        return existing
    row = await session.get(LocalPlanPreflightRecord, request.receipt_id)
    if row is None:
        raise fail("PREFLIGHT_REQUIRED", "Run a successful preflight before saving a plan.", 409)
    try:
        receipt = PreflightReceipt.model_validate(row.document)
        if (
            row.id != receipt.receipt_id
            or row.digest != receipt.receipt_digest
            or receipt.receipt_digest != request.receipt_digest
            or receipt.material is None
            or receipt.status != "READY_TO_SAVE"
        ):
            raise ValueError("receipt mismatch")
    except ValueError:
        raise fail(
            "PREFLIGHT_INTEGRITY_ERROR", "Preflight identity does not match the confirmation.", 409
        ) from None
    if receipt.expires_at <= datetime.now(UTC):
        raise fail(
            "PREFLIGHT_EXPIRED", "Preflight expired. Check the current configuration again.", 409
        )
    current, _checks = assess(receipt.material.request, catalog, credentials)
    if current is None or current.material_digest != receipt.material.material_digest:
        raise fail(
            "PREFLIGHT_STALE",
            "Task, configuration, runtime or admission changed. Preflight again.",
            409,
        )
    payload = {
        "schema_version": 1,
        "plan_id": "plan-" + receipt.receipt_digest[7:39],
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "preflight": receipt.model_dump(mode="json"),
        "status": "SAVED_PLAN_ONLY",
        "execution_authorized": False,
        "runs_created": 0,
        "episodes_created": 0,
    }
    plan = SavedPlan.model_validate({**payload, "plan_digest": canonical_digest(payload)})
    session.add(
        LocalTaskPlanRecord(
            id=plan.plan_id,
            preflight_id=receipt.receipt_id,
            idempotency_key=str(request.idempotency_key),
            digest=plan.plan_digest,
            document=plan.model_dump(mode="json"),
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await duplicate(session, request)
        if existing is None:
            raise fail(
                "IMMUTABLE_PLAN_CONFLICT", "Plan identity conflicts with a saved document.", 409
            ) from None
        return existing
    return plan
