from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from harnesslab.contracts.common import NetworkPolicy
from harnesslab.harness_lane.adapter import HarnessAdapterError
from harnesslab.harness_lane.fake import FakeCodexBackend, FakeCodexScenario
from harnesslab.harness_lane.prompt import render_codex_harness_prompt
from harnesslab.harness_lane.transport import (
    CodexCLITransport,
    MultiHarnessCLITransport,
    SubjectObservation,
    SubjectRequest,
    SubjectWorkspace,
)
from harnesslab.multi_harness.diagnostics import safe_process_diagnostics
from harnesslab.multi_harness.fake import FakeHarnessScenario, FakeMultiHarnessBackend
from harnesslab.multi_harness.prompt import render_harness_prompt
from tests.phase_g_helpers import ROOT
from tests.test_execution_interface import binding_for

KINDS = ["codex", "claude-code", "deepseek-harness"]


def setup(
    kind: str, tmp_path: Path, scenario: str = "solve"
) -> tuple[Any, SubjectRequest[Any, Any], SubjectWorkspace, Any, Any, Any]:
    binding = binding_for(kind, tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    context = SubjectWorkspace("transport-a1", workspace, None)
    args: dict[str, Any] = dict(
        task_instruction="Implement clamp.",
        task_digest="sha256:" + "a" * 64,
        workspace_input_digest="sha256:" + "b" * 64,
        context_digest=None,
        network_policy=NetworkPolicy.DENY,
    )
    backend: Any
    prompt: Any
    transport: Any
    if kind == "codex":
        backend = FakeCodexBackend(FakeCodexScenario(scenario))
        adapter = binding.runner.adapter
        prompt = render_codex_harness_prompt(**args)
        transport = CodexCLITransport(adapter, backend)
    else:
        backend = FakeMultiHarnessBackend(FakeHarnessScenario(scenario))
        adapter = binding.adapter
        prompt = render_harness_prompt(binding.profile.harness, **args)
        transport = MultiHarnessCLITransport(adapter, backend)
    request = SubjectRequest(
        "transport-a1", "micro-python-clamp", binding.profile, prompt, "transport-a1"
    )
    return binding, request, context, adapter, backend, transport


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "scenario", ["solve", "timeout", "process_error", "self_reported_success_wrong_workspace"]
)
async def test_cli_observation_preserves_legacy_collection_and_process_metadata(
    kind: str, scenario: str, tmp_path: Path
) -> None:
    _, request, workspace, adapter, backend, transport = setup(kind, tmp_path, scenario)
    plan = adapter.prepare(
        request.profile,
        request.prompt,
        workspace=workspace.workspace,
        context=workspace.context,
        task_id=request.task_id,
    )
    capture = await backend.run(plan)
    legacy = adapter.collect(capture, secret_values=backend.artifact_secret_values)
    observation = await transport.execute(request, workspace)
    assert observation.collection == legacy
    assert observation.execution_id == request.execution_id
    assert observation.exit_code == capture.exit_code
    assert observation.duration_ms == capture.duration_ms
    assert observation.timed_out == capture.timed_out
    assert observation.cancelled == capture.cancelled
    assert not hasattr(observation, "stdout_lines") and not hasattr(observation, "stderr_text")
    assert not hasattr(request, "argv") and not hasattr(request, "workspace")
    if kind != "codex":
        assert observation.diagnostics == safe_process_diagnostics(capture, secret_values=())


@pytest.mark.parametrize("kind", KINDS)
async def test_wrong_workspace_handle_never_enters_backend(kind: str, tmp_path: Path) -> None:
    _, request, workspace, _, backend, transport = setup(kind, tmp_path)
    with pytest.raises(HarnessAdapterError, match="workspace reference"):
        await transport.execute(request, replace(workspace, reference="another-attempt"))
    assert backend.plans == []


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("solve", [True, False])
async def test_runner_accepts_semantic_only_transport_and_keeps_verifier_authority(
    kind: str, solve: bool, tmp_path: Path
) -> None:
    binding, request, workspace, adapter, _, transport = setup(kind, tmp_path)
    template = await transport.execute(request, workspace)
    adapter.prepare = AsyncMock(side_effect=AssertionError("runner cannot prepare CLI plans"))
    calls = []

    class SemanticOnlyTransport:
        artifact_secret_values = ()

        async def execute(
            self, request: SubjectRequest[Any, Any], workspace: SubjectWorkspace
        ) -> SubjectObservation[Any]:
            calls.append(request)
            assert workspace.reference == request.workspace_reference
            if solve:
                (workspace.workspace / "calculator.py").write_text(
                    "def clamp(value, lower, upper):\n    return max(lower, min(value, upper))\n"
                )
            return replace(template, execution_id=request.execution_id)

    result = await binding.runner.run(
        ROOT / "tasks/micro-python-clamp/1.0.0",
        binding.profile,
        transport=SemanticOnlyTransport(),
        run_id="semantic-a1",
    )
    assert result.evidence.verifier_passed is solve
    assert len(calls) == 1
    assert result.evidence.run_id == "semantic-a1"
    adapter.prepare.assert_not_called()


@pytest.mark.parametrize("kind", KINDS)
async def test_other_attempt_observation_is_rejected_before_verification(
    kind: str, tmp_path: Path
) -> None:
    binding, request, workspace, _, _, transport = setup(kind, tmp_path)
    template = await transport.execute(request, workspace)
    binding.runner.sandbox.run_hidden_verifier_workspace = AsyncMock()

    class WrongAttemptTransport:
        artifact_secret_values = ()

        async def execute(
            self, request: SubjectRequest[Any, Any], workspace: SubjectWorkspace
        ) -> SubjectObservation[Any]:
            return replace(template, execution_id="wrong-a1")

    with pytest.raises(RuntimeError, match="another execution"):
        await binding.runner.run(
            ROOT / "tasks/micro-python-clamp/1.0.0",
            binding.profile,
            transport=WrongAttemptTransport(),
            run_id="correct-a1",
        )
    binding.runner.sandbox.run_hidden_verifier_workspace.assert_not_called()


async def test_failed_observation_cannot_claim_successful_communication(tmp_path: Path) -> None:
    _, request, workspace, _, _, transport = setup("codex", tmp_path, "timeout")
    observation = await transport.execute(request, workspace)
    with pytest.raises(HarnessAdapterError, match="completion disagrees"):
        replace(observation, completion="RETURNED")


async def test_simultaneous_timeout_and_cancellation_preserve_both_observed_flags(
    tmp_path: Path,
) -> None:
    _, request, workspace, adapter, backend, transport = setup("codex", tmp_path, "timeout")
    plan = adapter.prepare(
        request.profile,
        request.prompt,
        workspace=workspace.workspace,
        context=None,
        task_id=request.task_id,
    )
    original = await backend.run(plan)
    backend.run = AsyncMock(return_value=replace(original, cancelled=True))
    observation = await transport.execute(request, workspace)
    assert observation.cancelled is True and observation.timed_out is True
