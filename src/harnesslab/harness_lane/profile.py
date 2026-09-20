from __future__ import annotations

import hashlib
import json

from harnesslab.contracts.provider import ProviderProvenance
from harnesslab.harness_lane.models import CodexHarnessProfile
from harnesslab.sandbox.models import ImageIdentity

CODEX_CLI_VERSION = "0.149.0"
CODEX_IMAGE = "harnesslab-phase-e-codex:0.149.0"
CURRENT_CODEX_CLI_VERSION = "0.153.4"
CURRENT_CODEX_IMAGE = "harnesslab-codex:0.153.4"
SUPPORTED_CODEX_IMAGES = {
    CODEX_CLI_VERSION: CODEX_IMAGE,
    CURRENT_CODEX_CLI_VERSION: CURRENT_CODEX_IMAGE,
}
CODEX_PROVIDER_ROUTE = "codex-cli-default"
SUBJECT_TOOLCHAIN_PROFILE = "python3.12.11+temurin21-jdk+node24-bookworm"
SHELL_TOOL_ENVIRONMENT_POLICY = (
    "inherit=core;ignore_default_excludes=false;"
    "exclude=*KEY*,*SECRET*,*TOKEN*,*PASSWORD*;allow_login_shell=false"
)
CODEX_PERMISSION_PROFILE = "harnesslab-outer-sandbox"
CODEX_PERMISSION_FILESYSTEM_OVERRIDE = (
    'permissions.harnesslab-outer-sandbox.filesystem={":root"="write"}'
)
CODEX_PERMISSION_NETWORK_OVERRIDE = "permissions.harnesslab-outer-sandbox.network.enabled=false"


def canonical_codex_profile(
    image: ImageIdentity,
    *,
    requested_model: str = "gpt-5.6-sol",
    reasoning_effort: str = "high",
    execution_timeout_seconds: float = 300,
) -> CodexHarnessProfile:
    return CodexHarnessProfile(
        codex_cli_version=CODEX_CLI_VERSION,
        requested_model=requested_model,
        provider_route=CODEX_PROVIDER_ROUTE,
        reasoning_effort=reasoning_effort,
        built_in_behavior_profile=f"codex-cli-{CODEX_CLI_VERSION}-built-ins",
        execution_timeout_seconds=execution_timeout_seconds,
        codex_image=image,
        subject_toolchain_profile=SUBJECT_TOOLCHAIN_PROFILE,
        shell_tool_environment_policy=SHELL_TOOL_ENVIRONMENT_POLICY,
    )


def configured_gpt56_relay_codex_profile(
    image: ImageIdentity,
    *,
    provider_base_url_reference: str,
    reasoning_effort: str,
    execution_timeout_seconds: float = 90,
) -> CodexHarnessProfile:
    """Build the one typed K-B0 Codex relay provider; no free-form config is accepted."""

    if provider_base_url_reference != "HARNESSLAB_GPT56_RELAY_BASE_URL":
        raise ValueError("Codex relay base URL reference is not canonical")
    route = "gpt56-relay|responses|env:HARNESSLAB_GPT56_RELAY_BASE_URL/responses"
    provider = {
        "model_provider_id": "harnesslab_gpt56_relay",
        "provider_provenance": ProviderProvenance.TRUSTED_THIRD_PARTY_RELAY,
        "provider_base_url_reference": provider_base_url_reference,
        "provider_route": route,
        "provider_wire_api": "responses",
        "provider_credential_reference": "HARNESSLAB_GPT56_RELAY_API_KEY",
        "provider_supports_websockets": False,
    }
    canonical = json.dumps(provider, sort_keys=True, separators=(",", ":"), default=str)
    return CodexHarnessProfile(
        codex_cli_version=CODEX_CLI_VERSION,
        requested_model="gpt-5.6-sol",
        reasoning_effort=reasoning_effort,
        built_in_behavior_profile=f"codex-cli-{CODEX_CLI_VERSION}-built-ins",
        execution_timeout_seconds=execution_timeout_seconds,
        codex_image=image,
        subject_toolchain_profile=SUBJECT_TOOLCHAIN_PROFILE,
        shell_tool_environment_policy=SHELL_TOOL_ENVIRONMENT_POLICY,
        ignore_user_config=False,
        provider_config_digest="sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        **provider,
    )


def configured_responses_relay_codex_profile(
    image: ImageIdentity,
    *,
    requested_model: str,
    reasoning_effort: str = "high",
    execution_timeout_seconds: float = 600,
) -> CodexHarnessProfile:
    """Operator-only current relay profile; model identity is a request, not attestation.

    This does not register a model, resolve credentials, or authorize execution.
    Keep the historical K-B0 factory and its identities unchanged.
    """
    if image.reference != CURRENT_CODEX_IMAGE:
        raise ValueError("Current relay requires the separately pinned Codex image")
    provider = {
        "model_provider_id": "harnesslab_responses_relay",
        "provider_provenance": ProviderProvenance.TRUSTED_THIRD_PARTY_RELAY,
        "provider_base_url_reference": "HARNESSLAB_CODEX_RELAY_BASE_URL",
        "provider_route": "custom-relay|responses|env:HARNESSLAB_CODEX_RELAY_BASE_URL/responses",
        "provider_wire_api": "responses",
        "provider_credential_reference": "HARNESSLAB_CODEX_RELAY_API_KEY",
        "provider_supports_websockets": False,
    }
    canonical = json.dumps(provider, sort_keys=True, separators=(",", ":"), default=str)
    return CodexHarnessProfile(
        codex_cli_version=CURRENT_CODEX_CLI_VERSION,
        requested_model=requested_model,
        reasoning_effort=reasoning_effort,
        built_in_behavior_profile=f"codex-cli-{CURRENT_CODEX_CLI_VERSION}-built-ins",
        execution_timeout_seconds=execution_timeout_seconds,
        codex_image=image,
        subject_toolchain_profile=SUBJECT_TOOLCHAIN_PROFILE,
        shell_tool_environment_policy=SHELL_TOOL_ENVIRONMENT_POLICY,
        ignore_user_config=False,
        provider_config_digest="sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        **provider,
    )
