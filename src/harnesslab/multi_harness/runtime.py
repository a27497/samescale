from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from harnesslab.harness_lane.toolchains import extract_tool_version
from harnesslab.multi_harness.models import HarnessKind
from harnesslab.multi_harness.profile import (
    CLAUDE_CLI_VERSION,
    CLAUDE_IMAGE,
    DEEPSEEK_CLI_VERSION,
    DEEPSEEK_DEFAULT_MODEL,
    DEEPSEEK_DEFAULT_PROVIDER,
    DEEPSEEK_IMAGE,
    DEEPSEEK_NODE_ENTRYPOINT,
    DEEPSEEK_NODE_FLAG,
)
from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.preflight import _docker_runtime_preflight
from harnesslab.sandbox.subprocess_loop import run_on_subprocess_loop

CLAUDE_REQUIRED_HELP = (
    "--print",
    "--output-format",
    "--verbose",
    "--no-session-persistence",
    "--permission-mode",
    "--model",
    "--tools",
    "--setting-sources",
    "--mcp-config",
    "--disable-slash-commands",
    "--no-chrome",
)
DEEPSEEK_REQUIRED_HELP = (
    "--profile <name>",
    "--dump-config",
    "--dump-default-config",
    "--version",
    'dsh --profile headless "run the tests"',
)


def _validate_deepseek_effective_config(effective_text: str) -> None:
    required = (
        f"provider: {DEEPSEEK_DEFAULT_PROVIDER}",
        f"model: {DEEPSEEK_DEFAULT_MODEL}",
    )
    if any(item not in effective_text for item in required):
        raise RuntimeError("DeepSeek effective provider/model identity drifted")


@dataclass(frozen=True)
class MultiHarnessRuntimeDoctor:
    harness: HarnessKind
    image: ImageIdentity
    version: str
    required_flags: tuple[str, ...]
    tool_versions: dict[str, str]
    config_digest: str | None = None
    default_config_digest: str | None = None


class MultiHarnessRuntime:
    def __init__(self, harness: HarnessKind) -> None:
        self.harness = harness
        if harness is HarnessKind.CLAUDE_CODE:
            self.image = CLAUDE_IMAGE
            self.docker_directory = "claude"
        else:
            self.image = DEEPSEEK_IMAGE
            self.docker_directory = "deepseek"

    async def ensure_image(self) -> ImageIdentity:
        return await run_on_subprocess_loop(self._ensure_image())

    async def _ensure_image(self) -> ImageIdentity:
        _, environment = await _docker_runtime_preflight()
        cli = _DockerCLI(output_limit=4_000_000, environment=environment)
        inspected = await cli.run("image", "inspect", self.image, check=False)
        if inspected.returncode != 0:
            root = Path(__file__).resolve().parents[3]
            await cli.run(
                "build",
                "--tag",
                self.image,
                str(root / "docker" / self.docker_directory),
                timeout=900,
            )
        result = await cli.run(
            "image", "inspect", self.image, "--format", "{{json .Id}}|{{json .RepoDigests}}"
        )
        image_id, repo_digests = result.stdout.decode().strip().split("|", 1)
        return ImageIdentity(
            reference=self.image,
            image_id=json.loads(image_id),
            repo_digests=tuple(json.loads(repo_digests) or ()),
        )

    async def doctor(self) -> MultiHarnessRuntimeDoctor:
        image = await self.ensure_image()
        return await run_on_subprocess_loop(self._doctor(image))

    async def _doctor(self, image: ImageIdentity) -> MultiHarnessRuntimeDoctor:
        _, environment = await _docker_runtime_preflight()
        cli = _DockerCLI(output_limit=4_000_000, environment=environment)
        version_result = await cli.run(
            "run", "--rm", "--network", "none", self.image, "--version", timeout=60
        )
        version = version_result.stdout.decode().strip()
        expected = (
            f"{CLAUDE_CLI_VERSION} (Claude Code)"
            if self.harness is HarnessKind.CLAUDE_CODE
            else DEEPSEEK_CLI_VERSION
        )
        if version != expected:
            raise RuntimeError(f"{self.harness.value} version mismatch: {version!r}")
        help_result = await cli.run(
            "run", "--rm", "--network", "none", self.image, "--help", timeout=60
        )
        help_text = (help_result.stdout + help_result.stderr).decode()
        required = (
            CLAUDE_REQUIRED_HELP
            if self.harness is HarnessKind.CLAUDE_CODE
            else DEEPSEEK_REQUIRED_HELP
        )
        missing = tuple(item for item in required if item not in help_text)
        if missing:
            raise RuntimeError(f"{self.harness.value} help lacks required contracts: {missing}")
        tool_versions: dict[str, str] = {}
        for tool, command in {
            "python": ("python3", "--version"),
            "java": ("java", "-version"),
            "javac": ("javac", "-version"),
            "node": ("node", "--version"),
            "sqlite": ("sqlite3", "--version"),
        }.items():
            result = await cli.run(
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                command[0],
                self.image,
                *command[1:],
            )
            tool_versions[tool] = extract_tool_version(
                tool, (result.stdout + result.stderr).decode()
            )
        config_digest = None
        default_digest = None
        if self.harness is HarnessKind.DEEPSEEK:
            default = await cli.run(
                "run",
                "--rm",
                "--network",
                "none",
                self.image,
                "--profile",
                "headless",
                "--dump-default-config",
                timeout=60,
            )
            effective = await cli.run(
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                "node",
                self.image,
                DEEPSEEK_NODE_FLAG,
                DEEPSEEK_NODE_ENTRYPOINT,
                "--profile",
                "headless",
                "--dump-config",
                timeout=60,
            )
            if not default.stdout.strip() or not effective.stdout.strip():
                raise RuntimeError("DeepSeek config dumps were empty")
            effective_text = effective.stdout.decode()
            _validate_deepseek_effective_config(effective_text)
            default_digest = "sha256:" + hashlib.sha256(default.stdout).hexdigest()
            config_digest = "sha256:" + hashlib.sha256(effective.stdout).hexdigest()
        return MultiHarnessRuntimeDoctor(
            self.harness,
            image,
            version,
            required,
            tool_versions,
            config_digest,
            default_digest,
        )
