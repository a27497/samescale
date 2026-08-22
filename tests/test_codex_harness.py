from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from harnesslab.contracts.common import NetworkPolicy
from harnesslab.harness_lane.adapter import (
    CodexExecutionPlan,
    CodexHarnessAdapter,
    HarnessAdapterError,
)
from harnesslab.harness_lane.docker_backend import DockerCodexBackend
from harnesslab.harness_lane.fake import (
    PRIVATE_REASONING_SENTINEL,
    FakeCodexBackend,
    FakeCodexScenario,
)
from harnesslab.harness_lane.models import (
    CodexHarnessProfile,
    CodexProcessCapture,
    HarnessFailureCategory,
    HarnessLaneOutcome,
    ObservedModelStatus,
    TraceEventType,
)
from harnesslab.harness_lane.profile import (
    CODEX_CLI_VERSION,
    SHELL_TOOL_ENVIRONMENT_POLICY,
    canonical_codex_profile,
)
from harnesslab.harness_lane.prompt import (
    PROMPT_TEMPLATE_VERSION,
    CodexHarnessPrompt,
    render_codex_harness_prompt,
)
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.harness_lane.runtime import REQUIRED_EXEC_HELP, CodexRuntime
from harnesslab.harness_lane.toolchains import unsatisfied_tools
from harnesslab.harness_lane.trace import collect_codex_jsonl
from harnesslab.sandbox.docker_cli import CommandResult, _DockerCLI
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.runner import DockerSandbox
from harnesslab.tasks.package import TaskPackage, digest_tree

ROOT = Path(__file__).resolve().parents[1]
TASKS = (
    ROOT / "tasks" / "micro-python-clamp" / "1.0.0",
    ROOT / "tasks" / "micro-java-clamp" / "1.0.0",
    ROOT / "tasks" / "micro-typescript-clamp" / "1.0.0",
)


def fake_image() -> ImageIdentity:
    return ImageIdentity(
        reference="harnesslab-phase-e-codex:0.149.0",
        image_id="sha256:" + "1" * 64,
    )


def fake_profile() -> CodexHarnessProfile:
    return canonical_codex_profile(fake_image(), execution_timeout_seconds=30)


def prompt_for(workspace: Path) -> CodexHarnessPrompt:
    return render_codex_harness_prompt(
        task_instruction="Correct the clamp implementation.",
        task_digest="sha256:" + "2" * 64,
        workspace_input_digest="sha256:" + "3" * 64,
        context_digest=None,
        network_policy=NetworkPolicy.DENY,
    )


def all_artifact_text(root: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in root.rglob("*")
        if path.is_file()
    )


@pytest.mark.asyncio
async def test_codex_runtime_doctor_verifies_pinned_version_and_flags() -> None:
    result = await CodexRuntime().doctor()

    assert result.version == f"codex-cli {CODEX_CLI_VERSION}"
    assert result.image.image_id.startswith("sha256:")
    assert result.required_flags == REQUIRED_EXEC_HELP
    requirements = tuple(
        tool
        for task_path in TASKS
        for tool in TaskPackage.load(task_path).definition.expected_tools
    )
    assert not unsatisfied_tools(requirements, result.tool_versions)


def test_codex_profile_and_prompt_hashes_are_deterministic() -> None:
    first_profile = fake_profile()
    second_profile = fake_profile()
    first_prompt = render_codex_harness_prompt(
        task_instruction="Fix the task.",
        task_digest="sha256:" + "4" * 64,
        workspace_input_digest="sha256:" + "5" * 64,
        context_digest="sha256:" + "6" * 64,
        network_policy=NetworkPolicy.DENY,
    )
    second_prompt = render_codex_harness_prompt(
        task_instruction="Fix the task.",
        task_digest="sha256:" + "4" * 64,
        workspace_input_digest="sha256:" + "5" * 64,
        context_digest="sha256:" + "6" * 64,
        network_policy=NetworkPolicy.DENY,
    )

    assert first_profile.fingerprint == second_profile.fingerprint
    assert first_prompt.prompt_hash == second_prompt.prompt_hash
    assert first_prompt.template_version == PROMPT_TEMPLATE_VERSION
    with pytest.raises(ValidationError, match="frozen"):
        cast(Any, first_profile).requested_model = "invented"


def test_codex_exec_plan_uses_stdin_and_canonical_isolation_flags(tmp_path: Path) -> None:
    adapter = CodexHarnessAdapter()
    profile = fake_profile()
    plan = adapter.prepare(
        profile,
        prompt_for(tmp_path),
        workspace=tmp_path,
        context=None,
        task_id="micro-python-clamp",
    )

    assert plan.argv[0:3] == ("codex", "exec", "--json")
    assert plan.argv[-1] == "-"
    assert plan.prompt == prompt_for(tmp_path).text
    assert "--strict-config" in plan.argv
    assert "--ephemeral" in plan.argv
    assert "--ignore-user-config" in plan.argv
    assert "--ignore-rules" in plan.argv
    assert "--skip-git-repo-check" in plan.argv
    assert 'approval_policy="never"' in plan.argv
    assert 'web_search="disabled"' in plan.argv
    assert "sandbox_workspace_write.network_access=false" in plan.argv
    assert "mcp_servers={}" in plan.argv
    assert 'shell_environment_policy.inherit="core"' in plan.argv
    assert "shell_environment_policy.ignore_default_excludes=false" in plan.argv
    assert (
        'shell_environment_policy.exclude=["*KEY*","*SECRET*","*TOKEN*","*PASSWORD*"]' in plan.argv
    )
    assert "allow_login_shell=false" in plan.argv
    assert profile.shell_tool_environment_policy == SHELL_TOOL_ENVIRONMENT_POLICY
    assert profile.requested_model in plan.argv


def test_real_codex_backend_outer_docker_argv_is_hardened_and_secret_free(
    tmp_path: Path,
) -> None:
    adapter = CodexHarnessAdapter()
    plan = adapter.prepare(
        fake_profile(),
        prompt_for(tmp_path),
        workspace=tmp_path,
        context=None,
        task_id="micro-python-clamp",
    )
    secret = "explicit-fake-secret-not-for-argv"
    backend = DockerCodexBackend(explicitly_enabled=True, credentials={"OPENAI_API_KEY": secret})
    argv = backend.create_argv(plan, "harnesslab-codex-test")

    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "--read-only" in argv
    assert "ALL" in argv
    assert "no-new-privileges=true" in argv
    assert "10001:10001" in argv
    assert "/workspace" in " ".join(argv)
    assert "/context" not in " ".join(argv)
    assert "docker.sock" not in " ".join(argv)
    assert "CODEX_HOME" not in " ".join(argv)
    assert secret not in argv
    assert argv[-1] == "-"


@pytest.mark.asyncio
async def test_real_codex_cleanup_query_failure_is_unverified() -> None:
    empty_digest = "sha256:" + hashlib.sha256(b"").hexdigest()

    class CleanupQueryFailureCLI(_DockerCLI):
        def __init__(self) -> None:
            self.commands: list[tuple[str, ...]] = []

        async def run(
            self,
            *arguments: str,
            timeout: float = 60,
            environment: Mapping[str, str] | None = None,
            check: bool = True,
        ) -> CommandResult:
            self.commands.append(arguments)
            return CommandResult(
                1 if arguments[0] == "ps" else 0,
                b"",
                b"Cannot connect to the Docker daemon" if arguments[0] == "ps" else b"",
                empty_digest,
                empty_digest,
                False,
                False,
            )

    cli = CleanupQueryFailureCLI()
    with pytest.raises(HarnessAdapterError, match="cleanup was not verified"):
        await DockerCodexBackend(explicitly_enabled=True)._cleanup_outer_container(
            cli, "harnesslab-codex-cleanup-query-failure"
        )

    assert tuple(command[0] for command in cli.commands) == ("kill", "rm", "ps")


def test_task_expected_tools_reject_old_python_and_java() -> None:
    requirements = tuple(
        tool
        for task_path in TASKS
        for tool in TaskPackage.load(task_path).definition.expected_tools
    )

    failures = unsatisfied_tools(
        requirements,
        {"python": "3.11.13", "java": "17.0.16", "javac": "17.0.16", "node": "24.4.1"},
    )

    assert any(failure.startswith("python expected 3.12") for failure in failures)
    assert any(failure.startswith("java expected 21") for failure in failures)
    assert any(failure.startswith("javac expected 21") for failure in failures)
    assert not any(failure.startswith("node expected 24") for failure in failures)


def test_codex_harness_prompt_excludes_verifier_and_oracle(tmp_path: Path) -> None:
    copied = tmp_path / "micro-python-clamp" / "1.0.0"
    shutil.copytree(TASKS[0], copied)
    (copied / "verifier" / "hidden.txt").write_text("HIDDEN_VERIFIER_SENTINEL", encoding="utf-8")
    (copied / "oracle" / "hidden.txt").write_text("HIDDEN_ORACLE_SENTINEL", encoding="utf-8")
    package = TaskPackage.load(copied)
    materialized = package.materialize(tmp_path / "materialized")
    try:
        prompt = render_codex_harness_prompt(
            task_instruction=package.definition.instruction,
            task_digest=package.definition.content_digest,
            workspace_input_digest=digest_tree(materialized.workspace),
            context_digest=None,
            network_policy=NetworkPolicy.DENY,
        )
        assert "HIDDEN_VERIFIER_SENTINEL" not in prompt.text
        assert "HIDDEN_ORACLE_SENTINEL" not in prompt.text
        assert not (materialized.root / "verifier").exists()
        assert not (materialized.root / "oracle").exists()
    finally:
        materialized.cleanup()


def test_sanitized_jsonl_maps_trace_order_unknown_and_private_reasoning() -> None:
    lines = (
        json.dumps({"type": "thread.started", "thread_id": "thread-safe"}),
        json.dumps({"type": "turn.started"}),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "r1",
                    "type": "reasoning",
                    "text": PRIVATE_REASONING_SENTINEL,
                    "summary": [PRIVATE_REASONING_SENTINEL],
                },
            }
        ),
        json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "future", "type": "future_safe_item", "status": "completed"},
            }
        ),
        json.dumps({"type": "future.event", "id": "safe-structure"}),
        json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "m1", "type": "agent_message", "text": "public answer"},
            }
        ),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 4}}),
    )
    collection = collect_codex_jsonl(CodexProcessCapture(lines, 0, 3))

    assert [event.ordinal for event in collection.sanitized_events] == list(range(1, 8))
    assert [event.ordinal for event in collection.trace.events] == list(range(1, 8))
    assert TraceEventType.REASONING_PRESENT in [event.type for event in collection.trace.events]
    assert [event.type for event in collection.trace.events].count(TraceEventType.UNKNOWN) == 2
    assert PRIVATE_REASONING_SENTINEL not in collection.sanitized_jsonl
    assert PRIVATE_REASONING_SENTINEL not in collection.trace.canonical_json()
    assert collection.failure_category is None


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        pytest.param(
            FakeCodexScenario.MALFORMED_JSONL,
            HarnessFailureCategory.PROTOCOL_ERROR,
            id="protocol",
        ),
        pytest.param(
            FakeCodexScenario.TURN_FAILED,
            HarnessFailureCategory.MODEL_TURN_FAILED,
            id="model-turn",
        ),
        pytest.param(
            FakeCodexScenario.PROCESS_ERROR,
            HarnessFailureCategory.PROCESS_ERROR,
            id="process",
        ),
        pytest.param(FakeCodexScenario.TIMEOUT, HarnessFailureCategory.TIMEOUT, id="timeout"),
        pytest.param(FakeCodexScenario.CANCELLED, HarnessFailureCategory.CANCELLED, id="cancelled"),
        pytest.param(
            FakeCodexScenario.PROFILE_VIOLATION_WEB,
            HarnessFailureCategory.PROFILE_VIOLATION,
            id="profile-web",
        ),
        pytest.param(
            FakeCodexScenario.PROFILE_VIOLATION_MCP,
            HarnessFailureCategory.PROFILE_VIOLATION,
            id="profile-mcp",
        ),
    ],
)
@pytest.mark.asyncio
async def test_harness_failure_taxonomy_is_structurally_distinct(
    tmp_path: Path, scenario: FakeCodexScenario, expected: HarnessFailureCategory
) -> None:
    adapter = CodexHarnessAdapter()
    plan = adapter.prepare(
        fake_profile(),
        prompt_for(tmp_path),
        workspace=tmp_path,
        context=None,
        task_id="micro-python-clamp",
    )
    capture = await FakeCodexBackend(scenario).run(plan)
    collection = adapter.collect(capture)

    assert collection.failure_category is expected


def test_structured_authentication_error_is_not_guessed_from_free_text() -> None:
    structured = collect_codex_jsonl(
        CodexProcessCapture(
            (
                json.dumps({"type": "thread.started", "thread_id": "t"}),
                json.dumps(
                    {
                        "type": "error",
                        "error": {"code": "invalid_api_key", "message": "safe"},
                    }
                ),
            ),
            1,
            2,
        )
    )
    unstructured = collect_codex_jsonl(
        CodexProcessCapture(
            (
                json.dumps({"type": "thread.started", "thread_id": "t"}),
                json.dumps({"type": "error", "error": {"message": "authentication failed"}}),
            ),
            1,
            2,
        )
    )

    assert structured.failure_category is HarnessFailureCategory.AUTHENTICATION
    assert unstructured.failure_category is HarnessFailureCategory.MODEL_TURN_FAILED


@pytest.mark.asyncio
async def test_failed_intermediate_command_does_not_fail_completed_turn(tmp_path: Path) -> None:
    adapter = CodexHarnessAdapter()
    plan = adapter.prepare(
        fake_profile(),
        prompt_for(tmp_path),
        workspace=tmp_path,
        context=None,
        task_id="micro-python-clamp",
    )
    capture = await FakeCodexBackend(FakeCodexScenario.INTERMEDIATE_COMMAND_FAILURE).run(plan)
    collection = adapter.collect(capture)

    command = next(
        event for event in collection.trace.events if event.type is TraceEventType.COMMAND_EXECUTION
    )
    assert command.exit_code == 1
    assert collection.terminal_event == "turn.completed"
    assert collection.failure_category is None


@pytest.mark.asyncio
@pytest.mark.parametrize("task_path", TASKS, ids=("python", "java", "typescript"))
async def test_three_h_lane_tasks_fake_codex_pass_hidden_verifier(
    tmp_path: Path, task_path: Path
) -> None:
    image = await CodexRuntime().ensure_image()
    profile = canonical_codex_profile(image, execution_timeout_seconds=30)
    runner = CodexHarnessRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        sandbox=DockerSandbox(
            artifact_root=tmp_path / "sandbox-artifacts",
            runtime_root=tmp_path / "sandbox-runtime",
        ),
    )
    result = await runner.run(
        task_path,
        profile,
        backend=FakeCodexBackend(FakeCodexScenario.SOLVE),
        run_id=f"fake-{task_path.parent.name}-{task_path.parent.parent.name}",
    )

    evidence = result.evidence
    assert evidence.outcome is HarnessLaneOutcome.VERIFIED_PASS
    assert evidence.verifier_passed
    assert evidence.verifier_score == 1.0
    assert evidence.workspace_input_digest != evidence.workspace_output_digest
    assert len(evidence.changed_paths) == 1
    assert evidence.verifier_sandbox_manifest is not None
    assert (
        evidence.verifier_sandbox_manifest.workspace_input_digest
        == evidence.workspace_output_digest
    )
    assert evidence.profile.codex_image.image_id == image.image_id
    assert evidence.observed_model is None
    assert evidence.observed_model_status is ObservedModelStatus.NOT_EXPOSED
    assert PRIVATE_REASONING_SENTINEL not in all_artifact_text(result.artifact_directory)


@pytest.mark.asyncio
async def test_codex_self_report_cannot_override_hidden_verifier(tmp_path: Path) -> None:
    profile = canonical_codex_profile(await CodexRuntime().ensure_image())
    runner = CodexHarnessRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        sandbox=DockerSandbox(
            artifact_root=tmp_path / "sandbox-artifacts",
            runtime_root=tmp_path / "sandbox-runtime",
        ),
    )
    result = await runner.run(
        TASKS[0],
        profile,
        backend=FakeCodexBackend(FakeCodexScenario.SELF_REPORTED_SUCCESS_WRONG_WORKSPACE),
        run_id="self-report-wrong",
    )

    assert result.evidence.terminal_native_event == "turn.completed"
    assert result.evidence.process_exit_code == 0
    assert result.evidence.outcome is HarnessLaneOutcome.VERIFIED_FAIL
    assert result.evidence.verifier_passed is False
    assert result.evidence.changed_paths == ()


@pytest.mark.asyncio
async def test_filesystem_diff_is_authoritative_over_native_file_change(tmp_path: Path) -> None:
    profile = canonical_codex_profile(await CodexRuntime().ensure_image())
    result = await CodexHarnessRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        sandbox=DockerSandbox(
            artifact_root=tmp_path / "sandbox-artifacts",
            runtime_root=tmp_path / "sandbox-runtime",
        ),
    ).run(
        TASKS[0],
        profile,
        backend=FakeCodexBackend(FakeCodexScenario.FILE_CHANGE_LIE),
        run_id="file-change-lie",
    )

    assert TraceEventType.FILE_CHANGE in result.evidence.trace_event_types
    assert result.evidence.changed_paths == ()
    assert result.evidence.workspace_input_digest == result.evidence.workspace_output_digest
    assert result.evidence.outcome is HarnessLaneOutcome.VERIFIED_FAIL


@pytest.mark.asyncio
async def test_requested_model_is_not_fabricated_as_observed_model(tmp_path: Path) -> None:
    profile = canonical_codex_profile(await CodexRuntime().ensure_image())
    result = await CodexHarnessRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        sandbox=DockerSandbox(
            artifact_root=tmp_path / "sandbox-artifacts",
            runtime_root=tmp_path / "sandbox-runtime",
        ),
    ).run(
        TASKS[0],
        profile,
        backend=FakeCodexBackend(FakeCodexScenario.SELF_REPORTED_SUCCESS_WRONG_WORKSPACE),
        run_id="model-not-exposed",
    )

    assert result.evidence.requested_model == "gpt-5.6-sol"
    assert result.evidence.observed_model is None
    assert result.evidence.observed_model_status is ObservedModelStatus.NOT_EXPOSED


class CredentialEchoBackend(DockerCodexBackend):
    def __init__(self, secret: str) -> None:
        super().__init__(explicitly_enabled=True, credentials={"OPENAI_API_KEY": secret})

    async def run(self, plan: CodexExecutionPlan) -> CodexProcessCapture:
        secret = self.credentials["OPENAI_API_KEY"]
        (plan.workspace / "calculator.py").write_text(
            "def clamp(value: int, lower: int, upper: int) -> int:\n"
            "    return max(lower, min(value, upper))\n",
            encoding="utf-8",
        )
        return CodexProcessCapture(
            (
                json.dumps({"type": "thread.started", "thread_id": "secret-thread"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "m", "type": "agent_message", "text": secret},
                    }
                ),
                json.dumps({"type": "turn.completed", "usage": {}}),
            ),
            0,
            1,
        )


@pytest.mark.asyncio
async def test_backend_credentials_automatically_redact_all_harness_artifacts(
    tmp_path: Path,
) -> None:
    secret = "fake-provider-credential-boundary-value"
    profile = canonical_codex_profile(await CodexRuntime().ensure_image())
    backend = CredentialEchoBackend(secret)
    plan = CodexHarnessAdapter().prepare(
        profile,
        prompt_for(tmp_path),
        workspace=tmp_path,
        context=None,
        task_id="micro-python-clamp",
    )
    argv = backend.create_argv(plan, "harnesslab-codex-credential-boundary")
    assert "OPENAI_API_KEY" in argv
    assert secret not in argv
    assert backend.artifact_secret_values == (secret,)

    result = await CodexHarnessRunner(
        artifact_root=tmp_path / "artifacts", runtime_root=tmp_path / "runtime"
    ).run(
        TASKS[0],
        profile,
        backend=backend,
        run_id="redacted-native",
    )

    artifact_text = all_artifact_text(result.artifact_directory)
    assert result.evidence.outcome is HarnessLaneOutcome.VERIFIED_PASS
    assert secret not in artifact_text
    assert "[REDACTED]" in (
        result.artifact_directory / "native" / "codex.sanitized.jsonl"
    ).read_text(encoding="utf-8")
    for relative in (
        "native/codex.sanitized.jsonl",
        "trace/normalized.json",
        "manifest.json",
        "workspace/calculator.py",
        "verifier/manifest.json",
    ):
        assert secret not in (result.artifact_directory / relative).read_text(
            encoding="utf-8", errors="replace"
        )
