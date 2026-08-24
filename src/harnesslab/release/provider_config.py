from __future__ import annotations

from collections.abc import Mapping

from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.contracts.provider import ProviderProfile


def configured_model_profile(
    profile: ProviderProfile, environment: Mapping[str, str]
) -> ModelProfile:
    """Resolve a frozen non-secret profile into an executable direct/Judge profile offline."""

    return ModelProfile(
        requested_model=profile.requested_model,
        provider=profile.provider_id,
        base_url=profile.resolve_base_url(environment),
        route=profile.route,
        protocol=profile.protocol,
        reasoning=ReasoningProfile(
            effort=profile.reasoning_effort,
            max_output_tokens=profile.max_output_tokens,
        ),
        thinking_mode=profile.thinking_mode,
        thinking_transport=profile.thinking_transport,
        request_timeout_seconds=profile.timeout_seconds,
        credential_reference=profile.credential_reference,
    )
