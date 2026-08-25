from __future__ import annotations

import hashlib
import ipaddress
import json
from collections.abc import Mapping
from enum import StrEnum
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harnesslab.contracts.common import Identifier, Protocol, Sha256Digest


class ProviderProvenance(StrEnum):
    FIRST_PARTY_MODEL_API = "FIRST_PARTY_MODEL_API"
    FIRST_PARTY_PLATFORM_API = "FIRST_PARTY_PLATFORM_API"
    ALIBABA_HOSTED_MODEL = "ALIBABA_HOSTED_MODEL"
    TRUSTED_THIRD_PARTY_RELAY = "TRUSTED_THIRD_PARTY_RELAY"
    THIRD_PARTY_INFERENCE_PLATFORM = "THIRD_PARTY_INFERENCE_PLATFORM"


class ConfigurationState(StrEnum):
    CONFIGURED_NOT_SMOKED = "CONFIGURED_NOT_SMOKED"


class ThinkingMode(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class ThinkingTransport(StrEnum):
    DEEPSEEK_THINKING_OBJECT = "deepseek_thinking_object"
    BAILIAN_ENABLE_THINKING = "bailian_enable_thinking"


class ProviderProfile(BaseModel):
    """Non-secret, frozen provider configuration selected for Core evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: Identifier
    provider_id: Identifier
    provider_display_name: str = Field(min_length=1, max_length=200)
    provider_provenance: ProviderProvenance
    requested_model: str = Field(min_length=1, max_length=200)
    protocol: Protocol
    base_url_reference: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    fixed_base_url: str | None = None
    route: str
    route_identity: str = Field(min_length=1, max_length=800)
    credential_reference: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    model_family: str = Field(min_length=1, max_length=100)
    inference_provider: str = Field(min_length=1, max_length=200)
    reasoning_effort: str | None = Field(default=None, max_length=50)
    thinking_mode: ThinkingMode | None = None
    thinking_transport: ThinkingTransport | None = None
    timeout_seconds: int = Field(gt=0, le=600)
    max_output_tokens: int = Field(gt=0)
    observed_model_state: str = "NOT_VERIFIED_UNTIL_SMOKE"
    configuration_state: ConfigurationState = ConfigurationState.CONFIGURED_NOT_SMOKED
    upstream_model_claim: str | None = None
    operator_trust_assertion: str | None = None
    upstream_first_party_provenance: str | None = None
    profile_digest: Sha256Digest

    @field_validator("fixed_base_url")
    @classmethod
    def fixed_url_is_safe(cls, value: str | None) -> str | None:
        return validate_provider_base_url(value) if value is not None else None

    @field_validator("route")
    @classmethod
    def route_is_safe(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            not value.startswith("/")
            or value.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or unquote(value) != value
            or any(part in {"", ".", ".."} for part in value.split("/")[1:])
        ):
            raise ValueError("provider route must be a canonical single-origin path")
        return value

    @model_validator(mode="after")
    def profile_is_coherent(self) -> ProviderProfile:
        if (self.base_url_reference is None) == (self.fixed_base_url is None):
            raise ValueError("exactly one provider base URL source is required")
        suffix = {
            Protocol.RESPONSES: "/responses",
            Protocol.MESSAGES: "/messages",
            Protocol.CHAT_COMPLETIONS: "/chat/completions",
        }.get(self.protocol)
        if suffix is not None and not self.route.endswith(suffix):
            raise ValueError(f"{self.protocol.value} route must end with {suffix}")
        if (self.thinking_mode is None) != (self.thinking_transport is None):
            raise ValueError("thinking mode and transport must be selected together")
        if self.thinking_transport is not None and self.protocol is not Protocol.CHAT_COMPLETIONS:
            raise ValueError("typed thinking options are supported only by Chat Completions")
        is_relay = self.provider_provenance is ProviderProvenance.TRUSTED_THIRD_PARTY_RELAY
        relay_claims = (
            self.upstream_model_claim,
            self.operator_trust_assertion,
            self.upstream_first_party_provenance,
        )
        if is_relay and relay_claims != (
            "gpt-5.6-sol",
            "VERIFIED_BY_OPERATOR",
            "NOT_INDEPENDENTLY_VERIFIED",
        ):
            raise ValueError("trusted GPT relay requires the exact operator provenance limitation")
        if not is_relay and any(item is not None for item in relay_claims):
            raise ValueError("upstream relay claims are valid only for relay profiles")
        if self.route_identity != self.expected_route_identity:
            raise ValueError("provider route identity is not derived from the frozen endpoint")
        if self.profile_digest != self.expected_profile_digest:
            raise ValueError("provider profile digest mismatch")
        return self

    @property
    def expected_route_identity(self) -> str:
        base = (
            f"env:{self.base_url_reference}"
            if self.base_url_reference is not None
            else self.fixed_base_url
        )
        return f"{self.provider_id}|{self.protocol.value}|{base}{self.route}"

    @property
    def expected_profile_digest(self) -> str:
        raw = self.model_dump(mode="json", exclude={"profile_digest"})
        canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()

    def resolve_base_url(self, environment: Mapping[str, str]) -> str:
        if self.fixed_base_url is not None:
            return self.fixed_base_url
        assert self.base_url_reference is not None
        value = environment.get(self.base_url_reference)
        if not value:
            raise ValueError(f"missing provider URL reference: {self.base_url_reference}")
        return validate_provider_base_url(value)

    def resolved_route_identity(self, environment: Mapping[str, str]) -> str:
        endpoint = f"{self.resolve_base_url(environment)}{self.route}"
        return f"{self.provider_id}|{self.protocol.value}|{endpoint}"


def validate_provider_base_url(value: str) -> str:
    """Validate an operator URL without DNS resolution or a network connection."""

    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("provider URL must use canonical ASCII text") from exc
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.hostname is None:
        raise ValueError("provider URL must be absolute HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("provider URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("provider URL must not contain a query or fragment")
    if parsed.port not in {None, 443}:
        raise ValueError("provider URL must use HTTPS port 443")
    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname in {"localhost", "metadata.google.internal"} or hostname.endswith(
        (".localhost", ".local", ".internal")
    ):
        raise ValueError("provider URL target is local or metadata infrastructure")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("provider URL must use an allowlisted DNS hostname, not an IP literal")
    path_parts = parsed.path.split("/")[1:]
    if path_parts and path_parts[-1] == "":
        path_parts.pop()
    if unquote(parsed.path) != parsed.path or any(part in {"", ".", ".."} for part in path_parts):
        raise ValueError("provider URL path must use canonical unencoded segments")
    return f"https://{hostname}{parsed.path.rstrip('/')}"


def freeze_provider_profile(**values: object) -> ProviderProfile:
    """Construct a profile and bind its digest without accepting caller-supplied digests."""

    draft = ProviderProfile.model_construct(
        profile_digest="sha256:" + "0" * 64,
        **values,  # type: ignore[arg-type]
    )
    raw = draft.model_dump(mode="json", exclude={"profile_digest"})
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    return ProviderProfile.model_validate({**raw, "profile_digest": digest})
