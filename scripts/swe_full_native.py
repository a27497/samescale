"""Direct native Codex for new HumanEval controls, with the same provider-only boundary."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from harnesslab.egress import EgressProxyRuntime, boundary_for_provider_url
from harnesslab.sandbox.docker_cli import _DockerCLI, docker_environment
from scripts.coding_agent_eval import (
    digest,
    docker,
    load,
    native_arguments,
    restrictions,
    run_capture,
    save,
)
from scripts.swe_full_budget import ResponseMeter


async def run_native(
    case: Path, config: dict[str, Any], vendor: Path, auth: Path, *, initial: float, limit: float
) -> dict[str, Any]:
    if digest((vendor / "bin/codex").read_bytes()) != config["codex_binary_sha256"]:
        raise ValueError("native Codex identity drift")
    data = load(auth)
    if data.get("auth_mode") != "chatgpt":
        raise ValueError("existing ChatGPT reference required")
    secrets = [v.encode() for v in data.get("tokens", {}).values() if isinstance(v, str)]
    proxy_image = await EgressProxyRuntime().ensure_image()
    boundary = boundary_for_provider_url(
        config["provider_url"],
        network_name="samescale-full-" + uuid4().hex,
        proxy_name="samescale-full-proxy-" + uuid4().hex,
        proxy_image=proxy_image,
    )
    cli = _DockerCLI(environment=docker_environment(os.environ, {}))
    save(case / "egress-attestation.json", (await boundary.provision(cli)).model_dump(mode="json"))
    meter = ResponseMeter(
        case,
        network=boundary.subject_network_mode,
        image=config["python_image"],
        initial=initial,
        limit=limit,
    )
    name = "samescale-full-agent-" + uuid4().hex
    try:
        args = native_arguments(config)
        args[-1:-1] = meter.arguments()
        command = restrictions(
            name,
            boundary.subject_network_mode,
            config["python_image"],
            [
                f"type=bind,src={case / 'workspace'},dst=/workspace",
                f"type=bind,src={vendor},dst=/opt/codex,readonly",
                f"type=bind,src={auth},dst=/run/credential/auth.json,readonly",
            ],
        )
        command[command.index("--user") + 1] = f"{os.getuid()}:{os.getgid()}"
        command.pop()
        for key, value in {**boundary.subject_proxy_environment(), **meter.environment()}.items():
            command.extend(["--env", f"{key}={value}"])
        command += [
            config["python_image"],
            "python",
            "-c",
            "import os,pathlib,shutil; p=pathlib.Path('/tmp/codex-home'); p.mkdir(mode=0o700); "
            "shutil.copyfile('/run/credential/auth.json',p/'auth.json'); "
            "os.chmod(p/'auth.json',0o600); "
            "os.execv('/opt/codex/bin/codex'," + repr(args) + ")",
        ]
        subprocess.run(
            command, capture_output=True, check=True, env=docker_environment(os.environ, {})
        )
        save(case / "agent-container.json", json.loads(docker("inspect", name).stdout)[0])
        meter.watch(name)
        status = run_capture(
            ["docker", "start", "--attach", "--interactive", name],
            case / "agent",
            timeout=config["agent_timeout_seconds"],
            prompt=(case / "prompt.txt").read_bytes(),
            secrets=secrets,
            jsonl=True,
        )
        result = meter.finish()
        status["budget_stopped"] = result["stopped_budget"]
        status["meter_error"] = result["stopped_meter_error"]
        save(case / "agent-process.json", status)
    finally:
        if not meter.closed.is_set():
            meter.finish()
        docker("rm", "--force", name)
        (case / "egress.jsonl").write_bytes(docker("logs", boundary.proxy_name).stdout)
        await boundary.cleanup(cli)
    events = [json.loads(s) for s in (case / "agent.stdout").read_text().splitlines()]
    completed = [e for e in events if e.get("type") == "turn.completed"]
    observed = completed[-1].get("usage", {}) if completed else {}
    if not result["response_count"] or (
        observed
        and any(
            observed.get(k, 0) > result["usage"][k]
            for k in ("input_tokens", "cached_input_tokens", "output_tokens")
        )
    ):
        raise RuntimeError("missing/mismatched live response telemetry: stop paid execution")
    return result
