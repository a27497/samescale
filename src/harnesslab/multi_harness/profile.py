from __future__ import annotations

from harnesslab.contracts.provider import ProviderProvenance
from harnesslab.multi_harness.models import (
    ClaudeCredentialTransport,
    DeepSeekSessionExtraction,
    HarnessKind,
    MultiHarnessProfile,
    TraceCoverage,
)
from harnesslab.multi_harness.prompt import CLAUDE_PROMPT_VERSION, DEEPSEEK_PROMPT_VERSION
from harnesslab.sandbox.models import ImageIdentity

CLAUDE_CLI_VERSION = "2.1.241"
CLAUDE_PACKAGE_INTEGRITY = (
    "sha512-S7DWEmJJAsI5taAUjhKm6soXcFJYIVeTH6Lg9kmp3yntFllCP612hGwZ7thOGh8r7YaRUH9+"
    "1jCX5A9QGazsxg=="
)
CLAUDE_IMAGE = f"harnesslab-phase-f-claude:{CLAUDE_CLI_VERSION}"
DEEPSEEK_CLI_VERSION = "0.1.1-rc.2"
DEEPSEEK_PACKAGE_INTEGRITY = (
    "sha512-UP1UIh6q3Gme/yXRn/QL2P8IsVlv8Shpg22TRJIZPsCRWLm4CBiA1MUvXmJAfsOEETBMLAl+"
    "xWPtFw6ICsN3wg=="
)
DEEPSEEK_IMAGE = f"harnesslab-phase-f-deepseek:{DEEPSEEK_CLI_VERSION}"
DEEPSEEK_NODE_ENTRYPOINT = "/usr/local/bin/dsh"
DEEPSEEK_NODE_FLAG = "--expose-internals"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"
DEEPSEEK_DEFAULT_PROVIDER = "deepseek-official"
SUBJECT_TOOLCHAIN_PROFILE = "python3.12.11+temurin21-jdk+node24-bookworm"


def canonical_claude_profile(
    image: ImageIdentity,
    *,
    requested_model: str = "sonnet",
    execution_timeout_seconds: float = 300,
) -> MultiHarnessProfile:
    return MultiHarnessProfile(
        harness=HarnessKind.CLAUDE_CODE,
        cli_version=CLAUDE_CLI_VERSION,
        package_integrity=CLAUDE_PACKAGE_INTEGRITY,
        requested_model=requested_model,
        provider_route="anthropic-api/claude-code",
        prompt_template_version=CLAUDE_PROMPT_VERSION,
        tool_profile=("Read", "Edit", "Write", "Bash"),
        output_format="stream-json+verbose",
        trace_coverage=TraceCoverage.FULL_STREAM,
        image=image,
        subject_toolchain_profile=SUBJECT_TOOLCHAIN_PROFILE,
        execution_timeout_seconds=execution_timeout_seconds,
    )


def canonical_deepseek_profile(
    image: ImageIdentity,
    config_digest: str,
    *,
    requested_model: str = DEEPSEEK_DEFAULT_MODEL,
    execution_timeout_seconds: float = 300,
) -> MultiHarnessProfile:
    return MultiHarnessProfile(
        harness=HarnessKind.DEEPSEEK,
        cli_version=DEEPSEEK_CLI_VERSION,
        package_integrity=DEEPSEEK_PACKAGE_INTEGRITY,
        requested_model=requested_model,
        provider_route=f"{DEEPSEEK_DEFAULT_PROVIDER}/dsh-api-gateway",
        prompt_template_version=DEEPSEEK_PROMPT_VERSION,
        tool_profile=("headless-profile-public-contract",),
        output_format="final-stdout",
        trace_coverage=TraceCoverage.FINAL_OUTPUT_ONLY,
        image=image,
        subject_toolchain_profile=SUBJECT_TOOLCHAIN_PROFILE,
        execution_timeout_seconds=execution_timeout_seconds,
        config_digest=config_digest,
        developer_preview=True,
        session_extraction=DeepSeekSessionExtraction.DEFERRED_NOT_VERIFIED,
    )


def configured_qwen_opencode_go_claude_profile(
    image: ImageIdentity, *, execution_timeout_seconds: float = 90
) -> MultiHarnessProfile:
    return MultiHarnessProfile(
        harness=HarnessKind.CLAUDE_CODE,
        cli_version=CLAUDE_CLI_VERSION,
        package_integrity=CLAUDE_PACKAGE_INTEGRITY,
        requested_model="qwen3.8-max",
        provider_route="opencode-go|messages|https://opencode.ai/zen/go/v1/messages",
        provider_provenance=ProviderProvenance.THIRD_PARTY_INFERENCE_PLATFORM,
        provider_fixed_base_url="https://opencode.ai/zen/go",
        provider_credential_reference="HARNESSLAB_OPENCODE_GO_API_KEY",
        provider_credential_transport=ClaudeCredentialTransport.ANTHROPIC_API_KEY,
        prompt_template_version=CLAUDE_PROMPT_VERSION,
        tool_profile=("Read", "Edit", "Write", "Bash"),
        output_format="stream-json+verbose",
        trace_coverage=TraceCoverage.FULL_STREAM,
        image=image,
        subject_toolchain_profile=SUBJECT_TOOLCHAIN_PROFILE,
        execution_timeout_seconds=execution_timeout_seconds,
    )


def configured_qwen_alibaba_bailian_claude_profile(
    image: ImageIdentity, *, execution_timeout_seconds: float = 180
) -> MultiHarnessProfile:
    return MultiHarnessProfile(
        harness=HarnessKind.CLAUDE_CODE,
        cli_version=CLAUDE_CLI_VERSION,
        package_integrity=CLAUDE_PACKAGE_INTEGRITY,
        requested_model="qwen3.8-max",
        provider_route=(
            "alibaba-bailian|messages|env:HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL/v1/messages"
        ),
        provider_provenance=ProviderProvenance.ALIBABA_HOSTED_MODEL,
        provider_base_url_reference="HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL",
        provider_credential_reference="HARNESSLAB_ALIBABA_BAILIAN_API_KEY",
        provider_credential_transport=ClaudeCredentialTransport.ANTHROPIC_API_KEY,
        prompt_template_version=CLAUDE_PROMPT_VERSION,
        tool_profile=("Read", "Edit", "Write", "Bash"),
        output_format="stream-json+verbose",
        trace_coverage=TraceCoverage.FULL_STREAM,
        image=image,
        subject_toolchain_profile=SUBJECT_TOOLCHAIN_PROFILE,
        execution_timeout_seconds=execution_timeout_seconds,
    )


def configured_deepseek_v4flash_profile(
    image: ImageIdentity,
    config_digest: str,
    *,
    execution_timeout_seconds: float = 90,
) -> MultiHarnessProfile:
    return MultiHarnessProfile(
        harness=HarnessKind.DEEPSEEK,
        cli_version=DEEPSEEK_CLI_VERSION,
        package_integrity=DEEPSEEK_PACKAGE_INTEGRITY,
        requested_model="deepseek-v4-flash",
        provider_route=(
            "deepseek-official|chat_completions|https://api.deepseek.com/chat/completions"
        ),
        prompt_template_version=DEEPSEEK_PROMPT_VERSION,
        tool_profile=("headless-profile-public-contract",),
        output_format="final-stdout",
        trace_coverage=TraceCoverage.FINAL_OUTPUT_ONLY,
        image=image,
        subject_toolchain_profile=SUBJECT_TOOLCHAIN_PROFILE,
        execution_timeout_seconds=execution_timeout_seconds,
        config_digest=config_digest,
        developer_preview=True,
        session_extraction=DeepSeekSessionExtraction.DEFERRED_NOT_VERIFIED,
    )
