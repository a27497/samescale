from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.contracts.harness import HarnessProfile
from harnesslab.contracts.model import ModelProfile
from harnesslab.contracts.task import TaskDefinition


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    repetitions: int = Field(default=1, gt=0, le=10_000)
    prompt_hash: Sha256Digest
    harness_config_digest: Sha256Digest
    sandbox_image: str = Field(min_length=1, max_length=300)
    judge_definition: str | None = Field(default=None, max_length=300)
    seed: int | None = None


class ExperimentDefinition(BaseModel):
    """The explicit Task x Model x Harness x Config experimental unit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Identifier
    task: TaskDefinition
    model: ModelProfile
    harness: HarnessProfile
    config: ExperimentConfig
