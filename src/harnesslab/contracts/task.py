from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from harnesslab.contracts.common import EvaluationLane, Identifier, NetworkPolicy, Sha256Digest


class WorkspaceReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    uri: str = Field(min_length=1, max_length=500)
    digest: Sha256Digest


class ContextBundleReference(BaseModel):
    """Immutable identity for context supplied to model-only or paired evaluations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uri: str = Field(min_length=1, max_length=500)
    digest: Sha256Digest


class VerifierReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)


class ResourceBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    timeout_seconds: int = Field(gt=0, le=86_400)
    max_output_tokens: int | None = Field(default=None, gt=0)
    network_policy: NetworkPolicy = NetworkPolicy.DENY


class TaskDefinition(BaseModel):
    """Immutable task contract; execution and hidden verification are deliberately out of scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Identifier
    version: str = Field(min_length=1, max_length=100)
    domain: str = Field(min_length=1, max_length=100)
    lane_support: frozenset[EvaluationLane] = Field(min_length=1)
    instruction: str = Field(min_length=1)
    workspace: WorkspaceReference
    context_bundle: ContextBundleReference | None = None
    verifier: VerifierReference
    budget: ResourceBudget
    content_digest: Sha256Digest
