from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from harnesslab.egress import EgressProxyRuntime, preflight_egress_network_isolation
from harnesslab.harness_lane.adapter import HarnessAdapterError
from harnesslab.multi_harness.adapter import ClaudeCodeAdapter, HarnessExecutionPlan
from harnesslab.multi_harness.docker_backend import DockerMultiHarnessBackend
from harnesslab.multi_harness.models import (
    HarnessKind,
    HarnessProcessCapture,
    MultiHarnessRunResult,
)
from harnesslab.multi_harness.profile import (
    CLAUDE_IMAGE,
    configured_qwen_alibaba_bailian_claude_profile,
)
from harnesslab.multi_harness.runner import MultiHarnessRunner
from harnesslab.multi_harness.runtime import MultiHarnessRuntime
from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.runner import DockerSandbox

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "tasks" / "core-python-deduplicate" / "1.0.0"
FAKE_KEY = "keyless-verifier-lifecycle-fixture"
FAKE_BASE_URL = "https://fake-provider.test"

SOLUTION = """class RetryLedger:
    def __init__(self) -> None:
        self._results: dict[str, str] = {}

    def record_success(self, operation_key: str, result: str) -> bool:
        if not operation_key:
            raise ValueError("operation_key must not be empty")
        existing = self._results.get(operation_key)
        if existing is None:
            self._results[operation_key] = result
            return True
        if existing != result:
            raise ValueError("conflicting retry result")
        return False

    def lookup(self, operation_key: str) -> str | None:
        return self._results.get(operation_key)
"""

LOCAL_TLS_MESSAGES_SERVER = r"""
import http.server
import json
import ssl

SOLUTION = __SOLUTION__

def events_for(payload):
    has_tool_result = any(
        isinstance(message.get("content"), list)
        and any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in message["content"]
        )
        for message in payload.get("messages", [])
        if isinstance(message, dict)
    )
    start = {
        "type": "message_start",
        "message": {
            "id": "msg_keyless_lifecycle",
            "type": "message",
            "role": "assistant",
            "model": "qwen3.8-max",
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 0},
        },
    }
    if not has_tool_result:
        tool_input = json.dumps(
            {"file_path": "/workspace/events.py", "content": SOLUTION},
            separators=(",", ":"),
        )
        return [
            ("message_start", start),
            ("content_block_start", {
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_keyless_write",
                    "name": "Write",
                    "input": {},
                },
            }),
            ("content_block_delta", {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": tool_input},
            }),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                "usage": {"output_tokens": 1},
            }),
            ("message_stop", {"type": "message_stop"}),
        ]
    return [
        ("message_start", start),
        ("content_block_start", {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        }),
        ("content_block_delta", {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Done"},
        }),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 1},
        }),
        ("message_stop", {"type": "message_stop"}),
    ]

class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        payload = json.loads(self.rfile.read(length))
        events = events_for(payload)
        body = "".join(
            "event: " + event + "\ndata: "
            + json.dumps(data, separators=(",", ":")) + "\n\n"
            for event, data in events
        ).encode()
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return

server = http.server.ThreadingHTTPServer(("0.0.0.0", 443), Handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain("/certs/server.crt", "/certs/server.key")
server.socket = context.wrap_socket(server.socket, server_side=True)
print("READY", flush=True)
server.serve_forever()
""".replace("__SOLUTION__", repr(SOLUTION))


def generate_local_certificate(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=False)
    directory.chmod(0o755)
    key = directory / "server.key"
    certificate = directory / "server.crt"
    subprocess.run(
        (
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=fake-provider.test",
            "-addext",
            "subjectAltName=DNS:fake-provider.test",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
        ),
        check=True,
        capture_output=True,
        timeout=30,
    )
    key.chmod(0o644)
    certificate.chmod(0o644)
    return certificate


class KeylessMessagesBoundary:
    def __init__(self, certificate_root: Path, suffix: str) -> None:
        self.certificate_root = certificate_root.resolve()
        self.subject_network_mode = f"hl-vl-{suffix}-internal"
        self.server_name = f"hl-vl-{suffix}-provider"
        self.proxy_name: str | None = None

    def subject_proxy_environment(self) -> dict[str, str]:
        return {}

    async def provision(self, cli: _DockerCLI) -> None:
        await cli.run("network", "create", "--internal", self.subject_network_mode)
        try:
            await cli.run(
                "run",
                "--detach",
                "--name",
                self.server_name,
                "--network",
                self.subject_network_mode,
                "--network-alias",
                "fake-provider.test",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges=true",
                "--sysctl",
                "net.ipv4.ip_unprivileged_port_start=0",
                "--user",
                "10001:10001",
                "--restart",
                "no",
                "--mount",
                f"type=bind,src={self.certificate_root},dst=/certs,readonly",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=16m",
                "--entrypoint",
                "python",
                CLAUDE_IMAGE,
                "-c",
                LOCAL_TLS_MESSAGES_SERVER,
            )
            for _ in range(200):
                logs = await cli.run("logs", self.server_name, check=False)
                if b"READY" in logs.stdout:
                    return None
                await asyncio.sleep(0.05)
        except BaseException:
            await self.cleanup(cli)
            raise
        await self.cleanup(cli)
        raise HarnessAdapterError("keyless provider readiness was not observed")

    async def cleanup(self, cli: _DockerCLI) -> None:
        await cli.run("kill", self.server_name, check=False)
        await cli.run("rm", "--force", self.server_name, check=False)
        await cli.run("network", "rm", self.subject_network_mode, check=False)
        server = await cli.run(
            "ps", "--all", "--quiet", "--filter", f"name=^/{self.server_name}$", check=False
        )
        network = await cli.run(
            "network",
            "ls",
            "--quiet",
            "--filter",
            f"name=^{self.subject_network_mode}$",
            check=False,
        )
        if server.stdout.strip() or network.stdout.strip():
            raise HarnessAdapterError("keyless provider cleanup was not verified")


class KeylessTLSBackend(DockerMultiHarnessBackend):
    def __init__(self, *, certificate: Path, boundary: KeylessMessagesBoundary) -> None:
        super().__init__(
            explicitly_enabled=True,
            credentials={
                "HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL": FAKE_BASE_URL,
                "HARNESSLAB_ALIBABA_BAILIAN_API_KEY": FAKE_KEY,
            },
            egress_boundary=boundary,  # type: ignore[arg-type]
        )
        self.certificate = certificate.resolve()

    def create_argv(self, plan: HarnessExecutionPlan, container_name: str) -> tuple[str, ...]:
        arguments = list(super().create_argv(plan, container_name))
        index = arguments.index("--entrypoint")
        arguments[index:index] = (
            "--mount",
            f"type=bind,src={self.certificate},dst=/keyless-ca.pem,readonly",
        )
        return tuple(arguments)

    async def run(self, plan: HarnessExecutionPlan) -> HarnessProcessCapture:
        keyless_plan = replace(
            plan,
            environment_literals=(
                *plan.environment_literals,
                ("NODE_EXTRA_CA_CERTS", "/keyless-ca.pem"),
            ),
        )
        return await super().run(keyless_plan)


async def exact_live_handoff(
    root: Path,
    *,
    run_id: str,
    preceding_lifecycle_pressure: bool = False,
) -> MultiHarnessRunResult:
    root.mkdir(parents=True, exist_ok=False)
    if preceding_lifecycle_pressure:
        await MultiHarnessRuntime(HarnessKind.CLAUDE_CODE).doctor()
        await EgressProxyRuntime().ensure_image()
        await preflight_egress_network_isolation()
    certificate_root = root / "certificates"
    certificate = generate_local_certificate(certificate_root)
    runtime = await MultiHarnessRuntime(HarnessKind.CLAUDE_CODE).doctor()
    profile = configured_qwen_alibaba_bailian_claude_profile(
        runtime.image, execution_timeout_seconds=30
    )
    suffix = uuid4().hex[:12]
    boundary = KeylessMessagesBoundary(certificate_root, suffix)
    backend = KeylessTLSBackend(certificate=certificate, boundary=boundary)
    sandbox = DockerSandbox(
        artifact_root=root / "sandbox-artifacts",
        runtime_root=root / "sandbox-runtime",
    )
    try:
        return await MultiHarnessRunner(
            artifact_root=root / "harness-artifacts",
            runtime_root=root / "harness-runtime",
            sandbox=sandbox,
        ).run(
            TASK,
            profile,
            adapter=ClaudeCodeAdapter(),
            backend=backend,
            run_id=run_id,
        )
    finally:
        shutil.rmtree(certificate_root, ignore_errors=True)
