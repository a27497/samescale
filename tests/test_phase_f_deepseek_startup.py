# ruff: noqa: E501 -- the embedded local server is kept as executable fixture source.

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest

from harnesslab.harness_lane.models import HarnessFailureCategory
from harnesslab.multi_harness.adapter import DeepSeekHarnessAdapter
from harnesslab.multi_harness.diagnostics import safe_process_diagnostics
from harnesslab.multi_harness.docker_backend import DockerMultiHarnessBackend
from harnesslab.multi_harness.models import HarnessKind, TraceCoverage
from harnesslab.multi_harness.profile import (
    DEEPSEEK_IMAGE,
    DEEPSEEK_NODE_ENTRYPOINT,
    DEEPSEEK_NODE_FLAG,
    configured_deepseek_v4flash_profile,
)
from harnesslab.multi_harness.prompt import render_harness_prompt
from harnesslab.sandbox.artifacts import make_tree_writable
from harnesslab.sandbox.models import ImageIdentity

CALL7_CONFIG_DIGEST = "sha256:a0a0e9f380872097cb7f8b7356f36433a2afeb8de5044a9e63d4ed47b4bee9f5"
FAKE_KEY = "k-fast-2-keyless-deepseek-credential"


def _docker(
    *arguments: str, check: bool = True, timeout: float = 30
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ("docker", *arguments),
        check=check,
        capture_output=True,
        timeout=timeout,
    )


@dataclass(frozen=True)
class _LocalBoundary:
    subject_network_mode: str

    def subject_proxy_environment(self) -> dict[str, str]:
        return {}

    async def provision(self, _cli: object) -> None:
        return None

    async def cleanup(self, _cli: object) -> None:
        return None


LOCAL_CHAT_SERVER = r"""
import http.server
import json

class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        payload = json.loads(self.rfile.read(length))
        print(json.dumps({
            "authorization_present": bool(self.headers.get("authorization")),
            "model": payload.get("model"),
            "path": self.path,
            "stream": payload.get("stream"),
        }, sort_keys=True), flush=True)
        chunks = [
            {
                "id": "chatcmpl-keyless",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "deepseek-v4-flash",
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": "READY"}, "finish_reason": None}],
            },
            {
                "id": "chatcmpl-keyless",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "deepseek-v4-flash",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        ]
        body = "".join(
            "data: " + json.dumps(chunk, separators=(",", ":")) + "\n\n"
            for chunk in chunks
        ) + "data: [DONE]\n\n"
        encoded = body.encode()
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return

print("READY", flush=True)
http.server.ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
"""


def _start_server(network: str, name: str) -> None:
    _docker(
        "run",
        "--detach",
        "--name",
        name,
        "--network",
        network,
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--user",
        "10001:10001",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=16m",
        "--entrypoint",
        "python",
        DEEPSEEK_IMAGE,
        "-c",
        LOCAL_CHAT_SERVER,
    )
    for _ in range(100):
        if "READY" in _docker("logs", name, check=False).stdout.decode():
            return
        time.sleep(0.02)
    raise AssertionError("controlled DeepSeek server did not become ready")


@pytest.mark.asyncio
async def test_pinned_deepseek_profile_completes_against_keyless_local_transport(
    tmp_path: Path,
) -> None:
    image_id = json.loads(
        _docker("image", "inspect", DEEPSEEK_IMAGE, "--format", "{{json .Id}}").stdout
    )
    effective = _docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--entrypoint",
        "node",
        DEEPSEEK_IMAGE,
        DEEPSEEK_NODE_FLAG,
        DEEPSEEK_NODE_ENTRYPOINT,
        "--profile",
        "headless",
        "--dump-config",
    ).stdout
    config_digest = "sha256:" + hashlib.sha256(effective).hexdigest()
    assert config_digest == CALL7_CONFIG_DIGEST

    profile = configured_deepseek_v4flash_profile(
        ImageIdentity(reference=DEEPSEEK_IMAGE, image_id=image_id),
        config_digest,
        execution_timeout_seconds=15,
    )
    prompt = render_harness_prompt(
        HarnessKind.DEEPSEEK,
        task_instruction="Reply with exactly READY.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=profile.network_policy,
    )
    adapter = DeepSeekHarnessAdapter(observed_config_digest=config_digest)
    adapter.preflight(profile)
    make_tree_writable(tmp_path)
    plan = adapter.prepare(
        profile,
        prompt,
        workspace=tmp_path,
        context=None,
        task_id="k-fast-2-keyless",
    )
    suffix = uuid4().hex[:12]
    network = f"hl-kfast2-deepseek-{suffix}"
    server = f"hl-kfast2-deepseek-server-{suffix}"
    _docker("network", "create", "--internal", network)
    try:
        _start_server(network, server)
        backend = DockerMultiHarnessBackend(
            explicitly_enabled=True,
            credentials={
                "DEEPSEEK_API_KEY": FAKE_KEY,
                "DEEPSEEK_BASE_URL": f"http://{server}:8080",
            },
            egress_boundary=_LocalBoundary(network),  # type: ignore[arg-type]
        )
        capture = await backend.run(plan)
        logs = _docker("logs", server).stdout.decode().splitlines()
    finally:
        _docker("rm", "--force", server, check=False)
        _docker("network", "rm", network, check=False)

    collection = adapter.collect(capture, secret_values=(FAKE_KEY,))
    requests = [json.loads(line) for line in logs if line.startswith("{")]
    diagnostics = safe_process_diagnostics(
        capture,
        secret_values=(FAKE_KEY, f"http://{server}:8080"),
    )
    assert capture.exit_code == 0, diagnostics
    assert not capture.timed_out
    assert not capture.cancelled
    assert collection.failure_category is None
    assert collection.terminal_event == "process.completed"
    assert profile.trace_coverage is TraceCoverage.FINAL_OUTPUT_ONLY
    assert collection.observed_model is None
    assert collection.sanitized_events
    assert requests
    assert all(
        item
        == {
            "authorization_present": True,
            "model": "deepseek-v4-flash",
            "path": "/chat/completions",
            "stream": True,
        }
        for item in requests
    )
    assert HarnessFailureCategory.PROCESS_ERROR is not collection.failure_category
