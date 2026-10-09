"""Pinned, keyless Docker fixture using the existing Codex process/JSONL adapter.

No real CLI is invoked. The Python fixture writes an actual isolated workspace;
the independent hidden verifier remains in the production H-Lane runner.
"""

from __future__ import annotations

import json
from pathlib import Path

from harnesslab.harness_lane.adapter import CodexExecutionPlan, HarnessAdapterError
from harnesslab.harness_lane.docker_backend import DockerCodexBackend
from harnesslab.harness_lane.fake import PRIVATE_REASONING_SENTINEL
from harnesslab.harness_lane.models import CodexProcessCapture
from harnesslab.local_execution.models import ExecutionPolicy
from harnesslab.sandbox.docker_cli import _DockerCLI


def fixture_script(scenario: str) -> str:
    # Fixed trusted code. Never import hidden assets, user credentials or task programs.
    return "\n".join(
        [
            "import json, os, pathlib, sys, time",
            "p = pathlib.Path",
            'assert not p("/verifier").exists() and not p("/oracle").exists()',
            'assert not p("/var/run/docker.sock").exists() and not p("/run/docker.sock").exists()',
            'assert not p("/workspace/.codex").exists() and not p("/home/dev").exists()',
            'sensitive = ("KEY", "TOKEN", "SECRET", "PASSWORD")',
            "assert not any(k for k in os.environ if any(s in k for s in sensitive))",
            "def emit(x): print(json.dumps(x), flush=True)",
            'emit({"type":"thread.started","thread_id":"fake-isolated-thread"})',
            'emit({"type":"turn.started"})',
            f'emit({{"type":"item.completed","item":{{"id":"reasoning","type":"reasoning","text":{PRIVATE_REASONING_SENTINEL!r}}}}})',
            "assert sys.stdin.read()",
            f"time.sleep({30 if scenario == 'timeout' else 8 if scenario == 'slow' else 0})",
            f"scenario = {scenario!r}",
            'if scenario in ("solve", "slow", "verifier_timeout"):',
            '    solution = "def clamp(value, lower, upper):\\n"',
            '    solution += "    return max(lower, min(value, upper))\\n"',
            '    p("/workspace/calculator.py").write_text(solution)',
            '    change = {"path":"/workspace/calculator.py","kind":"update"}',
            '    item = {"id":"file","type":"file_change","status":"completed","changes":[change]}',
            '    emit({"type":"item.completed","item":item})',
            'claim = {"id":"claim","type":"agent_message","text":"Implemented; tests pass."}',
            'emit({"type":"item.completed","item":claim})',
            'emit({"type":"turn.completed"})',
        ]
    )


class IsolatedFakeCodexBackend(DockerCodexBackend):
    def __init__(self, policy: ExecutionPolicy) -> None:
        super().__init__(explicitly_enabled=True, credentials={})
        self.policy = policy
        self.expected_workspace: Path | None = None
        self.run_id: str | None = None

    def container_name(self, plan: CodexExecutionPlan) -> str:
        if self.run_id is None:
            raise HarnessAdapterError("Attempt identity required")
        return "harnesslab-local-" + self.run_id

    def create_argv(self, plan: CodexExecutionPlan, container_name: str) -> tuple[str, ...]:
        argv = list(super().create_argv(plan, container_name))
        argv[1:1] = ["--pull", "never"]
        # Always use the inspected content ID. No tag resolution or automatic image pull.
        index = argv.index("--entrypoint")
        argv[index:] = [
            "--entrypoint",
            "python3",
            self.policy.subject_image_identity,
            "-c",
            fixture_script(self.policy.scenario),
        ]
        return tuple(argv)

    async def run(self, plan: CodexExecutionPlan) -> CodexProcessCapture:
        if plan.task_id != "micro-python-clamp" or plan.context is not None:
            raise HarnessAdapterError(
                "Fake Worker supports only the approved clamp fixture without context"
            )
        self.expected_workspace = plan.workspace.resolve()
        return await super().run(plan)

    async def _verify_effective_security(self, cli: _DockerCLI, name: str) -> None:
        await super()._verify_effective_security(cli, name)
        raw = await cli.run("inspect", name)
        container = json.loads(raw.stdout)[0]
        mounts = container["Mounts"]
        binds = [m for m in mounts if m["Type"] == "bind"]
        host = container["HostConfig"]
        if (
            len(binds) != 1
            or binds[0]["Destination"] != "/workspace"
            or not binds[0]["RW"]
            or Path(binds[0]["Source"]) != self.expected_workspace
            or container["Image"] != self.policy.subject_image_identity
            or host["Memory"] != 1073741824
            or host["NanoCpus"] != 2000000000
            or host["PidsLimit"] != 256
            or host["RestartPolicy"]["Name"] != "no"
            or host.get("Devices")
            or host.get("PortBindings")
            or host.get("PidMode")
            or (
                container["Config"].get("Env")
                and any(
                    any(
                        word in e.split("=", 1)[0]
                        for word in ("TOKEN", "KEY", "SECRET", "PASSWORD")
                    )
                    for e in container["Config"]["Env"]
                )
            )
        ):
            raise HarnessAdapterError(
                "Fake subject mount/image/resource/environment attestation failed"
            )
