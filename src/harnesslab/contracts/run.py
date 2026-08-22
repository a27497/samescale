from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.contracts.common import Identifier, NetworkPolicy, Protocol, Sha256Digest


class RunStatus(StrEnum):
    PLANNED = "planned"
    QUEUED = "queued"
    CLAIMED = "claimed"
    PREPARING = "preparing"
    RUNNING = "running"
    VERIFYING = "verifying"
    SCORING = "scoring"
    COMPLETED = "completed"
    FAILED_INFRA = "failed_infra"
    FAILED_SUBJECT = "failed_subject"
    CANCELLED = "cancelled"


class RunRecord(BaseModel):
    """Run identity and comparability facts; no execution behavior lives in this contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    experiment_id: Identifier
    status: RunStatus
    task_id: Identifier
    task_version: str = Field(min_length=1, max_length=100)
    workspace_digest: Sha256Digest
    prompt_hash: Sha256Digest
    verifier_version: str = Field(min_length=1, max_length=100)
    requested_model: str = Field(min_length=1, max_length=200)
    observed_model: str | None = Field(default=None, max_length=200)
    provider: str = Field(min_length=1, max_length=100)
    route: str = Field(min_length=1, max_length=300)
    protocol: Protocol
    harness_id: Identifier
    harness_version: str = Field(min_length=1, max_length=100)
    harness_config_digest: Sha256Digest
    reasoning_budget: str | None = Field(default=None, max_length=100)
    network_policy: NetworkPolicy
    sandbox_image: str = Field(min_length=1, max_length=300)
    judge_definition: str | None = Field(default=None, max_length=300)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def timestamps_are_ordered(self) -> RunRecord:
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        return self
