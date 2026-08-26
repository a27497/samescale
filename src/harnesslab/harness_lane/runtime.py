from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from harnesslab.harness_lane.profile import CODEX_CLI_VERSION, CODEX_IMAGE
from harnesslab.harness_lane.toolchains import extract_tool_version
from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.preflight import _docker_runtime_preflight
from harnesslab.sandbox.subprocess_loop import run_on_subprocess_loop

REQUIRED_EXEC_HELP = (
    "--json",
    "--strict-config",
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    "--skip-git-repo-check",
    "--color",
    "--cd",
    "--model",
)


@dataclass(frozen=True)
class CodexRuntimeDoctor:
    image: ImageIdentity
    version: str
    required_flags: tuple[str, ...]
    tool_versions: dict[str, str]


class CodexRuntime:
    async def ensure_image(self) -> ImageIdentity:
        return await run_on_subprocess_loop(self._ensure_image())

    async def _ensure_image(self) -> ImageIdentity:
        _, environment = await _docker_runtime_preflight()
        cli = _DockerCLI(output_limit=1_000_000, environment=environment)
        inspected = await cli.run("image", "inspect", CODEX_IMAGE, check=False)
        if inspected.returncode != 0:
            repository_root = Path(__file__).resolve().parents[3]
            await cli.run(
                "build",
                "--tag",
                CODEX_IMAGE,
                str(repository_root / "docker" / "codex"),
                timeout=600,
            )
        result = await cli.run(
            "image",
            "inspect",
            CODEX_IMAGE,
            "--format",
            "{{json .Id}}|{{json .RepoDigests}}",
        )
        image_id_raw, repo_digests_raw = result.stdout.decode("utf-8").strip().split("|", 1)
        return ImageIdentity(
            reference=CODEX_IMAGE,
            image_id=json.loads(image_id_raw),
            repo_digests=tuple(json.loads(repo_digests_raw) or ()),
        )

    async def doctor(self) -> CodexRuntimeDoctor:
        image = await self.ensure_image()
        return await run_on_subprocess_loop(self._doctor(image))

    async def _doctor(self, image: ImageIdentity) -> CodexRuntimeDoctor:
        _, environment = await _docker_runtime_preflight()
        cli = _DockerCLI(output_limit=1_000_000, environment=environment)
        version_result = await cli.run(
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "codex",
            CODEX_IMAGE,
            "--version",
        )
        version = version_result.stdout.decode("utf-8").strip()
        if version != f"codex-cli {CODEX_CLI_VERSION}":
            raise RuntimeError(
                f"Codex image version mismatch: expected {CODEX_CLI_VERSION}, found {version}"
            )
        help_result = await cli.run(
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "codex",
            CODEX_IMAGE,
            "exec",
            "--help",
        )
        help_text = help_result.stdout.decode("utf-8")
        missing = tuple(flag for flag in REQUIRED_EXEC_HELP if flag not in help_text)
        if missing:
            raise RuntimeError(f"Codex exec lacks required pinned flags: {missing}")
        commands = {
            "python": ("python3", "--version"),
            "java": ("java", "-version"),
            "javac": ("javac", "-version"),
            "node": ("node", "--version"),
        }
        tool_versions: dict[str, str] = {}
        for tool, command in commands.items():
            result = await cli.run(
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                command[0],
                CODEX_IMAGE,
                *command[1:],
            )
            output = (result.stdout + result.stderr).decode("utf-8", errors="strict")
            tool_versions[tool] = extract_tool_version(tool, output)
        return CodexRuntimeDoctor(
            image=image,
            version=version,
            required_flags=REQUIRED_EXEC_HELP,
            tool_versions=tool_versions,
        )
