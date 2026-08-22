from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    stdout_digest: str
    stderr_digest: str
    stdout_truncated: bool
    stderr_truncated: bool


class DockerCommandError(RuntimeError):
    def __init__(self, command: str, result: CommandResult) -> None:
        super().__init__(f"Docker command failed: {command} (exit {result.returncode})")
        self.result = result


class DockerCommandTimeout(TimeoutError):
    def __init__(self, result: CommandResult) -> None:
        super().__init__("Docker command timed out")
        self.result = result


async def _capture(stream: asyncio.StreamReader | None, limit: int) -> tuple[bytes, str, bool]:
    if stream is None:
        empty_digest = hashlib.sha256(b"").hexdigest()
        return b"", f"sha256:{empty_digest}", False
    captured = bytearray()
    hasher = hashlib.sha256()
    total = 0
    while chunk := await stream.read(65_536):
        total += len(chunk)
        hasher.update(chunk)
        remaining = limit - len(captured)
        if remaining > 0:
            captured.extend(chunk[:remaining])
    return bytes(captured), f"sha256:{hasher.hexdigest()}", total > limit


class _DockerCLI:
    def __init__(self, executable: str = "docker", output_limit: int = 65_536) -> None:
        self.executable = executable
        self.output_limit = output_limit

    async def run(
        self,
        *arguments: str,
        timeout: float = 60,
        environment: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> CommandResult:
        process = await asyncio.create_subprocess_exec(
            self.executable,
            *arguments,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=dict(environment) if environment is not None else None,
        )
        stdout_task = asyncio.create_task(_capture(process.stdout, self.output_limit))
        stderr_task = asyncio.create_task(_capture(process.stderr, self.output_limit))
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            stdout, stdout_digest, stdout_truncated = await stdout_task
            stderr, stderr_digest, stderr_truncated = await stderr_task
            raise DockerCommandTimeout(
                CommandResult(
                    process.returncode or -1,
                    stdout,
                    stderr,
                    stdout_digest,
                    stderr_digest,
                    stdout_truncated,
                    stderr_truncated,
                )
            ) from None
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            await asyncio.gather(stdout_task, stderr_task)
            raise
        stdout, stdout_digest, stdout_truncated = await stdout_task
        stderr, stderr_digest, stderr_truncated = await stderr_task
        result = CommandResult(
            process.returncode or 0,
            stdout,
            stderr,
            stdout_digest,
            stderr_digest,
            stdout_truncated,
            stderr_truncated,
        )
        if check and result.returncode != 0:
            raise DockerCommandError(" ".join(arguments[:2]), result)
        return result


def docker_environment(secrets: Mapping[str, str]) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(secrets)
    return environment
