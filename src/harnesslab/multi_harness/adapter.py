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
from harnesslab.multi_harness.profile import CLAUDE_CLI_VERSION, DEEPSEEK_CLI_VERSION
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
        argv = (
            "claude",
            "--bare",
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
            "--mcp-config",
            "{}",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-chrome",
        )
        return HarnessExecutionPlan(
            HarnessKind.CLAUDE_CODE,
            argv,
            prompt.text,
            workspace,
            context,
            profile.execution_timeout_seconds,
            task_id,
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
            ("dsh", "--profile", "headless", prompt.text),
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
