from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from harnesslab.contracts.common import Identifier, NetworkPolicy


class HarnessProfile(BaseModel):
    """Reproducibility-relevant harness identity and configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Identifier
    adapter_type: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    git_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,40}$")
    model_mapping: dict[str, str] = Field(default_factory=dict)
    instruction_profile: str = Field(min_length=1, max_length=200)
    tool_profile: str = Field(min_length=1, max_length=200)
    network_policy: NetworkPolicy = NetworkPolicy.DENY
    trace_parser_version: str = Field(min_length=1, max_length=100)
