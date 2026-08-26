from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from harnesslab.cli import app
from harnesslab.egress import (
    EGRESS_PROXY_BASE,
    EGRESS_PROXY_IMAGE,
    EGRESS_PROXY_SOURCE_DIGEST,
    INTERNAL_NETWORK_GATEWAY_MODE_OPTION,
    EgressNetworkIsolationUnavailable,
    EgressPolicy,
    EgressProxyRuntime,
    EgressSecurityError,
    ProviderScopedDockerBoundary,
    preflight_egress_network_isolation,
)
from harnesslab.harness_lane.adapter import HarnessAdapterError
from harnesslab.harness_lane.docker_backend import (
    CodexBackendExecutionError,
    DockerCodexBackend,
)
from harnesslab.harness_lane.models import (
    CodexBackendFailureEvidence,
    CodexBackendFailurePhase,
    CodexProcessCapture,
    ObservedModelStatus,
)
from harnesslab.harness_lane.profile import CODEX_IMAGE, canonical_codex_profile
from harnesslab.model_lane.models import DirectModelOutcome
from harnesslab.multi_harness.docker_backend import DockerMultiHarnessBackend
from harnesslab.multi_harness.models import HarnessProcessCapture, TraceCoverage
from harnesslab.multi_harness.profile import (
    CLAUDE_IMAGE,
    DEEPSEEK_IMAGE,
    canonical_deepseek_profile,
    configured_deepseek_v4flash_profile,
    configured_qwen_opencode_go_claude_profile,
)
from harnesslab.multi_harness.runtime import _validate_deepseek_effective_config
from harnesslab.multi_harness.trace import collect_deepseek_final
from harnesslab.release.smoke import (
    EXPECTED_ADAPTERS,
    EXPECTED_CALL_IDS,
    EXPECTED_RUNNERS,
    REQUIRED_CONFIGURATION_REFERENCES,
    ProductionSmokeInvoker,
    ResolvedSmokeBinding,
    RuntimeIdentities,
    SmokeCallFailure,
    SmokeCallResult,
    SmokeControlPlane,
    SmokeControlPlaneError,
    SmokeExecutionStatus,
    SmokeFailureCategory,
    _validate_harness_observed_model,
    execute_real_smoke,
)
from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.preflight import _docker_runtime_preflight

ROOT = Path(__file__).resolve().parents[1]
RUNNER = CliRunner()
SAFE_ENVIRONMENT = {
    "HARNESSLAB_GPT56_RELAY_BASE_URL": "https://relay.example.test/v1",
    "HARNESSLAB_GPT56_RELAY_API_KEY": "fake-relay-key",
    "HARNESSLAB_OPENCODE_GO_API_KEY": "fake-opencode-go-key",
    "DEEPSEEK_API_KEY": "fake-deepseek-key",
}


def _image(reference: str, marker: str) -> ImageIdentity:
    return ImageIdentity(reference=reference, image_id="sha256:" + marker * 64)


def _runtime() -> RuntimeIdentities:
    return RuntimeIdentities(
        codex_image=_image(CODEX_IMAGE, "1"),
        claude_image=_image(CLAUDE_IMAGE, "2"),
        deepseek_image=_image(DEEPSEEK_IMAGE, "3"),
        egress_proxy_image=_image(EGRESS_PROXY_IMAGE, "4"),
        deepseek_config_digest="sha256:" + "5" * 64,
    )


class RecordingInvoker:
    def __init__(self, failing_call_id: str | None = None) -> None:
        self.failing_call_id = failing_call_id
        self.calls: list[ResolvedSmokeBinding] = []

    async def invoke(self, binding: ResolvedSmokeBinding) -> SmokeCallResult:
        self.calls.append(binding)
        call_id = binding.frozen.call.call_id
        if call_id == self.failing_call_id:
            raise SmokeCallFailure(SmokeFailureCategory.ROUTE_MISMATCH, "fake failure")
        return SmokeCallResult(
            call_id=call_id,
            evidence_references=(f"fake://{call_id}",),
            evidence_digests=("sha256:" + "6" * 64,),
        )


def _mutated_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    shutil.copytree(ROOT / "release", root / "release")
    task = next(
        item
        for item in json.loads((ROOT / "release/core-corpus.json").read_text())["tasks"]
        if item["task_id"] == "core-python-deduplicate"
    )
    source = ROOT / task["package_path"]
    shutil.copytree(source, root / task["package_path"])
    return root


def test_smoke_production_control_plane_exact_eight_call_binding() -> None:
    control = SmokeControlPlane.load(ROOT)
    assert tuple(binding.call.call_id for binding in control.bindings) == EXPECTED_CALL_IDS
    assert tuple(binding.runner_identity for binding in control.bindings) == EXPECTED_RUNNERS
    assert tuple(binding.adapter_identity for binding in control.bindings) == EXPECTED_ADAPTERS
    assert control.smoke_plan.max_top_level_launch_count == 8
    assert control.smoke_plan.max_output_token_ceiling == 14_256
    assert control.smoke_plan.release_plan_digest == control.release_plan.digest


def test_post_r4_smoke_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-2.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "07e48c2b3eb330c3ff56a8473bb98025f86490b3"
    assert history["receipt_digest"] == (
        "sha256:e25ddea75fa5ca2ade3167bc063d9b771da1af5381f5a13403af118e136976d2"
    )
    assert history["attempted_top_level_launches"] == 4
    assert [call["outcome"] for call in history["calls"]] == [
        "verified_fail",
        "verified_pass",
        "verified_pass",
        "INFRASTRUCTURE",
    ]
    assert [call.get("verifier_score") for call in history["calls"][:3]] == [0.8, 1.0, 1.0]
    assert history["calls_5_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert "/home/dev/harnesslab-evidence" not in serialized
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r5_smoke_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-3.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "519ee8034af845f636aac8d836536dd4c4601bd0"
    assert history["receipt_digest"] == (
        "sha256:bb0f747005b90caa1983168f84d9dcc468be7e1ea7e575f488ce66e41e30faae"
    )
    assert history["attempted_top_level_launches"] == 1
    assert history["calls"][0]["outcome"] == "provider_error"
    assert history["calls"][0]["provider_failure"] == "timeout"
    assert history["calls"][0]["timeout_phase"] == "read"
    assert history["calls_2_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert history["raw_evidence_hygiene"] == "REJECTED_CONFIG_VALUE_DISCLOSURE"
    audits = history["prior_v2_raw_evidence_audit"]
    assert [item["base_url_present"] for item in audits] == ["YES", "YES", "YES"]
    assert [item["api_key_present"] for item in audits] == ["NO", "NO", "NO"]
    assert "/home/dev/harnesslab-evidence" not in serialized
    assert SAFE_ENVIRONMENT["HARNESSLAB_GPT56_RELAY_BASE_URL"] not in serialized
    assert all(value not in serialized for name, value in SAFE_ENVIRONMENT.items() if "KEY" in name)
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r6_smoke_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-4.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "06027d08735886a2add1c492081154a4374ea3e2"
    assert history["receipt_digest"] == (
        "sha256:c3eb90ce738805311f8ed35209c86b387749865739b797047f2b0ac5207b0856"
    )
    assert history["attempted_top_level_launches"] == 4
    assert [call["outcome"] for call in history["calls"]] == [
        "verified_fail",
        "verified_pass",
        "verified_pass",
        "harness_error",
    ]
    codex = history["calls"][3]
    assert codex["harness_failure"] == "timeout"
    assert codex["duration_ms"] == 90592
    assert codex["observed_model"] is None
    assert codex["verifier"] == "NOT_RUN"
    assert codex["safe_diagnostics"] == [
        "PROXY_CONNECT_DENIED_403",
        "WEBSOCKET_TO_HTTPS_FALLBACK",
    ]
    assert history["calls_5_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert history["runtime_value_hygiene"] == {
        "base_url_present": "NO",
        "api_key_present": "NO",
    }
    assert "GENERATED_PROFILE_SUPPRESSED_BY_IGNORE_USER_CONFIG" in serialized
    assert "/home/dev/harnesslab-evidence" not in serialized
    assert SAFE_ENVIRONMENT["HARNESSLAB_GPT56_RELAY_BASE_URL"] not in serialized
    assert all(value not in serialized for name, value in SAFE_ENVIRONMENT.items() if "KEY" in name)
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r7_smoke_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-5.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "029c0d84036dc697786fad02910c4212298ed28c"
    assert history["receipt_digest"] == (
        "sha256:9a8e4892d2fd070f004038068bc30aa2b327f366414455cf494be4a65fb6941a"
    )
    assert history["attempted_top_level_launches"] == 4
    assert [call["outcome"] for call in history["calls"]] == [
        "verified_fail",
        "subject_output_error",
        "verified_pass",
        "harness_error",
    ]
    assert history["calls"][0]["verifier_score"] == 0.8
    assert history["calls"][1]["stop_reason"] == "max_tokens"
    assert history["calls"][2]["verifier_score"] == 1.0
    codex = history["calls"][3]
    assert codex["harness_failure"] == "timeout"
    assert codex["duration_ms"] == 90563
    assert codex["trace_coverage"] == "FULL_STREAM"
    assert codex["trace_event_count"] == 15
    assert codex["verifier"] == "NOT_RUN"
    assert history["calls_5_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert history["safe_route_diagnostics"] == {
        "builtin_provider_proxy_403_present": "NO",
        "websocket_fallback_present": "NO",
    }
    assert history["safe_command_diagnostics"] == {
        "command_execution_attempts": 5,
        "command_execution_failures": 5,
        "root_cause": "CODEX_INNER_BWRAP_USER_NAMESPACE_DENIED",
    }
    assert history["runtime_value_hygiene"] == {
        "relay_base_url_present": "NO",
        "api_key_present": "NO",
    }
    assert "/home/dev/harnesslab-evidence" not in serialized
    assert all(value not in serialized for name, value in SAFE_ENVIRONMENT.items() if "KEY" in name)
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_smoke_dry_run_preflight_performs_zero_provider_invocations() -> None:
    control = SmokeControlPlane.load(ROOT)
    receipt = control.preflight()
    assert receipt.status is SmokeExecutionStatus.SUCCEEDED
    assert receipt.attempted_top_level_launches == 0
    assert receipt.results == ()
    cli = RUNNER.invoke(app, ["release", "smoke", "preflight", "--repository-root", str(ROOT)])
    assert cli.exit_code == 0
    assert "SMOKE_CALL_BINDINGS=8" in cli.stdout
    assert "REAL_EVALUATION_CALL_COUNT=0" in cli.stdout
    disabled = RUNNER.invoke(app, ["release", "smoke", "execute", "--repository-root", str(ROOT)])
    assert disabled.exit_code == 2
    assert "real smoke requires --allow-real-smoke" in disabled.stdout
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "--allow-real-smoke" not in workflow
    assert "release smoke execute" not in workflow


def test_v2_credential_preflight_prints_presence_only() -> None:
    environment = {name: f"secret-value-for-{name}" for name in REQUIRED_CONFIGURATION_REFERENCES}
    result = RUNNER.invoke(app, ["release", "smoke", "credential-preflight"], env=environment)
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        f"{name}=SET" for name in REQUIRED_CONFIGURATION_REFERENCES
    ]
    assert all(value not in result.stdout for value in environment.values())

    environment.pop("HARNESSLAB_OPENCODE_GO_API_KEY")
    missing = RUNNER.invoke(app, ["release", "smoke", "credential-preflight"], env=environment)
    assert missing.exit_code == 2
    assert "HARNESSLAB_OPENCODE_GO_API_KEY=MISSING" in missing.stdout


@pytest.mark.asyncio
async def test_smoke_same_path_fake_execution_consumes_exact_plan_without_network() -> None:
    control = SmokeControlPlane.load(ROOT)
    bindings = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())
    invoker = RecordingInvoker()
    receipt = await control.execute(bindings, invoker, allow_real_smoke=True)
    assert receipt.status is SmokeExecutionStatus.SUCCEEDED
    assert receipt.attempted_top_level_launches == 8
    assert len(receipt.results) == 8
    assert tuple(item.frozen.call.call_id for item in invoker.calls) == EXPECTED_CALL_IDS
    assert tuple(item.frozen.call.max_output_tokens for item in invoker.calls) == (
        2000,
        2000,
        2000,
        2000,
        2000,
        2000,
        2000,
        256,
    )
    assert sum(int(item.frozen.call.top_level_launches) for item in invoker.calls) == 8
    assert {ref for item in invoker.calls for ref in item.frozen.call.credential_references} == set(
        REQUIRED_CONFIGURATION_REFERENCES
    )


@pytest.mark.asyncio
async def test_smoke_direct_subject_output_error_is_capability_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = SmokeControlPlane.load(ROOT)
    binding = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())[1]
    artifact = tmp_path / "subject-output-artifact"
    artifact.mkdir()
    (artifact / "manifest.json").write_text("{}\n", encoding="utf-8")

    class SubjectOutputRunner:
        def __init__(self, **_: object) -> None:
            pass

        async def run(self, *_: object, **__: object) -> SimpleNamespace:
            return SimpleNamespace(
                artifact_directory=artifact,
                evidence=SimpleNamespace(
                    provider_failure=None,
                    outcome=DirectModelOutcome.SUBJECT_OUTPUT_ERROR,
                    observed_model="qwen3.8-max",
                ),
            )

    monkeypatch.setattr("harnesslab.release.smoke.DirectModelRunner", SubjectOutputRunner)
    invoker = ProductionSmokeInvoker(ROOT, SAFE_ENVIRONMENT, tmp_path / "smoke")
    result = await invoker.invoke(binding)

    assert result.call_id == EXPECTED_CALL_IDS[1]
    assert len(result.evidence_references) == 1
    assert len(result.evidence_digests) == 1


@pytest.mark.asyncio
async def test_production_smoke_persists_codex_precapture_infrastructure_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = SmokeControlPlane.load(ROOT)
    binding = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())[3]
    secret = SAFE_ENVIRONMENT["HARNESSLAB_GPT56_RELAY_API_KEY"]
    runtime_url = SAFE_ENVIRONMENT["HARNESSLAB_GPT56_RELAY_BASE_URL"]

    class PreCaptureFailureBackend:
        def __init__(self, *, credentials: dict[str, str], **_: object) -> None:
            self.credentials = credentials
            self.egress_attestation = None

        @property
        def artifact_secret_values(self) -> tuple[str, ...]:
            return tuple(self.credentials.values())

        async def run(self, _: object) -> CodexProcessCapture:
            stderr_digest = (
                "sha256:"
                + hashlib.sha256(f"Codex failed; credential={secret}".encode()).hexdigest()
            )
            raise CodexBackendExecutionError(
                CodexBackendFailureEvidence(
                    phase=CodexBackendFailurePhase.CONTAINER_START,
                    duration_ms=3,
                    stderr_category="PRESENT",
                    stderr_digest=stderr_digest,
                )
            )

    monkeypatch.setattr("harnesslab.release.smoke.DockerCodexBackend", PreCaptureFailureBackend)
    invoker = ProductionSmokeInvoker(ROOT, SAFE_ENVIRONMENT, tmp_path / "smoke")
    with pytest.raises(SmokeCallFailure) as raised:
        await invoker.invoke(binding)

    assert raised.value.category is SmokeFailureCategory.INFRASTRUCTURE
    evidence_result = raised.value.evidence_result
    assert evidence_result is not None
    assert evidence_result.call_id == EXPECTED_CALL_IDS[3]
    artifact = Path(evidence_result.evidence_references[0])
    artifact_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in artifact.rglob("*")
        if path.is_file()
    )
    assert (artifact / "manifest.json").is_file()
    assert secret not in artifact_text
    assert runtime_url not in artifact_text
    assert secret not in str(raised.value)
    assert runtime_url not in str(raised.value)
    assert secret not in evidence_result.model_dump_json()
    assert runtime_url not in evidence_result.model_dump_json()


@pytest.mark.asyncio
async def test_smoke_missing_config_stops_before_first_call() -> None:
    control = SmokeControlPlane.load(ROOT)
    invoker = RecordingInvoker()
    environment = dict(SAFE_ENVIRONMENT)
    environment.pop("HARNESSLAB_OPENCODE_GO_API_KEY")
    with pytest.raises(SmokeControlPlaneError, match="HARNESSLAB_OPENCODE_GO_API_KEY"):
        control.resolve_real_bindings(environment, _runtime())
    assert invoker.calls == []


@pytest.mark.asyncio
async def test_smoke_abort_on_first_failure_never_invokes_calls_four_through_eight() -> None:
    control = SmokeControlPlane.load(ROOT)
    bindings = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())
    invoker = RecordingInvoker(EXPECTED_CALL_IDS[2])
    receipt = await control.execute(bindings, invoker, allow_real_smoke=True)
    assert receipt.status is SmokeExecutionStatus.ABORTED
    assert receipt.attempted_top_level_launches == 3
    assert receipt.failing_call_id == EXPECTED_CALL_IDS[2]
    assert receipt.failure_category is SmokeFailureCategory.ROUTE_MISMATCH
    assert tuple(item.frozen.call.call_id for item in invoker.calls) == EXPECTED_CALL_IDS[:3]
    assert len(receipt.results) == 2


@pytest.mark.asyncio
async def test_smoke_typed_codex_infrastructure_failure_stops_without_retry_or_fallback() -> None:
    control = SmokeControlPlane.load(ROOT)
    bindings = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())

    class TypedFailureInvoker(RecordingInvoker):
        async def invoke(self, binding: ResolvedSmokeBinding) -> SmokeCallResult:
            self.calls.append(binding)
            call_id = binding.frozen.call.call_id
            result = SmokeCallResult(
                call_id=call_id,
                evidence_references=(f"fake://{call_id}",),
                evidence_digests=("sha256:" + "7" * 64,),
            )
            if call_id == EXPECTED_CALL_IDS[3]:
                raise SmokeCallFailure(
                    SmokeFailureCategory.INFRASTRUCTURE,
                    "typed Codex infrastructure failure",
                    result,
                )
            return result

    invoker = TypedFailureInvoker()
    receipt = await control.execute(bindings, invoker, allow_real_smoke=True)

    assert receipt.status is SmokeExecutionStatus.ABORTED
    assert receipt.attempted_top_level_launches == 4
    assert receipt.failing_call_id == EXPECTED_CALL_IDS[3]
    assert receipt.failure_category is SmokeFailureCategory.INFRASTRUCTURE
    assert tuple(item.call_id for item in receipt.results) == EXPECTED_CALL_IDS[:4]
    assert tuple(item.frozen.call.call_id for item in invoker.calls) == EXPECTED_CALL_IDS[:4]


@pytest.mark.asyncio
async def test_smoke_one_judge_call_only() -> None:
    control = SmokeControlPlane.load(ROOT)
    bindings = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())
    assert sum(binding.frozen.call.lane == "J" for binding in bindings) == 1
    assert bindings[-1].frozen.call.judge_case_reference == (
        "judge_suites/core-calibration/1.0.0#label-l0-pass"
    )
    invoker = RecordingInvoker()
    receipt = await control.execute(bindings, invoker, allow_real_smoke=True)
    judge_calls = [item for item in invoker.calls if item.frozen.call.lane == "J"]
    assert receipt.status is SmokeExecutionStatus.SUCCEEDED
    assert len(judge_calls) == 1


@pytest.mark.parametrize(
    ("mutation", "value"),
    (
        ("ninth-call", None),
        ("task-id", "other-task"),
        ("task-digest", "sha256:" + "9" * 64),
        ("model", "other-model"),
        ("route", "other|responses|env:OTHER/responses"),
        ("output-ceiling", 14_257),
        ("judge-launches", 2),
    ),
)
def test_smoke_plan_mutation_or_ninth_call_is_rejected_before_execution(
    tmp_path: Path, mutation: str, value: object
) -> None:
    root = _mutated_repository(tmp_path)
    path = root / "release/core-real-smoke-plan.json"
    raw = json.loads(path.read_text())
    if mutation == "ninth-call":
        extra = dict(raw["calls"][-1])
        extra["call_id"] = "smoke-9-forbidden"
        raw["calls"].append(extra)
    elif mutation == "task-id":
        raw["calls"][0]["task_id"] = value
    elif mutation == "task-digest":
        raw["calls"][0]["task_digest"] = value
    elif mutation == "model":
        raw["calls"][0]["requested_model"] = value
    elif mutation == "route":
        raw["calls"][0]["provider_route"] = value
    elif mutation == "output-ceiling":
        raw["max_output_token_ceiling"] = value
    else:
        raw["calls"][-1]["top_level_launches"] = value
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SmokeControlPlaneError):
        SmokeControlPlane.load(root)


def test_smoke_ninth_call_is_rejected_before_execution(tmp_path: Path) -> None:
    root = _mutated_repository(tmp_path)
    path = root / "release/core-real-smoke-plan.json"
    raw = json.loads(path.read_text())
    extra = dict(raw["calls"][-1])
    extra["call_id"] = "smoke-9-forbidden"
    raw["calls"].append(extra)
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SmokeControlPlaneError):
        SmokeControlPlane.load(root)


def test_smoke_provider_fallbacks_are_rejected_in_production_assertions() -> None:
    control = SmokeControlPlane.load(ROOT)
    profiles = {profile.profile_id: profile for profile in control.release_plan.selected_profiles}
    with pytest.raises(SmokeControlPlaneError, match="Codex relay fallback"):
        control._assert_codex_route(
            canonical_codex_profile(_runtime().codex_image),
            profiles["harness-codex-gpt56-medium"],
            SAFE_ENVIRONMENT,
        )
    claude = configured_qwen_opencode_go_claude_profile(_runtime().claude_image).model_copy(
        update={"provider_fixed_base_url": "https://api.anthropic.com"}
    )
    with pytest.raises(SmokeControlPlaneError, match="Claude OpenCode Go route"):
        control._assert_claude_route(
            claude,
            profiles["harness-claude-qwen38-opencode-go"],
            SAFE_ENVIRONMENT,
        )
    with pytest.raises(SmokeControlPlaneError, match="DeepSeek official-route"):
        control._assert_deepseek_route(
            canonical_deepseek_profile(
                _runtime().deepseek_image, _runtime().deepseek_config_digest
            ),
            profiles["harness-deepseek-v4flash"],
            SAFE_ENVIRONMENT,
        )


def test_dsh_e1_not_exposed_is_accepted_without_observed_model_fabrication() -> None:
    profile = configured_deepseek_v4flash_profile(
        _runtime().deepseek_image, _runtime().deepseek_config_digest
    )
    collection = collect_deepseek_final(HarnessProcessCapture(("completed output",), "", 0, 1))
    _validate_harness_observed_model(
        profile,
        trace_coverage=profile.trace_coverage,
        observed_model_status=collection.observed_model_status,
        observed_model=collection.observed_model,
    )
    assert profile.requested_model == "deepseek-v4-flash"
    assert collection.observed_model_status is ObservedModelStatus.NOT_EXPOSED
    assert collection.observed_model is None
    assert collection.sanitized_events[0].observed_model is None
    assert profile.requested_model not in collection.sanitized_jsonl


def test_claude_smoke_requires_exact_exposed_observed_model() -> None:
    profile = configured_qwen_opencode_go_claude_profile(_runtime().claude_image)
    _validate_harness_observed_model(
        profile,
        trace_coverage=TraceCoverage.FULL_STREAM,
        observed_model_status=ObservedModelStatus.EXPOSED,
        observed_model="qwen3.8-max",
    )
    for status, observed_model in (
        (ObservedModelStatus.NOT_EXPOSED, None),
        (ObservedModelStatus.EXPOSED, "wrong-model"),
    ):
        with pytest.raises(SmokeCallFailure) as raised:
            _validate_harness_observed_model(
                profile,
                trace_coverage=TraceCoverage.FULL_STREAM,
                observed_model_status=status,
                observed_model=observed_model,
            )
        assert raised.value.category is SmokeFailureCategory.OBSERVED_MODEL_CONFLICT


def test_dsh_incoherent_observed_model_state_is_rejected() -> None:
    profile = configured_deepseek_v4flash_profile(
        _runtime().deepseek_image, _runtime().deepseek_config_digest
    )
    for coverage, status, observed_model in (
        (TraceCoverage.FINAL_OUTPUT_ONLY, ObservedModelStatus.EXPOSED, "deepseek-v4-flash"),
        (TraceCoverage.FINAL_OUTPUT_ONLY, ObservedModelStatus.NOT_EXPOSED, "deepseek-v4-flash"),
        (TraceCoverage.FULL_STREAM, ObservedModelStatus.NOT_EXPOSED, None),
    ):
        with pytest.raises(SmokeCallFailure) as raised:
            _validate_harness_observed_model(
                profile,
                trace_coverage=coverage,
                observed_model_status=status,
                observed_model=observed_model,
            )
        assert raised.value.category is SmokeFailureCategory.OBSERVED_MODEL_CONFLICT


def test_deepseek_runtime_config_drift_remains_rejected() -> None:
    _validate_deepseek_effective_config("provider: deepseek-official\nmodel: deepseek-v4-flash\n")
    for drifted in (
        "provider: other-provider\nmodel: deepseek-v4-flash\n",
        "provider: deepseek-official\nmodel: other-model\n",
    ):
        with pytest.raises(RuntimeError, match="effective provider/model identity drifted"):
            _validate_deepseek_effective_config(drifted)


def test_release_cli_normalizes_egress_isolation_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(*_: object, **__: object) -> object:
        raise EgressNetworkIsolationUnavailable("EGRESS_NETWORK_ISOLATION_UNAVAILABLE")

    monkeypatch.setattr("harnesslab.cli.execute_real_smoke", unavailable)
    result = RUNNER.invoke(
        app,
        [
            "release",
            "smoke",
            "execute",
            "--allow-real-smoke",
            "--repository-root",
            str(ROOT),
        ],
    )
    assert result.exit_code == 2
    assert "FAIL smoke execution: EGRESS_NETWORK_ISOLATION_UNAVAILABLE" in result.stdout
    assert "Traceback" not in result.stdout


def test_immutable_egress_proxy_image_identity_is_required() -> None:
    assert "@sha256:" in EGRESS_PROXY_BASE
    assert EGRESS_PROXY_SOURCE_DIGEST.startswith("sha256:")
    dockerfile = (ROOT / "docker/egress/Dockerfile").read_text()
    assert dockerfile.splitlines()[0] == f"FROM {EGRESS_PROXY_BASE}"
    assert EGRESS_PROXY_SOURCE_DIGEST in dockerfile
    proxy_bytes = (ROOT / "docker/egress/proxy.py").read_bytes()
    proxy_digest = "sha256:" + hashlib.sha256(proxy_bytes).hexdigest()
    assert proxy_digest == EGRESS_PROXY_SOURCE_DIGEST
    with pytest.raises(EgressSecurityError, match="inspected non-zero"):
        ProviderScopedDockerBoundary(
            EgressPolicy(allowed_hostname="provider.example.test"),
            "review-internal",
            "review-proxy",
            ImageIdentity(reference=EGRESS_PROXY_IMAGE, image_id="sha256:" + "0" * 64),
        )


def test_internal_network_create_argv_requires_isolated_gateway_mode() -> None:
    boundary = ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname="provider.example.test"),
        "review-internal",
        "review-proxy",
        _runtime().egress_proxy_image,
    )
    assert boundary.create_internal_network_argv() == (
        "network",
        "create",
        "--driver",
        "bridge",
        "--internal",
        "--ipv6=false",
        "-o",
        "com.docker.network.bridge.gateway_mode_ipv4=isolated",
        "review-internal",
    )


@pytest.mark.asyncio
async def test_real_smoke_network_isolation_preflight_fails_before_first_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_resolution_attempted = False

    async def unavailable() -> object:
        raise EgressNetworkIsolationUnavailable("EGRESS_NETWORK_ISOLATION_UNAVAILABLE")

    async def forbidden_runtime_resolution() -> RuntimeIdentities:
        nonlocal runtime_resolution_attempted
        runtime_resolution_attempted = True
        return _runtime()

    monkeypatch.setattr("harnesslab.release.smoke.preflight_egress_network_isolation", unavailable)
    monkeypatch.setattr(
        "harnesslab.release.smoke.resolve_runtime_identities", forbidden_runtime_resolution
    )
    with pytest.raises(
        EgressNetworkIsolationUnavailable, match="EGRESS_NETWORK_ISOLATION_UNAVAILABLE"
    ):
        await execute_real_smoke(
            ROOT,
            allow_real_smoke=True,
            environment=SAFE_ENVIRONMENT,
        )
    assert not runtime_resolution_attempted


@pytest.mark.asyncio
async def test_actual_docker_network_isolation_preflight_attests_and_cleans_up() -> None:
    attestation = await preflight_egress_network_isolation()
    assert attestation.driver == "bridge"
    assert attestation.internal is True
    assert attestation.enable_ipv6 is False
    assert attestation.gateway_mode_ipv4 == "isolated"
    _, environment = await _docker_runtime_preflight()
    cli = _DockerCLI(output_limit=1_000_000, environment=environment)
    absent = await cli.run("network", "inspect", attestation.network, check=False)
    assert absent.returncode != 0


@pytest.mark.asyncio
async def test_network_attestation_rejects_internal_bridge_without_isolated_gateway_mode() -> None:
    _, environment = await _docker_runtime_preflight()
    cli = _DockerCLI(output_limit=1_000_000, environment=environment)
    network = f"hl-review-mutation-{uuid4().hex[:12]}"
    boundary = ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname="provider.example.test"),
        network,
        "hl-review-mutation-unused-proxy",
        _runtime().egress_proxy_image,
    )
    try:
        await cli.run(
            "network",
            "create",
            "--driver",
            "bridge",
            "--internal",
            "--ipv6=false",
            network,
        )
        inspected = await cli.run("network", "inspect", network)
        options = json.loads(inspected.stdout)[0]["Options"] or {}
        assert options.get(INTERNAL_NETWORK_GATEWAY_MODE_OPTION) != "isolated"
        with pytest.raises(
            EgressNetworkIsolationUnavailable, match="EGRESS_NETWORK_ISOLATION_UNAVAILABLE"
        ):
            await boundary.attest_internal_network(cli)
    finally:
        await cli.run("network", "rm", network, check=False)
    absent = await cli.run("network", "inspect", network, check=False)
    assert absent.returncode != 0


@pytest.mark.asyncio
async def test_egress_cleanup_attempts_every_resource_after_partial_failure() -> None:
    class FailingCLI:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        async def run(self, *arguments: str, **_: object) -> object:
            self.calls.append(arguments)
            if arguments[0] == "kill":
                raise RuntimeError("synthetic subject cleanup failure")
            return SimpleNamespace(
                returncode=1 if arguments[:2] == ("network", "inspect") else 0,
                stdout=b"",
            )

    cli = FailingCLI()
    boundary = ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname="provider.example.test"),
        "review-internal",
        "review-proxy",
        _runtime().egress_proxy_image,
    )
    with pytest.raises(EgressSecurityError, match="cleanup was not verified"):
        await boundary.cleanup(cli)
    assert ("rm", "--force", "review-proxy") in cli.calls
    assert ("network", "rm", "review-internal") in cli.calls
    assert ("network", "inspect", "review-internal") in cli.calls


@pytest.mark.asyncio
async def test_codex_and_multiharness_cleanup_continue_after_subject_failure() -> None:
    class PartialFailureCLI:
        def __init__(self, subject: str) -> None:
            self.subject = subject
            self.calls: list[tuple[str, ...]] = []

        async def run(self, *arguments: str, **_: object) -> object:
            self.calls.append(arguments)
            if arguments == ("kill", self.subject):
                raise RuntimeError("synthetic subject cleanup failure")
            return SimpleNamespace(
                returncode=1 if arguments[:2] == ("network", "inspect") else 0,
                stdout=b"",
            )

    for backend_type, prefix in (
        (DockerCodexBackend, "codex"),
        (DockerMultiHarnessBackend, "multi"),
    ):
        boundary = ProviderScopedDockerBoundary(
            EgressPolicy(allowed_hostname="provider.example.test"),
            f"{prefix}-internal",
            f"{prefix}-proxy",
            _runtime().egress_proxy_image,
        )
        backend = backend_type(egress_boundary=boundary)
        cli = PartialFailureCLI(f"{prefix}-subject")
        with pytest.raises(HarnessAdapterError, match="cleanup was not verified"):
            await backend._cleanup_execution(
                cast(_DockerCLI, cli), f"{prefix}-subject", create_attempted=True
            )
        assert ("rm", "--force", f"{prefix}-proxy") in cli.calls
        assert ("network", "rm", f"{prefix}-internal") in cli.calls


@pytest.mark.asyncio
async def test_actual_local_docker_egress_topology_denies_bypass_and_cleans_up() -> None:
    identity = await EgressProxyRuntime().ensure_image()
    _, environment = await _docker_runtime_preflight()
    cli = _DockerCLI(output_limit=1_000_000, environment=environment)
    suffix = uuid4().hex[:12]
    network = f"hl-review-{suffix}-internal"
    proxy = f"hl-review-{suffix}-proxy"
    subject = f"hl-review-{suffix}-subject"
    verifier = f"hl-review-{suffix}-verifier"
    boundary = ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname="provider.example.test"),
        network,
        proxy,
        identity,
    )
    sentinel_connection = asyncio.Event()

    async def record_sentinel_connection(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        sentinel_connection.set()
        writer.close()
        await writer.wait_closed()

    sentinel = await asyncio.start_server(record_sentinel_connection, "0.0.0.0", 0)
    sentinel_port = int(sentinel.sockets[0].getsockname()[1])
    provisioned = False
    try:
        attestation = await boundary.provision(cli)
        provisioned = True
        assert attestation.image.image_id == identity.image_id
        assert attestation.networks == tuple(sorted((network, "bridge")))
        assert attestation.internal_network_is_internal
        assert attestation.internal_network_security.driver == "bridge"
        assert attestation.internal_network_security.internal is True
        assert attestation.internal_network_security.enable_ipv6 is False
        assert attestation.internal_network_security.gateway_mode_ipv4 == "isolated"
        assert not attestation.privileged
        assert attestation.read_only_rootfs
        assert attestation.user == "10001:10001"
        assert "ALL" in attestation.cap_drop
        assert "no-new-privileges=true" in attestation.security_options
        assert not attestation.published_ports
        assert not attestation.docker_socket_mounted
        network_inspect = await cli.run("network", "inspect", network)
        ipam_config = json.loads(network_inspect.stdout)[0]["IPAM"]["Config"][0]
        assert "Gateway" not in ipam_config
        subnet = ipaddress.ip_network(ipam_config["Subnet"])
        ordinary_gateway = str(subnet.network_address + 1)

        subject_code = f"""
import socket, sys, time
deadline = time.monotonic() + 5
while True:
    try:
        sock = socket.create_connection(({proxy!r}, 8080), timeout=1)
        break
    except OSError:
        if time.monotonic() >= deadline:
            raise
sock.sendall(b'CONNECT undeclared.invalid:443 HTTP/1.1\\r\\nHost: undeclared.invalid\\r\\n\\r\\n')
reply = sock.recv(128)
sock.close()
if not reply.startswith(b'HTTP/1.1 403'):
    sys.exit(10)
try:
    socket.create_connection(('1.1.1.1', 443), timeout=1)
except OSError:
    pass
else:
    sys.exit(11)
try:
    socket.create_connection(({ordinary_gateway!r}, {sentinel_port}), timeout=1)
except OSError:
    sys.exit(0)
sys.exit(12)
"""
        await cli.run(
            "create",
            "--name",
            subject,
            "--network",
            network,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--entrypoint",
            "python",
            EGRESS_PROXY_IMAGE,
            "-c",
            subject_code,
        )
        subject_networks = await cli.run(
            "inspect", subject, "--format", "{{json .NetworkSettings.Networks}}"
        )
        assert tuple(json.loads(subject_networks.stdout).keys()) == (network,)
        subject_result = await cli.run("start", "--attach", subject, check=False, timeout=15)
        assert subject_result.returncode == 0
        assert not sentinel_connection.is_set()

        verifier_code = """
import socket, sys
try:
    socket.create_connection(('1.1.1.1', 443), timeout=1)
except OSError:
    sys.exit(0)
sys.exit(12)
"""
        await cli.run(
            "create",
            "--name",
            verifier,
            "--network",
            "none",
            "--entrypoint",
            "python",
            EGRESS_PROXY_IMAGE,
            "-c",
            verifier_code,
        )
        verifier_network = await cli.run(
            "inspect", verifier, "--format", "{{json .HostConfig.NetworkMode}}"
        )
        assert json.loads(verifier_network.stdout) == "none"
        verifier_result = await cli.run("start", "--attach", verifier, check=False, timeout=10)
        assert verifier_result.returncode == 0
    finally:
        sentinel.close()
        await sentinel.wait_closed()
        for container in (subject, verifier):
            await cli.run("kill", container, check=False)
            await cli.run("rm", "--force", container, check=False)
        if provisioned:
            await boundary.cleanup(cli)
    for container in (subject, verifier, proxy):
        absent = await cli.run(
            "ps", "--all", "--quiet", "--filter", f"name=^/{container}$", check=False
        )
        assert not absent.stdout.strip()
    absent_network = await cli.run("network", "inspect", network, check=False)
    assert absent_network.returncode != 0
