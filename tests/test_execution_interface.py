from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, TypedDict
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from harnesslab.cli import app
from harnesslab.comparability.manifest import load_manifest_facts
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane, Protocol
from harnesslab.contracts.model import ModelProfile
from harnesslab.experiment.evidence import validate_manifest_against_slot
from harnesslab.experiment.execution import (
    CodexHarnessBinding,
    DirectModelBinding,
    ExecutionContractError,
    ExecutionDispatcher,
    ExecutionRequest,
    MultiHarnessBinding,
    execution_capabilities,
    resolved_comparison_profile_identity,
)
from harnesslab.experiment.outcomes import StatisticalOutcome, normalize_lane_evidence
from harnesslab.experiment.plan import build_experiment_plan
from harnesslab.harness_lane.fake import FakeCodexBackend, FakeCodexScenario
from harnesslab.harness_lane.profile import canonical_codex_profile
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.model_lane.fake import FakeDirectProvider
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.multi_harness.fake import FakeHarnessScenario, FakeMultiHarnessBackend
from harnesslab.multi_harness.models import HarnessKind
from harnesslab.multi_harness.runner import MultiHarnessRunner
from harnesslab.sandbox.models import ImageIdentity
from tests.phase_g_helpers import ROOT, basic_spec, cell
from tests.test_experiment_e2e import PATCH
from tests.test_multi_harness import adapter_for, fake_profile


class RunnerRoots(TypedDict):
    artifact_root: Path
    runtime_root: Path


KINDS = ("direct-model", "codex", "claude-code", "deepseek-harness")


def binding_for(kind: str, tmp_path: Path) -> Any:
    roots: RunnerRoots = {
        "artifact_root": tmp_path / "artifacts",
        "runtime_root": tmp_path / "runtime",
    }
    if kind == "direct-model":
        return DirectModelBinding(
            DirectModelRunner(**roots, allow_custom_endpoint=True),
            ModelProfile(
                requested_model="fake-model",
                provider="fake",
                base_url="https://fake.invalid",
                route="/responses",
                protocol=Protocol.RESPONSES,
            ),
            FakeDirectProvider(PATCH),
        )
    if kind == "codex":
        return CodexHarnessBinding(
            CodexHarnessRunner(**roots),
            canonical_codex_profile(
                ImageIdentity(reference="fake-codex:interface", image_id="sha256:" + "7" * 64)
            ),
            FakeCodexBackend(),
        )
    harness = HarnessKind(kind)
    return MultiHarnessBinding(
        MultiHarnessRunner(**roots),
        fake_profile(harness),
        adapter_for(harness),
        FakeMultiHarnessBackend(),
    )


def request_for(binding: Any) -> ExecutionRequest:
    profile = binding.profile
    direct = isinstance(binding, DirectModelBinding)
    codex = isinstance(binding, CodexHarnessBinding)
    spec_cell = cell(
        "subject",
        EvaluationLane.MODEL if direct else EvaluationLane.HARNESS,
        requested_model=profile.requested_model,
        provider_route=profile.provider_route_identity if direct else profile.provider_route,
        harness="direct-model" if direct else "codex" if codex else profile.harness.value,
        harness_version="evidence-schema-1"
        if direct
        else (profile.codex_cli_version if codex else profile.cli_version),
        reasoning_effort=profile.reasoning.effort
        if direct
        else (profile.reasoning_effort if codex else None),
        profile_identity=resolved_comparison_profile_identity(profile),
        harness_config_identity=canonical_digest(profile.model_dump(mode="json")),
    )
    spec = basic_spec(repeat_count=1).model_copy(
        update={"cells": (spec_cell,), "paired_comparisons": ()}
    )
    slot = build_experiment_plan(spec, ROOT).run_slots[0]
    return ExecutionRequest(execution_id="interface-attempt-a1", slot=slot)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("required", ["streaming", "active_cancellation", "session_resume"])
async def test_unsupported_requirement_never_enters_runner(
    kind: str, required: str, tmp_path: Path
) -> None:
    binding = binding_for(kind, tmp_path)
    binding.runner.run = AsyncMock()
    request = request_for(binding).model_copy(update={"required_capabilities": (required,)})
    with pytest.raises(ExecutionContractError, match=required):
        await ExecutionDispatcher(ROOT, {"subject": binding}).execute(request)
    binding.runner.run.assert_not_called()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "field",
    [
        "requested_model",
        "profile_identity",
        "harness_config_identity",
        "provider_route",
        "reasoning_effort",
    ],
)
async def test_changed_config_is_rejected_before_subject_call(
    kind: str, field: str, tmp_path: Path
) -> None:
    binding = binding_for(kind, tmp_path)
    request = request_for(binding)
    binding.runner.run = AsyncMock()
    changed = "sha256:" + "a" * 64 if field.endswith("identity") else "changed-private-value"
    request = request.model_copy(update={"slot": request.slot.model_copy(update={field: changed})})
    with pytest.raises(ExecutionContractError, match=field) as failure:
        await ExecutionDispatcher(ROOT, {"subject": binding}).execute(request)
    assert changed not in str(failure.value)
    binding.runner.run.assert_not_called()


@pytest.mark.parametrize(
    "field",
    [
        "task_digest",
        "workspace_input_digest",
        "context_identity",
        "verifier_identity",
        "budget_identity",
    ],
)
async def test_changed_task_contract_is_rejected_before_runner(field: str, tmp_path: Path) -> None:
    binding = binding_for("codex", tmp_path)
    request = request_for(binding)
    binding.runner.run = AsyncMock()
    task = request.slot.task.model_copy(update={field: "sha256:" + "a" * 64})
    request = request.model_copy(update={"slot": request.slot.model_copy(update={"task": task})})
    with pytest.raises(ExecutionContractError, match="task, verifier or task budget"):
        await ExecutionDispatcher(ROOT, {"subject": binding}).execute(request)
    binding.runner.run.assert_not_called()


@pytest.mark.parametrize(
    "path", ["/tmp/task", "../tasks/a", "tasks/../../private", "C:/tasks/a", r"tasks\a"]
)
def test_request_rejects_host_paths_and_process_controls(path: str, tmp_path: Path) -> None:
    data = request_for(binding_for("codex", tmp_path)).model_dump(mode="json")
    data["slot"]["task"]["package_path"] = path
    with pytest.raises(ValidationError):
        ExecutionRequest.model_validate(data)


def test_extra_process_controls_cannot_enter_request(tmp_path: Path) -> None:
    data = request_for(binding_for("codex", tmp_path)).model_dump(mode="json")
    for key in ["argv", "environment", "workspace", "shell"]:
        with pytest.raises(ValidationError):
            ExecutionRequest.model_validate({**data, key: "not-accepted"})


async def test_symlink_escape_never_reaches_runner(tmp_path: Path) -> None:
    binding = binding_for("codex", tmp_path)
    request = request_for(binding)
    root = tmp_path / "repository"
    (root / "tasks").mkdir(parents=True)
    (root / request.slot.task.package_path.split("/")[0] / "micro-python-clamp").symlink_to(
        ROOT / "tasks/micro-python-clamp", target_is_directory=True
    )
    binding.runner.run = AsyncMock()
    with pytest.raises(ValueError, match="escapes"):
        await ExecutionDispatcher(root, {"subject": binding}).execute(request)
    binding.runner.run.assert_not_called()


@pytest.mark.parametrize("kind", KINDS)
async def test_keyless_dispatch_preserves_real_hidden_verifier_and_manifest(
    kind: str, tmp_path: Path
) -> None:
    binding = binding_for(kind, tmp_path)
    request = request_for(binding)
    result = await ExecutionDispatcher(ROOT, {"subject": binding}).execute(request)
    assert result.evidence.run_id == request.execution_id
    assert result.evidence.verifier_passed is True
    assert normalize_lane_evidence(result.evidence) is StatisticalOutcome.CAPABILITY_PASS
    manifest = result.artifact_directory / "manifest.json"
    raw = json.loads(manifest.read_text())
    validate_manifest_against_slot(raw, load_manifest_facts(manifest), request.slot)
    assert result.evidence.verifier_sandbox_manifest is not None
    assert (
        result.evidence.verifier_sandbox_manifest.workspace_input_digest
        == result.evidence.workspace_output_digest
    )


@pytest.mark.parametrize("kind", ["codex", "claude-code", "deepseek-harness"])
async def test_self_report_is_still_rejected_by_hidden_verifier(kind: str, tmp_path: Path) -> None:
    binding = binding_for(kind, tmp_path)
    backend = (
        FakeCodexBackend(FakeCodexScenario.SELF_REPORTED_SUCCESS_WRONG_WORKSPACE)
        if kind == "codex"
        else FakeMultiHarnessBackend(FakeHarnessScenario.SELF_REPORTED_SUCCESS_WRONG_WORKSPACE)
    )
    binding = replace(binding, backend=backend)
    result = await ExecutionDispatcher(ROOT, {"subject": binding}).execute(request_for(binding))
    assert result.evidence.verifier_passed is False
    assert normalize_lane_evidence(result.evidence) is StatisticalOutcome.CAPABILITY_FAIL


@pytest.mark.parametrize("kind", ["codex", "claude-code", "deepseek-harness"])
@pytest.mark.parametrize("scenario", ["timeout", "process_error"])
async def test_transport_failures_remain_failures_without_verifier_pass(
    kind: str, scenario: str, tmp_path: Path
) -> None:
    binding = binding_for(kind, tmp_path)
    backend = (
        FakeCodexBackend(FakeCodexScenario(scenario))
        if kind == "codex"
        else FakeMultiHarnessBackend(FakeHarnessScenario(scenario))
    )
    binding = replace(binding, backend=backend)
    result = await ExecutionDispatcher(ROOT, {"subject": binding}).execute(request_for(binding))
    assert result.evidence.verifier_passed is None
    assert normalize_lane_evidence(result.evidence) is StatisticalOutcome.INFRA_FAILURE


def test_capability_cli_is_keyless_and_does_not_claim_runtime_readiness() -> None:
    result = CliRunner().invoke(app, ["experiment", "execution-capabilities"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["execution_authorized"] is False
    assert data["runtime_health"] == "NOT_VERIFIED"
    assert set(data["bindings"]) == set(KINDS)
    assert execution_capabilities()["direct-model"].transport == "PROVIDER"
    assert execution_capabilities()["deepseek-harness"].trace == "FINAL_ONLY"


@pytest.mark.parametrize("kind", KINDS)
async def test_lazy_production_bindings_use_same_contract_with_keyless_transports(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # These are the existing production factories; only the subject communication
    # backend is replaced. Workspace materialization and Docker verifier stay real.
    import harnesslab.release.matrix as matrix
    from harnesslab.egress import EGRESS_PROXY_IMAGE

    original = binding_for(kind, tmp_path)
    roots: RunnerRoots = {
        "artifact_root": tmp_path / "production-artifacts",
        "runtime_root": tmp_path / "production-runtime",
    }
    binding: (
        matrix._DirectProductionBinding
        | matrix._CodexProductionBinding
        | matrix._MultiProductionBinding
    )
    if kind == "direct-model":
        binding = matrix._DirectProductionBinding(
            profile=original.profile, provider=original.provider, environment={}, **roots
        )
    else:
        kwargs: dict[str, Any] = {
            "profile": original.profile,
            "provider_url": "https://fake.invalid",
            "proxy_image": ImageIdentity(
                reference=EGRESS_PROXY_IMAGE, image_id="sha256:" + "8" * 64
            ),
            "credentials": {},
            **roots,
        }
        if kind == "codex":
            monkeypatch.setattr(matrix, "DockerCodexBackend", lambda **_: original.backend)
            binding = matrix._CodexProductionBinding(**kwargs)
        else:
            monkeypatch.setattr(matrix, "DockerMultiHarnessBackend", lambda **_: original.backend)
            binding = matrix._MultiProductionBinding(adapter=original.adapter, **kwargs)
    request = request_for(original)
    dispatcher = ExecutionDispatcher(ROOT, {"subject": binding})
    assert dispatcher.capabilities("subject") == execution_capabilities()[kind]
    rejected = request.model_copy(
        update={"slot": request.slot.model_copy(update={"requested_model": "changed-model"})}
    )
    with pytest.raises(ExecutionContractError, match="requested_model"):
        await dispatcher.execute(rejected)
    assert not (original.provider.requests if kind == "direct-model" else original.backend.plans)
    result = await dispatcher.execute(request)
    assert result.evidence.verifier_passed is True
    manifest = result.artifact_directory / "manifest.json"
    validate_manifest_against_slot(
        json.loads(manifest.read_text()), load_manifest_facts(manifest), request.slot
    )


@pytest.mark.parametrize("kind", ["codex", "claude-code", "deepseek-harness"])
async def test_missing_trace_cannot_become_a_verified_pass(kind: str, tmp_path: Path) -> None:
    from harnesslab.harness_lane.models import CodexProcessCapture
    from harnesslab.multi_harness.models import HarnessProcessCapture

    binding = binding_for(kind, tmp_path)
    binding.backend.run = AsyncMock(
        return_value=(
            CodexProcessCapture((), 0, 1)
            if kind == "codex"
            else HarnessProcessCapture((), "", 0, 1)
        )
    )
    result = await ExecutionDispatcher(ROOT, {"subject": binding}).execute(request_for(binding))
    assert result.evidence.verifier_passed is None
    assert normalize_lane_evidence(result.evidence) is StatisticalOutcome.INFRA_FAILURE


async def test_legacy_bindings_keep_unknown_capabilities_and_no_implicit_retry(
    tmp_path: Path,
) -> None:
    binding = binding_for("codex", tmp_path)
    request = request_for(binding)

    class Legacy:
        run = AsyncMock(side_effect=RuntimeError("controlled error"))

    legacy = Legacy()
    dispatcher = ExecutionDispatcher(ROOT, {"subject": legacy})
    assert dispatcher.capabilities("subject").transport == "LEGACY"
    assert dispatcher.capabilities("subject").trace == "UNKNOWN"
    with pytest.raises(RuntimeError, match="controlled error"):
        await dispatcher.execute(request)
    assert legacy.run.await_count == 1


async def test_direct_cli_fixture_reaches_verifier_through_unified_dispatch(tmp_path: Path) -> None:
    from harnesslab.experiment.cli import FAKE_PATCH

    binding = binding_for("direct-model", tmp_path)
    binding = replace(binding, provider=FakeDirectProvider(FAKE_PATCH))
    result = await ExecutionDispatcher(ROOT, {"subject": binding}).execute(request_for(binding))
    assert result.evidence.verifier_passed is True


@pytest.mark.parametrize("drift", [False, True])
async def test_direct_effective_profile_is_checked_even_with_plan_identity_overrides(
    drift: bool, tmp_path: Path
) -> None:
    binding = binding_for("direct-model", tmp_path)
    request = request_for(binding)
    frozen_digest = canonical_digest(binding.profile.model_dump(mode="json"))
    request = request.model_copy(
        update={
            "slot": request.slot.model_copy(
                update={"effective_runtime_profile_identity": frozen_digest}
            )
        }
    )
    binding.runner.plan_profile_identity = request.slot.profile_identity
    binding.runner.plan_harness_config_identity = request.slot.harness_config_identity
    if drift:
        binding = replace(
            binding,
            profile=binding.profile.model_copy(
                update={"request_timeout_seconds": binding.profile.request_timeout_seconds + 1}
            ),
        )
    binding.runner.run = AsyncMock(return_value="opaque-result-fixture")
    dispatcher = ExecutionDispatcher(ROOT, {"subject": binding})
    if drift:
        with pytest.raises(ExecutionContractError, match="effective_runtime_profile_identity"):
            await dispatcher.execute(request)
        binding.runner.run.assert_not_called()
    else:
        result: object = await dispatcher.execute(request)
        assert result == "opaque-result-fixture"
        binding.runner.run.assert_awaited_once()
