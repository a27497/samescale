from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.custom_eval.models import CustomEvaluationPlan
from harnesslab.local_execution.subscription import SubscriptionPlanningBudget
from harnesslab.registry.models import (
    HarnessDefinition,
    HarnessProfileDefinition,
    ProviderDefinition,
    ProviderModelProfile,
    RegistryModel,
    canonical_digest,
)


class PlanningBudget(RegistryModel):
    wall_time_seconds: int = Field(gt=0, le=3600, strict=True)
    output_tokens_estimate: int = Field(gt=0, le=1_000_000, strict=True)
    cost_budget_usd: float = Field(gt=0, le=1000, allow_inf_nan=False)


class PlanRequest(RegistryModel):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    task_reference: str = Field(pattern=r"^[a-zA-Z0-9._-]+@[0-9]+\.[0-9]+\.[0-9]+$", max_length=160)
    provider_profile_id: Identifier
    harness_profile_id: Identifier
    budget: PlanningBudget | SubscriptionPlanningBudget | None = None


class TaskInspection(RegistryModel):
    reference: str
    task_owner: str
    task_category: str
    task_identity: Sha256Digest
    workspace_identity: Sha256Digest
    verifier_identity: Sha256Digest
    oracle_identity: Sha256Digest
    managed_snapshot_identity: Sha256Digest
    source_root_id: str
    source_relative_path: str
    source_identity: Sha256Digest
    structural_validation: Literal["PASS"] = "PASS"
    behavioral_validation: Literal["TRUSTED_PRIOR_RESULT", "NOT_VERIFIED"]
    qualification_identity: Sha256Digest | None
    eligible_for_planning: bool
    reason_codes: tuple[str, ...]
    verifier_executed: Literal[False] = False


class FrozenProvider(ProviderDefinition):
    # A plan snapshot must use the same canonical keys in storage, HTTP and its digest.
    # Keep Registry's historical public credential_ref alias outside this new DTO.
    credential_reference: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")


class FrozenModelProfile(ProviderModelProfile):
    credential_reference: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")


class FrozenConfiguration(RegistryModel):
    provider: FrozenProvider
    model: FrozenModelProfile
    harness: HarnessDefinition
    harness_profile: HarnessProfileDefinition
    configuration_identity: Sha256Digest
    image_identity: Sha256Digest
    application_version: str
    application_code_identity: Sha256Digest
    runtime_probe: Literal[
        "LOCAL_IMAGE_METADATA_ONLY", "OPERATOR_IMAGE_ID_WORKER_RECHECK_REQUIRED"
    ] = "LOCAL_IMAGE_METADATA_ONLY"
    provider_health: Literal["NOT_PROBED"] = "NOT_PROBED"


class PlanMaterial(RegistryModel):
    request: PlanRequest
    task: TaskInspection
    configuration: FrozenConfiguration
    policy_identity: Sha256Digest
    custom_plan: CustomEvaluationPlan
    # These describe the required future enforcement, not an active reservation.
    budget_semantics: dict[str, str]
    workspace_policy: Literal["ISOLATED_COPY_REQUIRED_HIDDEN_ASSETS_EXCLUDED"] = (
        "ISOLATED_COPY_REQUIRED_HIDDEN_ASSETS_EXCLUDED"
    )
    material_digest: Sha256Digest

    @model_validator(mode="after")
    def exact_single_attempt(self) -> PlanMaterial:
        if self.material_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"material_digest"})
        ):
            raise ValueError("material digest mismatch")
        if (
            len(self.custom_plan.targets) != 1
            or len(self.custom_plan.tasks) != 1
            or len(self.custom_plan.run_slots) != 1
            or self.custom_plan.repeat_count != 1
            or not self.task.eligible_for_planning
            or self.request.budget is None
        ):
            raise ValueError("a plan must contain exactly one admitted task and one attempt")
        return self


class PlanningCheck(RegistryModel):
    code: str
    passed: bool


class PreflightReceipt(RegistryModel):
    schema_version: Literal[1] = 1
    receipt_id: str
    created_at: datetime
    expires_at: datetime
    status: Literal["READY_TO_SAVE", "BLOCKED"]
    checks: tuple[PlanningCheck, ...]
    material: PlanMaterial | None
    execution_authorized: Literal[False] = False
    provider_calls: Literal[0] = 0
    verifier_calls: Literal[0] = 0
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def receipt_is_bound(self) -> PreflightReceipt:
        if self.receipt_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_digest"})
        ):
            raise ValueError("preflight digest mismatch")
        ready = all(c.passed for c in self.checks) and self.material is not None
        if not self.checks or ready != (self.status == "READY_TO_SAVE"):
            raise ValueError("preflight status mismatch")
        return self


class PlanConfirmation(RegistryModel):
    receipt_id: str = Field(max_length=100)
    receipt_digest: Sha256Digest
    idempotency_key: UUID
    confirm_plan_only: bool = Field(strict=True)

    @field_validator("confirm_plan_only")
    @classmethod
    def explicit_confirmation(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("explicit plan-only confirmation is required")
        return value


class SavedPlan(RegistryModel):
    schema_version: Literal[1] = 1
    plan_id: str
    created_at: datetime
    preflight: PreflightReceipt
    status: Literal["SAVED_PLAN_ONLY"] = "SAVED_PLAN_ONLY"
    execution_authorized: Literal[False] = False
    runs_created: Literal[0] = 0
    episodes_created: Literal[0] = 0
    plan_digest: Sha256Digest

    @model_validator(mode="after")
    def saved_plan_is_bound(self) -> SavedPlan:
        if self.preflight.status != "READY_TO_SAVE" or self.plan_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"plan_digest"})
        ):
            raise ValueError("saved plan integrity mismatch")
        return self
