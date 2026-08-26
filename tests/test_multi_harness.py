from __future__ import annotations

import hashlib
import shutil
import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from harnesslab.harness_lane.adapter import HarnessAdapterError
from harnesslab.harness_lane.models import (
    HarnessFailureCategory,
    HarnessLaneOutcome,
    TraceEventType,
)
from harnesslab.multi_harness.adapter import (
    ClaudeCodeAdapter,
    DeepSeekHarnessAdapter,
    HarnessExecutionPlan,
)
from harnesslab.multi_harness.docker_backend import DockerMultiHarnessBackend
from harnesslab.multi_harness.fake import (
    PRIVATE_CLAUDE_REASONING_SENTINEL,
    FakeHarnessScenario,
    FakeMultiHarnessBackend,
)
from harnesslab.multi_harness.models import (
    DeepSeekSessionExtraction,
    HarnessKind,
    HarnessProcessCapture,
    ProcessDiagnosticCategory,
    StartupFailureCategory,
    TraceCoverage,
)
from harnesslab.multi_harness.profile import (
    CLAUDE_CLI_VERSION,
    DEEPSEEK_CLI_VERSION,
    canonical_claude_profile,
    canonical_deepseek_profile,
)
from harnesslab.multi_harness.prompt import (
    CLAUDE_PROMPT_VERSION,
    render_harness_prompt,
)
from harnesslab.multi_harness.runner import MultiHarnessRunner
from harnesslab.multi_harness.runtime import (
    CLAUDE_REQUIRED_HELP,
    DEEPSEEK_REQUIRED_HELP,
    MultiHarnessRuntime,
)
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.runner import DockerSandbox
from harnesslab.tasks.package import TaskPackage, digest_tree

ROOT = Path(__file__).resolve().parents[1]
TASKS = {
    "python": ROOT / "tasks" / "micro-python-clamp" / "1.0.0",
    "java": ROOT / "tasks" / "micro-java-clamp" / "1.0.0",
    "typescript": ROOT / "tasks" / "micro-typescript-clamp" / "1.0.0",
}


def fake_image(harness: HarnessKind) -> ImageIdentity:
    return ImageIdentity(
        reference=f"fake-{harness.value}:phase-f",
        image_id="sha256:" + ("4" if harness is HarnessKind.CLAUDE_CODE else "5") * 64,
    )


def fake_profile(harness: HarnessKind):  # type: ignore[no-untyped-def]
    if harness is HarnessKind.CLAUDE_CODE:
        return canonical_claude_profile(fake_image(harness), execution_timeout_seconds=30)
    return canonical_deepseek_profile(
        fake_image(harness), "sha256:" + "6" * 64, execution_timeout_seconds=30
    )


def adapter_for(harness: HarnessKind):  # type: ignore[no-untyped-def]
    return (
        ClaudeCodeAdapter()
        if harness is HarnessKind.CLAUDE_CODE
        else DeepSeekHarnessAdapter(observed_config_digest="sha256:" + "6" * 64)
    )


def artifact_text(root: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in root.rglob("*")
        if path.is_file()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", list(HarnessKind), ids=("claude", "deepseek"))
@pytest.mark.parametrize("language", tuple(TASKS))
async def test_three_h_lane_tasks_pass_each_phase_f_hidden_verifier(
    tmp_path: Path, harness: HarnessKind, language: str
) -> None:
    runner = MultiHarnessRunner(
        artifact_root=tmp_path / "artifacts", runtime_root=tmp_path / "runtime"
    )
    result = await runner.run(
        TASKS[language],
        fake_profile(harness),
        adapter=adapter_for(harness),
        backend=FakeMultiHarnessBackend(),
        run_id=f"{harness.value}-{language}",
    )

    assert result.evidence.outcome is HarnessLaneOutcome.VERIFIED_PASS
    assert result.evidence.verifier_passed is True
    assert result.evidence.verifier_score == 1.0
    assert result.evidence.changed_paths
    assert result.evidence.verifier_sandbox_manifest is not None
    assert (
        result.evidence.verifier_sandbox_manifest.workspace_input_digest
        == result.evidence.workspace_output_digest
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", list(HarnessKind), ids=("claude", "deepseek"))
async def test_multiharness_runner_normalizes_restrictive_managed_context_without_identity_drift(
    tmp_path: Path, harness: HarnessKind
) -> None:
    copied_task = tmp_path / "micro-typescript-clamp" / "1.0.0"
    shutil.copytree(TASKS["typescript"], copied_task)
    source_context = copied_task / "context"
    for path in (source_context, *source_context.rglob("*")):
        path.chmod(0o700 if path.is_dir() else 0o600)
    source_modes = {
        path.relative_to(source_context).as_posix() or ".": stat.S_IMODE(path.stat().st_mode)
        for path in (source_context, *source_context.rglob("*"))
    }
    package = TaskPackage.load(copied_task)
    assert package.definition.context_bundle is not None
    context_digest = package.definition.context_bundle.digest

    class InspectingBackend(FakeMultiHarnessBackend):
        async def run(self, plan: HarnessExecutionPlan) -> HarnessProcessCapture:
            assert plan.context is not None
            for path in (plan.context, *plan.context.rglob("*")):
                mode = stat.S_IMODE(path.stat().st_mode)
                assert mode & (0o555 if path.is_dir() else 0o444) == (
                    0o555 if path.is_dir() else 0o444
                )
            assert digest_tree(plan.context) == context_digest
            return await super().run(plan)

    profile = fake_profile(harness)
    result = await MultiHarnessRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        sandbox=DockerSandbox(
            artifact_root=tmp_path / "sandbox-artifacts",
            runtime_root=tmp_path / "sandbox-runtime",
        ),
    ).run(
        copied_task,
        profile,
        adapter=adapter_for(harness),
        backend=InspectingBackend(),
        run_id=f"restrictive-context-{harness.value}",
    )

    expected_prompt = render_harness_prompt(
        harness,
        task_instruction=package.definition.instruction,
        task_digest=package.definition.content_digest,
        workspace_input_digest=result.evidence.workspace_input_digest,
        context_digest=context_digest,
        network_policy=profile.network_policy,
    )
    assert result.evidence.outcome is HarnessLaneOutcome.VERIFIED_PASS
    assert result.evidence.workspace_input_digest == package.definition.workspace.digest
    assert result.evidence.context_digest == context_digest
    assert result.evidence.prompt_hash == expected_prompt.prompt_hash
    assert {
        path.relative_to(source_context).as_posix() or ".": stat.S_IMODE(path.stat().st_mode)
        for path in (source_context, *source_context.rglob("*"))
    } == source_modes


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", list(HarnessKind), ids=("claude", "deepseek"))
async def test_phase_f_self_report_cannot_override_hidden_verifier(
    tmp_path: Path, harness: HarnessKind
) -> None:
    result = await MultiHarnessRunner(
        artifact_root=tmp_path / "artifacts", runtime_root=tmp_path / "runtime"
    ).run(
        TASKS["python"],
        fake_profile(harness),
        adapter=adapter_for(harness),
        backend=FakeMultiHarnessBackend(FakeHarnessScenario.SELF_REPORTED_SUCCESS_WRONG_WORKSPACE),
        run_id=f"wrong-{harness.value}",
    )

    assert result.evidence.outcome is HarnessLaneOutcome.VERIFIED_FAIL
    assert result.evidence.verifier_passed is False
    assert result.evidence.changed_paths == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "expected"),
    (
        (FakeHarnessScenario.MALFORMED, HarnessFailureCategory.PROTOCOL_ERROR),
        (FakeHarnessScenario.PROCESS_ERROR, HarnessFailureCategory.PROCESS_ERROR),
        (FakeHarnessScenario.TIMEOUT, HarnessFailureCategory.TIMEOUT),
        (FakeHarnessScenario.PROFILE_VIOLATION, HarnessFailureCategory.PROFILE_VIOLATION),
    ),
)
async def test_claude_failed_attempts_preserve_taxonomy_and_skip_verifier(
    tmp_path: Path,
    scenario: FakeHarnessScenario,
    expected: HarnessFailureCategory,
) -> None:
    result = await MultiHarnessRunner(
        artifact_root=tmp_path / "artifacts", runtime_root=tmp_path / "runtime"
    ).run(
        TASKS["python"],
        fake_profile(HarnessKind.CLAUDE_CODE),
        adapter=ClaudeCodeAdapter(),
        backend=FakeMultiHarnessBackend(scenario),
        run_id=f"failed-{scenario.value.replace('_', '-')}",
    )
    assert result.evidence.outcome is HarnessLaneOutcome.HARNESS_ERROR
    assert result.evidence.harness_failure is expected
    assert result.evidence.verifier_sandbox_manifest is None


def test_claude_plan_is_non_bare_isolated_stream_json_with_canonical_tools(
    tmp_path: Path,
) -> None:
    profile = fake_profile(HarnessKind.CLAUDE_CODE)
    prompt = render_harness_prompt(
        HarnessKind.CLAUDE_CODE,
        task_instruction="Fix clamp.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=profile.network_policy,
    )
    plan = ClaudeCodeAdapter().prepare(
        profile, prompt, workspace=tmp_path, context=None, task_id="micro-python-clamp"
    )

    assert plan.argv[:3] == ("claude", "-p", prompt.text)
    assert "--bare" not in plan.argv
    assert (
        plan.argv[plan.argv.index("--output-format")],
        plan.argv[plan.argv.index("--output-format") + 1],
    ) == ("--output-format", "stream-json")
    assert "--verbose" in plan.argv
    assert "--forward-subagent-text" not in plan.argv
    assert plan.argv[plan.argv.index("--tools") + 1] == "Read,Edit,Write,Bash"
    assert plan.argv[plan.argv.index("--setting-sources") + 1] == ""
    assert plan.argv[plan.argv.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert "--disable-slash-commands" in plan.argv
    assert "AskUserQuestion" not in plan.argv
    assert "WebSearch" not in plan.argv
    assert dict(plan.environment_literals) == {
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "CLAUDE_CODE_NO_MODEL_FALLBACK": "1",
        "CLAUDE_CONFIG_DIR": "/tmp/claude-config",
    }


@pytest.mark.asyncio
async def test_phase_f_zero_stdout_exit_one_persists_only_redacted_safe_diagnostics(
    tmp_path: Path,
) -> None:
    secret = "r12-fake-stderr-secret"
    runtime_url = "https://r12-private-runtime.example.test"
    raw_stderr = (
        "Error: Invalid MCP configuration: mcpServers: Invalid input "
        f"credential={secret} runtime={runtime_url}"
    )

    class StartupFailureBackend(FakeMultiHarnessBackend):
        @property
        def artifact_secret_values(self) -> tuple[str, ...]:
            return (secret, runtime_url)

        async def run(self, plan: HarnessExecutionPlan) -> HarnessProcessCapture:
            return HarnessProcessCapture((), raw_stderr, 1, 1658)

    result = await MultiHarnessRunner(
        artifact_root=tmp_path / "artifacts", runtime_root=tmp_path / "runtime"
    ).run(
        TASKS["python"],
        fake_profile(HarnessKind.CLAUDE_CODE),
        adapter=ClaudeCodeAdapter(),
        backend=StartupFailureBackend(),
        run_id="safe-startup-failure",
    )

    persisted = artifact_text(result.artifact_directory)
    redacted = raw_stderr.replace(secret, "[REDACTED]").replace(runtime_url, "[REDACTED]")
    assert result.evidence.outcome is HarnessLaneOutcome.HARNESS_ERROR
    assert result.evidence.harness_failure is HarnessFailureCategory.PROCESS_ERROR
    assert result.evidence.process_exit_code == 1
    assert result.evidence.trace_event_count == 0
    assert result.evidence.stdout_line_count == 0
    assert result.evidence.stderr_category is ProcessDiagnosticCategory.PRESENT
    assert result.evidence.stderr_digest == (
        "sha256:" + hashlib.sha256(redacted.encode()).hexdigest()
    )
    assert (
        result.evidence.startup_failure_category is StartupFailureCategory.PROVIDER_BOOTSTRAP_ERROR
    )
    assert raw_stderr not in persisted
    assert "Invalid MCP configuration" not in persisted
    assert secret not in persisted
    assert runtime_url not in persisted


def test_deepseek_plan_uses_only_public_headless_contract(tmp_path: Path) -> None:
    profile = fake_profile(HarnessKind.DEEPSEEK)
    prompt = render_harness_prompt(
        HarnessKind.DEEPSEEK,
        task_instruction="Fix clamp.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=profile.network_policy,
    )
    plan = DeepSeekHarnessAdapter(observed_config_digest=profile.config_digest or "").prepare(
        profile, prompt, workspace=tmp_path, context=None, task_id="micro-python-clamp"
    )

    assert plan.argv == ("dsh", "--profile", "headless", prompt.text)
    assert "jsonl" not in " ".join(plan.argv).lower()
    assert profile.trace_coverage is TraceCoverage.FINAL_OUTPUT_ONLY
    assert profile.session_extraction is DeepSeekSessionExtraction.DEFERRED_NOT_VERIFIED


@pytest.mark.asyncio
async def test_claude_trace_is_safe_ordered_and_private_reasoning_free(tmp_path: Path) -> None:
    result = await MultiHarnessRunner(
        artifact_root=tmp_path / "artifacts", runtime_root=tmp_path / "runtime"
    ).run(
        TASKS["python"],
        fake_profile(HarnessKind.CLAUDE_CODE),
        adapter=ClaudeCodeAdapter(),
        backend=FakeMultiHarnessBackend(),
        run_id="claude-safe-trace",
    )

    types = result.evidence.trace_event_types
    assert types == (
        TraceEventType.THREAD_STARTED,
        TraceEventType.REASONING_PRESENT,
        TraceEventType.FILE_CHANGE,
        TraceEventType.AGENT_MESSAGE,
        TraceEventType.TURN_COMPLETED,
    )
    assert PRIVATE_CLAUDE_REASONING_SENTINEL not in artifact_text(result.artifact_directory)
    assert result.evidence.observed_model == "fake-observed-claude-model"


def test_claude_retry_and_unknown_events_remain_observable() -> None:
    from harnesslab.multi_harness.models import HarnessProcessCapture
    from harnesslab.multi_harness.trace import collect_claude_stream

    lines = (
        '{"type":"system","subtype":"init","tools":["Read","Edit","Write","Bash"],'
        '"mcp_servers":[],"plugins":[]}',
        '{"type":"system","subtype":"api_retry","attempt":2,"max_retries":10,'
        '"retry_delay_ms":750.5,"error_status":529,"error":"overloaded",'
        '"uuid":"retry-uuid","session_id":"safe-session-id"}',
        '{"type":"future_event","subtype":"new"}',
        '{"type":"result","subtype":"success","is_error":false,"result":"done"}',
    )
    collection = collect_claude_stream(HarnessProcessCapture(lines, "", 0, 1))

    assert collection.retry_count == 1
    retry = collection.sanitized_events[1]
    assert retry.model_dump(exclude_none=True) == {
        "ordinal": 2,
        "event_type": "system.api_retry",
        "item_id": "retry-uuid",
        "thread_id": "safe-session-id",
        "file_changes": (),
        "reasoning_present": False,
        "error_code": "overloaded",
        "attempt": 2,
        "max_retries": 10,
        "retry_delay_ms": 750.5,
        "error_status": 529,
    }
    normalized_retry = collection.trace.events[1]
    assert normalized_retry.attempt == 2
    assert normalized_retry.max_retries == 10
    assert normalized_retry.retry_delay_ms == 750.5
    assert normalized_retry.error_status == 529
    assert normalized_retry.error_code == "overloaded"
    assert tuple(event.type for event in collection.trace.events) == (
        TraceEventType.THREAD_STARTED,
        TraceEventType.API_RETRY,
        TraceEventType.UNKNOWN,
        TraceEventType.TURN_COMPLETED,
    )


def test_claude_unexpected_init_tool_is_profile_violation() -> None:
    from harnesslab.multi_harness.models import HarnessProcessCapture
    from harnesslab.multi_harness.trace import collect_claude_stream

    lines = (
        '{"type":"system","subtype":"init","tools":["Read","Edit","Write","Bash",'
        '"WebSearch"],"mcp_servers":[],"plugins":[]}',
        '{"type":"result","subtype":"success","is_error":false,"result":"done"}',
    )
    collection = collect_claude_stream(HarnessProcessCapture(lines, "", 0, 1))
    assert collection.failure_category is HarnessFailureCategory.PROFILE_VIOLATION


@pytest.mark.parametrize(
    ("error_type", "expected"),
    (
        ("authentication_error", HarnessFailureCategory.AUTHENTICATION),
        ("configuration_error", HarnessFailureCategory.CONFIGURATION),
        ("timeout_error", HarnessFailureCategory.TIMEOUT),
        ("cancelled", HarnessFailureCategory.CANCELLED),
        ("overloaded_error", HarnessFailureCategory.MODEL_TURN_FAILED),
    ),
)
def test_claude_structured_failure_taxonomy_does_not_guess_from_text(
    error_type: str, expected: HarnessFailureCategory
) -> None:
    from harnesslab.multi_harness.models import HarnessProcessCapture
    from harnesslab.multi_harness.trace import collect_claude_stream

    lines = (
        '{"type":"system","subtype":"init","tools":["Read","Edit","Write","Bash"],'
        '"mcp_servers":[],"plugins":[]}',
        '{"type":"error","message":"authentication timeout words are not classified",'
        f'"error":{{"type":"{error_type}"}}}}',
    )
    collection = collect_claude_stream(HarnessProcessCapture(lines, "", 0, 1))
    assert collection.failure_category is expected


def test_deepseek_config_drift_fails_preflight() -> None:
    profile = fake_profile(HarnessKind.DEEPSEEK)
    with pytest.raises(HarnessAdapterError, match="config digest drifted"):
        DeepSeekHarnessAdapter(observed_config_digest="sha256:" + "9" * 64).preflight(profile)


def test_phase_f_profiles_and_prompt_hashes_are_deterministic() -> None:
    profile = fake_profile(HarnessKind.CLAUDE_CODE)
    assert profile.fingerprint == fake_profile(HarnessKind.CLAUDE_CODE).fingerprint
    prompt = render_harness_prompt(
        HarnessKind.CLAUDE_CODE,
        task_instruction="Fix clamp.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=profile.network_policy,
    )
    assert prompt.template_version == CLAUDE_PROMPT_VERSION
    assert (
        prompt.prompt_hash
        == render_harness_prompt(
            HarnessKind.CLAUDE_CODE,
            task_instruction="Fix clamp.",
            task_digest="sha256:" + "1" * 64,
            workspace_input_digest="sha256:" + "2" * 64,
            context_digest=None,
            network_policy=profile.network_policy,
        ).prompt_hash
    )
    payload = profile.model_dump(mode="json")
    payload["cli_version"] = "2.1.240"
    with pytest.raises(ValidationError, match=r"2\.1\.241"):
        type(profile).model_validate(payload)


def test_phase_f_outer_docker_argv_is_hardened_and_secret_free(tmp_path: Path) -> None:
    profile = fake_profile(HarnessKind.DEEPSEEK)
    prompt = render_harness_prompt(
        HarnessKind.DEEPSEEK,
        task_instruction="Fix clamp.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=profile.network_policy,
    )
    plan = DeepSeekHarnessAdapter(observed_config_digest=profile.config_digest or "").prepare(
        profile, prompt, workspace=tmp_path, context=None, task_id="micro-python-clamp"
    )
    secret = "phase-f-fake-secret-not-for-argv"
    argv = DockerMultiHarnessBackend(
        explicitly_enabled=True, credentials={"DEEPSEEK_API_KEY": secret}
    ).create_argv(plan, "phase-f-test")

    assert argv[argv.index("--network") + 1] == "none"
    assert "--read-only" in argv
    assert "ALL" in argv
    assert "no-new-privileges=true" in argv
    assert "10001:10001" in argv
    assert "docker.sock" not in " ".join(argv)
    assert secret not in argv


@pytest.mark.asyncio
async def test_deepseek_final_output_redacts_exact_backend_secret(tmp_path: Path) -> None:
    secret = "deepseek-private-fixture-value"
    result = await MultiHarnessRunner(
        artifact_root=tmp_path / "artifacts", runtime_root=tmp_path / "runtime"
    ).run(
        TASKS["python"],
        fake_profile(HarnessKind.DEEPSEEK),
        adapter=DeepSeekHarnessAdapter(observed_config_digest="sha256:" + "6" * 64),
        backend=FakeMultiHarnessBackend(secret_values=(secret,)),
        run_id="deepseek-redaction",
    )
    assert secret not in artifact_text(result.artifact_directory)
    assert result.evidence.trace_coverage is TraceCoverage.FINAL_OUTPUT_ONLY
    assert result.evidence.trace_event_types == (TraceEventType.AGENT_MESSAGE,)


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", list(HarnessKind), ids=("claude", "deepseek"))
async def test_phase_f_runtime_doctors_verify_pins_flags_and_toolchains(
    harness: HarnessKind,
) -> None:
    result = await MultiHarnessRuntime(harness).doctor()
    package_versions = {
        HarnessKind.CLAUDE_CODE: f"{CLAUDE_CLI_VERSION} (Claude Code)",
        HarnessKind.DEEPSEEK: DEEPSEEK_CLI_VERSION,
    }
    assert result.version == package_versions[harness]
    assert result.required_flags == (
        CLAUDE_REQUIRED_HELP if harness is HarnessKind.CLAUDE_CODE else DEEPSEEK_REQUIRED_HELP
    )
    assert result.tool_versions["python"].startswith("3.12.")
    assert result.tool_versions["java"].startswith("21.")
    assert result.tool_versions["javac"].startswith("21.")
    assert result.tool_versions["node"].startswith("24.")
    requirements = tuple(
        tool for path in TASKS.values() for tool in TaskPackage.load(path).definition.expected_tools
    )
    from harnesslab.harness_lane.toolchains import unsatisfied_tools

    assert not unsatisfied_tools(requirements, result.tool_versions)
    if harness is HarnessKind.DEEPSEEK:
        assert result.config_digest is not None
        assert result.default_config_digest is not None
