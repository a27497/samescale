from __future__ import annotations

from harnesslab.harness_lane.models import CodexHarnessProfile
from harnesslab.sandbox.models import ImageIdentity

CODEX_CLI_VERSION = "0.149.0"
CODEX_IMAGE = "harnesslab-phase-e-codex:0.149.0"
CODEX_PROVIDER_ROUTE = "codex-cli-default"
SUBJECT_TOOLCHAIN_PROFILE = "python3.12.11+temurin21-jdk+node24-bookworm"
SHELL_TOOL_ENVIRONMENT_POLICY = (
    "inherit=core;ignore_default_excludes=false;"
    "exclude=*KEY*,*SECRET*,*TOKEN*,*PASSWORD*;allow_login_shell=false"
)


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
