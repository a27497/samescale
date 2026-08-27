from __future__ import annotations

import hashlib
import json
import shutil
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.model_lane import patch as patch_contract
from harnesslab.model_lane import prompt as prompt_contract
from harnesslab.model_lane import runner as runner_contract
from harnesslab.model_lane.fake import FakeDirectProvider
from harnesslab.model_lane.models import (
    DirectModelOutcome,
    GenerationSettings,
    ProviderError,
    ProviderFailureCategory,
    ProviderInvocationError,
    ProviderReadTimeoutStage,
    ProviderRequest,
    ProviderResult,
    ProviderTimeoutPhase,
)
from harnesslab.model_lane.patch import parse_direct_patch
from harnesslab.model_lane.runner import DirectModelRunError, DirectModelRunner
from harnesslab.sandbox.models import IsolatedVerifierResult, SandboxStatus
from harnesslab.sandbox.runner import DockerSandbox
from harnesslab.tasks.package import TaskPackage, digest_tree, sha256_bytes

TASK_ROOT = Path(__file__).resolve().parents[1] / "tasks" / "micro-python-clamp" / "1.0.0"
FAKE_KEY = "gate-d-fake-key-not-a-real-credential"


def fake_profile() -> ModelProfile:
    return ModelProfile(
        requested_model="fake-requested-model",
        provider="fake-direct-provider",
        base_url="https://fake-provider.invalid/v1",
        route="/responses",
        protocol=Protocol.RESPONSES,
        reasoning=ReasoningProfile(effort="low", max_output_tokens=2000),
        credential_reference="GATE_D_FAKE_API_KEY",
    )


def correct_patch() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "operations": [
                {
                    "op": "write",
                    "path": "calculator.py",
                    "content": (
                        "def clamp(value: int, lower: int, upper: int) -> int:\n"
                        "    return max(lower, min(value, upper))\n"
                    ),
                }
            ],
        },
        separators=(",", ":"),
    )


def all_file_bytes(root: Path) -> bytes:
    return b"".join(path.read_bytes() for path in root.rglob("*") if path.is_file())


class SafeFailureProvider:
    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        raise ProviderInvocationError(
            ProviderFailureCategory.RATE_LIMIT,
            "synthetic safe failure",
            status_code=429,
            request_id="safe-failure-id",
            response_status="rate_limited",
            latency_ms=17,
        )


class SafeTimeoutProvider:
    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        raise ProviderInvocationError(
            ProviderFailureCategory.TIMEOUT,
            f"unsafe timeout detail {FAKE_KEY}",
            status_code=200,
            request_id="safe-read-timeout-id",
            latency_ms=90_454,
            timeout_phase=ProviderTimeoutPhase.READ,
            read_timeout_stage=ProviderReadTimeoutStage.READING_RESPONSE_BODY,
            response_header_latency_ms=31,
            response_body_bytes_received=127,
        )


class OutputBudgetExhaustedProvider:
    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        return ProviderResult(
            requested_model=request.profile.requested_model,
            observed_model=request.profile.requested_model,
            provider=request.profile.provider,
            endpoint_identity=request.profile.provider_route_identity,
            protocol=request.profile.protocol,
            request_id="truncated-request-id",
            public_output_text='{"schema_version":1,"operations":[',
            usage={"input_tokens": 10, "output_tokens": 2000, "total_tokens": 2010},
            stop_reason="max_tokens",
            response_status="truncated",
            latency_ms=17,
        )


def test_cleanup_reporting_cannot_be_promoted_to_run_failure() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        runner_contract._report_cleanup_failure("synthetic cleanup warning")


@pytest.mark.asyncio
async def test_fake_provider_m_lane_e2e_uses_isolated_verifier_and_safe_evidence(
    tmp_path: Path,
) -> None:
    sandbox = DockerSandbox(
        runtime_root=tmp_path / "sandbox-runtime",
        artifact_root=tmp_path / "sandbox-artifacts",
    )
    package = TaskPackage.load(TASK_ROOT)
    baseline = package.materialize(tmp_path / "baseline")
    try:
        baseline_input_digest = digest_tree(baseline.workspace)
        baseline_result = await sandbox.run_hidden_verifier_workspace(
            package, baseline.workspace, run_id="gate-d-baseline"
        )
    finally:
        baseline.cleanup()
    assert not baseline_result.passed

    provider = FakeDirectProvider(correct_patch(), observed_model="fake-observed-model")
    runner = DirectModelRunner(
        artifact_root=tmp_path / "model-artifacts",
        runtime_root=tmp_path / "model-runtime",
        sandbox=sandbox,
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )
    result = await runner.run(TASK_ROOT, fake_profile(), adapter=provider, run_id="gate-d-e2e")

    evidence = result.evidence
    assert evidence.outcome is DirectModelOutcome.VERIFIED_PASS
    assert evidence.verifier_passed
    assert evidence.verifier_score == 1.0
    assert evidence.requested_model == "fake-requested-model"
    assert evidence.observed_model == "fake-observed-model"
    assert evidence.requested_model != evidence.observed_model
    assert evidence.task_id == package.definition.id
    assert evidence.task_version == package.definition.version
    assert evidence.task_digest == package.definition.content_digest
    assert evidence.workspace_input_digest == baseline_input_digest
    assert evidence.workspace_input_digest != evidence.workspace_output_digest
    expected_patch = parse_direct_patch(correct_patch())
    assert evidence.parsed_patch_digest == sha256_bytes(
        expected_patch.canonical_json().encode("utf-8")
    )
    assert evidence.prompt_template_version == prompt_contract.PROMPT_TEMPLATE_VERSION
    request = provider.requests[0]
    prompt_canonical = json.dumps(
        {
            "template_version": evidence.prompt_template_version,
            "instructions": request.instructions,
            "input": request.input,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert evidence.prompt_hash == f"sha256:{hashlib.sha256(prompt_canonical).hexdigest()}"
    assert evidence.provider == fake_profile().provider
    assert evidence.endpoint_identity == (
        "fake-direct-provider|responses|https://fake-provider.invalid/v1/responses"
    )
    assert evidence.protocol is Protocol.RESPONSES
    assert evidence.generation_settings.model_dump() == {
        "effort": "low",
        "temperature": None,
        "max_output_tokens": 2000,
        "request_timeout_seconds": 60.0,
        "attempt_count": 1,
    }
    with pytest.raises(ValidationError, match="frozen"):
        evidence.generation_settings.effort = "high"  # type: ignore[misc]
    assert evidence.provider_result is not None
    assert evidence.provider_result.request_id == "fake-response-1"
    assert evidence.provider_result.usage.total_tokens == 125
    assert evidence.provider_result.response_status == "completed"
    assert evidence.provider_result.latency_ms == 0
    assert evidence.public_response_text == correct_patch()
    assert evidence.public_response_digest == (
        "sha256:" + hashlib.sha256(correct_patch().encode("utf-8")).hexdigest()
    )
    assert evidence.verifier_sandbox_manifest is not None
    assert evidence.verifier_sandbox_manifest.run_id != baseline_result.run.run_id
    assert evidence.verifier_sandbox_manifest.role == "verifier"
    assert evidence.verifier_sandbox_manifest.task_digest == evidence.task_digest
    assert evidence.verifier_sandbox_manifest.status is SandboxStatus.SUCCEEDED
    assert (result.artifact_directory / "workspace" / "calculator.py").is_file()
    assert evidence.workspace_output_digest == digest_tree(result.artifact_directory / "workspace")
    assert evidence.verifier_artifact_namespace == "verifier"
    assert evidence.verifier_artifact_digest == digest_tree(result.artifact_directory / "verifier")
    assert (result.artifact_directory / "verifier" / "stdout.txt").is_file()
    assert (result.artifact_directory / "verifier" / "stderr.txt").is_file()
    assert len(provider.requests) == 1
    persisted = json.loads((result.artifact_directory / "manifest.json").read_text("utf-8"))
    assert persisted == evidence.model_dump(mode="json")
    assert FAKE_KEY not in all_file_bytes(tmp_path).decode("utf-8", errors="ignore")


@pytest.mark.asyncio
async def test_task_package_context_reaches_runner_prompt_and_evidence(tmp_path: Path) -> None:
    copied_task = tmp_path / "micro-python-clamp" / "1.0.0"
    shutil.copytree(TASK_ROOT, copied_task)
    context = copied_task / "context"
    context.mkdir()
    (context / "visible.txt").write_text("SUBJECT_VISIBLE_CONTEXT", encoding="utf-8")
    task_yaml = copied_task / "task.yaml"
    task_yaml.write_text(
        task_yaml.read_text(encoding="utf-8").replace(
            "workspace_path: workspace\n",
            "workspace_path: workspace\ncontext_path: context\n",
        ),
        encoding="utf-8",
    )
    provider = FakeDirectProvider(correct_patch())
    runner = DirectModelRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        sandbox=DockerSandbox(
            runtime_root=tmp_path / "sandbox-runtime",
            artifact_root=tmp_path / "sandbox-artifacts",
        ),
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )

    result = await runner.run(
        copied_task,
        fake_profile(),
        adapter=provider,
        run_id="context-e2e",
    )

    assert "SUBJECT_VISIBLE_CONTEXT" in provider.requests[0].input
    assert result.evidence.context_digest == digest_tree(context)
    assert result.evidence.outcome is DirectModelOutcome.VERIFIED_PASS


@pytest.mark.asyncio
async def test_malformed_patch_fails_closed_without_workspace_snapshot(tmp_path: Path) -> None:
    runner = DirectModelRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )
    result = await runner.run(
        TASK_ROOT,
        fake_profile(),
        adapter=FakeDirectProvider("```json\n{}\n```"),
        run_id="malformed-patch",
    )

    assert result.evidence.outcome is DirectModelOutcome.SUBJECT_OUTPUT_ERROR
    assert result.evidence.workspace_output_digest is None
    assert result.evidence.verifier_sandbox_manifest is None
    assert not (result.artifact_directory / "workspace").exists()


@pytest.mark.asyncio
async def test_output_budget_exhaustion_is_subject_output_failure(tmp_path: Path) -> None:
    runner = DirectModelRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )
    result = await runner.run(
        TASK_ROOT,
        fake_profile(),
        adapter=OutputBudgetExhaustedProvider(),
        run_id="output-budget-exhausted",
    )

    assert result.evidence.outcome is DirectModelOutcome.SUBJECT_OUTPUT_ERROR
    assert result.evidence.provider_failure is None
    assert result.evidence.provider_error is None
    assert result.evidence.provider_result is not None
    assert result.evidence.provider_result.stop_reason == "max_tokens"
    assert result.evidence.provider_result.response_status == "truncated"
    assert result.evidence.provider_result.usage.output_tokens == 2000
    assert result.evidence.public_response_text is not None
    assert "exhausted the output-token budget" in result.evidence.summary
    assert result.evidence.verifier_sandbox_manifest is None


@pytest.mark.asyncio
async def test_model_refusal_bypasses_patch_workspace_and_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject_patch_parsing(public_output: str) -> None:
        raise AssertionError(f"refusal reached patch parsing: {public_output}")

    monkeypatch.setattr(runner_contract, "parse_direct_patch", reject_patch_parsing)
    provider = FakeDirectProvider("PUBLIC_MODEL_REFUSAL", refused=True)
    runner = DirectModelRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        sandbox=ExplodingSandbox(),
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )

    result = await runner.run(
        TASK_ROOT,
        fake_profile(),
        adapter=provider,
        run_id="subject-refusal",
    )

    evidence = result.evidence
    assert evidence.outcome is DirectModelOutcome.SUBJECT_REFUSAL
    assert evidence.provider_result is not None
    assert evidence.provider_result.refused
    assert evidence.provider_result.attempt_count == 1
    assert evidence.provider_failure is None
    assert evidence.provider_error is None
    assert evidence.public_response_text == "PUBLIC_MODEL_REFUSAL"
    assert evidence.public_response_digest == sha256_bytes(b"PUBLIC_MODEL_REFUSAL")
    assert evidence.parsed_patch_digest is None
    assert evidence.workspace_output_digest is None
    assert evidence.verifier_sandbox_manifest is None
    assert evidence.verifier_artifact_namespace is None
    assert evidence.verifier_artifact_digest is None
    assert evidence.verifier_passed is None
    assert evidence.verifier_score is None
    assert len(provider.requests) == 1
    assert not (result.artifact_directory / "workspace").exists()
    assert not (result.artifact_directory / "verifier").exists()

    execution_payload = evidence.model_dump(mode="json")
    execution_payload["workspace_output_digest"] = evidence.workspace_input_digest
    with pytest.raises(ValidationError, match="subject execution evidence"):
        type(evidence).model_validate(execution_payload)

    misattributed_payload = evidence.model_dump(mode="json")
    misattributed_payload["outcome"] = DirectModelOutcome.SUBJECT_OUTPUT_ERROR
    with pytest.raises(ValidationError, match="requires subject_refusal outcome"):
        type(evidence).model_validate(misattributed_payload)

    with pytest.raises(ValidationError, match="frozen"):
        evidence.outcome = DirectModelOutcome.SUBJECT_OUTPUT_ERROR  # type: ignore[misc]


@pytest.mark.asyncio
async def test_provider_failure_category_is_preserved_in_evidence(tmp_path: Path) -> None:
    runner = DirectModelRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )
    result = await runner.run(
        TASK_ROOT,
        fake_profile(),
        adapter=FakeDirectProvider("", failure=ProviderFailureCategory.TIMEOUT),
        run_id="provider-timeout",
    )

    assert result.evidence.outcome is DirectModelOutcome.PROVIDER_ERROR
    assert result.evidence.provider_failure is ProviderFailureCategory.TIMEOUT
    assert result.evidence.provider_error is not None
    assert result.evidence.provider_error.category is ProviderFailureCategory.TIMEOUT
    assert result.evidence.provider_error.attempt_count == 1
    assert result.evidence.provider_result is None


@pytest.mark.asyncio
async def test_timeout_phase_is_persisted_in_canonical_evidence_without_raw_detail(
    tmp_path: Path,
) -> None:
    runner = DirectModelRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )
    result = await runner.run(
        TASK_ROOT,
        fake_profile(),
        adapter=SafeTimeoutProvider(),
        run_id="provider-read-timeout",
    )

    error = result.evidence.provider_error
    canonical = result.evidence.canonical_json()
    assert result.evidence.outcome is DirectModelOutcome.PROVIDER_ERROR
    assert result.evidence.provider_failure is ProviderFailureCategory.TIMEOUT
    assert error is not None
    assert error.category is ProviderFailureCategory.TIMEOUT
    assert error.timeout_phase is ProviderTimeoutPhase.READ
    assert error.read_timeout_stage is ProviderReadTimeoutStage.READING_RESPONSE_BODY
    assert error.response_header_latency_ms == 31
    assert error.response_body_bytes_received == 127
    assert error.status_code == 200
    assert error.request_id == "safe-read-timeout-id"
    assert error.response_status is None
    assert error.latency_ms == 90_454
    assert error.attempt_count == 1
    assert '"timeout_phase":"read"' in canonical
    assert '"read_timeout_stage":"reading_response_body"' in canonical
    assert '"response_header_latency_ms":31' in canonical
    assert '"response_body_bytes_received":127' in canonical
    assert FAKE_KEY not in canonical
    assert "unsafe timeout detail" not in canonical
    artifacts = all_file_bytes(result.artifact_directory)
    assert FAKE_KEY.encode() not in artifacts
    assert b"unsafe timeout detail" not in artifacts


def test_provider_error_timeout_phase_schema_fails_closed() -> None:
    historical = ProviderError(category=ProviderFailureCategory.TIMEOUT)
    assert historical.timeout_phase is None

    with pytest.raises(ValidationError, match="timeout phase requires a timeout"):
        ProviderError(
            category=ProviderFailureCategory.RATE_LIMIT,
            timeout_phase=ProviderTimeoutPhase.READ,
        )

    with pytest.raises(ValidationError):
        ProviderError.model_validate(
            {"category": "timeout", "timeout_phase": "not-a-timeout-phase"}
        )


def test_provider_error_read_timeout_diagnostics_fail_closed() -> None:
    waiting = ProviderError(
        category=ProviderFailureCategory.TIMEOUT,
        timeout_phase=ProviderTimeoutPhase.READ,
        read_timeout_stage=ProviderReadTimeoutStage.WAITING_FOR_RESPONSE_HEADERS,
    )
    assert waiting.response_header_latency_ms is None
    assert waiting.response_body_bytes_received is None

    body = ProviderError(
        category=ProviderFailureCategory.TIMEOUT,
        timeout_phase=ProviderTimeoutPhase.READ,
        read_timeout_stage=ProviderReadTimeoutStage.READING_RESPONSE_BODY,
        response_header_latency_ms=12,
        response_body_bytes_received=34,
        status_code=200,
        request_id="safe-id",
    )
    assert body.response_body_bytes_received == 34

    invalid_payloads = (
        {
            "category": "rate_limit",
            "read_timeout_stage": "waiting_for_response_headers",
        },
        {
            "category": "timeout",
            "timeout_phase": "connect",
            "read_timeout_stage": "waiting_for_response_headers",
        },
        {
            "category": "timeout",
            "timeout_phase": "read",
            "read_timeout_stage": "waiting_for_response_headers",
            "response_header_latency_ms": 1,
        },
        {
            "category": "timeout",
            "timeout_phase": "read",
            "read_timeout_stage": "waiting_for_response_headers",
            "status_code": 200,
        },
        {
            "category": "timeout",
            "timeout_phase": "read",
            "read_timeout_stage": "reading_response_body",
            "response_header_latency_ms": 1,
        },
    )
    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            ProviderError.model_validate(payload)


@pytest.mark.asyncio
async def test_safe_provider_failure_facts_are_persisted_without_raw_response(
    tmp_path: Path,
) -> None:
    runner = DirectModelRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )
    result = await runner.run(
        TASK_ROOT,
        fake_profile(),
        adapter=SafeFailureProvider(),
        run_id="safe-provider-error",
    )

    error = result.evidence.provider_error
    assert error is not None
    assert error.category is ProviderFailureCategory.RATE_LIMIT
    assert error.status_code == 429
    assert error.request_id == "safe-failure-id"
    assert error.response_status == "rate_limited"
    assert error.latency_ms == 17
    assert "raw" not in result.evidence.canonical_json().casefold()


@pytest.mark.asyncio
async def test_credential_content_is_withheld_from_all_phase_d_artifacts(tmp_path: Path) -> None:
    leaked_patch = json.dumps(
        {
            "schema_version": 1,
            "operations": [{"op": "write", "path": "credential.txt", "content": FAKE_KEY}],
        },
        separators=(",", ":"),
    )
    artifact_root = tmp_path / "artifacts"
    runner = DirectModelRunner(
        artifact_root=artifact_root,
        runtime_root=tmp_path / "runtime",
        sandbox=DockerSandbox(
            runtime_root=tmp_path / "sandbox-runtime",
            artifact_root=tmp_path / "sandbox-artifacts",
        ),
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )
    with pytest.raises(DirectModelRunError, match="exact run secret"):
        await runner.run(
            TASK_ROOT,
            fake_profile(),
            adapter=FakeDirectProvider(leaked_patch),
            run_id="credential-leak",
        )

    assert FAKE_KEY.encode() not in all_file_bytes(tmp_path)
    assert not (artifact_root / "credential-leak").exists()


@pytest.mark.asyncio
async def test_prompt_containing_exact_credential_is_not_sent_to_provider(
    tmp_path: Path,
) -> None:
    copied_task = tmp_path / "micro-python-clamp" / "1.0.0"
    shutil.copytree(TASK_ROOT, copied_task)
    instruction = copied_task / "instruction.md"
    instruction.write_text(
        instruction.read_text(encoding="utf-8") + f"\n{FAKE_KEY}\n",
        encoding="utf-8",
    )
    provider = FakeDirectProvider(correct_patch())
    runtime_root = tmp_path / "runtime"
    artifact_root = tmp_path / "artifacts"
    runner = DirectModelRunner(
        artifact_root=artifact_root,
        runtime_root=runtime_root,
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )

    with pytest.raises(DirectModelRunError, match="exact run secret"):
        await runner.run(
            copied_task,
            fake_profile(),
            adapter=provider,
            run_id="prompt-secret",
        )

    assert provider.requests == []
    assert FAKE_KEY.encode() not in all_file_bytes(runtime_root)
    assert FAKE_KEY.encode() not in all_file_bytes(artifact_root)


def test_generation_settings_are_deeply_immutable() -> None:
    settings = GenerationSettings(
        effort="low",
        max_output_tokens=2000,
        request_timeout_seconds=60,
    )
    with pytest.raises(ValidationError, match="frozen"):
        settings.effort = "high"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_prompt_template_version_in_evidence_comes_from_rendered_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prompt_contract, "PROMPT_TEMPLATE_VERSION", "direct-patch-v1-test")
    runner = DirectModelRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )
    result = await runner.run(
        TASK_ROOT,
        fake_profile(),
        adapter=FakeDirectProvider("{}"),
        run_id="prompt-version",
    )

    assert result.evidence.prompt_template_version == "direct-patch-v1-test"


@pytest.mark.asyncio
async def test_direct_model_evidence_rejects_conflicting_provider_identity(
    tmp_path: Path,
) -> None:
    runner = DirectModelRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )
    result = await runner.run(
        TASK_ROOT,
        fake_profile(),
        adapter=FakeDirectProvider("{}"),
        run_id="identity-coherence",
    )
    payload = result.evidence.model_dump(mode="json")
    assert payload["provider_result"] is not None
    payload["provider_result"]["provider"] = "contradictory-provider"

    with pytest.raises(ValidationError, match="identity mismatch"):
        type(result.evidence).model_validate(payload)


@pytest.mark.asyncio
async def test_direct_model_evidence_rejects_multiple_provider_attempts(
    tmp_path: Path,
) -> None:
    runner = DirectModelRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )
    result = await runner.run(
        TASK_ROOT,
        fake_profile(),
        adapter=FakeDirectProvider("{}"),
        run_id="attempt-coherence",
    )
    payload = result.evidence.model_dump(mode="json")
    assert payload["provider_result"] is not None
    payload["provider_result"]["attempt_count"] = 2

    with pytest.raises(ValidationError, match="literal_error"):
        type(result.evidence).model_validate(payload)


class ExplodingSandbox(DockerSandbox):
    async def run_hidden_verifier_workspace(
        self,
        package: TaskPackage,
        workspace: Path,
        *,
        timeout_seconds: float = 15,
        run_id: str | None = None,
        secret_values: tuple[str, ...] = (),
    ) -> IsolatedVerifierResult:
        raise RuntimeError("synthetic verifier preflight failure")


@pytest.mark.asyncio
async def test_unexpected_verifier_exception_is_persisted_as_infra_error(
    tmp_path: Path,
) -> None:
    runner = DirectModelRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        sandbox=ExplodingSandbox(),
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )

    result = await runner.run(
        TASK_ROOT,
        fake_profile(),
        adapter=FakeDirectProvider(correct_patch()),
        run_id="verifier-preflight-error",
    )

    assert result.evidence.outcome is DirectModelOutcome.INFRA_ERROR
    assert result.evidence.summary == "isolated verification failed: RuntimeError"
    assert result.evidence.verifier_sandbox_manifest is None


@pytest.mark.asyncio
async def test_workspace_staging_failure_is_not_blame_assigned_to_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_staging(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(patch_contract, "_apply_direct_patch_in_place", fail_staging)
    runner = DirectModelRunner(
        artifact_root=tmp_path / "artifacts",
        runtime_root=tmp_path / "runtime",
        environment={"GATE_D_FAKE_API_KEY": FAKE_KEY},
    )

    result = await runner.run(
        TASK_ROOT,
        fake_profile(),
        adapter=FakeDirectProvider(correct_patch()),
        run_id="patch-storage-error",
    )

    assert result.evidence.outcome is DirectModelOutcome.INFRA_ERROR
    assert "DirectPatchInfrastructureError" in result.evidence.summary
