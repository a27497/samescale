"""User-authorized external CLI pilot; never dispatches SameScale REAL_CODEX."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import tarfile
from pathlib import Path
from uuid import uuid4

from harnesslab.egress import EgressProxyRuntime, boundary_for_provider_url
from harnesslab.sandbox.docker_cli import _DockerCLI, docker_environment
from scripts.coding_agent_eval import (
    REPO,
    SPEC,
    digest,
    docker,
    load,
    native_arguments,
    restrictions,
    run_capture,
    save,
)
from scripts.swe_full_budget import ResponseMeter
from scripts.swe_mixed_eval import check_inputs


async def agents(
    root: Path,
    output: Path,
    vendor: Path,
    auth: Path,
    task_ids: list[str] | None = None,
    budget: tuple[float, float] | None = None,
) -> None:
    check_inputs(root)
    mixed = load(root / "config.json")
    config = load(SPEC / "config.json")
    config["agent_timeout_seconds"] = 900
    if output.exists() or output.is_relative_to(REPO):
        raise ValueError("new evidence directory outside Git required")
    if digest((vendor / "bin/codex").read_bytes()) != config["codex_binary_sha256"]:
        raise ValueError("Codex binary identity drift")
    auth_data = load(auth)
    if auth_data.get("auth_mode") != "chatgpt" or os.getuid() == 0:
        raise ValueError("expected existing non-root ChatGPT credential reference")
    secrets = [v.encode() for v in auth_data.get("tokens", {}).values() if isinstance(v, str)]
    output.mkdir(parents=True, mode=0o700)
    save(output / "runtime-config.json", config)
    save(
        output / "selection.json",
        {
            "task_ids": task_ids if task_ids is not None else mixed["pilot_task_ids"],
            "full_stage": "NOT_RUN",
            "execution_route": "EXTERNAL_CODEX_CLI",
            "product_REAL_CODEX": "UNCHANGED_CLOSED",
        },
    )
    selected = task_ids if task_ids is not None else mixed["pilot_task_ids"]
    proxy_image = await EgressProxyRuntime().ensure_image()
    cli = _DockerCLI(environment=docker_environment(os.environ, {}))
    for task_id in selected:
        task = next(t for t in mixed["tasks"] if t["instance_id"] == task_id)
        row = load(root / "hidden" / (task_id + ".json"))
        case = output / task_id
        case.mkdir()
        workspace = case / "workspace"
        workspace.mkdir()
        # Export only the fixed base tree. No upstream history or oracle is exposed.
        with (case / "base.tar").open("xb") as stream:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    task["image"],
                    "git",
                    "-C",
                    "/testbed",
                    "archive",
                    task["base_commit"],
                ],
                stdout=stream,
                check=True,
                env=docker_environment(os.environ, {}),
            )
        with tarfile.open(case / "base.tar") as archive:
            archive.extractall(workspace, filter="data")
        subprocess.run(["git", "init", "-q", str(workspace)], check=True)
        for args in (
            ["add", "-A"],
            [
                "-c",
                "user.name=SameScale baseline",
                "-c",
                "user.email=baseline@localhost",
                "commit",
                "-q",
                "-m",
                "fixed baseline",
            ],
        ):
            subprocess.run(["git", "-C", str(workspace), *args], check=True)
        # Keep installed dependencies, remove upstream history/setup scripts from Subject FS.
        context = case / "subject-image"
        context.mkdir()
        (context / "Dockerfile").write_text(
            "FROM " + task["image"] + "\nUSER root\n"
            "RUN rm -rf /testbed /root/*.sh /root/.cache /root/.gitconfig\n"
            "ENV PATH=/opt/miniconda3/envs/testbed/bin:/opt/miniconda3/bin:$PATH\n"
            "ENTRYPOINT []\n"
        )
        build = run_capture(
            [
                "docker",
                "build",
                "--network",
                "none",
                "--iidfile",
                str(context / "image-id"),
                str(context),
            ],
            case / "subject-build",
            timeout=180,
        )
        save(case / "subject-build-process.json", build)
        if build["exit_code"]:
            raise RuntimeError("subject image build failed before provider execution")
        image = (context / "image-id").read_text().strip()
        prompt = (
            "Fix the issue described below in this repository. The repository is the fixed "
            "original source tree, with installed project dependencies available. You may inspect "
            "source and existing tests, and run your own checks. Independent hidden tests are "
            "unavailable. Do not retrieve the benchmark, upstream fixes, or access credentials. "
            "Do not modify .git metadata. In your final message include exactly one standalone "
            "line: SAMESCALE_SELF_REPORT=PASS, SAMESCALE_SELF_REPORT=FAIL, or "
            "SAMESCALE_SELF_REPORT=UNKNOWN. PASS means you believe the task is fully correct; "
            "FAIL means incomplete/incorrect; UNKNOWN means you cannot decide. Your claim is "
            "recorded separately from verification.\n\nIssue:\n" + row["problem_statement"]
        )
        (case / "prompt.txt").write_text(prompt)
        boundary = boundary_for_provider_url(
            config["provider_url"],
            network_name="samescale-external-" + uuid4().hex,
            proxy_name="samescale-external-proxy-" + uuid4().hex,
            proxy_image=proxy_image,
        )
        name = "samescale-external-agent-" + uuid4().hex
        attestation = await boundary.provision(cli)
        save(case / "egress-attestation.json", attestation.model_dump(mode="json"))
        meter = (
            ResponseMeter(
                case,
                network=boundary.subject_network_mode,
                image=config["python_image"],
                initial=budget[0],
                limit=budget[1],
            )
            if budget
            else None
        )
        meter_result = None
        try:
            mounts = [
                f"type=bind,src={workspace},dst=/workspace",
                f"type=bind,src={vendor},dst=/opt/codex,readonly",
                f"type=bind,src={auth},dst=/run/credential/auth.json,readonly",
            ]
            command = restrictions(name, boundary.subject_network_mode, image, mounts)
            command[command.index("--user") + 1] = f"{os.getuid()}:{os.getgid()}"
            command[command.index("--memory") + 1] = "4g"
            command.pop()
            for key, value in boundary.subject_proxy_environment().items():
                command.extend(["--env", f"{key}={value}"])
            arguments = native_arguments(config)
            if meter:
                arguments[-1:-1] = meter.arguments()
                for key, value in meter.environment().items():
                    command.extend(["--env", f"{key}={value}"])
            command.extend(
                [
                    image,
                    "python",
                    "-c",
                    "import os,pathlib,shutil; p=pathlib.Path('/tmp/codex-home'); "
                    "p.mkdir(mode=0o700); "
                    "shutil.copyfile('/run/credential/auth.json',p/'auth.json'); "
                    "os.chmod(p/'auth.json',0o600); "
                    "os.execv('/opt/codex/bin/codex'," + repr(arguments) + ")",
                ]
            )
            subprocess.run(
                command, capture_output=True, check=True, env=docker_environment(os.environ, {})
            )
            save(case / "agent-container.json", json.loads(docker("inspect", name).stdout)[0])
            if meter:
                meter.watch(name)
            print("REAL EXTERNAL CLI START " + task_id, flush=True)
            status = run_capture(
                ["docker", "start", "--attach", "--interactive", name],
                case / "agent",
                timeout=config["agent_timeout_seconds"],
                prompt=prompt.encode(),
                secrets=secrets,
                jsonl=True,
            )
            if meter:
                meter_result = meter.finish()
                status["budget_stopped"] = meter_result["stopped_budget"]
                status["meter_error"] = meter_result["stopped_meter_error"]
            save(case / "agent-process.json", status)
        finally:
            if meter and not meter.closed.is_set():
                meter.finish()
            docker("rm", "--force", name)
            (case / "egress.jsonl").write_bytes(docker("logs", boundary.proxy_name).stdout)
            await boundary.cleanup(cli)
        # Derive from saved original code; preserve file modes and symlink text.
        from scripts.swe_external_delivery import delivery

        delivery(case)
        events = [json.loads(line) for line in (case / "agent.stdout").read_text().splitlines()]
        completed = [e for e in events if e.get("type") == "turn.completed"]
        finals = [
            e["item"].get("text", "")
            for e in events
            if e.get("type") == "item.completed"
            and e.get("item", {}).get("type") == "agent_message"
        ]
        if meter_result:
            observed = completed[-1].get("usage", {}) if completed else {}
            if observed:
                differences = {
                    k: meter_result["usage"][k] - observed.get(k, 0)
                    for k in ("input_tokens", "cached_input_tokens", "output_tokens")
                }
                if any(value < 0 for value in differences.values()):
                    save(
                        case / "meter-undercoverage.json",
                        {"turn_usage": observed, "response_usage": meter_result["usage"]},
                    )
                    raise RuntimeError("live meter undercovers CLI usage; stop paid execution")
                save(
                    case / "meter-reconciliation.json",
                    {
                        "turn_usage": observed,
                        "response_usage": meter_result["usage"],
                        "extra_response_usage": differences,
                        "budget_counts_all_responses_including_zero_output_startup": True,
                    },
                )
            if not meter_result["response_count"] or meter_result["stopped_meter_error"]:
                raise RuntimeError("no valid response telemetry; stop paid execution")
        print(
            json.dumps(
                {
                    "task": task_id,
                    "process": status,
                    "usage": [e.get("usage") for e in completed],
                    "final": finals[-1:],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex-vendor", type=Path, required=True)
    parser.add_argument("--auth-file", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(
        agents(
            args.root.absolute(),
            args.output.absolute(),
            args.codex_vendor.absolute(),
            args.auth_file.absolute(),
        )
    )
