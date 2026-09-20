from __future__ import annotations

import importlib.util
import json
import stat
import tomllib
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest

from harnesslab.contracts.common import NetworkPolicy
from harnesslab.harness_lane.adapter import CodexHarnessAdapter, HarnessAdapterError
from harnesslab.harness_lane.docker_backend import DockerCodexBackend
from harnesslab.harness_lane.models import CodexHarnessProfile
from harnesslab.harness_lane.profile import (
    CODEX_IMAGE,
    CURRENT_CODEX_CLI_VERSION,
    CURRENT_CODEX_IMAGE,
    canonical_codex_profile,
    configured_gpt56_relay_codex_profile,
    configured_responses_relay_codex_profile,
)
from harnesslab.harness_lane.prompt import render_codex_harness_prompt
from harnesslab.harness_lane.runtime import CodexRuntime
from harnesslab.sandbox.docker_cli import _DockerCLI, docker_environment
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.preflight import _docker_runtime_preflight

ROOT = Path(__file__).resolve().parents[1]


def current_profile() -> CodexHarnessProfile:
    return configured_responses_relay_codex_profile(
        ImageIdentity(reference=CURRENT_CODEX_IMAGE, image_id="sha256:" + "7" * 64),
        requested_model="gpt-6-astra",
    )


def test_plan_binds_model_effort_runtime_and_secret_references(tmp_path: Path) -> None:
    profile = current_profile()
    prompt = render_codex_harness_prompt(
        task_instruction="Fix the task.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=NetworkPolicy.DENY,
    )
    plan = CodexHarnessAdapter().prepare(
        profile, prompt, workspace=tmp_path, context=None, task_id="task"
    )
    assert plan.argv[plan.argv.index("--model") + 1] == "gpt-6-astra"
    assert 'model_reasoning_effort="high"' in plan.argv
    assert plan.environment_references == (
        ("HARNESSLAB_CODEX_RELAY_BASE_URL", "HARNESSLAB_CODEX_RELAY_BASE_URL"),
    )
    backend = DockerCodexBackend(
        credentials={
            "HARNESSLAB_CODEX_RELAY_API_KEY": "test-only-credential",
            "HARNESSLAB_CODEX_RELAY_BASE_URL": "https://relay.example.test/v1",
        }
    )
    docker_argv = backend.create_argv(plan, "current-setup-test")
    # Execution uses the inspected immutable image, even if a mutable tag moves.
    assert docker_argv[docker_argv.index("--entrypoint") + 2] == profile.codex_image.image_id
    assert docker_argv[docker_argv.index("--network") + 1] == "none"
    assert "--read-only" in docker_argv
    assert not backend.explicitly_enabled
    public = json.dumps(docker_argv) + profile.canonical_json()
    assert "test-only-credential" not in public
    assert "https://relay.example.test/v1" not in public


@pytest.mark.parametrize(
    "change",
    [
        {"codex_cli_version": "0.999.0"},
        {"codex_image": ImageIdentity(reference=CODEX_IMAGE, image_id="sha256:" + "7" * 64)},
        {"provider_credential_reference": "DIFFERENT_API_KEY"},
        {"model_provider_id": "invented-provider"},
    ],
)
def test_inconsistent_current_profile_is_blocked(change: dict[str, Any]) -> None:
    with pytest.raises(HarnessAdapterError):
        CodexHarnessAdapter().preflight(current_profile().model_copy(update=change))


def test_versions_are_opt_in_and_historical_profiles_unchanged() -> None:
    assert CodexRuntime().image_reference == CODEX_IMAGE
    assert CodexRuntime(version=CURRENT_CODEX_CLI_VERSION).image_reference == CURRENT_CODEX_IMAGE
    with pytest.raises(ValueError, match="Unsupported"):
        CodexRuntime(version="latest")
    # Frozen fingerprints from the pre-change factory at 2a08b4d.
    image = ImageIdentity(reference=CODEX_IMAGE, image_id="sha256:" + "1" * 64)
    assert canonical_codex_profile(image).fingerprint == (
        "sha256:b0182e25076edb9a7c22249d97ef5366c03e1cdef026dce6c99209540634bf5f"
    )
    historical = configured_gpt56_relay_codex_profile(
        image,
        provider_base_url_reference="HARNESSLAB_GPT56_RELAY_BASE_URL",
        reasoning_effort="high",
    )
    assert historical.fingerprint == (
        "sha256:db438dbf76f8bf37a2dd92198c102e9f44f8edcbeae95858b856f01c2c2a0199"
    )
    with pytest.raises(ValueError, match="separately pinned"):
        configured_responses_relay_codex_profile(image, requested_model="gpt-6-astra")


def entrypoint() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "current_entrypoint", ROOT / "docker/codex/runtime_entrypoint.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_entrypoint_materializes_private_config_and_strips_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = entrypoint()
    home = tmp_path / "isolated-home"
    monkeypatch.setattr(module, "CODEX_HOME", home)
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.delenv(module.BASE_URL_REFERENCE, raising=False)
    monkeypatch.setenv(module.CURRENT_BASE_URL_REFERENCE, "https://relay.example.test/v1")
    monkeypatch.setenv("HARNESSLAB_CODEX_RELAY_API_KEY", "test-only-credential")
    monkeypatch.setattr(module.sys, "argv", ["runtime", "--profile", "harnesslab-runtime"])
    captured = {}
    monkeypatch.setattr(module.os, "execvpe", lambda exe, args, env: captured.update(env))
    module.main()
    path = home / "harnesslab-runtime.config.toml"
    config = tomllib.loads(path.read_text())
    assert config["model_provider"] == "harnesslab_responses_relay"
    provider = config["model_providers"]["harnesslab_responses_relay"]
    assert provider["env_key"] == "HARNESSLAB_CODEX_RELAY_API_KEY"
    assert provider["wire_api"] == "responses"
    assert provider["supports_websockets"] is False
    assert "test-only-credential" not in path.read_text()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert module.CURRENT_BASE_URL_REFERENCE not in captured
    assert captured["HARNESSLAB_CODEX_RELAY_API_KEY"] == "test-only-credential"
    with pytest.raises(FileExistsError):
        module.main()


def test_entrypoint_rejects_ambiguous_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    module = entrypoint()
    monkeypatch.setenv(module.BASE_URL_REFERENCE, "https://old.example.test/v1")
    monkeypatch.setenv(module.CURRENT_BASE_URL_REFERENCE, "https://new.example.test/v1")
    with pytest.raises(RuntimeError, match="ambiguous"):
        module.main()


@pytest.mark.asyncio
async def test_current_docker_strict_config_and_sandbox_without_provider(tmp_path: Path) -> None:
    image = await CodexRuntime(version=CURRENT_CODEX_CLI_VERSION).ensure_image()
    profile = configured_responses_relay_codex_profile(image, requested_model="gpt-6-astra")
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o777)
    workspace.chmod(0o777)
    prompt = render_codex_harness_prompt(
        task_instruction="Unused: no coding request is sent.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=NetworkPolicy.DENY,
    )
    plan = CodexHarnessAdapter().prepare(
        profile, prompt, workspace=workspace, context=None, task_id="offline-probe"
    )
    # Only fake credentials, no network, empty stdin: CLI validates then exits.
    credentials = {
        "HARNESSLAB_CODEX_RELAY_API_KEY": "test-only-credential",
        "HARNESSLAB_CODEX_RELAY_BASE_URL": "https://relay.example.test/v1",
    }
    _, environment = await _docker_runtime_preflight()
    cli = _DockerCLI(environment=environment)
    backend = DockerCodexBackend(credentials=credentials)
    overrides = tuple(
        argument
        for index, value in enumerate(plan.argv)
        if value == "-c"
        for argument in ("-c", plan.argv[index + 1])
    )
    probe = (
        "import errno,os,pathlib,socket; "
        "assert os.getuid()==10001; "
        "pathlib.Path('/workspace/probe.txt').write_text('ok'); "
        "\ntry: pathlib.Path('/usr/local/forbidden').write_text('bad')"
        "\nexcept OSError: pass"
        "\nelse: raise AssertionError('rootfs writable')"
        "\ntry: socket.socket(socket.AF_INET,socket.SOCK_STREAM)"
        "\nexcept OSError as e: assert e.errno==errno.EPERM"
        "\nelse: raise AssertionError('network syscall permitted')"
        "\nprint('ISOLATION_PASS')"
    )
    sandbox_plan = replace(
        plan,
        argv=(
            "codex",
            "sandbox",
            "-C",
            "/workspace",
            "--profile",
            "harnesslab-runtime",
            *overrides,
            "-P",
            "harnesslab-outer-sandbox",
            "--",
            "python3",
            "-c",
            probe,
        ),
    )
    for kind, selected in (("config", plan), ("sandbox", sandbox_plan)):
        name = f"hl-current-{uuid4().hex[:12]}-{kind}"
        try:
            await cli.run(
                *backend.create_argv(selected, name),
                environment=docker_environment(environment, credentials),
            )
            await backend._verify_effective_security(cli, name)
            result = await cli.run("start", "--attach", "--interactive", name, check=False)
            output = result.stdout + result.stderr
            if kind == "config":
                assert result.returncode == 1, output
                assert b"No prompt provided via stdin." in output, output
                assert b"configuration error" not in output.lower()
            else:
                assert result.returncode == 0, output
                assert b"ISOLATION_PASS" in output
                assert (workspace / "probe.txt").read_text() == "ok"
        finally:
            await cli.run("rm", "--force", name, check=False)
            remaining = await cli.run("ps", "--all", "--quiet", "--filter", f"name=^/{name}$")
            assert not remaining.stdout.strip()
