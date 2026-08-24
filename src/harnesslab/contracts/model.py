from __future__ import annotations

from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.provider import ThinkingMode, ThinkingTransport


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
    base_url: str = Field(min_length=1, max_length=500)
    route: str = Field(min_length=1, max_length=300)
    protocol: Protocol
    reasoning: ReasoningProfile = Field(default_factory=ReasoningProfile)
    thinking_mode: ThinkingMode | None = None
    thinking_transport: ThinkingTransport | None = None
    request_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    credential_reference: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]*$",
        description="Environment-variable name only; never a credential value.",
    )

    @field_validator("base_url")
    @classmethod
    def base_url_is_safe(cls, value: str) -> str:
        try:
            value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("base_url must use canonical ASCII URL text") from exc
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTPS URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url must not contain credentials")
        hostname = parsed.hostname
        if hostname is None:
            raise ValueError("base_url must contain a hostname")
        if parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain a query or fragment")
        path_parts = parsed.path.split("/")[1:]
        if path_parts and path_parts[-1] == "":
            path_parts.pop()
        if unquote(parsed.path) != parsed.path or any(
            part in {"", ".", ".."} for part in path_parts
        ):
            raise ValueError("base_url path must have canonical unencoded segments")
        canonical_host = hostname.casefold()
        if ":" in canonical_host:
            canonical_host = f"[{canonical_host}]"
        authority = canonical_host
        if parsed.port is not None:
            authority = f"{authority}:{parsed.port}"
        return f"https://{authority}{parsed.path.rstrip('/')}"

    @field_validator("route")
    @classmethod
    def route_is_safe(cls, value: str) -> str:
        try:
            value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("route must use canonical ASCII URL text") from exc
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("route must be a single-origin absolute path")
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("route must not contain an origin, query, or fragment")
        if unquote(parsed.path) != parsed.path or any(
            part in {"", ".", ".."} for part in parsed.path.split("/")[1:]
        ):
            raise ValueError("route must have canonical unencoded segments")
        return value

    @model_validator(mode="after")
    def protocol_route_is_core(self) -> ModelProfile:
        expected_suffix = {
            Protocol.RESPONSES: "/responses",
            Protocol.MESSAGES: "/messages",
            Protocol.CHAT_COMPLETIONS: "/chat/completions",
        }.get(self.protocol)
        if expected_suffix is not None and not self.route.endswith(expected_suffix):
            raise ValueError(f"{self.protocol.value} route must end with {expected_suffix}")
        if (self.thinking_mode is None) != (self.thinking_transport is None):
            raise ValueError("thinking mode and typed transport must be selected together")
        if self.thinking_transport is not None and self.protocol is not Protocol.CHAT_COMPLETIONS:
            raise ValueError("typed thinking options require Chat Completions")
        return self
