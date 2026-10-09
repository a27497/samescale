from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from harnesslab.contracts.common import Sha256Digest
from harnesslab.local_plans.models import PlanningBudget
from harnesslab.registry.models import RegistryModel, canonical_digest


class ExecutionPolicy(RegistryModel):
    schema_version: Literal[1] = 1
    mode: Literal["FAKE_CODEX"] = "FAKE_CODEX"
    artifact_root: Path
    runtime_root: Path
    subject_image_identity: Sha256Digest
    verifier_image_identity: Sha256Digest
    # Fake is trusted host code, not a user-provided script or an oracle reader.
    fixture_task_identities: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=20)
    scenario: Literal["solve", "wrong_workspace", "timeout", "slow", "verifier_timeout"] = "solve"
    authorization_ttl_seconds: int = Field(default=300, ge=1, le=900, strict=True)
    lease_seconds: int = Field(default=15, ge=5, le=120, strict=True)

    @property
    def identity(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class AuthorizationRequest(RegistryModel):
    plan_digest: Sha256Digest
    run_slot_digest: Sha256Digest
    idempotency_key: UUID
    mode: Literal["FAKE_CODEX", "REAL_CODEX"]
    confirmed_budget: PlanningBudget
    max_model_cost_usd: float = Field(ge=0, le=1000, allow_inf_nan=False)
    confirm_one_attempt: bool = Field(strict=True)
    acknowledge_reference_budgets: bool = Field(strict=True)

    @model_validator(mode="after")
    def explicit_confirmation(self) -> AuthorizationRequest:
        if not self.confirm_one_attempt or not self.acknowledge_reference_budgets:
            raise ValueError("Separate one-attempt authorization and budget confirmation required")
        return self


class ExecutionAuthorization(RegistryModel):
    authorization_id: str
    plan_id: str
    plan_digest: Sha256Digest
    run_slot_digest: Sha256Digest
    request: AuthorizationRequest
    operator_identity: Sha256Digest
    execution_policy_identity: Sha256Digest
    created_at: datetime
    expires_at: datetime
    model_calls_allowed: Literal[0] = 0
    cost_enforcement: Literal["ZERO_MODEL_CALLS_NETWORK_NONE_NO_CREDENTIALS"] = (
        "ZERO_MODEL_CALLS_NETWORK_NONE_NO_CREDENTIALS"
    )
    token_enforcement: Literal["REFERENCE_ONLY_NOT_A_HARD_LIMIT"] = (
        "REFERENCE_ONLY_NOT_A_HARD_LIMIT"
    )
    digest: Sha256Digest

    @model_validator(mode="after")
    def bound(self) -> ExecutionAuthorization:
        if self.digest != canonical_digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("Execution authorization integrity failed")
        if (
            self.request.plan_digest != self.plan_digest
            or self.request.run_slot_digest != self.run_slot_digest
        ):
            raise ValueError("Authorization request binding failed")
        if self.request.mode != "FAKE_CODEX" or self.request.max_model_cost_usd != 0:
            raise ValueError("This boundary grants zero model calls only")
        return self
