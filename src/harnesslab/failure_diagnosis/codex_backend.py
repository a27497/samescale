# ruff: noqa: RUF001
"""Explicit external subscription CLI; no provider keys, tool registry or subject workspace."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from harnesslab.egress import (
    EGRESS_PROXY_BASE,
    EGRESS_PROXY_IMAGE,
    EGRESS_PROXY_SOURCE_DIGEST,
    boundary_for_provider_url,
)
from harnesslab.failure_diagnosis.models import BackendObservation
from harnesslab.failure_diagnosis.service import BackendReply, ForbiddenToolError, canonical, sha256
from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.models import ImageIdentity

CLI_VERSION = "0.162.1"
CLI_SHA256 = "628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1"


def subprocess_environment() -> dict[str, str]:
    # Enumerate non-secret names. Do not iterate, read or copy arbitrary inherited variables.
    return {
        name: value
        for name in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "XDG_RUNTIME_DIR")
        if (value := os.environ.get(name)) is not None
    }


def tool_free_catalog(model: str) -> dict[str, Any]:
    return {
        "models": [
            {
                "slug": model,
                "display_name": model,
                "description": "Advisory diagnosis",
                "base_instructions": (
                    "Read only public evidence. Return advisory diagnosis JSON. No tools."
                ),
                "supported_reasoning_levels": [{"effort": "low", "description": "Diagnosis"}],
                "default_reasoning_level": "low",
                "shell_type": "disabled",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 1,
                "availability_nux": None,
                "upgrade": None,
                "model_messages": None,
                "include_apps_usage_instructions": False,
                "support_verbosity": False,
                "default_verbosity": None,
                "apply_patch_tool_type": None,
                "truncation_policy": {"mode": "bytes", "limit": 64000},
                "context_window": 200000,
                "experimental_supported_tools": [],
                "tool_mode": "direct",
            }
        ]
    }


def cli_arguments(model: str) -> list[str]:
    features: list[str] = json.loads(Path(__file__).with_name("codex_features.json").read_text())
    settings = [f"features.{name}=false" for name in features]
    settings += [
        'model_catalog_json="/input/catalog.json"',
        'web_search="disabled"',
        "tools.update_plan.enabled=false",
        "tools.experimental_request_user_input.enabled=false",
        'model_reasoning_effort="low"',
        'model_reasoning_summary="none"',
        'forced_login_method="chatgpt"',
        'chatgpt_base_url="https://chatgpt.com/backend-api/"',
    ]
    return [
        "/vendor/bin/codex",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        *[part for setting in settings for part in ("-c", setting)],
        "--json",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--skip-git-repo-check",
        "--model",
        model,
        "--output-schema",
        "/input/schema.json",
        "-",
    ]


def parse_native_output(data: bytes) -> tuple[str, dict[str, int] | None]:
    """Keep final JSON and native usage only; never archive private reasoning or raw wire output."""
    if len(data) > 256000:
        raise ValueError("CLI output limit")
    final: str | None = None
    tokens = None
    completed = False
    for line in data.splitlines():
        event = json.loads(line)
        kind = event.get("type")
        if kind == "item.completed":
            item = event["item"]
            if item.get("type") == "agent_message":
                final = item["text"]
            elif item.get("type") not in {"reasoning", "error"}:
                raise ForbiddenToolError("non-message CLI item rejected")
        elif kind in {"item.started", "item.updated"}:
            if event.get("item", {}).get("type") not in {"agent_message", "reasoning", "error"}:
                raise ForbiddenToolError("tool event rejected")
        elif kind == "turn.completed":
            completed = True
            usage = event.get("usage")
            if isinstance(usage, dict):
                tokens = {k: v for k, v in usage.items() if type(v) is int and v >= 0}
        elif kind not in {"thread.started", "turn.started"}:
            raise ValueError("CLI did not finish a clean diagnosis turn")
    if final is None or not completed:
        raise ValueError("missing final JSON")
    return final, tokens


class CodexSubscriptionBackend:
    def __init__(
        self, vendor: Path, credential_reference: Path, *, model: str = "gpt-6.1-sol"
    ) -> None:
        self.vendor = vendor.resolve()
        self.credential_reference = credential_reference
        self.model = model
        self.calls = 0
        self.tokens: dict[str, int] | None = None
        self.version: str | None = None
        self.last_response: str | None = None
        self.event_counts: dict[str, int] = {}

    def observation(self) -> BackendObservation:
        return BackendObservation(
            backend="外部Codex CLI（无工具）",
            model=self.model,
            cli_version=self.version,
            invocation_count=self.calls,
            tokens=self.tokens,
            billing="ChatGPT 订阅额度，无单独计费" if self.calls else "未调用订阅模型",
        )

    async def complete(self, prompt: str, schema: dict[str, Any]) -> BackendReply:
        executable = self.vendor / "bin/codex"
        if sha256(executable.read_bytes()) != CLI_SHA256:
            raise ValueError("unsupported CLI binary")
        env = subprocess_environment()
        probe = await asyncio.create_subprocess_exec(
            str(executable),
            "--version",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            version, _ = await probe.communicate()
        finally:
            if probe.returncode is None:
                probe.kill()
                await probe.wait()
        if version.decode().strip() != f"codex-cli {CLI_VERSION}":
            raise ValueError("unsupported CLI version")
        self.version = CLI_VERSION
        if self.credential_reference.is_symlink() or not self.credential_reference.is_file():
            raise ValueError("regular ChatGPT credential reference required")
        docker = _DockerCLI(environment=env)
        inspected = await docker.run("image", "inspect", EGRESS_PROXY_IMAGE)
        image = json.loads(inspected.stdout)[0]
        expected = {
            "com.harnesslab.egress.version": "1.0.0",
            "com.harnesslab.egress.base": EGRESS_PROXY_BASE.split("@")[1],
            "com.harnesslab.egress.source": EGRESS_PROXY_SOURCE_DIGEST,
        }
        if any(image["Config"]["Labels"].get(k) != v for k, v in expected.items()):
            raise ValueError("proxy identity mismatch")
        identity = ImageIdentity(
            reference=EGRESS_PROXY_IMAGE,
            image_id=image["Id"],
            repo_digests=tuple(image.get("RepoDigests") or ()),
        )
        name = "ss-diagnosis-" + uuid4().hex[:12]
        boundary = boundary_for_provider_url(
            "https://chatgpt.com/backend-api/codex/responses",
            network_name=name + "-net",
            proxy_name=name + "-proxy",
            proxy_image=identity,
        )
        process: asyncio.subprocess.Process | None = None
        with tempfile.TemporaryDirectory(prefix="ss-diagnosis-input-") as temporary:
            root = Path(temporary)
            root.chmod(0o755)
            for filename, value in (
                ("schema.json", schema),
                ("catalog.json", tool_free_catalog(self.model)),
            ):
                (root / filename).write_bytes(canonical(value))
                (root / filename).chmod(0o444)
            try:
                await boundary.provision(docker)
                args = [
                    "docker",
                    "run",
                    "--pull=never",
                    "--rm",
                    "--name",
                    name,
                    "--interactive",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--pids-limit=64",
                    "--memory=512m",
                    "--cpus=1",
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
                    "--network",
                    boundary.subject_network_mode,
                    "--tmpfs",
                    f"/tmp:rw,nosuid,nodev,size=32m,uid={os.getuid()},gid={os.getgid()}",
                    "--tmpfs",
                    "/workspace:ro,nosuid,nodev,size=1m,mode=555",
                    "--workdir",
                    "/workspace",
                    "--volume",
                    f"{root}:/input:ro",
                    "--volume",
                    f"{self.vendor}:/vendor:ro",
                    "--volume",
                    f"{self.credential_reference.resolve()}:/credential/auth.json:ro",
                    "--env",
                    "CODEX_HOME=/tmp/codex",
                    "--env",
                    "HOME=/tmp/home",
                ]
                for k, v in boundary.subject_proxy_environment().items():
                    args += ["--env", f"{k}={v}"]
                # Bootstrap copies the reference into private tmpfs; nothing is recorded.
                args += [
                    EGRESS_PROXY_BASE,
                    "sh",
                    "-c",
                    "umask 077; mkdir -p /tmp/codex /tmp/home; "
                    'cp /credential/auth.json /tmp/codex/auth.json; exec "$@"',
                    "diagnosis",
                    *cli_arguments(self.model),
                ]
                self.calls += 1  # One physical CLI invocation; no automated retry.
                process = await asyncio.create_subprocess_exec(
                    *args,
                    env=env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                assert process.stdin is not None and process.stdout is not None
                process.stdin.write(prompt.encode())
                await process.stdin.drain()
                process.stdin.close()
                chunks = bytearray()
                while chunk := await process.stdout.read(8192):
                    chunks.extend(chunk)
                    if len(chunks) > 256000:
                        raise ValueError("bounded CLI output exceeded")
                await process.wait()
                if process.returncode:
                    raise RuntimeError("external CLI failed")
                # Bounded protocol names only. No content from reasoning/errors is retained.
                known = {
                    "agent_message",
                    "reasoning",
                    "error",
                    "todo_list",
                    "file_change",
                    "command_execution",
                    "mcp_tool_call",
                    "web_search",
                    "collab_tool_call",
                }
                for line in chunks.splitlines():
                    event = json.loads(line)
                    raw_kind = event.get("item", {}).get("type")
                    kind = raw_kind if raw_kind in known else "other_event"
                    self.event_counts[kind] = self.event_counts.get(kind, 0) + 1
                text, self.tokens = parse_native_output(bytes(chunks))
                self.last_response = text
                return BackendReply(text, self.observation())
            finally:
                if process is not None and process.returncode is None:
                    process.kill()
                    await process.wait()
                try:
                    await docker.run("rm", "--force", name, check=False)
                    remaining = await docker.run(
                        "ps", "--all", "--quiet", "--filter", f"name=^/{name}$"
                    )
                    if remaining.stdout.strip():
                        raise RuntimeError("diagnosis container cleanup not proven")
                finally:
                    await boundary.cleanup(docker)
