from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from harnesslab.harness_lane.models import (
    CodexCollection,
    CodexHarnessProfile,
    CodexProcessCapture,
    NormalizedTrace,
)
from harnesslab.harness_lane.profile import (
    CODEX_CLI_VERSION,
    CODEX_IMAGE,
    CODEX_PERMISSION_FILESYSTEM_OVERRIDE,
    CODEX_PERMISSION_NETWORK_OVERRIDE,
    CODEX_PERMISSION_PROFILE,
    SHELL_TOOL_ENVIRONMENT_POLICY,
    SUPPORTED_CODEX_IMAGES,
)
from harnesslab.harness_lane.prompt import CodexHarnessPrompt
from harnesslab.harness_lane.trace import collect_codex_jsonl


class HarnessAdapterError(RuntimeError):
    """The trusted Harness adapter could not establish its declared execution contract."""


@dataclass(frozen=True)
class CodexExecutionPlan:
    argv: tuple[str, ...]
    prompt: str
    workspace: Path
    context: Path | None
    timeout_seconds: float
    task_id: str
    environment_references: tuple[tuple[str, str], ...] = ()
    image_reference: str = CODEX_IMAGE


class CodexBackend(Protocol):
    @property
    def artifact_secret_values(self) -> tuple[str, ...]: ...

    async def run(self, plan: CodexExecutionPlan) -> CodexProcessCapture: ...


class HarnessAdapter(Protocol):
    def preflight(self, profile: CodexHarnessProfile) -> None: ...

    def prepare(
        self,
        profile: CodexHarnessProfile,
        prompt: CodexHarnessPrompt,
        *,
        workspace: Path,
        context: Path | None,
        task_id: str,
    ) -> CodexExecutionPlan: ...

    async def execute(
        self, plan: CodexExecutionPlan, backend: CodexBackend
    ) -> CodexProcessCapture: ...

    def collect(
        self, capture: CodexProcessCapture, *, secret_values: tuple[str, ...]
    ) -> CodexCollection: ...

    def normalize(self, collection: CodexCollection) -> NormalizedTrace: ...


class CodexHarnessAdapter:
    """One Codex adapter. It never decides whether the coding task is correct."""

    def preflight(self, profile: CodexHarnessProfile) -> None:
        if profile.codex_cli_version not in SUPPORTED_CODEX_IMAGES:
            raise HarnessAdapterError(
                f"Codex CLI must be pinned to a supported version; "
                f"found {profile.codex_cli_version}"
            )
        if profile.codex_cli_version != CODEX_CLI_VERSION and (
            profile.codex_image.reference != SUPPORTED_CODEX_IMAGES[profile.codex_cli_version]
        ):
            raise HarnessAdapterError("Codex image reference and CLI version disagree")
        if profile.model_provider_id == "harnesslab_responses_relay" and (
            profile.codex_cli_version == CODEX_CLI_VERSION
        ):
            raise HarnessAdapterError("Current relay requires the current Codex runtime")
        if profile.model_provider_id is not None:
            provider_refs = {
                "harnesslab_gpt56_relay": (
                    "HARNESSLAB_GPT56_RELAY_BASE_URL",
                    "HARNESSLAB_GPT56_RELAY_API_KEY",
                ),
                "harnesslab_responses_relay": (
                    "HARNESSLAB_CODEX_RELAY_BASE_URL",
                    "HARNESSLAB_CODEX_RELAY_API_KEY",
                ),
            }
            if (
                provider_refs.get(profile.model_provider_id)
                != (profile.provider_base_url_reference, profile.provider_credential_reference)
                or profile.provider_wire_api != "responses"
                or profile.provider_supports_websockets
            ):
                raise HarnessAdapterError("Codex provider does not match the runtime contract")
        if profile.codex_image.image_id == "sha256:" + "0" * 64:
            raise HarnessAdapterError("Codex image identity must come from an inspected image")
        if profile.shell_tool_environment_policy != SHELL_TOOL_ENVIRONMENT_POLICY:
            raise HarnessAdapterError("Codex shell-tool environment policy is not canonical")
        if profile.codex_permission_profile != CODEX_PERMISSION_PROFILE:
            raise HarnessAdapterError("Codex permission profile is not canonical")

    def prepare(
        self,
        profile: CodexHarnessProfile,
        prompt: CodexHarnessPrompt,
        *,
        workspace: Path,
        context: Path | None,
        task_id: str,
    ) -> CodexExecutionPlan:
        self.preflight(profile)
        if not workspace.is_dir() or workspace.is_symlink():
            raise HarnessAdapterError("subject workspace is unavailable or unsafe")
        if context is not None and (not context.is_dir() or context.is_symlink()):
            raise HarnessAdapterError("subject context is unavailable or unsafe")
        provider_config: tuple[str, ...] = ()
        environment_references: tuple[tuple[str, str], ...] = ()
        user_config_flags = ("--ignore-user-config",) if profile.ignore_user_config else ()
        if profile.model_provider_id is not None:
            assert profile.provider_base_url_reference is not None
            assert profile.provider_credential_reference is not None
            assert profile.provider_wire_api == "responses"
            provider_config = (
                "--profile",
                "harnesslab-runtime",
            )
            environment_references = (
                (
                    (
                        "HARNESSLAB_CODEX_RELAY_BASE_URL"
                        if profile.model_provider_id == "harnesslab_responses_relay"
                        else "HARNESSLAB_GPT56_RELAY_BASE_URL"
                    ),
                    profile.provider_base_url_reference,
                ),
            )
        argv = (
            "codex",
            "exec",
            "--json",
            "--strict-config",
            "--ephemeral",
            *user_config_flags,
            "--ignore-rules",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--cd",
            "/workspace",
            "--model",
            profile.requested_model,
            *provider_config,
            "-c",
            'approval_policy="never"',
            "-c",
            'web_search="disabled"',
            "-c",
            "check_for_update_on_startup=false",
            "-c",
            "features.remote_models=false",
            "-c",
            "features.remote_plugin=false",
            "-c",
            "features.plugins=false",
            "-c",
            f'default_permissions="{profile.codex_permission_profile}"',
            "-c",
            CODEX_PERMISSION_FILESYSTEM_OVERRIDE,
            "-c",
            CODEX_PERMISSION_NETWORK_OVERRIDE,
            "-c",
            f'model_reasoning_effort="{profile.reasoning_effort}"',
            "-c",
            "mcp_servers={}",
            "-c",
            'shell_environment_policy.inherit="core"',
            "-c",
            "shell_environment_policy.ignore_default_excludes=false",
            "-c",
            'shell_environment_policy.exclude=["*KEY*","*SECRET*","*TOKEN*","*PASSWORD*"]',
            "-c",
            "allow_login_shell=false",
            "-",
        )
        return CodexExecutionPlan(
            argv=argv,
            prompt=prompt.text,
            workspace=workspace,
            context=context,
            timeout_seconds=profile.execution_timeout_seconds,
            task_id=task_id,
            environment_references=environment_references,
            image_reference=profile.codex_image.image_id,
        )

    async def execute(self, plan: CodexExecutionPlan, backend: CodexBackend) -> CodexProcessCapture:
        return await backend.run(plan)

    def collect(
        self, capture: CodexProcessCapture, *, secret_values: tuple[str, ...] = ()
    ) -> CodexCollection:
        return collect_codex_jsonl(capture, secret_values=secret_values)

    def normalize(self, collection: CodexCollection) -> NormalizedTrace:
        return collection.trace
