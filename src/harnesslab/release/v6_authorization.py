from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harnesslab.contracts.common import Sha256Digest

V6_MATRIX_EXECUTION_PROFILE_IDENTITY = (
    "sha256:85117b2577f3456e0df573ed2467d19dee64bebca748e178bd92017dea6133b7"
)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class V6CanaryAuthorizationRequest(_FrozenModel):
    """Operator-owned authority for only the preregistered three-call V6 canary."""

    schema_version: Literal[1] = 1
    scope: Literal["CORE_REAL_MATRIX_V6_THREE_CALL_CANARY"]
    authorization_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{2,99}$")
    operator_reference: str = Field(min_length=1, max_length=200)
    authorized_at: datetime
    experiment_id: Literal["core-real-matrix-v6"]
    plan_digest: Literal["sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a"]
    canary_plan_digest: Sha256Digest
    preflight_receipt_digest: Sha256Digest
    spend_authorized: Literal[True]
    allow_real_canary: Literal[True]
    max_primary_calls: Literal[3] = 3
    retries: Literal[0] = 0
    semantic_retries: Literal[0] = 0
    substitutions: Literal[0] = 0
    matrix_execution_authorized: Literal[False] = False

    @field_validator("authorized_at")
    @classmethod
    def authorization_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authorization timestamp must include a timezone")
        return value


class V6CanaryAuthorizationReceipt(V6CanaryAuthorizationRequest):
    authorization_digest: Sha256Digest

    @property
    def expected_authorization_digest(self) -> str:
        return _digest(self.model_dump(mode="json", exclude={"authorization_digest"}))

    @model_validator(mode="after")
    def digest_is_bound(self) -> V6CanaryAuthorizationReceipt:
        if self.authorization_digest != self.expected_authorization_digest:
            raise ValueError("V6 canary authorization digest mismatch")
        return self


class V6MatrixAuthorizationReceipt(_FrozenModel):
    """A deliberately disjoint gate for a future 630-slot V6 Matrix authorization."""

    schema_version: Literal[1] = 1
    scope: Literal["CORE_REAL_MATRIX_V6_630_SLOT_MATRIX"]
    authorization_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{2,99}$")
    operator_reference: str = Field(min_length=1, max_length=200)
    authorized_at: datetime
    experiment_id: Literal["core-real-matrix-v6"]
    plan_digest: Literal["sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a"]
    authorized_slot_count: Literal[630]
    execution_profile_identity: Literal[
        "sha256:85117b2577f3456e0df573ed2467d19dee64bebca748e178bd92017dea6133b7"
    ]
    pricing_inputs_digest: Sha256Digest
    spend_authorized: Literal[True]
    matrix_execution_authorized: Literal[True]
    authorization_digest: Sha256Digest

    @property
    def expected_authorization_digest(self) -> str:
        return _digest(self.model_dump(mode="json", exclude={"authorization_digest"}))

    @model_validator(mode="after")
    def digest_is_bound(self) -> V6MatrixAuthorizationReceipt:
        if self.authorized_at.tzinfo is None or self.authorized_at.utcoffset() is None:
            raise ValueError("Matrix authorization timestamp must include a timezone")
        if self.authorization_digest != self.expected_authorization_digest:
            raise ValueError("V6 Matrix authorization digest mismatch")
        return self


def issue_v6_canary_authorization(
    request: V6CanaryAuthorizationRequest,
) -> V6CanaryAuthorizationReceipt:
    raw = request.model_dump(mode="json")
    return V6CanaryAuthorizationReceipt.model_validate(
        {**raw, "authorization_digest": _digest(raw)}
    )


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


__all__ = [
    "V6_MATRIX_EXECUTION_PROFILE_IDENTITY",
    "V6CanaryAuthorizationReceipt",
    "V6CanaryAuthorizationRequest",
    "V6MatrixAuthorizationReceipt",
    "issue_v6_canary_authorization",
]
