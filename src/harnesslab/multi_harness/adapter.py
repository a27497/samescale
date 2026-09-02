from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from harnesslab.harness_lane.adapter import HarnessAdapterError
from harnesslab.multi_harness.models import (
    HarnessKind,
    HarnessProcessCapture,
    MultiHarnessCollection,
    MultiHarnessProfile,
)
from harnesslab.multi_harness.profile import (
    CLAUDE_CLI_VERSION,
    DEEPSEEK_CLI_VERSION,
    DEEPSEEK_NODE_ENTRYPOINT,
    DEEPSEEK_NODE_FLAG,
)
from harnesslab.multi_harness.prompt import MultiHarnessPrompt
from harnesslab.multi_harness.trace import collect_claude_stream, collect_deepseek_final


@dataclass(frozen=True)
class HarnessExecutionPlan:
    harness: HarnessKind
    argv: tuple[str, ...]
    prompt: str
    workspace: Path
    context: Path | None
    timeout_seconds: float
    task_id: str
    environment_references: tuple[tuple[str, str], ...] = ()
    environment_literals: tuple[tuple[str, str], ...] = ()


class MultiHarnessBackend(Protocol):
    @property
    def artifact_secret_values(self) -> tuple[str, ...]: ...

    async def run(self, plan: HarnessExecutionPlan) -> HarnessProcessCapture: ...


class MultiHarnessAdapter(Protocol):
    def preflight(self, profile: MultiHarnessProfile) -> None: ...

    def prepare(
        self,
        profile: MultiHarnessProfile,
        prompt: MultiHarnessPrompt,
        *,
        workspace: Path,
        context: Path | None,
        task_id: str,
    ) -> HarnessExecutionPlan: ...

    def collect(
        self, capture: HarnessProcessCapture, *, secret_values: tuple[str, ...]
    ) -> MultiHarnessCollection: ...


def _safe_paths(workspace: Path, context: Path | None) -> None:
    if not workspace.is_dir() or workspace.is_symlink():
        raise HarnessAdapterError("subject workspace is unavailable or unsafe")
    if context is not None and (not context.is_dir() or context.is_symlink()):
        raise HarnessAdapterError("subject context is unavailable or unsafe")


class ClaudeCodeAdapter:
    """Claude Code H-Lane adapter; it never decides task correctness."""

    def __init__(
        self,
        *,
        max_turns: int | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        if max_turns is not None and max_turns <= 0:
            raise HarnessAdapterError("Claude max turns must be positive")
        if max_output_tokens is not None and max_output_tokens <= 0:
            raise HarnessAdapterError("Claude max output tokens must be positive")
        self.max_turns = max_turns
        self.max_output_tokens = max_output_tokens

    def preflight(self, profile: MultiHarnessProfile) -> None:
        if profile.harness is not HarnessKind.CLAUDE_CODE:
            raise HarnessAdapterError("Claude adapter received another harness profile")
        if profile.cli_version != CLAUDE_CLI_VERSION:
            raise HarnessAdapterError(f"Claude Code must be pinned to {CLAUDE_CLI_VERSION}")

    def prepare(
        self,
        profile: MultiHarnessProfile,
        prompt: MultiHarnessPrompt,
        *,
        workspace: Path,
        context: Path | None,
        task_id: str,
    ) -> HarnessExecutionPlan:
        _safe_paths(workspace, context)
        argv: tuple[str, ...] = (
            "claude",
            "-p",
            prompt.text,
            "--output-format",
            "stream-json",
            "--verbose",
            "--no-session-persistence",
            "--permission-mode",
            "bypassPermissions",
            "--model",
            profile.requested_model,
            "--tools",
            "Read,Edit,Write,Bash",
            "--setting-sources",
            "",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-chrome",
        )
        if self.max_turns is not None:
            argv = (*argv, "--max-turns", str(self.max_turns))
        environment_references: tuple[tuple[str, str], ...] = ()
        environment_literals: tuple[tuple[str, str], ...] = (
            ("CLAUDE_CODE_DISABLE_AUTO_MEMORY", "1"),
            ("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1"),
            ("CLAUDE_CODE_NO_MODEL_FALLBACK", "1"),
            ("CLAUDE_CONFIG_DIR", "/tmp/claude-config"),
        )
        if self.max_output_tokens is not None:
            environment_literals = (
                *environment_literals,
                ("CLAUDE_CODE_MAX_OUTPUT_TOKENS", str(self.max_output_tokens)),
            )
        if profile.provider_credential_reference is not None:
            assert profile.provider_credential_reference is not None
            assert profile.provider_credential_transport is not None
            environment_references = (
                (
                    profile.provider_credential_transport.value,
                    profile.provider_credential_reference,
                ),
            )
            if profile.provider_fixed_base_url is not None:
                base_url = profile.provider_fixed_base_url
            else:
                assert profile.provider_base_url_reference is not None
                environment_references = (
                    ("ANTHROPIC_BASE_URL", profile.provider_base_url_reference),
                    *environment_references,
                )
                base_url = None
            literal_values = [
                ("ANTHROPIC_MODEL", profile.requested_model),
                *environment_literals,
            ]
            if base_url is not None:
                literal_values.insert(0, ("ANTHROPIC_BASE_URL", base_url))
            environment_literals = tuple(literal_values)
        return HarnessExecutionPlan(
            HarnessKind.CLAUDE_CODE,
            argv,
            prompt.text,
            workspace,
            context,
            profile.execution_timeout_seconds,
            task_id,
            environment_references,
            environment_literals,
        )

    def collect(
        self, capture: HarnessProcessCapture, *, secret_values: tuple[str, ...] = ()
    ) -> MultiHarnessCollection:
        return collect_claude_stream(capture, secret_values=secret_values)


class DeepSeekHarnessAdapter:
    """Public E1 `dsh --profile headless` adapter; no private test driver is used."""

    def __init__(self, *, observed_config_digest: str) -> None:
        if not observed_config_digest.startswith("sha256:"):
            raise HarnessAdapterError("DeepSeek observed config identity must be a SHA-256 digest")
        self.observed_config_digest = observed_config_digest

    def preflight(self, profile: MultiHarnessProfile) -> None:
        if profile.harness is not HarnessKind.DEEPSEEK:
            raise HarnessAdapterError("DeepSeek adapter received another harness profile")
        if profile.cli_version != DEEPSEEK_CLI_VERSION:
            raise HarnessAdapterError(f"DeepSeek Harness must be pinned to {DEEPSEEK_CLI_VERSION}")
        if self.observed_config_digest != profile.config_digest:
            raise HarnessAdapterError("DeepSeek effective config digest drifted from the profile")

    def prepare(
        self,
        profile: MultiHarnessProfile,
        prompt: MultiHarnessPrompt,
        *,
        workspace: Path,
        context: Path | None,
        task_id: str,
    ) -> HarnessExecutionPlan:
        _safe_paths(workspace, context)
        return HarnessExecutionPlan(
            HarnessKind.DEEPSEEK,
            (
                "node",
                DEEPSEEK_NODE_FLAG,
                DEEPSEEK_NODE_ENTRYPOINT,
                "--profile",
                "headless",
                prompt.text,
            ),
            prompt.text,
            workspace,
            context,
            profile.execution_timeout_seconds,
            task_id,
        )

    def collect(
        self, capture: HarnessProcessCapture, *, secret_values: tuple[str, ...] = ()
    ) -> MultiHarnessCollection:
        return collect_deepseek_final(capture, secret_values=secret_values)
