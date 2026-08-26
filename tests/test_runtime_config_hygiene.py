from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from harnesslab.contracts.common import NetworkPolicy, Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.egress import EGRESS_PROXY_IMAGE
from harnesslab.harness_lane.adapter import CodexExecutionPlan, CodexHarnessAdapter
from harnesslab.harness_lane.docker_backend import DockerCodexBackend
from harnesslab.harness_lane.models import (
    CodexHarnessProfile,
    CodexProcessCapture,
    HarnessLaneOutcome,
)
from harnesslab.harness_lane.profile import (
    CODEX_IMAGE,
    configured_gpt56_relay_codex_profile,
)
from harnesslab.harness_lane.prompt import render_codex_harness_prompt
from harnesslab.harness_lane.runner import CodexHarnessRunner
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
from harnesslab.sandbox.models import ImageIdentity

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "tasks" / "micro-python-clamp" / "1.0.0"
BASE_URL_REFERENCE = "HARNESSLAB_GPT56_RELAY_BASE_URL"
API_KEY_REFERENCE = "HARNESSLAB_GPT56_RELAY_API_KEY"
RUNTIME_URL = "https://r6-runtime-sentinel.example.test/private"
FAKE_KEY = "r6-fake-api-key-sentinel"
SAFE_ROUTE_IDENTITY = "gpt56-relay|responses|env:HARNESSLAB_GPT56_RELAY_BASE_URL/responses"


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


def _codex_plan(tmp_path: Path) -> CodexExecutionPlan:
    prompt = render_codex_harness_prompt(
        task_instruction="Fix the visible task.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=NetworkPolicy.DENY,
    )
    return CodexHarnessAdapter().prepare(
        _codex_profile(), prompt, workspace=tmp_path, context=None, task_id="task"
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
    assert "--ignore-user-config" in plan.argv
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
    assert RUNTIME_URL not in script.read_text(encoding="utf-8")


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
