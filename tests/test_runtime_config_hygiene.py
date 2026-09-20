from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest

from harnesslab.contracts.common import NetworkPolicy, Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.egress import (
    EGRESS_PROXY_IMAGE,
    EgressPolicy,
    EgressProxyRuntime,
    ProviderScopedDockerBoundary,
)
from harnesslab.harness_lane.adapter import CodexExecutionPlan, CodexHarnessAdapter
from harnesslab.harness_lane.docker_backend import DockerCodexBackend
from harnesslab.harness_lane.models import (
    CodexHarnessProfile,
    CodexProcessCapture,
    HarnessLaneOutcome,
)
from harnesslab.harness_lane.profile import (
    CODEX_IMAGE,
    CODEX_PERMISSION_FILESYSTEM_OVERRIDE,
    CODEX_PERMISSION_NETWORK_OVERRIDE,
    CODEX_PERMISSION_PROFILE,
    configured_gpt56_relay_codex_profile,
)
from harnesslab.harness_lane.prompt import render_codex_harness_prompt
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.harness_lane.runtime import CodexRuntime
from harnesslab.model_lane.models import DirectModelOutcome
from harnesslab.model_lane.providers import OpenAIResponsesAdapter
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.multi_harness.profile import CLAUDE_IMAGE, DEEPSEEK_IMAGE
from harnesslab.release.smoke import (
    ProductionSmokeInvoker,
    RuntimeIdentities,
    SmokeControlPlane,
    SmokeExecutionReceipt,
    SmokeExecutionStatus,
)
from harnesslab.sandbox.docker_cli import _DockerCLI, docker_environment
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.preflight import _docker_runtime_preflight

ROOT = Path(__file__).resolve().parents[1]
_GATE_D_SPEC = importlib.util.spec_from_file_location(
    "verify_gate_d", ROOT / "scripts/verify_gate_d.py"
)
assert _GATE_D_SPEC is not None and _GATE_D_SPEC.loader is not None
_GATE_D_MODULE = importlib.util.module_from_spec(_GATE_D_SPEC)
sys.modules[_GATE_D_SPEC.name] = _GATE_D_MODULE
_GATE_D_SPEC.loader.exec_module(_GATE_D_MODULE)
REAL_PROVIDER_ENVIRONMENT_REFERENCES = cast(
    tuple[str, ...], _GATE_D_MODULE.REAL_PROVIDER_ENVIRONMENT_REFERENCES
)
gate_d_subprocess_environment = cast(Any, _GATE_D_MODULE.gate_d_subprocess_environment)
TASK = ROOT / "tasks" / "micro-python-clamp" / "1.0.0"
BASE_URL_REFERENCE = "HARNESSLAB_GPT56_RELAY_BASE_URL"
API_KEY_REFERENCE = "HARNESSLAB_GPT56_RELAY_API_KEY"
RUNTIME_URL = "https://r6-runtime-sentinel.example.test/private"
FAKE_KEY = "r6-fake-api-key-sentinel"
SAFE_ROUTE_IDENTITY = "gpt56-relay|responses|env:HARNESSLAB_GPT56_RELAY_BASE_URL/responses"
R7_RUNTIME_URL = "https://r7-relay-sentinel.example.test/v1"
R7_FAKE_KEY = "r7-fake-api-key-sentinel"
GATE_D_ENV_SENTINEL = "gate-d-ambient-provider-sentinel-must-not-escape"


def test_gate_d_subprocess_environment_isolates_real_provider_configuration() -> None:
    source = {
        **os.environ,
        **{name: GATE_D_ENV_SENTINEL for name in REAL_PROVIDER_ENVIRONMENT_REFERENCES},
        "DATABASE_URL": "postgresql+psycopg://preserved.example/test",
        "GATE_D_UNRELATED_ENV": "preserved",
    }
    child = gate_d_subprocess_environment(source)
    assert all(name not in child for name in REAL_PROVIDER_ENVIRONMENT_REFERENCES)
    assert child["DATABASE_URL"] == source["DATABASE_URL"]
    assert child["GATE_D_UNRELATED_ENV"] == "preserved"
    assert GATE_D_ENV_SENTINEL not in json.dumps(child, sort_keys=True)


def test_gate_d_sanitized_subprocess_keeps_missing_credential_tests_keyless() -> None:
    source = {
        **os.environ,
        **{name: GATE_D_ENV_SENTINEL for name in REAL_PROVIDER_ENVIRONMENT_REFERENCES},
    }
    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_phase_kb0_review.py::test_v2_credential_preflight_prints_presence_only",
            "tests/test_provider_adapters.py::test_missing_credential_fails_before_http_request",
        ),
        cwd=ROOT,
        env=gate_d_subprocess_environment(source),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    assert GATE_D_ENV_SENTINEL not in output


def _direct_profile() -> ModelProfile:
    return ModelProfile(
        requested_model="gpt-5.6-sol",
        provider="gpt56-relay",
        base_url_reference=BASE_URL_REFERENCE,
        route="/responses",
        protocol=Protocol.RESPONSES,
        reasoning=ReasoningProfile(effort="medium", max_output_tokens=2000),
        request_timeout_seconds=90,
        credential_reference=API_KEY_REFERENCE,
    )


def _environment() -> dict[str, str]:
    return {BASE_URL_REFERENCE: RUNTIME_URL, API_KEY_REFERENCE: FAKE_KEY}


def _response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "r6-keyless-response",
            "status": "completed",
            "model": "gpt-5.6-sol",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "{}"}],
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        },
    )


def _artifact_text(root: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in root.rglob("*")
        if path.is_file()
    )


@pytest.mark.asyncio
async def test_direct_success_uses_runtime_url_but_persists_only_route_identity(
    tmp_path: Path,
) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return _response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DirectModelRunner(
            artifact_root=tmp_path / "artifacts",
            runtime_root=tmp_path / "runtime",
            environment=_environment(),
            allow_custom_endpoint=True,
        ).run(
            TASK,
            _direct_profile(),
            adapter=OpenAIResponsesAdapter(client=client, environment=_environment()),
            run_id="r6-direct-success",
        )

    assert result.evidence.provider_result is not None
    serialized_result = result.evidence.provider_result.model_dump_json()
    serialized_evidence = result.evidence.canonical_json()
    assert requested_urls == [f"{RUNTIME_URL}/responses"]
    assert result.evidence.outcome is DirectModelOutcome.SUBJECT_OUTPUT_ERROR
    assert result.evidence.endpoint_identity == SAFE_ROUTE_IDENTITY
    assert SAFE_ROUTE_IDENTITY in serialized_result
    assert RUNTIME_URL not in _direct_profile().model_dump_json()
    assert RUNTIME_URL not in serialized_result
    assert RUNTIME_URL not in serialized_evidence
    assert RUNTIME_URL not in _artifact_text(result.artifact_directory)


@pytest.mark.asyncio
async def test_direct_failure_uses_runtime_url_without_persisting_value(
    tmp_path: Path,
) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        raise httpx.ReadTimeout("keyless timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DirectModelRunner(
            artifact_root=tmp_path / "artifacts",
            runtime_root=tmp_path / "runtime",
            environment=_environment(),
            allow_custom_endpoint=True,
        ).run(
            TASK,
            _direct_profile(),
            adapter=OpenAIResponsesAdapter(client=client, environment=_environment()),
            run_id="r6-direct-failure",
        )

    assert requested_urls == [f"{RUNTIME_URL}/responses"]
    assert result.evidence.outcome is DirectModelOutcome.PROVIDER_ERROR
    assert result.evidence.endpoint_identity == SAFE_ROUTE_IDENTITY
    assert RUNTIME_URL not in result.evidence.canonical_json()
    assert RUNTIME_URL not in _artifact_text(result.artifact_directory)


def _codex_profile() -> CodexHarnessProfile:
    return configured_gpt56_relay_codex_profile(
        ImageIdentity(
            reference="harnesslab-phase-e-codex:0.149.0",
            image_id="sha256:" + "6" * 64,
        ),
        provider_base_url_reference=BASE_URL_REFERENCE,
        reasoning_effort="medium",
    )


def _codex_plan(tmp_path: Path, *, image: ImageIdentity | None = None) -> CodexExecutionPlan:
    prompt = render_codex_harness_prompt(
        task_instruction="Fix the visible task.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=NetworkPolicy.DENY,
    )
    profile = _codex_profile()
    if image is not None:
        profile = profile.model_copy(update={"codex_image": image})
    return CodexHarnessAdapter().prepare(
        profile, prompt, workspace=tmp_path, context=None, task_id="task"
    )


def test_codex_runtime_url_is_environment_only_and_ephemeral(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _codex_profile()
    plan = _codex_plan(tmp_path)
    backend = DockerCodexBackend(
        credentials={BASE_URL_REFERENCE: RUNTIME_URL, API_KEY_REFERENCE: FAKE_KEY}
    )
    docker_argv = backend.create_argv(plan, "r6-codex-subject")
    persistent_forms = "\n".join(
        (
            profile.canonical_json(),
            json.dumps(plan.argv),
            json.dumps(docker_argv),
            json.dumps(plan.environment_references),
        )
    )

    assert plan.environment_references == ((BASE_URL_REFERENCE, BASE_URL_REFERENCE),)
    assert RUNTIME_URL not in persistent_forms
    assert FAKE_KEY not in persistent_forms
    assert SAFE_ROUTE_IDENTITY in profile.canonical_json()
    assert "--ignore-user-config" not in plan.argv
    assert profile.ignore_user_config is False
    assert profile.ambient_user_config_isolated is True
    assert profile.provider_supports_websockets is False
    assert plan.argv[plan.argv.index("--profile") + 1] == "harnesslab-runtime"
    assert docker_argv[docker_argv.index("--entrypoint") + 1] == (
        "/usr/local/bin/harnesslab-codex-runtime"
    )
    assert backend.artifact_secret_values == (RUNTIME_URL, FAKE_KEY)

    script = ROOT / "docker" / "codex" / "runtime_entrypoint.py"
    spec = importlib.util.spec_from_file_location("r6_runtime_entrypoint", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    isolated_home = tmp_path / "ephemeral-codex-home"
    monkeypatch.setattr(module, "CODEX_HOME", isolated_home)
    monkeypatch.setenv("CODEX_HOME", str(isolated_home))
    validated = cast(Any, module)._validated_base_url(RUNTIME_URL)
    cast(Any, module)._materialize_runtime_profile(validated)
    runtime_config = (isolated_home / "harnesslab-runtime.config.toml").read_text(encoding="utf-8")
    assert RUNTIME_URL in runtime_config
    assert "supports_websockets = false" in runtime_config
    assert f'default_permissions = "{CODEX_PERMISSION_PROFILE}"' in runtime_config
    assert runtime_config.index("default_permissions") < runtime_config.index("[model_providers.")
    assert f"[permissions.{CODEX_PERMISSION_PROFILE}.filesystem]" in runtime_config
    assert '":root" = "write"' in runtime_config
    assert f"[permissions.{CODEX_PERMISSION_PROFILE}.network]" in runtime_config
    assert "enabled = false" in runtime_config
    assert stat.S_IMODE((isolated_home / "harnesslab-runtime.config.toml").stat().st_mode) == 0o600
    assert RUNTIME_URL not in script.read_text(encoding="utf-8")


def test_runtime_entrypoint_removes_url_only_from_codex_child_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = ROOT / "docker" / "codex" / "runtime_entrypoint.py"
    spec = importlib.util.spec_from_file_location("r7_runtime_entrypoint", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    isolated_home = tmp_path / "ephemeral-codex-home"
    captured: dict[str, object] = {}

    def capture_exec(file: str, argv: tuple[str, ...], environment: dict[str, str]) -> None:
        captured.update(file=file, argv=argv, environment=environment)

    monkeypatch.setattr(module, "CODEX_HOME", isolated_home)
    monkeypatch.setattr(module.os, "execvpe", capture_exec)
    monkeypatch.setenv("CODEX_HOME", str(isolated_home))
    monkeypatch.setenv(BASE_URL_REFERENCE, R7_RUNTIME_URL)
    monkeypatch.setenv(API_KEY_REFERENCE, R7_FAKE_KEY)
    monkeypatch.setattr(
        module.sys, "argv", ["harnesslab-codex-runtime", "--profile", "harnesslab-runtime"]
    )

    cast(Any, module).main()

    child_environment = cast(dict[str, str], captured["environment"])
    assert captured["file"] == "codex"
    assert BASE_URL_REFERENCE not in child_environment
    assert child_environment[API_KEY_REFERENCE] == R7_FAKE_KEY
    runtime_config = (isolated_home / "harnesslab-runtime.config.toml").read_text(encoding="utf-8")
    assert R7_RUNTIME_URL in runtime_config
    assert f'env_key = "{API_KEY_REFERENCE}"' in runtime_config
    assert "supports_websockets = false" in runtime_config
    assert f'default_permissions = "{CODEX_PERMISSION_PROFILE}"' in runtime_config


@pytest.mark.asyncio
async def test_pinned_codex_split_sandbox_executes_with_outer_filesystem_and_seccomp_network(
    tmp_path: Path,
) -> None:
    image = await CodexRuntime().ensure_image()
    preflight, environment = await _docker_runtime_preflight()
    cli = _DockerCLI(output_limit=1_000_000, environment=environment)
    workspace = tmp_path / "workspace"
    context = tmp_path / "context"
    workspace.mkdir(mode=0o777)
    context.mkdir(mode=0o755)
    workspace.chmod(0o777)
    context.chmod(0o755)
    workspace_input = workspace / "workspace-input.txt"
    context_input = context / "context-input.txt"
    workspace_input.write_text("workspace-readable\n", encoding="utf-8")
    context_input.write_text("context-readable\n", encoding="utf-8")
    workspace_input.chmod(0o644)
    context_input.chmod(0o644)
    suffix = uuid4().hex[:12]
    strict_name = f"hl-r9-{suffix}-strict"
    sandbox_name = f"hl-r9-{suffix}-sandbox"
    profile_overrides = (
        "-c",
        f'default_permissions="{CODEX_PERMISSION_PROFILE}"',
        "-c",
        CODEX_PERMISSION_FILESYSTEM_OVERRIDE,
        "-c",
        CODEX_PERMISSION_NETWORK_OVERRIDE,
    )
    strict_plan = CodexExecutionPlan(
        argv=(
            "codex",
            "exec",
            "--strict-config",
            "--ignore-user-config",
            "--ephemeral",
            "--skip-git-repo-check",
            "--profile",
            "harnesslab-runtime",
            *profile_overrides,
            "-",
        ),
        prompt="",
        workspace=workspace,
        context=context,
        timeout_seconds=10,
        task_id="r9-strict-config",
        environment_references=((BASE_URL_REFERENCE, BASE_URL_REFERENCE),),
    )
    probe = (
        'test "$PWD" = /workspace || exit 21; '
        "test -r /workspace/workspace-input.txt || exit 22; "
        "ls /workspace >/dev/null || exit 23; "
        "cp /workspace/workspace-input.txt /workspace/r9-written.txt || exit 24; "
        "test -s /workspace/r9-written.txt || exit 25; "
        "if touch /usr/local/r9-rootfs-write-forbidden 2>/dev/null; then exit 31; fi; "
        "test -r /context/context-input.txt || exit 26; "
        "if touch /context/r9-context-write-forbidden 2>/dev/null; then exit 32; fi; "
        "python3 -c 'import errno,socket; "
        "x=None; "
        "\ntry: socket.socket(socket.AF_INET,socket.SOCK_STREAM)"
        "\nexcept OSError as e: x=e.errno"
        "\nraise SystemExit(0 if x == errno.EPERM else 41)'; "
        "printf 'R9_SPLIT_SANDBOX_PASS\\n'"
    )
    sandbox_plan = CodexExecutionPlan(
        argv=(
            "codex",
            "sandbox",
            "-C",
            "/workspace",
            "--profile",
            "harnesslab-runtime",
            *profile_overrides,
            "-P",
            CODEX_PERMISSION_PROFILE,
            "--",
            "/usr/bin/bash",
            "-c",
            probe,
        ),
        prompt="",
        workspace=workspace,
        context=context,
        timeout_seconds=10,
        task_id="r9-split-sandbox",
        environment_references=((BASE_URL_REFERENCE, BASE_URL_REFERENCE),),
    )
    backend = DockerCodexBackend(
        explicitly_enabled=True,
        credentials={BASE_URL_REFERENCE: RUNTIME_URL, API_KEY_REFERENCE: FAKE_KEY},
    )
    create_environment = docker_environment(
        environment,
        {BASE_URL_REFERENCE: RUNTIME_URL, API_KEY_REFERENCE: FAKE_KEY},
    )
    try:
        await cli.run(
            *backend.create_argv(strict_plan, strict_name), environment=create_environment
        )
        await backend._verify_effective_security(cli, strict_name)
        await backend._execute_attached_process(
            preflight.cli_path,
            strict_name,
            strict_plan,
            environment,
        )
        strict_state = await cli.run("inspect", strict_name, "--format", "{{json .State.ExitCode}}")
        strict_logs = await cli.run("logs", strict_name, check=False)
        strict_output = strict_logs.stdout + strict_logs.stderr
        assert json.loads(strict_state.stdout) == 1
        assert strict_output.endswith(b"No prompt provided via stdin.\n")
        assert b"configuration error" not in strict_output.lower()

        sandbox_argv = backend.create_argv(sandbox_plan, sandbox_name)
        serialized_argv = "\n".join(sandbox_argv)
        assert image.reference == CODEX_IMAGE
        assert "--sandbox" not in sandbox_plan.argv
        assert "features.use_legacy_landlock" not in serialized_argv
        assert "--privileged" not in sandbox_argv
        assert "--cap-add" not in sandbox_argv
        assert "seccomp=unconfined" not in serialized_argv
        assert "apparmor=unconfined" not in serialized_argv.casefold()
        assert "docker.sock" not in serialized_argv
        assert "--publish" not in sandbox_argv and "-p" not in sandbox_argv
        await cli.run(*sandbox_argv, environment=create_environment)
        await backend._verify_effective_security(cli, sandbox_name)
        result = await cli.run("start", "--attach", sandbox_name, check=False)
        combined = result.stdout + result.stderr
        assert result.returncode == 0, combined.decode("utf-8", errors="replace")
        assert result.stdout == b"R9_SPLIT_SANDBOX_PASS\n"
        assert b"bwrap" not in combined.lower()
        assert (workspace / "r9-written.txt").read_text(encoding="utf-8") == (
            "workspace-readable\n"
        )
        assert not (context / "r9-context-write-forbidden").exists()
    finally:
        for name in (strict_name, sandbox_name):
            await cli.run("kill", name, check=False)
            await cli.run("rm", "--force", name, check=False)
            absent = await cli.run(
                "ps", "--all", "--quiet", "--filter", f"name=^/{name}$", check=False
            )
            assert not absent.stdout.strip()


@pytest.mark.asyncio
async def test_pinned_codex_uses_generated_isolated_relay_profile_without_websockets(
    tmp_path: Path,
) -> None:
    image = await CodexRuntime().ensure_image()
    proxy_image = await EgressProxyRuntime().ensure_image()
    preflight, docker_cli_environment = await _docker_runtime_preflight()
    suffix = uuid4().hex[:12]
    network_name = f"hl-r7-{suffix}-internal"
    proxy_name = f"hl-r7-{suffix}-proxy"
    subject_name = f"hl-r7-{suffix}-subject"
    hostile_host_home = tmp_path / "host-codex-home"
    hostile_host_home.mkdir()
    (hostile_host_home / "config.toml").write_text(
        'model_provider = "evil-host-provider"\n'
        "[model_providers.evil-host-provider]\n"
        'name = "Host provider that must stay outside the container"\n'
        'base_url = "https://evil-host-provider.example.test"\n'
        'env_key = "R7_EVIL_HOST_KEY"\n'
        'wire_api = "responses"\n',
        encoding="utf-8",
    )
    project_config = tmp_path / ".codex" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text(
        'model_provider = "evil-project-provider"\n'
        "[model_providers.evil-project-provider]\n"
        'name = "Project provider that must be denied"\n'
        'base_url = "https://evil-project-provider.example.test"\n'
        'env_key = "R7_EVIL_PROJECT_KEY"\n'
        'wire_api = "responses"\n',
        encoding="utf-8",
    )
    host_environment = dict(docker_cli_environment)
    host_environment["CODEX_HOME"] = str(hostile_host_home)
    cli = _DockerCLI(output_limit=1_000_000, environment=host_environment)
    boundary = ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname="r7-relay-sentinel.example.test"),
        network_name,
        proxy_name,
        proxy_image,
    )
    recording_proxy = r"""
import asyncio
import json

async def handle(reader, writer):
    authority = "MALFORMED"
    try:
        header = await reader.readuntil(b"\r\n\r\n")
        request_line = header.split(b"\r\n", 1)[0].decode("ascii", errors="strict")
        method, authority, version = request_line.split(" ")
        if method != "CONNECT" or version not in {"HTTP/1.0", "HTTP/1.1"}:
            authority = "MALFORMED"
    except Exception:
        authority = "MALFORMED"
    print(json.dumps({"authority": authority}, sort_keys=True), flush=True)
    writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
    await writer.drain()
    writer.close()
    await writer.wait_closed()

async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", 8080)
    async with server:
        await server.serve_forever()

asyncio.run(main())
"""
    plan = _codex_plan(tmp_path, image=image)
    backend = DockerCodexBackend(
        explicitly_enabled=True,
        credentials={BASE_URL_REFERENCE: R7_RUNTIME_URL, API_KEY_REFERENCE: R7_FAKE_KEY},
        egress_boundary=boundary,
    )
    child_attestation: dict[str, object] | None = None
    authorities: set[str] = set()
    process: asyncio.subprocess.Process | None = None
    stdout_task: asyncio.Task[bytes] | None = None
    stderr_task: asyncio.Task[bytes] | None = None
    try:
        await cli.run(*boundary.create_internal_network_argv())
        await cli.run(
            "create",
            "--name",
            proxy_name,
            "--network",
            network_name,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--restart",
            "no",
            "--user",
            "10001:10001",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=16m",
            "--entrypoint",
            "python",
            EGRESS_PROXY_IMAGE,
            "-c",
            recording_proxy,
        )
        await cli.run("start", proxy_name)
        create_environment = docker_environment(
            host_environment,
            {BASE_URL_REFERENCE: R7_RUNTIME_URL, API_KEY_REFERENCE: R7_FAKE_KEY},
        )
        docker_argv = backend.create_argv(plan, subject_name)
        assert R7_RUNTIME_URL not in docker_argv
        assert R7_FAKE_KEY not in docker_argv
        await cli.run(*docker_argv, environment=create_environment)
        subject_inspect = await cli.run(
            "inspect", subject_name, "--format", "{{json .Mounts}}|{{json .HostConfig.NetworkMode}}"
        )
        mounts_raw, network_raw = subject_inspect.stdout.decode().strip().split("|", 1)
        mounts = json.loads(mounts_raw)
        assert json.loads(network_raw) == network_name
        assert all(mount["Source"] != str(hostile_host_home) for mount in mounts)

        process = await asyncio.create_subprocess_exec(
            preflight.cli_path,
            "start",
            "--attach",
            "--interactive",
            subject_name,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=host_environment,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        stdout_task = asyncio.create_task(process.stdout.read())
        stderr_task = asyncio.create_task(process.stderr.read())
        process.stdin.write(plan.prompt.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

        environment_probe = r"""
import json
import os
import stat
from pathlib import Path

raw_environment = Path("/proc/1/environ").read_bytes().split(b"\0")
names = {entry.split(b"=", 1)[0].decode() for entry in raw_environment if b"=" in entry}
config_path = Path("/tmp/codex-home/harnesslab-runtime.config.toml")
config = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
print(json.dumps({
    "api_key_present": "HARNESSLAB_GPT56_RELAY_API_KEY" in names,
    "base_url_present": "HARNESSLAB_GPT56_RELAY_BASE_URL" in names,
    "codex_home_isolated": any(
        entry == b"CODEX_HOME=/tmp/codex-home" for entry in raw_environment
    ),
    "generated_profile_mode": stat.S_IMODE(config_path.stat().st_mode) if config else None,
    "generated_provider_selected": 'model_provider = "harnesslab_gpt56_relay"' in config,
    "supports_websockets_false": "supports_websockets = false" in config,
}, sort_keys=True))
"""
        for _ in range(200):
            logs = await cli.run("logs", proxy_name, check=False)
            for line in logs.stdout.decode("utf-8", errors="strict").splitlines():
                record = json.loads(line)
                authorities.add(cast(str, record["authority"]))
            probe = await cli.run(
                "exec", subject_name, "python", "-c", environment_probe, check=False
            )
            if probe.returncode == 0 and probe.stdout.strip():
                child_attestation = cast(dict[str, object], json.loads(probe.stdout))
            if authorities and child_attestation is not None:
                break
            if process.returncode is not None and child_attestation is None:
                break
            await asyncio.sleep(0.05)

        assert child_attestation == {
            "api_key_present": True,
            "base_url_present": False,
            "codex_home_isolated": True,
            "generated_profile_mode": 0o600,
            "generated_provider_selected": True,
            "supports_websockets_false": True,
        }
        assert authorities == {"r7-relay-sentinel.example.test:443"}
    finally:
        await cli.run("kill", subject_name, check=False)
        await cli.run("rm", "--force", subject_name, check=False)
        await cli.run("kill", proxy_name, check=False)
        await cli.run("rm", "--force", proxy_name, check=False)
        await cli.run("network", "rm", network_name, check=False)
        if process is not None and process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()
    stdout = await stdout_task if stdout_task is not None else b""
    stderr = await stderr_task if stderr_task is not None else b""
    transport_output = (stdout + stderr).decode("utf-8", errors="replace").casefold()
    assert "websocket" not in transport_output
    for name in (subject_name, proxy_name):
        absent = await cli.run("ps", "--all", "--quiet", "--filter", f"name=^/{name}$", check=False)
        assert not absent.stdout.strip()
    assert (await cli.run("network", "inspect", network_name, check=False)).returncode != 0


class _RuntimeValueEchoBackend(DockerCodexBackend):
    async def run(self, _: CodexExecutionPlan) -> CodexProcessCapture:
        return CodexProcessCapture(
            (
                json.dumps({"type": "thread.started", "thread_id": "r6-safe-thread"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "r6-message",
                            "type": "agent_message",
                            "text": f"runtime={RUNTIME_URL}; credential={FAKE_KEY}",
                        },
                    }
                ),
                json.dumps({"type": "turn.failed", "error": {"message": "safe failure"}}),
            ),
            1,
            1,
        )


@pytest.mark.asyncio
async def test_codex_runtime_values_are_absent_from_every_harness_artifact(
    tmp_path: Path,
) -> None:
    backend = _RuntimeValueEchoBackend(
        explicitly_enabled=True,
        credentials={BASE_URL_REFERENCE: RUNTIME_URL, API_KEY_REFERENCE: FAKE_KEY},
    )
    result = await CodexHarnessRunner(
        artifact_root=tmp_path / "artifacts", runtime_root=tmp_path / "runtime"
    ).run(TASK, _codex_profile(), backend=backend, run_id="r6-codex-value-hygiene")

    serialized = result.evidence.canonical_json() + _artifact_text(result.artifact_directory)
    assert result.evidence.outcome is HarnessLaneOutcome.HARNESS_ERROR
    assert RUNTIME_URL not in serialized
    assert FAKE_KEY not in serialized
    assert SAFE_ROUTE_IDENTITY in serialized
    assert "[REDACTED]" in serialized


@pytest.mark.asyncio
async def test_smoke_result_and_receipt_exclude_runtime_url_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = {
        **_environment(),
        "HARNESSLAB_OPENCODE_GO_API_KEY": "r6-fake-opencode-key",
        "DEEPSEEK_API_KEY": "r6-fake-deepseek-key",
    }
    runtime = RuntimeIdentities(
        codex_image=ImageIdentity(reference=CODEX_IMAGE, image_id="sha256:" + "1" * 64),
        claude_image=ImageIdentity(reference=CLAUDE_IMAGE, image_id="sha256:" + "2" * 64),
        deepseek_image=ImageIdentity(reference=DEEPSEEK_IMAGE, image_id="sha256:" + "3" * 64),
        egress_proxy_image=ImageIdentity(
            reference=EGRESS_PROXY_IMAGE, image_id="sha256:" + "4" * 64
        ),
        deepseek_config_digest="sha256:" + "5" * 64,
    )
    control = SmokeControlPlane.load(ROOT)
    binding = control.resolve_real_bindings(environment, runtime)[0]

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{RUNTIME_URL}/responses"
        return _response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(
            "harnesslab.release.smoke.OpenAIResponsesAdapter",
            lambda *, environment: OpenAIResponsesAdapter(
                client=client, environment=_environment()
            ),
        )
        smoke_result = await ProductionSmokeInvoker(ROOT, environment, tmp_path / "smoke").invoke(
            binding
        )

    receipt = SmokeExecutionReceipt(
        plan_id=control.smoke_plan.plan_id,
        smoke_plan_digest=control.smoke_plan_digest,
        release_plan_digest=control.release_plan.digest,
        status=SmokeExecutionStatus.SUCCEEDED,
        attempted_top_level_launches=1,
        results=(smoke_result,),
    )
    report_representation = json.dumps(receipt.model_dump(mode="json"), indent=2)
    persisted = _artifact_text(Path(smoke_result.evidence_references[0]))
    assert RUNTIME_URL not in smoke_result.model_dump_json()
    assert RUNTIME_URL not in receipt.canonical_json()
    assert RUNTIME_URL not in report_representation
    assert RUNTIME_URL not in persisted
