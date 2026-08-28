from __future__ import annotations

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.registry.seeds import (
    ALIBABA_ANTHROPIC_BASE_URL_REFERENCE,
    ALIBABA_CREDENTIAL_REFERENCE,
    ALIBABA_OPENAI_BASE_URL_REFERENCE,
)


def configured_alibaba_bailian_profile(
    requested_model: str,
    protocol: Protocol,
    *,
    max_output_tokens: int = 2000,
) -> ModelProfile:
    """Build a secret-free, operator-configured Bailian profile without probing it."""

    if (
        not requested_model
        or len(requested_model) > 60
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in requested_model
        )
    ):
        raise ValueError("Alibaba requested model must be explicitly configured and safe")
    routes = {
        Protocol.CHAT_COMPLETIONS: (ALIBABA_OPENAI_BASE_URL_REFERENCE, "/chat/completions"),
        Protocol.RESPONSES: (ALIBABA_OPENAI_BASE_URL_REFERENCE, "/responses"),
        Protocol.MESSAGES: (ALIBABA_ANTHROPIC_BASE_URL_REFERENCE, "/v1/messages"),
    }
    try:
        base_url_reference, route = routes[protocol]
    except KeyError as exc:
        raise ValueError(
            "Alibaba supports only OpenAI-compatible Chat/Responses or Anthropic Messages"
        ) from exc
    return ModelProfile(
        requested_model=requested_model,
        provider="alibaba-bailian",
        base_url_reference=base_url_reference,
        route=route,
        protocol=protocol,
        reasoning=ReasoningProfile(max_output_tokens=max_output_tokens),
        request_timeout_seconds=180,
        credential_reference=ALIBABA_CREDENTIAL_REFERENCE,
    )
