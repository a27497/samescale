from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from harnesslab.contracts.common import Protocol


class ReasoningProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    effort: str | None = Field(default=None, max_length=50)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, gt=0)


class ModelProfile(BaseModel):
    """Requested model and provider route; observed identity belongs to a RunRecord."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_model: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=100)
    route: str = Field(min_length=1, max_length=300)
    protocol: Protocol
    reasoning: ReasoningProfile = Field(default_factory=ReasoningProfile)
    credential_reference: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]*$",
        description="Environment-variable name only; never a credential value.",
    )
